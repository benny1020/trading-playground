import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime, JSON
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class Strategy(Base):
    __tablename__ = "strategies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    strategy_type = Column(
        String(50),
        nullable=False,
        comment="momentum, mean_reversion, factor, pairs, breakout, custom",
    )
    parameters = Column(JSON, nullable=True, default=dict)
    market = Column(
        String(20),
        nullable=False,
        default="KOSPI",
        comment="KOSPI, KOSDAQ, US, ALL",
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    def __repr__(self):
        return f"<Strategy id={self.id} name={self.name} type={self.strategy_type}>"
