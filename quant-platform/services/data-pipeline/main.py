"""
Data Pipeline Service for Quantitative Trading Platform
Fetches KOSPI, KOSDAQ, US stock data and market indices,
stores them in PostgreSQL, scheduled with APScheduler.
"""

import os
import logging
import time
from datetime import datetime, date, timedelta
from typing import Optional

import pandas as pd
import numpy as np
from dotenv import load_dotenv
from sqlalchemy import (
    create_engine, text, Column, Integer, String, Float,
    BigInteger, Date, DateTime, UniqueConstraint
)
from sqlalchemy.orm import declarative_base, Session
from sqlalchemy.dialects.postgresql import insert as pg_insert
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
import redis

load_dotenv()

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("data-pipeline")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://quant:quant123@localhost:5432/quantdb")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# US Stocks: S&P 500 sample (25 symbols)
US_SYMBOLS = [
    "AAPL", "GOOGL", "MSFT", "AMZN", "META",
    "NVDA", "TSLA", "BRK-B", "JPM", "JNJ",
    "XOM", "UNH", "V", "PG", "MA",
    "HD", "CVX", "LLY", "ABBV", "MRK",
    "PEP", "KO", "AVGO", "COST", "WMT",
]

# Market indices
INDEX_SYMBOLS = {
    "KS11":  "KOSPI",
    "KQ11":  "KOSDAQ",
    "^GSPC": "US",
    "^IXIC": "US",
}

# ---------------------------------------------------------------------------
# SQLAlchemy Models
# ---------------------------------------------------------------------------
Base = declarative_base()


class MarketData(Base):
    __tablename__ = "market_data"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False)
    market = Column(String(20), nullable=False)
    date = Column(Date, nullable=False)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float, nullable=False)
    volume = Column(BigInteger)
    adj_close = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("symbol", "date", name="uq_market_data_symbol_date"),)


class StockInfo(Base):
    __tablename__ = "stock_info"

    symbol = Column(String(20), primary_key=True)
    name = Column(String(200))
    market = Column(String(20))
    sector = Column(String(100))
    industry = Column(String(100))
    market_cap = Column(BigInteger)
    updated_at = Column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_engine():
    return create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=5, max_overflow=10)


def init_db(engine):
    """Create tables if they don't exist and apply raw DDL extras."""
    Base.metadata.create_all(engine)
    ddl = """
    CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
    CREATE INDEX IF NOT EXISTS idx_market_data_symbol_date ON market_data(symbol, date);
    CREATE INDEX IF NOT EXISTS idx_market_data_market ON market_data(market);
    """
    with engine.connect() as conn:
        for stmt in ddl.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                try:
                    conn.execute(text(stmt))
                except Exception as exc:
                    logger.debug("DDL skip: %s", exc)
        conn.commit()
    logger.info("Database initialised")


def upsert_market_data(engine, records: list[dict]):
    """Bulk upsert into market_data via PostgreSQL ON CONFLICT DO UPDATE."""
    if not records:
        return
    with engine.connect() as conn:
        stmt = pg_insert(MarketData).values(records)
        stmt = stmt.on_conflict_do_update(
            index_elements=["symbol", "date"],
            set_={
                "open": stmt.excluded.open,
                "high": stmt.excluded.high,
                "low": stmt.excluded.low,
                "close": stmt.excluded.close,
                "volume": stmt.excluded.volume,
                "adj_close": stmt.excluded.adj_close,
            },
        )
        conn.execute(stmt)
        conn.commit()
    logger.info("Upserted %d records into market_data", len(records))


def upsert_stock_info(engine, records: list[dict]):
    if not records:
        return
    with engine.connect() as conn:
        stmt = pg_insert(StockInfo).values(records)
        stmt = stmt.on_conflict_do_update(
            index_elements=["symbol"],
            set_={
                "name": stmt.excluded.name,
                "market": stmt.excluded.market,
                "sector": stmt.excluded.sector,
                "industry": stmt.excluded.industry,
                "market_cap": stmt.excluded.market_cap,
                "updated_at": datetime.utcnow(),
            },
        )
        conn.execute(stmt)
        conn.commit()
    logger.info("Upserted %d records into stock_info", len(records))


# ---------------------------------------------------------------------------
# Data fetching helpers
# ---------------------------------------------------------------------------

