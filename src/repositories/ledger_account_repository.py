from sqlalchemy import case, func

from database import Context
from models import LedgerAccount, LedgerAccountType, LedgerEntry


class LedgerAccountRepository:
    """As contas do ledger. Só aqui existe query sobre elas."""

    def __init__(self, context: Context) -> None:
        self.session = context.db_session

    def get_by_key(self, ledger_account_key: str) -> LedgerAccount:
        return (
            self.session.query(LedgerAccount)
            .filter(LedgerAccount.ledger_account_key == ledger_account_key)
            .first()
        )

    def get_balance(self, ledger_account: LedgerAccount) -> int:
        """O saldo, somado dos lançamentos: nunca uma coluna.

        D - C nas contas do lado `asset`; C - D nas demais. Sem trava:
        quem lê não disputa linha com ninguém.
        """
        debit_minus_credit = case(
            (LedgerEntry.direction == LedgerEntry.DEBIT, LedgerEntry.amount_in_cents),
            else_=-LedgerEntry.amount_in_cents,
        )

        total = (
            self.session.query(func.coalesce(func.sum(debit_minus_credit), 0))
            .filter(LedgerEntry.ledger_account_id == ledger_account.id)
            .scalar()
        )

        if ledger_account.ledger_account_type.side != LedgerAccountType.ASSET:
            total = -total

        return int(total)
