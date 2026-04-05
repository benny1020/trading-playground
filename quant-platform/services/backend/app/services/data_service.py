import logging
from typing import List, Optional
from datetime import datetime, date

import pandas as pd
import FinanceDataReader as fdr
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.models.market_data import MarketData

logger = logging.getLogger(__name__)

MARKET_INDEX_MAP = {
    "KOSPI": "KS11",
    "KOSDAQ": "KQ11",
    "US": "^GSPC",
    "SP500": "^GSPC",
    "NASDAQ": "^IXIC",
    "DOW": "^DJI",
}


class DataService:
    def fetch_kospi_stocks(self, db: Session, start: str = "2020-01-01", end: Optional[str] = None):
        """Fetch KOSPI constituent stocks data and persist to DB."""
        if end is None:
            end = datetime.today().strftime("%Y-%m-%d")

        try:
            kospi_listing = fdr.StockListing("KOSPI")
            symbols = kospi_listing["Code"].tolist()[:50]  # Limit to top 50 for initial load

            logger.info(f"Fetching {len(symbols)} KOSPI stocks from {start} to {end}")

            for symbol in symbols:
                try:
                    df = fdr.DataReader(symbol, start, end)
                    if df.empty:
                        continue
                    self._upsert_price_data(db, df, symbol, "KOSPI")
                except Exception as e:
                    logger.warning(f"Failed to fetch KOSPI {symbol}: {e}")
                    continue

            db.commit()
            logger.info("KOSPI data fetch complete")
        except Exception as e:
            logger.error(f"Error fetching KOSPI stocks: {e}")
            db.rollback()
            raise

    def fetch_kosdaq_stocks(self, db: Session, start: str = "2020-01-01", end: Optional[str] = None):
        """Fetch KOSDAQ stocks and persist to DB."""
        if end is None:
            end = datetime.today().strftime("%Y-%m-%d")

        try:
            kosdaq_listing = fdr.StockListing("KOSDAQ")
            symbols = kosdaq_listing["Code"].tolist()[:50]

            logger.info(f"Fetching {len(symbols)} KOSDAQ stocks from {start} to {end}")

            for symbol in symbols:
                try:
                    df = fdr.DataReader(symbol, start, end)
                    if df.empty:
                        continue
                    self._upsert_price_data(db, df, symbol, "KOSDAQ")
                except Exception as e:
                    logger.warning(f"Failed to fetch KOSDAQ {symbol}: {e}")
                    continue

            db.commit()
            logger.info("KOSDAQ data fetch complete")
        except Exception as e:
            logger.error(f"Error fetching KOSDAQ stocks: {e}")
            db.rollback()
            raise

    def fetch_us_stocks(self, symbols: List[str], start: str, end: str) -> pd.DataFrame:
        """Fetch US stocks via FinanceDataReader. Returns adjusted close prices."""
        dfs = {}
        for symbol in symbols:
            try:
                df = fdr.DataReader(symbol, start, end)
                if df.empty:
                    continue
                # Use Adj Close if available, else Close
                if "Adj Close" in df.columns:
                    dfs[symbol] = df["Adj Close"]
                elif "Close" in df.columns:
                    dfs[symbol] = df["Close"]
            except Exception as e:
                logger.warning(f"Failed to fetch US stock {symbol}: {e}")
                continue

        if not dfs:
            return pd.DataFrame()

        return pd.DataFrame(dfs)

    def get_market_index(self, market: str, start: str, end: str) -> pd.Series:
        """
        Get benchmark index.
        - KOSPI -> KS11
        - KOSDAQ -> KQ11
        - US -> ^GSPC (S&P 500)
        """
        ticker = MARKET_INDEX_MAP.get(market.upper(), market)
        try:
            df = fdr.DataReader(ticker, start, end)
            if df.empty:
                return pd.Series(dtype=float)
            if "Close" in df.columns:
                return df["Close"]
            return df.iloc[:, 0]
        except Exception as e:
            logger.error(f"Failed to fetch market index {ticker}: {e}")
            return pd.Series(dtype=float)

    def get_price_data(
        self,
        symbols: List[str],
        start: str,
        end: str,
        market: str = "KOSPI",
    ) -> pd.DataFrame:
        """
        Unified price data fetcher for all markets.
        Returns DataFrame with adjusted close prices: rows=dates, columns=symbols.
        """
        dfs = {}
        for symbol in symbols:
            try:
                df = fdr.DataReader(symbol, start, end)
                if df.empty:
                    continue

                if "Adj Close" in df.columns:
                    series = df["Adj Close"]
                elif "Close" in df.columns:
                    series = df["Close"]
                else:
                    series = df.iloc[:, 0]

                dfs[symbol] = series
            except Exception as e:
                logger.warning(f"Failed to fetch {symbol} ({market}): {e}")
                continue

        if not dfs:
            return pd.DataFrame()

        result = pd.DataFrame(dfs)
        result.index = pd.to_datetime(result.index)
        result = result.sort_index()
        return result

    def get_price_data_from_db(
        self,
        db: Session,
        symbols: List[str],
        start: str,
        end: str,
        market: str = "KOSPI",
    ) -> pd.DataFrame:
        """Fetch price data from local database if available."""
        start_date = pd.to_datetime(start).date()
        end_date = pd.to_datetime(end).date()

        records = (
            db.query(MarketData)
            .filter(
                and_(
                    MarketData.symbol.in_(symbols),
                    MarketData.market == market,
                    MarketData.date >= start_date,
                    MarketData.date <= end_date,
                )
            )
            .all()
        )

        if not records:
            return pd.DataFrame()

        data = []
        for r in records:
            data.append(
                {
                    "date": r.date,
                    "symbol": r.symbol,
                    "close": r.adj_close if r.adj_close else r.close,
                }
            )

        df = pd.DataFrame(data)
        if df.empty:
            return df

        pivot = df.pivot(index="date", columns="symbol", values="close")
        pivot.index = pd.to_datetime(pivot.index)
        pivot = pivot.sort_index()
        return pivot

    def search_stocks(self, market: str, query: str) -> List[dict]:
        """Search for stocks by name or code in a given market."""
        try:
            if market.upper() == "KOSPI":
                listing = fdr.StockListing("KOSPI")
            elif market.upper() == "KOSDAQ":
                listing = fdr.StockListing("KOSDAQ")
            elif market.upper() in ("US", "NYSE", "NASDAQ"):
                listing = fdr.StockListing("NYSE")
            else:
                listing = fdr.StockListing("KOSPI")

            if query:
                mask = (
                    listing["Code"].str.contains(query, case=False, na=False)
                    | listing["Name"].str.contains(query, case=False, na=False)
                )
                listing = listing[mask]

            return listing.head(50).to_dict(orient="records")
        except Exception as e:
            logger.error(f"Error searching stocks: {e}")
            return []

    def _upsert_price_data(self, db: Session, df: pd.DataFrame, symbol: str, market: str):
        """Upsert price data for a single symbol into the DB."""
        for dt, row in df.iterrows():
            record_date = pd.Timestamp(dt).date() if not isinstance(dt, date) else dt

            existing = (
                db.query(MarketData)
                .filter(
                    and_(
                        MarketData.symbol == symbol,
                        MarketData.date == record_date,
                    )
                )
                .first()
            )

            open_val = float(row.get("Open", 0)) if pd.notna(row.get("Open")) else None
            high_val = float(row.get("High", 0)) if pd.notna(row.get("High")) else None
            low_val = float(row.get("Low", 0)) if pd.notna(row.get("Low")) else None
            close_val = float(row.get("Close", 0)) if pd.notna(row.get("Close")) else None
            volume_val = float(row.get("Volume", 0)) if pd.notna(row.get("Volume")) else None
            adj_close_val = (
                float(row.get("Adj Close", row.get("Close", 0)))
                if pd.notna(row.get("Adj Close", row.get("Close")))
                else None
            )

            if existing:
                existing.open = open_val
                existing.high = high_val
                existing.low = low_val
                existing.close = close_val
                existing.volume = volume_val
                existing.adj_close = adj_close_val
            else:
                record = MarketData(
                    symbol=symbol,
                    market=market,
                    date=record_date,
                    open=open_val,
                    high=high_val,
                    low=low_val,
                    close=close_val,
                    volume=volume_val,
                    adj_close=adj_close_val,
                )
                db.add(record)


data_service = DataService()
