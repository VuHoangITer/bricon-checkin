import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, Text
from extensions import Base


class SystemSettings(Base):
    __tablename__ = "system_settings"

    id         = Column(String(64), primary_key=True)  # key
    value      = Column(String(256), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # Keys mac dinh:
    # "min_checkin_minutes" -> "15"


class CheckinSession(Base):
    """Luu trang thai check-in dang dien ra (chua checkout)."""
    __tablename__ = "checkin_sessions"

    id         = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id    = Column(String(36), nullable=False)
    store_id   = Column(String(36), nullable=False)
    checkin_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    checkin_lat = Column(String(32))
    checkin_lon = Column(String(32))

    # 3 anh
    photo1_url = Column(String(512))  # anh bang hieu - bat buoc
    photo1_lat = Column(String(32))
    photo1_lon = Column(String(32))
    photo1_at  = Column(DateTime(timezone=True))

    photo2_url = Column(String(512))  # anh BRICON - khong bat buoc
    photo2_lat = Column(String(32))
    photo2_lon = Column(String(32))
    photo2_at  = Column(DateTime(timezone=True))

    photo3_url = Column(String(512))  # anh doi thu dau tien - bat buoc
    photo3_lat = Column(String(32))
    photo3_lon = Column(String(32))
    photo3_at  = Column(DateTime(timezone=True))

    # Luu tat ca url anh slot 3 (pipe separated): url1|url2|url3
    photo_public_id = Column(String(2048))

    note = Column(String(1000))