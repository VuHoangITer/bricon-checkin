import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import Column, DateTime, Float, Text, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from extensions import Base

VN_TZ = timezone(timedelta(hours=7))


class LocationLog(Base):
    """
    Ghi lai moi lan cap nhat toa do cua hang.
    - action: 'set'  -> lan dau dat toa do (chua co truoc do)
    - action: 'fix'  -> sua toa do bi sai
    """
    __tablename__ = "location_logs"

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id   = Column(UUID(as_uuid=True), ForeignKey("stores.id", ondelete="CASCADE"), nullable=False)
    user_id    = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    action     = Column(String(16), nullable=False)   # 'set' | 'fix'

    # Toa do cu (null neu chua co)
    old_lat    = Column(Float)
    old_lon    = Column(Float)

    # Toa do moi
    new_lat    = Column(Float, nullable=False)
    new_lon    = Column(Float, nullable=False)

    # Khoang cach lech so voi toa do cu (m), null neu chua co toa do cu
    delta_m    = Column(Float)

    # Anh chup tai cho (bat buoc khi action='fix')
    photo_url  = Column(Text)

    note       = Column(Text)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(VN_TZ))

    store = relationship("Store", backref="location_logs")
    user  = relationship("User")

    def to_dict(self):
        return {
            "id":         str(self.id),
            "store_id":   str(self.store_id),
            "store_name": self.store.store_name if self.store else None,
            "user_id":    str(self.user_id),
            "user_name":  self.user.full_name   if self.user  else None,
            "action":     self.action,
            "old_lat":    self.old_lat,
            "old_lon":    self.old_lon,
            "new_lat":    self.new_lat,
            "new_lon":    self.new_lon,
            "delta_m":    round(self.delta_m, 1) if self.delta_m else None,
            "photo_url":  self.photo_url,
            "note":       self.note,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }