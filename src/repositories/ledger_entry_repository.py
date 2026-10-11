from sqlalchemy import case, func

from database import Context
from models import LedgerAccount, LedgerEntry, LedgerTransaction


class LedgerEntryRepository:
    """As pernas de cada transação. Só se inserem: o banco recusa UPDATE e DELETE."""

    def __init__(self, context: Context) -> None:
        self.session = context.db_session

    def create(
        self,
        ledger_transaction: LedgerTransaction,
        ledger_account: LedgerAccount,
        direction: str,
        amount_in_cents: int,
    ) -> LedgerEntry:
        ledger_entry = LedgerEntry()
        ledger_entry.ledger_transaction_id = ledger_transaction.id
        ledger_entry.ledger_account_id = ledger_account.id
        ledger_entry.direction = direction
        ledger_entry.amount_in_cents = amount_in_cents

        self.session.add(ledger_entry)
        self.session.flush()

        return ledger_entry

    def totals_by_client(self, ledger_transaction_id: int) -> list:
        """Σ D e Σ C das pernas gravadas da transação, por `client_key`:
        [(client_key, débitos, créditos)]. Lido do banco, não da memória."""
        debit = case((LedgerEntry.direction == LedgerEntry.DEBIT, LedgerEntry.amount_in_cents), else_=0)
        credit = case((LedgerEntry.direction == LedgerEntry.CREDIT, LedgerEntry.amount_in_cents), else_=0)

        rows = (
            self.session.query(LedgerAccount.client_key, func.sum(debit), func.sum(credit))
            .join(LedgerAccount, LedgerEntry.ledger_account_id == LedgerAccount.id)
            .filter(LedgerEntry.ledger_transaction_id == ledger_transaction_id)
            .group_by(LedgerAccount.client_key)
            .all()
        )

        return [(client_key, int(debits), int(credits)) for client_key, debits, credits in rows]

    def list_by_transactions(self, ledger_transaction_ids: list) -> list:
        """As pernas das transações pedidas, cada uma com a sua conta:
        [(LedgerEntry, LedgerAccount)], por transação, débitos primeiro, e `id`.

        `LedgerEntry` não tem relationship com a conta: por isso a tupla.
        """
        return (
            self.session.query(LedgerEntry, LedgerAccount)
            .join(LedgerAccount, LedgerEntry.ledger_account_id == LedgerAccount.id)
            .filter(LedgerEntry.ledger_transaction_id.in_(ledger_transaction_ids))
            .order_by(LedgerEntry.ledger_transaction_id, LedgerEntry.direction.desc(), LedgerEntry.id)
            .all()
        )