def df_to_records(df: pd.DataFrame, symbol: str, market: str) -> list[dict]:
    """Convert a DataFrame with OHLCV columns to a list of dicts for upsert."""
    records = []
    col_map = {
        "Open": "open", "High": "high", "Low": "low",
        "Close": "close", "Volume": "volume", "Adj Close": "adj_close",
    }
    df = df.rename(columns=col_map)
    df.index = pd.to_datetime(df.index)

    required = {"close"}
    available = set(df.columns)
    if not required.issubset(available):
        logger.warning("Symbol %s missing required columns, skipping", symbol)
        return records

    for idx, row in df.iterrows():
        close_val = row.get("close")
        if pd.isna(close_val):
            continue
        records.append({
            "symbol": symbol,
            "market": market,
            "date": idx.date(),
            "open": None if pd.isna(row.get("open", float("nan"))) else float(row.get("open", float("nan"))),
            "high": None if pd.isna(row.get("high", float("nan"))) else float(row.get("high", float("nan"))),
            "low": None if pd.isna(row.get("low", float("nan"))) else float(row.get("low", float("nan"))),
            "close": float(close_val),
            "volume": None if pd.isna(row.get("volume", float("nan"))) else int(row.get("volume", 0)),
            "adj_close": None if pd.isna(row.get("adj_close", float("nan"))) else float(row.get("adj_close", float("nan"))),
        })
    return records


def fetch_fdr_data(symbol: str, start: str, end: str, market: str) -> list[dict]:
    """Fetch OHLCV via FinanceDataReader."""
    import FinanceDataReader as fdr
    try:
        df = fdr.DataReader(symbol, start, end)
        if df is None or df.empty:
            logger.warning("No FDR data for %s", symbol)
            return []
        return df_to_records(df, symbol, market)
    except Exception as exc:
        logger.error("FDR fetch failed for %s: %s", symbol, exc)
        return []


def fetch_yfinance_data(symbol: str, start: str, end: str, market: str) -> list[dict]:
    """Fetch OHLCV via yfinance."""
    import yfinance as yf
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(start=start, end=end, auto_adjust=False)
        if df is None or df.empty:
            logger.warning("No yfinance data for %s", symbol)
            return []
        return df_to_records(df, symbol, market)
    except Exception as exc:
        logger.error("yfinance fetch failed for %s: %s", symbol, exc)
        return []


def fetch_with_retry(fetch_fn, *args, retries: int = 3, delay: float = 5.0) -> list[dict]:
    for attempt in range(1, retries + 1):
        result = fetch_fn(*args)
        if result:
            return result
        if attempt < retries:
            logger.info("Retry %d/%d for %s in %.1fs", attempt, retries, args[0], delay)
            time.sleep(delay)
    return []


# ---------------------------------------------------------------------------
# KOSPI / KOSDAQ symbol discovery
# ---------------------------------------------------------------------------

