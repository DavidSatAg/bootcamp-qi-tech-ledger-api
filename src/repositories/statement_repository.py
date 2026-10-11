from datetime import datetime
from uuid import uuid4

from sqlalchemy import case, func
from sqlalchemy.orm import aliased

from database import Context
from models import LedgerAccount, LedgerEntry, LedgerTransaction, Statement


class StatementRepository:
    """Os extratos. Só aqui existe query sobre eles."""

    def __init__(self, context: Context) -> None:
        self.session = context.db_session

    def get_by_key(self, statement_key: str) -> Statement:
        return self.session.query(Statement).filter(Statement.statement_key == statement_key).first()

    def find_by_hash(self, content_hash: str) -> Statement:
        """O extrato com esse `content_hash`, ou None (RN-11). Sem trava."""
        return (
            self.session.query(Statement)
            .filter(Statement.content_hash == content_hash)
            .order_by(Statement.id)
            .first()
        )

    def get_by_id(self, statement_id: int) -> Statement:
        return self.session.query(Statement).filter(Statement.id == statement_id).one()

    def get_key_by_id(self, statement_id: int) -> str:
        return self.session.query(Statement.statement_key).filter(Statement.id == statement_id).scalar()

    def get_successor_key(self, statement_id: int) -> str:
        """A chave do extrato que supersede este, ou None."""
        return (
            self.session.query(Statement.statement_key)
            .filter(Statement.supersedes_statement_id == statement_id)
            .scalar()
        )

    def get_last(self, ledger_account_id: int) -> Statement:
        """O último extrato da conta, na ordem de emissão (RN-08)."""
        return (
            self.session.query(Statement)
            .filter(Statement.ledger_account_id == ledger_account_id)
            .order_by(Statement.created_at.desc(), Statement.id.desc())
            .first()
        )

    def list_current(self, ledger_account_id: int) -> list:
        """Os extratos vigentes da conta: os que nenhum outro supersede (D0009 :75)."""
        successor = aliased(Statement)
        is_superseded = (
            self.session.query(successor.id).filter(successor.supersedes_statement_id == Statement.id).exists()
        )

        return (
            self.session.query(Statement)
            .filter(Statement.ledger_account_id == ledger_account_id, ~is_superseded)
            .order_by(Statement.id)
            .all()
        )

    def list_lines(self, ledger_account_id: int, start: datetime, end: datetime, cutoff: datetime) -> list:
        """[(LedgerEntry, LedgerTransaction)] da conta com a data-valor em
        [start, end) e lançados até o corte (RN-01), por (value_date, id)."""
        return (
            self.session.query(LedgerEntry, LedgerTransaction)
            .join(LedgerTransaction, LedgerEntry.ledger_transaction_id == LedgerTransaction.id)
            .filter(
                LedgerEntry.ledger_account_id == ledger_account_id,
                LedgerTransaction.value_date >= start,
                LedgerTransaction.value_date < end,
                LedgerEntry.created_at <= cutoff,
            )
            .order_by(LedgerTransaction.value_date, LedgerEntry.id)
            .all()
        )

    def sum_before(self, ledger_account_id: int, start: datetime, cutoff: datetime) -> tuple:
        """(débitos, créditos) da conta com a data-valor antes de `start` e
        lançados até o corte: a base do saldo de abertura (RN-09)."""
        debit = case((LedgerEntry.direction == LedgerEntry.DEBIT, LedgerEntry.amount_in_cents), else_=0)
        credit = case((LedgerEntry.direction == LedgerEntry.CREDIT, LedgerEntry.amount_in_cents), else_=0)

        total_debit, total_credit = (
            self.session.query(func.coalesce(func.sum(debit), 0), func.coalesce(func.sum(credit), 0))
            .join(LedgerTransaction, LedgerEntry.ledger_transaction_id == LedgerTransaction.id)
            .filter(
                LedgerEntry.ledger_account_id == ledger_account_id,
                LedgerTransaction.value_date < start,
                LedgerEntry.created_at <= cutoff,
            )
            .one()
        )

        return int(total_debit), int(total_credit)

    def create(
        self,
        ledger_account: LedgerAccount,
        period_start: datetime,
        period_end: datetime,
        previous_statement: Statement | None,
        supersedes_statement: Statement | None,
        content_hash: str,
        created_at: datetime,
    ) -> Statement:
        """Grava o extrato com uma chave nova e o `created_at` = o corte (A9).

        O `flush` manda o INSERT agora: a UNIQUE do sucessor dispara aqui,
        não no commit.
        """
        statement = Statement()
        statement.statement_key = str(uuid4())
        statement.ledger_account = ledger_account
        statement.period_start = period_start
        statement.period_end = period_end
        statement.previous_statement_id = previous_statement.id if previous_statement is not None else None
        statement.supersedes_statement_id = supersedes_statement.id if supersedes_statement is not None else None
        statement.content_hash = content_hash
        statement.created_at = created_at

        self.session.add(statement)
        self.session.flush()

        return statement
