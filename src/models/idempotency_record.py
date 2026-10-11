from sqlalchemy import CHAR, Column, DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from models.base import Base


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_record"

    id = Column(Integer, primary_key=True)
    client_key = Column(CHAR(36), nullable=False)
    endpoint = Column(String(255), nullable=False)
    idempotency_key = Column(String(255), nullable=False)
    request_fingerprint = Column(CHAR(64), nullable=False)
    response_status = Column(Integer, nullable=False)
    response_keys = Column(JSONB, nullable=False, server_default="[]")
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (UniqueConstraint("client_key", "endpoint", "idempotency_key"),)