def get_krx_top_symbols(market: str, top_n: int) -> list[tuple[str, str]]:
    """
    Returns [(symbol, name), ...] for the top N stocks by market cap
    using pykrx.  Falls back to a hard-coded list on error.
    """
    try:
        from pykrx import stock as pykrx_stock
        today_str = date.today().strftime("%Y%m%d")
        # Try previous trading days if today returns empty (weekend/holiday)
        for delta in range(0, 5):
            d = (date.today() - timedelta(days=delta)).strftime("%Y%m%d")
            tickers = pykrx_stock.get_market_ticker_list(d, market=market)
            if tickers:
                break
        else:
            raise ValueError("No tickers from pykrx")

        caps = []
        for tk in tickers[:200]:  # limit API calls
            try:
                info = pykrx_stock.get_market_cap_by_ticker(d, market=market)
                if tk in info.index:
                    caps.append((tk, int(info.loc[tk, "시가총액"])))
            except Exception:
                pass
            time.sleep(0.05)

        caps.sort(key=lambda x: x[1], reverse=True)
        top_tickers = [t for t, _ in caps[:top_n]]

        result = []
        for tk in top_tickers:
            try:
                name = pykrx_stock.get_market_ticker_name(tk)
            except Exception:
                name = tk
            result.append((tk, name))
        return result

    except Exception as exc:
        logger.warning("pykrx symbol fetch failed (%s), using fallback list: %s", market, exc)
        if market == "KOSPI":
            return [
                ("005930", "삼성전자"), ("000660", "SK하이닉스"), ("005380", "현대차"),
                ("035420", "NAVER"), ("051910", "LG화학"), ("006400", "삼성SDI"),
                ("035720", "카카오"), ("028260", "삼성물산"), ("012330", "현대모비스"),
                ("207940", "삼성바이오로직스"), ("068270", "셀트리온"), ("105560", "KB금융"),
                ("055550", "신한지주"), ("086790", "하나금융지주"), ("003550", "LG"),
                ("015760", "한국전력"), ("017670", "SK텔레콤"), ("030200", "KT"),
                ("096770", "SK이노베이션"), ("010950", "S-Oil"), ("032830", "삼성생명"),
                ("003490", "대한항공"), ("018260", "삼성에스디에스"), ("009150", "삼성전기"),
                ("011200", "HMM"), ("066570", "LG전자"), ("034730", "SK"),
                ("000270", "기아"), ("011170", "롯데케미칼"), ("009830", "한화솔루션"),
                ("010130", "고려아연"), ("011780", "금호석유"), ("042660", "한화오션"),
                ("036460", "한국가스공사"), ("078930", "GS"), ("000720", "현대건설"),
                ("004020", "현대제철"), ("161390", "한국타이어앤테크놀로지"),
                ("008770", "호텔신라"), ("024110", "기업은행"),
                ("139480", "이마트"), ("069960", "현대백화점"),
                ("000810", "삼성화재"), ("005830", "DB손해보험"),
                ("128940", "한미약품"), ("326030", "SK바이오팜"),
                ("247540", "에코프로비엠"), ("086280", "현대글로비스"),
                ("010060", "OCI홀딩스"), ("011790", "SKC"),
            ]
        else:  # KOSDAQ
            return [
                ("247540", "에코프로비엠"), ("086520", "에코프로"), ("357780", "솔브레인"),
                ("196170", "알테오젠"), ("145020", "휴젤"), ("112040", "위메이드"),
                ("263750", "펄어비스"), ("041510", "에스엠"), ("122870", "와이지엔터테인먼트"),
                ("035900", "JYP Ent."), ("293490", "카카오게임즈"), ("251270", "넷마블"),
                ("095340", "ISC"), ("039030", "이오테크닉스"), ("042700", "한미반도체"),
                ("240810", "원익IPS"), ("083790", "크레버스"), ("054620", "APS홀딩스"),
                ("403870", "HPSP"), ("214150", "클래시스"), ("142280", "하이소닉"),
                ("140860", "파크시스템스"), ("064760", "티씨케이"), ("093320", "케이씨에스"),
                ("131030", "옵투스제약"), ("078600", "대주전자재료"), ("290930", "에스피시스템스"),
                ("032500", "케이엠더블유"), ("041960", "코미팜"), ("066970", "엘앤에프"),
            ]


# ---------------------------------------------------------------------------
# Main pipeline tasks
# ---------------------------------------------------------------------------

