import uuid
from datetime import datetime, timezone, timedelta

VN_TZ = timezone(timedelta(hours=7))
from sqlalchemy import Column, DateTime, Text, Float, Integer, ForeignKey, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from extensions import Base


class Checkin(Base):
    __tablename__ = "checkins"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id        = Column(UUID(as_uuid=True), ForeignKey("stores.id"), nullable=False)
    user_id         = Column(UUID(as_uuid=True), ForeignKey("users.id"),  nullable=False)
    latitude        = Column(Float, nullable=False)
    longitude       = Column(Float, nullable=False)
    accuracy_m      = Column(Float)
    description     = Column(Text)
    photo_url       = Column(Text)
    photo2_url      = Column(Text)
    photo3_url      = Column(Text)
    photo_public_id = Column(Text)
    checkin_at      = Column(DateTime(timezone=True), default=lambda: datetime.now(VN_TZ))
    duration_min    = Column(Integer)

    store = relationship("Store", back_populates="checkins")
    user  = relationship("User",  back_populates="checkins")

    __table_args__ = (
        CheckConstraint(
            "latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180",
            name="ck_checkins_valid_coords",
        ),
    )

    def to_dict(self):
        return {
            "id":               str(self.id),
            "store_id":         str(self.store_id),
            "store_name":       self.store.store_name if self.store else None,
            "user_id":          str(self.user_id),
            "user_name":        self.user.full_name   if self.user  else None,
            "latitude":         self.latitude,
            "longitude":        self.longitude,
            "description":      self.description,
            "photo_url":        self.photo_url,
            "photo2_url":       self.photo2_url,
            "photo3_url":       self.photo3_url,
            "photo_public_id":  self.photo_public_id,
            "checkin_at":       self.checkin_at.isoformat() if self.checkin_at else None,
            "duration_min":     self.duration_min,
        }