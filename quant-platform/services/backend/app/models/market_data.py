import uuid
from datetime import datetime
from sqlalchemy import Column, String, Float, DateTime, JSON, Date, Text, Integer, Index
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class MarketData(Base):
    __tablename__ = "market_data"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol = Column(String(20), nullable=False, index=True)
    market = Column(String(20), nullable=False, index=True, comment="KOSPI, KOSDAQ, US")
    date = Column(Date, nullable=False, index=True)
    open = Column(Float, nullable=True)
    high = Column(Float, nullable=True)
    low = Column(Float, nullable=True)
    close = Column(Float, nullable=True)
    volume = Column(Float, nullable=True)
    adj_close = Column(Float, nullable=True)

    __table_args__ = (
        Index("ix_market_data_symbol_date", "symbol", "date", unique=True),
    )

    def __repr__(self):
        return f"<MarketData symbol={self.symbol} date={self.date} close={self.close}>"


class Paper(Base):
    __tablename__ = "papers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(500), nullable=False)
    authors = Column(JSON, nullable=True, default=list, comment="List of author names")
    abstract = Column(Text, nullable=True)
    url = Column(String(1000), nullable=True, unique=True)
    source = Column(String(50), nullable=False, comment="arxiv or ssrn")
    published_date = Column(Date, nullable=True)
    tags = Column(JSON, nullable=True, default=list, comment="List of topic tags")
    summary = Column(Text, nullable=True, comment="AI-generated summary")
    relevance_score = Column(Float, nullable=True, comment="0.0 to 1.0")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<Paper id={self.id} title={self.title[:50]}>"
