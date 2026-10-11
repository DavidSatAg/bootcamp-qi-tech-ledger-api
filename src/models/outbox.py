from sqlalchemy import CHAR, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from models.base import Base
from models import LedgerTransaction, OutboxStatus


class Outbox(Base):
    __tablename__ = "outbox"

    id = Column(Integer, primary_key=True)
    outbox_key = Column(CHAR(36), nullable=False)
    outbox_status_id = Column(Integer, ForeignKey(OutboxStatus.id), nullable=False)
    ledger_transaction_id = Column(Integer, ForeignKey(LedgerTransaction.id), nullable=False)
    beneficiary_party_key = Column(String(36), nullable=False)
    dispatch_idempotency_key = Column(String(255), nullable=False)
    payload = Column(JSONB, nullable=False)
    attempt_count = Column(Integer, nullable=False, server_default="0")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("outbox_key"),
        UniqueConstraint("dispatch_idempotency_key"),
    )

    outbox_status = relationship("OutboxStatus", foreign_keys=[outbox_status_id], lazy="selectin")
