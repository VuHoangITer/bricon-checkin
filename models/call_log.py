import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import Column, DateTime, Text, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from extensions import Base

VN_TZ = timezone(timedelta(hours=7))


class CallLog(Base):
    __tablename__ = "call_logs"

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id   = Column(UUID(as_uuid=True), ForeignKey("stores.id"), nullable=False)
    user_id    = Column(UUID(as_uuid=True), ForeignKey("users.id"),  nullable=False)
    called_at  = Column(DateTime(timezone=True), default=lambda: datetime.now(VN_TZ))
    note       = Column(Text)

    store = relationship("Store", back_populates="call_logs")
    user  = relationship("User",  back_populates="call_logs")

    def to_dict(self):
        return {
            "id":        str(self.id),
            "store_id":  str(self.store_id),
            "store_name": self.store.store_name if self.store else None,
            "user_id":   str(self.user_id),
            "user_name": self.user.full_name   if self.user  else None,
            "called_at": self.called_at.isoformat() if self.called_at else None,
            "note":      self.note,
        }