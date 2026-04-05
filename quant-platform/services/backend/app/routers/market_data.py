from typing import List, Optional
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.market_data import MarketData
from app.services.data_service import data_service

router = APIRouter()


# ---- Pydantic Schemas ----

class PricePoint(BaseModel):
    date: date
    open: Optional[float]
    high: Optional[float]
    low: Optional[float]
    close: Optional[float]
    volume: Optional[float]
    adj_close: Optional[float]

    class Config:
        from_attributes = True


class StockInfo(BaseModel):
    code: str
    name: Optional[str]
    market: Optional[str]
    sector: Optional[str] = None


class RefreshRequest(BaseModel):
    market: str = "KOSPI"
    start: str = "2020-01-01"


# ---- Background refresh helper ----

def _refresh_market_data(market: str, start: str, db: Session):
    """Background task to trigger market data refresh."""
    try:
        if market.upper() == "KOSPI":
            data_service.fetch_kospi_stocks(db, start=start)
        elif market.upper() == "KOSDAQ":
            data_service.fetch_kosdaq_stocks(db, start=start)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Market data refresh failed: {e}")


# ---- Endpoints ----

@router.get("/stocks", summary="Search stocks in a market")
def search_stocks(
    market: str = Query("KOSPI", description="KOSPI, KOSDAQ, or US"),
    search: Optional[str] = Query(None, description="Search by name or code"),
):
    """
    Search for stocks in a given market.
    Example: GET /api/market-data/stocks?market=KOSPI&search=삼성
    """
    results = data_service.search_stocks(market=market, query=search or "")
    return {
        "market": market,
        "query": search,
        "count": len(results),
        "stocks": results,
    }


@router.get("/{symbol}/prices", summary="Get historical price data for a symbol")
def get_symbol_prices(
    symbol: str,
    start: str = Query("2020-01-01", description="Start date (YYYY-MM-DD)"),
    end: str = Query(None, description="End date (YYYY-MM-DD), defaults to today"),
    market: str = Query("KOSPI", description="KOSPI, KOSDAQ, or US"),
    db: Session = Depends(get_db),
):
    """
    Get OHLCV price data for a specific symbol.
    First tries the local database; falls back to live data from FinanceDataReader.
    """
    from datetime import datetime
    if end is None:
        end = datetime.today().strftime("%Y-%m-%d")

    # Try database first
    db_records = (
        db.query(MarketData)
        .filter(
            MarketData.symbol == symbol,
            MarketData.date >= start,
            MarketData.date <= end,
        )
        .order_by(MarketData.date)
        .all()
    )

    if db_records:
        prices = [
            {
                "date": str(r.date),
                "open": r.open,
                "high": r.high,
                "low": r.low,
                "close": r.close,
                "volume": r.volume,
                "adj_close": r.adj_close,
            }
            for r in db_records
        ]
        return {
            "symbol": symbol,
            "market": market,
            "source": "database",
            "count": len(prices),
            "prices": prices,
        }

    # Fall back to live data
    try:
        import FinanceDataReader as fdr
        df = fdr.DataReader(symbol, start, end)
        if df.empty:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No price data found for symbol '{symbol}'.",
            )

        prices = []
        for dt, row in df.iterrows():
            prices.append(
                {
                    "date": str(dt.date() if hasattr(dt, "date") else dt),
                    "open": float(row.get("Open")) if row.get("Open") is not None else None,
                    "high": float(row.get("High")) if row.get("High") is not None else None,
                    "low": float(row.get("Low")) if row.get("Low") is not None else None,
                    "close": float(row.get("Close")) if row.get("Close") is not None else None,
                    "volume": float(row.get("Volume")) if row.get("Volume") is not None else None,
                    "adj_close": float(row.get("Adj Close", row.get("Close"))) if row.get("Adj Close", row.get("Close")) is not None else None,
                }
            )

        return {
            "symbol": symbol,
            "market": market,
            "source": "live",
            "count": len(prices),
            "prices": prices,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch price data: {str(e)}",
        )


@router.post("/refresh", status_code=status.HTTP_202_ACCEPTED, summary="Trigger market data refresh")
def refresh_market_data(
    payload: RefreshRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Trigger a background refresh of market data for the specified market.
    Returns immediately; data is fetched in the background.
    """
    background_tasks.add_task(_refresh_market_data, payload.market, payload.start, db)
    return {
        "status": "accepted",
        "message": f"Market data refresh for {payload.market} started in background.",
        "market": payload.market,
        "start": payload.start,
    }


@router.get("/index/{market}", summary="Get market index data")
def get_market_index(
    market: str,
    start: str = Query("2020-01-01", description="Start date (YYYY-MM-DD)"),
    end: str = Query(None, description="End date (YYYY-MM-DD)"),
):
    """
    Get benchmark index data.
    - KOSPI -> KS11 (KOSPI Composite)
    - KOSDAQ -> KQ11 (KOSDAQ Composite)
    - US -> ^GSPC (S&P 500)
    """
    from datetime import datetime
    if end is None:
        end = datetime.today().strftime("%Y-%m-%d")

    series = data_service.get_market_index(market, start, end)
    if series.empty:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No index data found for market '{market}'.",
        )

    data = [
        {"date": str(idx.date() if hasattr(idx, "date") else idx), "value": float(val)}
        for idx, val in series.items()
        if not __import__("math").isnan(val)
    ]

    return {
        "market": market,
        "count": len(data),
        "data": data,
    }
