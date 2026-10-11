import hashlib
import inspect
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError

import errors
from controllers.base_controller import BaseController
from controllers.posting_controller import IDEMPOTENCY_TTL, PostingController
from dtos import StatementDTO
from errors import (
    IdempotencyKeyConflict,
    InternalError,
    InvalidSchema,
    LedgerAccountNotFound,
    LockTimeout,
    QIException,
    StatementNotFound,
    StatementPeriodAlreadyIssued,
)
from models import LedgerAccountType, LedgerEntry
from repositories import IdempotencyRecordRepository, LedgerAccountRepository, StatementRepository

ENDPOINT = "POST /statement"

# O status que o registro de idempotência guarda para o replay. O status da
# resposta HTTP sai do resource, e os dois são o 201 do §3.1.
SUCCESS_STATUS = 201

# A UNIQUE(supersedes_statement_id) do database.sql não tem nome: este é o
# que o Postgres dá a ela (RN-08).
SUPERSEDES_CONSTRAINT = "statement_supersedes_statement_id_key"

# Os instantes do texto do hash: UTC, microssegundos e `Z` (decisão A2).
HASH_INSTANT_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


def hash_instant(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime(HASH_INSTANT_FORMAT)


def hash_field(value) -> str:
    """Nulo vira vazio; '' já é vazio (RN-02)."""
    if value is None:
        return ""
    return str(value)


class StatementController(BaseController):
    """O extrato com hash encadeado de uma conta (D0009)."""

    def __init__(self) -> None:
        super().__init__(__name__)
        self.statement_repository = StatementRepository(self.context)
        self.ledger_account_repository = LedgerAccountRepository(self.context)
        self.idempotency_record_repository = IdempotencyRecordRepository(self.context)

    def issue(self, payload: dict, idempotency_key: str, raw_body: bytes) -> dict:
        """Emite o extrato do período, na ordem da RN-04.

        O registro da chave vem antes da trava (RN-05). O erro depois dele
        também é gravado, por SAVEPOINT, e por isso há commit no caminho de
        erro: é o desvio D-02 da 05a, com as quatro linhas no
        `PostingController.post`, herdado aqui sem peça nova.
        """
        PostingController.require_idempotency_key(idempotency_key)
        period_start, period_end = self._period(payload)

        ledger_account = self.ledger_account_repository.get_by_key(payload["ledger_account_key"])
        if ledger_account is None:
            raise LedgerAccountNotFound(payload["ledger_account_key"])

        idempotency_record, replayed_key = self._register_idempotency_key(
            ledger_account.client_key, idempotency_key, raw_body
        )

        if replayed_key is not None:
            return self.get_by_key(replayed_key)

        execution = self.session.begin_nested()
        try:
            statement_dto = self._issue(ledger_account, period_start, period_end)
        except Exception as error:
            execution.rollback()
            qi_exception = self._as_qi_exception(error)
            self.idempotency_record_repository.set_response(
                idempotency_record, qi_exception.http_status, [qi_exception.code]
            )
            self.session.commit()
            raise qi_exception from error

        execution.commit()
        self.idempotency_record_repository.set_response(
            idempotency_record, SUCCESS_STATUS, [statement_dto["statement_key"]]
        )
        self.session.commit()

        return statement_dto

    def get_by_key(self, statement_key: str) -> dict:
        self.logger.debug(f"Buscando o extrato de chave {statement_key}")

        statement = self.statement_repository.get_by_key(statement_key)

        if statement is None:
            raise StatementNotFound(statement_key)

        lines = self.statement_repository.list_lines(
            statement.ledger_account_id, statement.period_start, statement.period_end, statement.created_at
        )

        return self._to_dict(statement, lines)

    def _issue(self, ledger_account, period_start: datetime, period_end: datetime) -> dict:
        """A trava, o corte, as linhas, o hash e o INSERT (RN-06, RN-08)."""
        cutoff = self.ledger_account_repository.lock_for_statement(ledger_account)
        if cutoff is None:
            raise LockTimeout()

        lines = self.statement_repository.list_lines(ledger_account.id, period_start, period_end, cutoff)
        supersedes_statement = self._superseded_statement(ledger_account, period_start, period_end, lines)

        previous_statement = self.statement_repository.get_last(ledger_account.id)
        content_hash = self._content_hash(
            ledger_account.ledger_account_key, period_start, period_end, previous_statement, lines
        )

        try:
            statement = self.statement_repository.create(
                ledger_account, period_start, period_end, previous_statement, supersedes_statement, content_hash, cutoff
            )
        except IntegrityError as error:
            # Defesa: com a trava da RN-06, a 2ª emissão cai na RN-07 antes daqui.
            constraint_name = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
            if constraint_name == SUPERSEDES_CONSTRAINT:
                raise StatementPeriodAlreadyIssued() from error
            raise

        return self._to_dict(statement, lines)

    def _superseded_statement(self, ledger_account, period_start: datetime, period_end: datetime, lines: list):
        """O vigente que este extrato supersede, ou None para um original (RN-07).

        Vigente sobreposto de outro período → 017. Vigente do mesmo período:
        se há linha lançada depois dele, este é o sucessor; senão → 017.
        """
        for current in self.statement_repository.list_current(ledger_account.id):
            same_period = current.period_start == period_start and current.period_end == period_end
            overlaps = current.period_start < period_end and period_start < current.period_end

            if not overlaps:
                continue

            if not same_period:
                raise StatementPeriodAlreadyIssued(ledger_account.ledger_account_key, period_start, period_end)

            has_late_entry = any(ledger_entry.created_at > current.created_at for ledger_entry, _tx in lines)
            if not has_late_entry:
                raise StatementPeriodAlreadyIssued(ledger_account.ledger_account_key, period_start, period_end)

            return current

        return None

    def _register_idempotency_key(self, client_key: str, idempotency_key: str, raw_body: bytes) -> tuple:
        """SAVEPOINT + INSERT do registro, como o passo 1 da 05a (D0003
        :56-60). Devolve (registro, None) para seguir, ou (None, chave do
        extrato) no replay de sucesso."""
        request_fingerprint = hashlib.sha256(raw_body).hexdigest()
        expires_at = datetime.now(timezone.utc) + IDEMPOTENCY_TTL

        savepoint = self.session.begin_nested()
        try:
            idempotency_record = self.idempotency_record_repository.create(
                client_key=client_key,
                endpoint=ENDPOINT,
                idempotency_key=idempotency_key,
                request_fingerprint=request_fingerprint,
                expires_at=expires_at,
            )
        except IntegrityError:
            savepoint.rollback()
            return self._collide(client_key, idempotency_key, request_fingerprint, expires_at)

        savepoint.commit()

        return idempotency_record, None

    def _collide(self, client_key: str, idempotency_key: str, request_fingerprint: str, expires_at: datetime) -> tuple:
        """A chave já existe: vencida, segue como nova; outra impressão, 010;
        a mesma, replay da resposta guardada (D0003 :52-54)."""
        idempotency_record = self.idempotency_record_repository.get_for_update(client_key, ENDPOINT, idempotency_key)

        if idempotency_record.expires_at <= datetime.now(timezone.utc):
            self.idempotency_record_repository.renew(idempotency_record, request_fingerprint, expires_at)
            return idempotency_record, None

        if idempotency_record.request_fingerprint != request_fingerprint:
            raise IdempotencyKeyConflict()

        if 200 <= idempotency_record.response_status < 300:
            return None, idempotency_record.response_keys[0]

        raise self._replay_error(idempotency_record)

    def _replay_error(self, idempotency_record) -> QIException:
        """O erro guardado, de novo, como o `PostingController._stored_error`:
        a classe com o `code` guardado, criada sem argumentos (RN-13, D-03)."""
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

    def _as_qi_exception(self, error: Exception) -> QIException:
        """O erro como ele vai ser gravado e respondido: o nosso, como veio;
        o imprevisto, logado e trocado pelo InternalError."""
        if isinstance(error, QIException):
            return error

        self.logger.exception("Erro inesperado na emissão do extrato")
        return InternalError()

    def _period(self, payload: dict) -> tuple:
        """As datas do corpo. O `pattern` do schema conta dígitos, não dias:
        2026-02-30 passa por ele e morre aqui, como pedido malformado (400).
        O período é semiaberto e não vazio: `start < end` (decisão A3)."""
        try:
            period_start = datetime.fromisoformat(payload["period_start"])
            period_end = datetime.fromisoformat(payload["period_end"])
        except ValueError:
            raise InvalidSchema("period_start and period_end must be real dates")

        if period_start >= period_end:
            raise InvalidSchema("period_start must be before period_end")

        return period_start, period_end

    def _content_hash(self, ledger_account_key: str, period_start, period_end, previous_statement, lines: list) -> str:
        """SHA-256, em hex, do cabeçalho e das linhas, uma por linha (RN-02,
        RN-03, A2)."""
        previous_content_hash = previous_statement.content_hash if previous_statement is not None else ""
        header = [ledger_account_key, hash_instant(period_start), hash_instant(period_end), previous_content_hash]
        text_lines = ["|".join(header)]

        for ledger_entry, ledger_transaction in lines:
            fields = [
                hash_field(ledger_entry.id),
                ledger_entry.direction,
                hash_field(int(ledger_entry.amount_in_cents)),
                hash_instant(ledger_transaction.value_date),
                ledger_transaction.ledger_transaction_key,
                ledger_transaction.ledger_transaction_type.enumerator,
                hash_field(ledger_transaction.contract_key),
                hash_field(ledger_transaction.period_reference),
                hash_field(ledger_transaction.split_version),
                hash_field(ledger_transaction.payer_party_key),
            ]
            text_lines.append("|".join(fields))

        return hashlib.sha256("\n".join(text_lines).encode("utf-8")).hexdigest()

    def _balances(self, statement, lines: list) -> dict:
        """Abertura, totais D/C das linhas e fechamento, orientados pelo lado
        da conta: D - C em `asset`, C - D nas demais (RN-09). Fora do hash."""
        opening_debit, opening_credit = self.statement_repository.sum_before(
            statement.ledger_account_id, statement.period_start, statement.created_at
        )

        total_debit = 0
        total_credit = 0
        for ledger_entry, _ledger_transaction in lines:
            if ledger_entry.direction == LedgerEntry.DEBIT:
                total_debit += int(ledger_entry.amount_in_cents)
            else:
                total_credit += int(ledger_entry.amount_in_cents)

        opening_balance = opening_debit - opening_credit
        movement = total_debit - total_credit
        if statement.ledger_account.ledger_account_type.side != LedgerAccountType.ASSET:
            opening_balance = -opening_balance
            movement = -movement

        return {
            "opening_balance_in_cents": opening_balance,
            "total_debit_in_cents": total_debit,
            "total_credit_in_cents": total_credit,
            "closing_balance_in_cents": opening_balance + movement,
        }

    def _to_dict(self, statement, lines: list) -> dict:
        """O extrato com os campos derivados de agora. `lines` são as do corte
        = `created_at`; com elas e o `previous` gravado, o hash é recalculado:
        verificar é recalcular (RN-10)."""
        previous_statement = None
        previous_statement_key = None
        if statement.previous_statement_id is not None:
            previous_statement = self.statement_repository.get_by_id(statement.previous_statement_id)
            previous_statement_key = previous_statement.statement_key

        recalculated_hash = self._content_hash(
            statement.ledger_account.ledger_account_key,
            statement.period_start,
            statement.period_end,
            previous_statement,
            lines,
        )

        supersedes_statement_key = None
        if statement.supersedes_statement_id is not None:
            supersedes_statement_key = self.statement_repository.get_key_by_id(statement.supersedes_statement_id)

        superseded_by_statement_key = self.statement_repository.get_successor_key(statement.id)

        return StatementDTO.obj_to_dict(
            statement,
            recalculated_hash == statement.content_hash,
            lines,
            self._balances(statement, lines),
            previous_statement_key,
            supersedes_statement_key,
            superseded_by_statement_key,
        )
