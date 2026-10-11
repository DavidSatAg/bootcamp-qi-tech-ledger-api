from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint, func
from models.base import Base
from models import LedgerAccount


class SplitSnapshot(Base):
    __tablename__ = "split_snapshot"

    id = Column(Integer, primary_key=True)
    contract_key = Column(String(36), nullable=False)
    split_version = Column(Integer, nullable=False)
    source_ledger_account_id = Column(Integer, ForeignKey(LedgerAccount.id), nullable=False)
    ledger_account_id = Column(Integer, ForeignKey(LedgerAccount.id), nullable=False)
    allocation_type = Column(String(20), nullable=False)
    percentage = Column(Numeric(7, 4))
    amount_in_cents = Column(Numeric(20, 0))
    rent_amount_in_cents = Column(Numeric(20, 0), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (UniqueConstraint("contract_key", "split_version", "ledger_account_id"),)

    PERCENTAGE = "percentage"
    FIXED = "fixed"
    REMAINDER = "remainder"
