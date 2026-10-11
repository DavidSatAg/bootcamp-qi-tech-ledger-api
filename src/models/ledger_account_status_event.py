from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship
from models.base import Base
from models import LedgerAccount, LedgerAccountStatus


class LedgerAccountStatusEvent(Base):
    __tablename__ = "ledger_account_status_event"

    id = Column(Integer, primary_key=True)
    ledger_account_id = Column(Integer, ForeignKey(LedgerAccount.id), nullable=False)
    from_status_id = Column(Integer, ForeignKey(LedgerAccountStatus.id))
    to_status_id = Column(Integer, ForeignKey(LedgerAccountStatus.id), nullable=False)
    actor = Column(String(255), nullable=False)
    reason = Column(String(255))
    trace_id = Column(String(64), nullable=False)
    event_datetime = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    from_status = relationship("LedgerAccountStatus", foreign_keys=[from_status_id], lazy="selectin")
    to_status = relationship("LedgerAccountStatus", foreign_keys=[to_status_id], lazy="selectin")
