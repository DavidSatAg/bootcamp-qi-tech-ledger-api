from sqlalchemy import CHAR, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import relationship
from models.base import Base
from models import LedgerTransactionType


class LedgerTransaction(Base):
    __tablename__ = "ledger_transaction"

    id = Column(Integer, primary_key=True)
    ledger_transaction_key = Column(CHAR(36), nullable=False)
    ledger_transaction_type_id = Column(Integer, ForeignKey(LedgerTransactionType.id), nullable=False)
    contract_key = Column(String(36), nullable=False, server_default="")
    period_reference = Column(String(7), nullable=False, server_default="")
    split_version = Column(Integer)
    payer_party_key = Column(String(36), nullable=False, server_default="")
    end_to_end_id = Column(String(64))
    value_date = Column(DateTime(timezone=True), nullable=False)
    actor = Column(String(255), nullable=False)
    reason = Column(String(255))
    trace_id = Column(String(64), nullable=False)
    reverses_transaction_id = Column(Integer, ForeignKey("ledger_transaction.id"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("ledger_transaction_key"),
        UniqueConstraint("end_to_end_id"),
    )

    ledger_transaction_type = relationship("LedgerTransactionType", foreign_keys=[ledger_transaction_type_id], lazy="selectin")
