from sqlalchemy import CHAR, Column, DateTime, ForeignKey, Integer, Numeric, func
from models.base import Base
from models import LedgerAccount, LedgerTransaction


class LedgerEntry(Base):
    __tablename__ = "ledger_entry"

    id = Column(Integer, primary_key=True)
    ledger_transaction_id = Column(Integer, ForeignKey(LedgerTransaction.id), nullable=False)
    ledger_account_id = Column(Integer, ForeignKey(LedgerAccount.id), nullable=False)
    direction = Column(CHAR(1), nullable=False)
    amount_in_cents = Column(Numeric(20, 0), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    DEBIT = "D"
    CREDIT = "C"
