import hashlib
import inspect
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError, OperationalError

import errors
from constants import LOCK_TIMEOUT
from controllers.base_controller import BaseController
from errors import (
    CurrencyMismatch,
    IdempotencyKeyConflict,
    InsufficientBalance,
    InternalError,
    InvalidSchema,
    LedgerAccountNotMovable,
    LockTimeout,
    PurposePairNotAllowed,
    QIException,
    TransactionDoesNotBalance,
)
from models import LedgerAccountStatus, LedgerAccountType, LedgerEntry
from repositories import (
    IdempotencyRecordRepository,
    LedgerAccountRepository,
    LedgerEntryRepository,
    LedgerTransactionRepository,
    PurposeRuleRepository,
)
from utils.request_context import get_request_id

IDEMPOTENCY_KEY_MAX_LENGTH = 255
IDEMPOTENCY_TTL = timedelta(hours=24)

# A UNIQUE(end_to_end_id) do database.sql não tem nome: este é o que o
# Postgres dá a ela.
END_TO_END_ID_CONSTRAINT = "ledger_transaction_end_to_end_id_key"

# O SQLSTATE do Postgres para "lock_not_available": a trava não veio dentro
# do lock_timeout.
LOCK_NOT_AVAILABLE = "55P03"


class PostingController(BaseController):
    """O motor de postagem: o único caminho por onde o dinheiro se move
    (guia do Ledger §5; D0001).

    Toda rota que move dinheiro monta as pernas e os pares de propósito e
    chama `post`. Nunca dois motores.
    """

    def __init__(self) -> None:
        super().__init__(__name__)
        self.idempotency_record_repository = IdempotencyRecordRepository(self.context)
        self.ledger_transaction_repository = LedgerTransactionRepository(self.context)
        self.ledger_entry_repository = LedgerEntryRepository(self.context)
        self.ledger_account_repository = LedgerAccountRepository(self.context)
        self.purpose_rule_repository = PurposeRuleRepository(self.context)

    @staticmethod
    def require_idempotency_key(idempotency_key: str) -> None:
        """Toda rota que move dinheiro exige a `Idempotency-Key` (RFC :107-110).

        Faltar a chave é pedido malformado, como o schema: 400, e nada se
        grava (D0003 :62-63).
        """
        if not idempotency_key:
            raise InvalidSchema("Idempotency-Key header is required")

        if len(idempotency_key) > IDEMPOTENCY_KEY_MAX_LENGTH:
            raise InvalidSchema(
                f"Idempotency-Key header is longer than {IDEMPOTENCY_KEY_MAX_LENGTH} characters"
            )

    def post(
        self,
        idempotency: dict,
        transaction: dict,
        legs: list,
        purpose_pairs: list,
        success_status: int,
        after_lock=None,
        after_write=None,
        record_error=True,
    ) -> str:
        """Posta uma transação e devolve a `ledger_transaction_key`.

        `idempotency` = {client_key, endpoint, key, raw_body};
        `transaction` = as colunas de `ledger_transaction` que a rota
        preenche, com `ledger_transaction_type` como enumerador;
        `legs` = [(LedgerAccount, "D" | "C", centavos)];
        `purpose_pairs` = [(origem, destino)], contas a conferir na
        `purpose_rule`; `after_lock`, se vier, é a conferência da rota que
        depende da trava (passo 5), chamada sem argumentos logo depois dela;
        `after_write`, se vier, recebe a transação gravada depois do passo 8,
        no mesmo SAVEPOINT (a outbox do repasse, fatia 09 RN-06).
        Com `record_error=False`, o erro não é gravado e desfaz a transação
        inteira (o webhook do provedor, fatia 10 RN-06).
        O commit é a última linha.

        O erro também é gravado (RN-11, desvio D-02), e por isso este é o
        único controller que commita no caminho de erro:
        1. Princípio tocado: erro previsto não grava nada, e o controller só
           commita depois que a regra passou.
        2. Por que não funciona sem: a mesma chave tem de devolver o mesmo
           erro (D0003 :51-52). Sem o erro gravado, a repetição — ou a
           requisição que esperava no INSERT da mesma chave — roda o motor
           de novo e pode responder outra coisa.
        3. A peça, e por que é a menor: um SAVEPOINT de execução logo depois
           do registro. No erro, ROLLBACK TO SAVEPOINT desfaz só o movimento;
           o registro recebe o status e o código; e o commit é o desta mesma
           transação, sem sessão nova nem segundo commit.
        4. O que não faz: não grava falha de schema nem o 035 (que saem antes
           do registro), não grava movimento pela metade, não tenta de novo e
           não guarda a description dinâmica do erro.
           Nem grava o erro do webhook do provedor (`record_error=False`,
           fatia 10, D-02): lá a idempotência é a do `provider_event`, e o
           erro desfaz a transação inteira, com o `provider_event` junto.
        """
        idempotency_record, replayed_key = self._register_idempotency_key(idempotency)

        if replayed_key is not None:
            return replayed_key

        execution = self.session.begin_nested()
        try:
            ledger_transaction_key = self._execute(transaction, legs, purpose_pairs, after_lock, after_write)
        except Exception as error:
            execution.rollback()
            qi_exception = self._as_qi_exception(error)
            if not record_error:
                self.session.rollback()
                raise qi_exception from error
            self.idempotency_record_repository.set_response(
                idempotency_record, qi_exception.http_status, [qi_exception.code]
            )
            self.session.commit()
            raise qi_exception from error

        execution.commit()
        self.idempotency_record_repository.set_response(idempotency_record, success_status, [ledger_transaction_key])
        self.session.commit()

        return ledger_transaction_key

    def _execute(self, transaction: dict, legs: list, purpose_pairs: list, after_lock, after_write) -> str:
        """Passos 2 a 8, nesta ordem: o par proibido sai antes da trava, e o
        que depende da trava, depois dela (guia do Ledger §5); e a releitura
        do status depois do 7 (RN-08 da fatia 08)."""
        self._check_accounts(legs)
        self._check_purpose_pairs(purpose_pairs)
        locked = self._lock_net_debits(legs)

        if after_lock is not None:
            after_lock()

        self._check_funds(locked)

        ledger_transaction = self._write(transaction, legs)
        self._recheck_accounts(legs)
        self._check_balanced(ledger_transaction)

        if after_write is not None:
            after_write(ledger_transaction)

        return ledger_transaction.ledger_transaction_key

    def _as_qi_exception(self, error: Exception) -> QIException:
        """O erro como ele vai ser gravado e respondido: o nosso, como veio;
        o imprevisto, logado e trocado pelo InternalError."""
        if isinstance(error, QIException):
            return error

        self.logger.exception("Erro inesperado no motor de postagem")
        return InternalError()

    def _register_idempotency_key(self, idempotency: dict) -> tuple:
        """Passo 1 (D0003 :56-60): SAVEPOINT + INSERT do registro, com a
        resposta provisória. Devolve (registro, None) para seguir, ou
        (None, chave guardada) no replay de sucesso.

        A colisão é a UNIQUE do escopo: desfaz-se só o SAVEPOINT, e o
        registro que já existia é lido com trava. Quem chegou junto com a
        mesma chave esperou no INSERT até a outra transação commitar.
        """
        request_fingerprint = hashlib.sha256(idempotency["raw_body"]).hexdigest()
        expires_at = datetime.now(timezone.utc) + IDEMPOTENCY_TTL

        savepoint = self.session.begin_nested()
        try:
            idempotency_record = self.idempotency_record_repository.create(
                client_key=idempotency["client_key"],
                endpoint=idempotency["endpoint"],
                idempotency_key=idempotency["key"],
                request_fingerprint=request_fingerprint,
                expires_at=expires_at,
            )
        except IntegrityError:
            savepoint.rollback()
            return self._collide(idempotency, request_fingerprint, expires_at)

        savepoint.commit()

        return idempotency_record, None

    def _collide(self, idempotency: dict, request_fingerprint: str, expires_at: datetime) -> tuple:
        """A chave já existe: vencida, segue como nova; outra impressão, 010;
        a mesma, replay da resposta guardada (D0003 :52-54)."""
        idempotency_record = self.idempotency_record_repository.get_for_update(
            idempotency["client_key"], idempotency["endpoint"], idempotency["key"]
        )

        if idempotency_record.expires_at <= datetime.now(timezone.utc):
            self.idempotency_record_repository.renew(idempotency_record, request_fingerprint, expires_at)
            return idempotency_record, None

        if idempotency_record.request_fingerprint != request_fingerprint:
            raise IdempotencyKeyConflict()

        if 200 <= idempotency_record.response_status < 300:
            return None, idempotency_record.response_keys[0]

        raise self._stored_error(idempotency_record)

    def _stored_error(self, idempotency_record) -> QIException:
        """O erro guardado, de novo: a classe com o `code` guardado, criada
        sem argumentos (RN-13), achada como no `error_verification`. Sai a
        `description` genérica: o corpo só repete igual nos erros de texto fixo.
        """
        code = idempotency_record.response_keys[0]

        for _class_name, error_class in inspect.getmembers(errors, inspect.isclass):
            if issubclass(error_class, QIException) and error_class is not QIException and error_class.code == code:
                return error_class()

        # Inalcançável: todo `code` gravado vem de uma classe de `errors`.
        internal_error = InternalError()
        return QIException(
            internal_error.title,
            code,
            idempotency_record.response_status,
            internal_error.description,
            internal_error.translation,
        )

    def _check_accounts(self, legs: list) -> None:
        """Passo 2: toda conta das pernas aceita movimento, numa moeda só.
        Lê o status sem trava (RN-05)."""
        currencies = set()

        for ledger_account, _direction, _amount_in_cents in legs:
            if ledger_account.ledger_account_status.enumerator != LedgerAccountStatus.ACTIVE:
                raise LedgerAccountNotMovable()
            currencies.add(ledger_account.currency)

        if len(currencies) > 1:
            raise CurrencyMismatch()

    def _recheck_accounts(self, legs: list) -> None:
        """O passo 2 de novo, depois de gravar as pernas e antes do passo 8
        (fatia 08, RN-08).

        O passo 2 lê o status sem trava. Um encerramento que trave as contas
        entre ele e o passo 7 faz o INSERT da perna esperar na FK (o `FOR
        KEY SHARE` da conta conflita com o `FOR UPDATE` do encerramento) até
        o commit dele; daí em diante, só esta releitura vê o `closed`. Sem
        ela, a conta fecharia com saldo. Lê colunas, não entidades, e não
        trava nada (D0007: crédito nunca trava).
        """
        ledger_account_ids = [ledger_account.id for ledger_account, _direction, _amount_in_cents in legs]
        statuses = self.ledger_account_repository.get_statuses(ledger_account_ids)

        for ledger_account_id in ledger_account_ids:
            if statuses[ledger_account_id] != LedgerAccountStatus.ACTIVE:
                raise LedgerAccountNotMovable()

    def _check_purpose_pairs(self, purpose_pairs: list) -> None:
        """Passo 3, antes de qualquer trava: cada par está na `purpose_rule`,
        e no mesmo contrato quando a regra o exige."""
        for source, target in purpose_pairs:
            source_purpose_code = source.purpose_code.enumerator
            target_purpose_code = target.purpose_code.enumerator
            purpose_rule = self.purpose_rule_repository.get_rule(source_purpose_code, target_purpose_code)

            if purpose_rule is None:
                raise PurposePairNotAllowed(source_purpose_code, target_purpose_code)

            if purpose_rule.requires_same_contract and source.contract_key != target.contract_key:
                raise PurposePairNotAllowed(source_purpose_code, target_purpose_code)

    def _lock_net_debits(self, legs: list) -> list:
        """Passo 4: trava, em `id` crescente e com `lock_timeout`, as contas
        de passivo e patrimônio cujo líquido nas pernas é débito (D0007
        :35-55). Devolve [(conta, líquido devedor)], em `id`; nenhuma conta,
        nenhum SQL.

        O `55P03` vira o 011 aqui: passado adiante, o `_as_qi_exception` o
        trocaria pelo InternalError. Outro erro de banco sobe como está.
        """
        accounts = dict()
        net_debits = dict()

        for ledger_account, direction, amount_in_cents in legs:
            signed_amount = amount_in_cents
            if direction == LedgerEntry.CREDIT:
                signed_amount = -amount_in_cents
            accounts[ledger_account.id] = ledger_account
            net_debits[ledger_account.id] = net_debits.get(ledger_account.id, 0) + signed_amount

        locked = [
            (accounts[ledger_account_id], net_debits[ledger_account_id])
            for ledger_account_id in sorted(accounts)
            if accounts[ledger_account_id].ledger_account_type.side != LedgerAccountType.ASSET
            and net_debits[ledger_account_id] > 0
        ]

        if not locked:
            return locked

        try:
            self.ledger_account_repository.lock_for_update(
                [ledger_account.id for ledger_account, _net_debit in locked], LOCK_TIMEOUT
            )
        except OperationalError as error:
            if getattr(error.orig, "pgcode", None) == LOCK_NOT_AVAILABLE:
                raise LockTimeout() from error
            raise

        return locked

    def _check_funds(self, locked: list) -> None:
        """Passo 6: o saldo de cada conta travada, somado DEPOIS da trava,
        cobre o líquido devedor dela (G:360). Somado antes, outro débito
        commitado no meio passaria despercebido (D0007 :46-47)."""
        for ledger_account, net_debit in locked:
            if self.ledger_account_repository.get_balance(ledger_account) < net_debit:
                raise InsufficientBalance()

    def _write(self, transaction: dict, legs: list):
        """Passo 7: o cabeçalho e as pernas.

        O `end_to_end_id` já usado é a mesma entrada sob outra chave: 010,
        gravado sob a chave nova (desvio D-01). Outra violação sobe como
        está e vira InternalError.
        """
        try:
            ledger_transaction = self.ledger_transaction_repository.create(transaction, get_request_id())
        except IntegrityError as error:
            constraint_name = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
            if constraint_name == END_TO_END_ID_CONSTRAINT:
                raise IdempotencyKeyConflict() from error
            raise

        for ledger_account, direction, amount_in_cents in legs:
            self.ledger_entry_repository.create(ledger_transaction, ledger_account, direction, amount_in_cents)

        return ledger_transaction

    def _check_balanced(self, ledger_transaction) -> None:
        """Passo 8: Σ D = Σ C no todo e em cada livro, lido das pernas gravadas."""
        totals = self.ledger_entry_repository.totals_by_client(ledger_transaction.id)

        all_debits = 0
        all_credits = 0
        for _client_key, debits, credits in totals:
            if debits != credits:
                raise TransactionDoesNotBalance()
            all_debits = all_debits + debits
            all_credits = all_credits + credits

        if all_debits != all_credits:
            raise TransactionDoesNotBalance()
