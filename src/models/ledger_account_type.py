from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint, func
from models.base import Base


class LedgerAccountType(Base):
    __tablename__ = "ledger_account_type"

    id = Column(Integer, primary_key=True)
    enumerator = Column(String(50), nullable=False)
    side = Column(String(10), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (UniqueConstraint("enumerator"),)

    EXTERNAL = "external"
    EARMARK = "earmark"
    OWN = "own"
    SUSPENSE = "suspense"
    CLEARING = "clearing"
    REVENUE = "revenue"

    ASSET = "asset"
    LIABILITY = "liability"
    EQUITY = "equity"
