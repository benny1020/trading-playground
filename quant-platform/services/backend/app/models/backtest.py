import uuid
from datetime import datetime
from sqlalchemy import Column, String, Float, DateTime, JSON, ForeignKey, Text, Date
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base


class BacktestRun(Base):
    __tablename__ = "backtest_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    strategy_id = Column(UUID(as_uuid=True), ForeignKey("strategies.id"), nullable=False)
    name = Column(String(255), nullable=False)
    status = Column(
        String(20),
        nullable=False,
        default="pending",
        comment="pending, running, completed, failed",
    )
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    initial_capital = Column(Float, nullable=False, default=100_000_000.0)
    commission_rate = Column(Float, nullable=False, default=0.0015)
    symbols = Column(JSON, nullable=True, default=list)
    market = Column(String(20), nullable=False, default="KOSPI")
    results = Column(JSON, nullable=True, comment="Performance metrics dict")
    equity_curve = Column(JSON, nullable=True, comment="List of {date, value} dicts")
    trades = Column(JSON, nullable=True, comment="List of trade dicts")
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    strategy = relationship("Strategy", backref="backtest_runs", lazy="select")

    def __repr__(self):
        return f"<BacktestRun id={self.id} name={self.name} status={self.status}>"
