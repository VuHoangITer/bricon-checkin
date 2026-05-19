import uuid
from datetime import datetime
from sqlalchemy import Column, Boolean, DateTime, Text, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from extensions import Base


class Assignment(Base):
    __tablename__ = "assignments"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id     = Column(UUID(as_uuid=True), ForeignKey("users.id",  ondelete="CASCADE"), nullable=False)
    store_id    = Column(UUID(as_uuid=True), ForeignKey("stores.id", ondelete="CASCADE"), nullable=False)
    assigned_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    assigned_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    is_active   = Column(Boolean, nullable=False, default=True)
    note        = Column(Text)

    user  = relationship("User",  foreign_keys=[user_id], back_populates="assignments")
    store = relationship("Store", back_populates="assignments")

    __table_args__ = (UniqueConstraint("user_id", "store_id"),)
