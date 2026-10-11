from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, UniqueConstraint, false, func
from sqlalchemy.orm import relationship
from models.base import Base
from models import PurposeCode


class PurposeRule(Base):
    __tablename__ = "purpose_rule"

    id = Column(Integer, primary_key=True)
    source_purpose_code_id = Column(Integer, ForeignKey(PurposeCode.id), nullable=False)
    target_purpose_code_id = Column(Integer, ForeignKey(PurposeCode.id), nullable=False)
    requires_same_contract = Column(Boolean, nullable=False, server_default=false())
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (UniqueConstraint("source_purpose_code_id", "target_purpose_code_id"),)

    source_purpose_code = relationship("PurposeCode", foreign_keys=[source_purpose_code_id], lazy="selectin")
    target_purpose_code = relationship("PurposeCode", foreign_keys=[target_purpose_code_id], lazy="selectin")
