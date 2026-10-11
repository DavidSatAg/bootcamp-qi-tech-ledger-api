from sqlalchemy import CHAR, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from models.base import Base
from models import Outbox


class ProviderEvent(Base):
    __tablename__ = "provider_event"

    id = Column(Integer, primary_key=True)
    provider_event_key = Column(CHAR(36), nullable=False)
    provider_reference = Column(String(255), nullable=False)
    event_type = Column(String(50), nullable=False)
    outbox_id = Column(Integer, ForeignKey(Outbox.id))
    raw_payload = Column(JSONB, nullable=False)
    received_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("provider_event_key"),
        UniqueConstraint("provider_reference"),
    )
