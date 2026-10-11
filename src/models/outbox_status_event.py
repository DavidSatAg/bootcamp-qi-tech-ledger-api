from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship
from models.base import Base
from models import Outbox, OutboxStatus


class OutboxStatusEvent(Base):
    __tablename__ = "outbox_status_event"

    id = Column(Integer, primary_key=True)
    outbox_id = Column(Integer, ForeignKey(Outbox.id), nullable=False)
    from_status_id = Column(Integer, ForeignKey(OutboxStatus.id))
    to_status_id = Column(Integer, ForeignKey(OutboxStatus.id), nullable=False)
    actor = Column(String(255), nullable=False)
    reason = Column(String(255))
    trace_id = Column(String(64), nullable=False)
    event_datetime = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    from_status = relationship("OutboxStatus", foreign_keys=[from_status_id], lazy="selectin")
    to_status = relationship("OutboxStatus", foreign_keys=[to_status_id], lazy="selectin")
