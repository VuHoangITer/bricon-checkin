import uuid
import enum
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, Text, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from extensions import Base


class UserRole(str, enum.Enum):
    admin     = "admin"
    manager   = "manager"
    sales     = "sales"
    telesales = "telesales"


class User(Base):
    __tablename__ = "users"

    id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username      = Column(String(64),  unique=True, nullable=False)
    full_name     = Column(String(128), nullable=False)
    phone         = Column(String(20))
    email         = Column(String(128), unique=True)
    password_hash = Column(Text, nullable=False)
    role          = Column(SAEnum(UserRole), nullable=False, default=UserRole.sales)
    is_active     = Column(Boolean, nullable=False, default=True)
    created_at    = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at    = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    assignments = relationship("Assignment", foreign_keys="Assignment.user_id", back_populates="user")
    checkins    = relationship("Checkin",  back_populates="user")
    call_logs   = relationship("CallLog", back_populates="user")