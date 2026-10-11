import hashlib
from datetime import datetime, timezone

from controllers.base_controller import BaseController
from controllers.posting_controller import PostingController
from dtos import StatementDTO
from errors import InvalidSchema, LedgerAccountNotFound, LockTimeout, StatementNotFound
from models import LedgerAccountType, LedgerEntry
from repositories import LedgerAccountRepository, StatementRepository

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

    def issue(self, payload: dict, idempotency_key: str, raw_body: bytes) -> dict:
        """Emite o extrato do período, na ordem da RN-04. O commit é a última linha."""
        PostingController.require_idempotency_key(idempotency_key)
        period_start, period_end = self._period(payload)

        ledger_account = self.ledger_account_repository.get_by_key(payload["ledger_account_key"])
        if ledger_account is None:
            raise LedgerAccountNotFound(payload["ledger_account_key"])

        cutoff = self.ledger_account_repository.lock_for_statement(ledger_account)
        if cutoff is None:
            raise LockTimeout()

        previous_statement = self.statement_repository.get_last(ledger_account.id)
        lines = self.statement_repository.list_lines(ledger_account.id, period_start, period_end, cutoff)
        content_hash = self._content_hash(
            ledger_account.ledger_account_key, period_start, period_end, previous_statement, lines
        )

        statement = self.statement_repository.create(
            ledger_account, period_start, period_end, previous_statement, None, content_hash, cutoff
        )
        statement_dto = self._to_dict(statement, lines)

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
        previous_statement_key = None
        if statement.previous_statement_id is not None:
            previous_statement_key = self.statement_repository.get_key_by_id(statement.previous_statement_id)

        supersedes_statement_key = None
        if statement.supersedes_statement_id is not None:
            supersedes_statement_key = self.statement_repository.get_key_by_id(statement.supersedes_statement_id)

        superseded_by_statement_key = self.statement_repository.get_successor_key(statement.id)

        return StatementDTO.obj_to_dict(
            statement,
            lines,
            self._balances(statement, lines),
            previous_statement_key,
            supersedes_statement_key,
            superseded_by_statement_key,
        )
