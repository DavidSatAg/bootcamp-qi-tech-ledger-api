from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint, func
from models.base import Base


class LedgerTransactionType(Base):
    __tablename__ = "ledger_transaction_type"

    id = Column(Integer, primary_key=True)
    enumerator = Column(String(50), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (UniqueConstraint("enumerator"),)

    INFLOW = "inflow"
    ALLOCATION = "allocation"
    SPLIT = "split"
    INTERNAL = "internal"
    PAYOUT = "payout"
    SETTLEMENT = "settlement"
    DISPATCH_RETURN = "dispatch_return"
    REVERSAL = "reversal"
