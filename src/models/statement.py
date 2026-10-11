from sqlalchemy import CHAR, Column, DateTime, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.orm import relationship
from models.base import Base
from models import LedgerAccount


class Statement(Base):
    __tablename__ = "statement"

    id = Column(Integer, primary_key=True)
    statement_key = Column(CHAR(36), nullable=False)
    ledger_account_id = Column(Integer, ForeignKey(LedgerAccount.id), nullable=False)
    period_start = Column(DateTime(timezone=True), nullable=False)
    period_end = Column(DateTime(timezone=True), nullable=False)
    previous_statement_id = Column(Integer, ForeignKey("statement.id"))
    supersedes_statement_id = Column(Integer, ForeignKey("statement.id"))
    content_hash = Column(CHAR(64), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("statement_key"),
        UniqueConstraint("supersedes_statement_id"),
    )

    ledger_account = relationship("LedgerAccount", foreign_keys=[ledger_account_id], lazy="selectin")