def run_pipeline(engine):
    """Full data pipeline: fetch KRX + US data and store in PostgreSQL."""
    end_date = date.today().strftime("%Y-%m-%d")
    start_date = (date.today() - timedelta(days=730)).strftime("%Y-%m-%d")  # 2 years

    logger.info("=== Pipeline run started (start=%s, end=%s) ===", start_date, end_date)

    all_records: list[dict] = []
    stock_info_records: list[dict] = []

    # ------------------------------------------------------------------
    # 1. KOSPI top 50
    # ------------------------------------------------------------------
    logger.info("Fetching KOSPI top 50 stocks...")
    kospi_symbols = get_krx_top_symbols("KOSPI", 50)
    for symbol, name in kospi_symbols:
        records = fetch_with_retry(fetch_fdr_data, symbol, start_date, end_date, "KOSPI")
        all_records.extend(records)
        stock_info_records.append({
            "symbol": symbol, "name": name, "market": "KOSPI",
            "sector": None, "industry": None, "market_cap": None,
            "updated_at": datetime.utcnow(),
        })
        time.sleep(0.2)

    # ------------------------------------------------------------------
    # 2. KOSDAQ top 30
    # ------------------------------------------------------------------
    logger.info("Fetching KOSDAQ top 30 stocks...")
    kosdaq_symbols = get_krx_top_symbols("KOSDAQ", 30)
    for symbol, name in kosdaq_symbols:
        records = fetch_with_retry(fetch_fdr_data, symbol, start_date, end_date, "KOSDAQ")
        all_records.extend(records)
        stock_info_records.append({
            "symbol": symbol, "name": name, "market": "KOSDAQ",
            "sector": None, "industry": None, "market_cap": None,
            "updated_at": datetime.utcnow(),
        })
        time.sleep(0.2)

    # ------------------------------------------------------------------
    # 3. US stocks (yfinance)
    # ------------------------------------------------------------------
    logger.info("Fetching US stocks (%d symbols)...", len(US_SYMBOLS))
    import yfinance as yf
    for symbol in US_SYMBOLS:
        records = fetch_with_retry(fetch_yfinance_data, symbol, start_date, end_date, "US")
        all_records.extend(records)

        # Fetch basic info
        try:
            ticker_obj = yf.Ticker(symbol)
            info = ticker_obj.info
            stock_info_records.append({
                "symbol": symbol,
                "name": info.get("longName") or info.get("shortName") or symbol,
                "market": "US",
                "sector": info.get("sector"),
                "industry": info.get("industry"),
                "market_cap": info.get("marketCap"),
                "updated_at": datetime.utcnow(),
            })
        except Exception as exc:
            logger.warning("Could not fetch yfinance info for %s: %s", symbol, exc)
            stock_info_records.append({
                "symbol": symbol, "name": symbol, "market": "US",
                "sector": None, "industry": None, "market_cap": None,
                "updated_at": datetime.utcnow(),
            })
        time.sleep(0.5)

    # ------------------------------------------------------------------
    # 4. Market indices
    # ------------------------------------------------------------------
    logger.info("Fetching market indices...")
    for idx_symbol, idx_market in INDEX_SYMBOLS.items():
        if idx_symbol.startswith("^"):
            records = fetch_with_retry(fetch_yfinance_data, idx_symbol, start_date, end_date, idx_market)
        else:
            records = fetch_with_retry(fetch_fdr_data, idx_symbol, start_date, end_date, idx_market)
        all_records.extend(records)
        stock_info_records.append({
            "symbol": idx_symbol, "name": idx_symbol, "market": idx_market,
            "sector": "Index", "industry": "Market Index", "market_cap": None,
            "updated_at": datetime.utcnow(),
        })
        time.sleep(0.3)

    # ------------------------------------------------------------------
    # 5. Store everything
    # ------------------------------------------------------------------
    logger.info("Storing %d market data records...", len(all_records))
    upsert_market_data(engine, all_records)
    upsert_stock_info(engine, stock_info_records)

    # ------------------------------------------------------------------
    # 6. Publish completion event to Redis
    # ------------------------------------------------------------------
    try:
        r = redis.from_url(REDIS_URL)
        r.set(
            "data_pipeline:last_run",
            datetime.utcnow().isoformat(),
            ex=86400 * 7,
        )
        r.publish("data_pipeline:events", "pipeline_complete")
        logger.info("Redis event published")
    except Exception as exc:
        logger.warning("Redis publish failed (non-critical): %s", exc)

    logger.info("=== Pipeline run complete ===")


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

def main():
    engine = get_engine()
    init_db(engine)

    # Run immediately on startup
    logger.info("Running initial pipeline on startup...")
    try:
        run_pipeline(engine)
    except Exception as exc:
        logger.error("Initial pipeline run failed: %s", exc, exc_info=True)

    # Schedule: weekdays at 18:00 KST (UTC+9 = 09:00 UTC)
    scheduler = BlockingScheduler(timezone="Asia/Seoul")
    scheduler.add_job(
        func=run_pipeline,
        args=[engine],
        trigger=CronTrigger(
            day_of_week="mon-fri",
            hour=18,
            minute=0,
            timezone="Asia/Seoul",
        ),
        id="daily_pipeline",
        name="Daily Market Data Pipeline",
        misfire_grace_time=3600,
    )

    logger.info("Scheduler started — daily pipeline at 18:00 KST on weekdays")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped")


if __name__ == "__main__":
    main()
