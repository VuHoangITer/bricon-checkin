import uuid
import enum
from datetime import datetime
from sqlalchemy import (Column, String, DateTime, Text, Float,
                        Integer, Date, ForeignKey, Enum as SAEnum)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from extensions import Base


class StoreType(str, enum.Enum):
    new         = "new"          # chua mua hang  → trang
    retail      = "retail"       # cua hang ban le → xanh
    agent       = "agent"        # dai ly          → vang
    distributor = "distributor"  # nha phan phoi   → do


class StoreStatus(str, enum.Enum):
    active   = "active"
    inactive = "inactive"
    prospect = "prospect"


_COLORS = {
    StoreType.new:         "#FFFFFF",
    StoreType.retail:      "#22C55E",
    StoreType.agent:       "#EAB308",
    StoreType.distributor: "#EF4444",
}


class Store(Base):
    __tablename__ = "stores"

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_code = Column(String(32),  unique=True, nullable=False)
    store_name = Column(String(256), nullable=False)
    store_type = Column(SAEnum(StoreType),   nullable=False, default=StoreType.new)
    status     = Column(SAEnum(StoreStatus), nullable=False, default=StoreStatus.active)

    address    = Column(Text)
    district   = Column(String(128))
    ward       = Column(String(128))
    province   = Column(String(128))
    latitude   = Column(Float)
    longitude  = Column(Float)
    owner_name = Column(String(128))
    phone      = Column(String(20))

    created_by        = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_at        = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at        = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    last_order_date   = Column(Date)
    last_checkin_date = Column(Date)
    total_orders      = Column(Integer, nullable=False, default=0)

    assignments = relationship("Assignment", back_populates="store")
    checkins    = relationship("Checkin",    back_populates="store")
    call_logs = relationship("CallLog", back_populates="store")

    def marker_color(self):
        return _COLORS.get(self.store_type, "#FFFFFF")

    def full_address(self) -> str:
        """Ghep dia chi day du: so nha + phuong + quan + tinh."""
        parts = []
        if self.address:  parts.append(self.address)
        if self.ward:     parts.append(self.ward)
        if self.district: parts.append(self.district)
        if self.province: parts.append(self.province)
        return ", ".join(parts) if parts else ""

    def to_geojson(self):
        return {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [self.longitude, self.latitude]},
            "properties": {
                "id":           str(self.id),
                "code":         self.store_code,
                "name":         self.store_name,
                "type":         self.store_type.value,
                "color":        self.marker_color(),
                "address":      self.full_address(),
                "ward":         self.ward,
                "district":     self.district,
                "province":     self.province,
                "owner":        self.owner_name,
                "phone":        self.phone,
                "last_checkin": self.last_checkin_date.isoformat() if self.last_checkin_date else None,
                "last_order":   self.last_order_date.isoformat()   if self.last_order_date   else None,
            },
        }