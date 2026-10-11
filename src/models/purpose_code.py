from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint, func
from models.base import Base


class PurposeCode(Base):
    __tablename__ = "purpose_code"

    id = Column(Integer, primary_key=True)
    enumerator = Column(String(50), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (UniqueConstraint("enumerator"),)

    CASH = "CASH"
    UNALLOCATED = "UNALLOCATED"
    TRANSIT = "TRANSIT"
    OWN = "OWN"
    PLATFORM_FEE = "PLATFORM_FEE"
    WALLET = "WALLET"
    COLLECTION = "COLLECTION"
    RENT = "RENT"
    IPTU = "IPTU"
    CONDO = "CONDO"
    WATER = "WATER"
    ELECTRICITY = "ELECTRICITY"
    DEPOSIT = "DEPOSIT"
