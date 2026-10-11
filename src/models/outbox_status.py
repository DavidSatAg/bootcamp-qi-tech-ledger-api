from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint, func
from models.base import Base


class OutboxStatus(Base):
    __tablename__ = "outbox_status"

    id = Column(Integer, primary_key=True)
    enumerator = Column(String(50), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (UniqueConstraint("enumerator"),)

    PENDING = "pending"
    IN_FLIGHT = "in_flight"
    SENT = "sent"
    SETTLED = "settled"
    FAILED = "failed"
    DEAD = "dead"
