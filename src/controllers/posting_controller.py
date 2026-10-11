import hashlib
from datetime import datetime, timedelta, timezone

from controllers.base_controller import BaseController
from errors import (
    CurrencyMismatch,
    InvalidSchema,
    LedgerAccountNotMovable,
    PurposePairNotAllowed,
    TransactionDoesNotBalance,
)
from models import LedgerAccountStatus
from repositories import (
    IdempotencyRecordRepository,
    LedgerEntryRepository,
    LedgerTransactionRepository,
    PurposeRuleRepository,
)
from utils.request_context import get_request_id

IDEMPOTENCY_KEY_MAX_LENGTH = 255
IDEMPOTENCY_TTL = timedelta(hours=24)


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
    ) -> str:
        """Posta uma transação e devolve a `ledger_transaction_key`.

        `idempotency` = {client_key, endpoint, key, raw_body};
        `transaction` = as colunas de `ledger_transaction` que a rota
        preenche, com `ledger_transaction_type` como enumerador;
        `legs` = [(LedgerAccount, "D" | "C", centavos)];
        `purpose_pairs` = [(origem, destino)], contas a conferir na
        `purpose_rule`. O commit é a última linha.
        """
        idempotency_record = self._register_idempotency_key(idempotency)

        self._check_accounts(legs)
        self._check_purpose_pairs(purpose_pairs)

        ledger_transaction = self._write(transaction, legs)
        self._check_balanced(ledger_transaction)

        self.idempotency_record_repository.set_response(
            idempotency_record, success_status, [ledger_transaction.ledger_transaction_key]
        )
        self.session.commit()

        return ledger_transaction.ledger_transaction_key

    def _register_idempotency_key(self, idempotency: dict):
        """Passo 1: SAVEPOINT + INSERT do registro, com a resposta provisória."""
        savepoint = self.session.begin_nested()

        idempotency_record = self.idempotency_record_repository.create(
            client_key=idempotency["client_key"],
            endpoint=idempotency["endpoint"],
            idempotency_key=idempotency["key"],
            request_fingerprint=hashlib.sha256(idempotency["raw_body"]).hexdigest(),
            expires_at=datetime.now(timezone.utc) + IDEMPOTENCY_TTL,
        )
        savepoint.commit()

        return idempotency_record

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

    def _write(self, transaction: dict, legs: list):
        """Passo 7: o cabeçalho e as pernas."""
        ledger_transaction = self.ledger_transaction_repository.create(transaction, get_request_id())

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
