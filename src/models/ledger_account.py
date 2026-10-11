from sqlalchemy import CHAR, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import relationship
from models.base import Base
from models import LedgerAccountStatus, LedgerAccountType, PurposeCode


class LedgerAccount(Base):
    __tablename__ = "ledger_account"

    id = Column(Integer, primary_key=True)
    ledger_account_key = Column(CHAR(36), nullable=False)
    client_key = Column(CHAR(36), nullable=False)
    contract_key = Column(String(36), nullable=False, server_default="")
    ledger_account_type_id = Column(Integer, ForeignKey(LedgerAccountType.id), nullable=False)
    ledger_account_status_id = Column(Integer, ForeignKey(LedgerAccountStatus.id), nullable=False)
    purpose_code_id = Column(Integer, ForeignKey(PurposeCode.id), nullable=False)
    owner_party_key = Column(String(36), nullable=False, server_default="")
    owner_role = Column(String(20), nullable=False, server_default="")
    currency = Column(CHAR(3), nullable=False, server_default="BRL")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("ledger_account_key"),
        UniqueConstraint("client_key", "ledger_account_type_id", "purpose_code_id", "contract_key", "owner_party_key"),
    )

    ledger_account_type = relationship("LedgerAccountType", foreign_keys=[ledger_account_type_id], lazy="selectin")
    ledger_account_status = relationship("LedgerAccountStatus", foreign_keys=[ledger_account_status_id], lazy="selectin")
    purpose_code = relationship("PurposeCode", foreign_keys=[purpose_code_id], lazy="selectin")
    status_events = relationship("LedgerAccountStatusEvent", lazy="selectin")
