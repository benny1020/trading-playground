import uuid
from typing import List, Optional
from datetime import datetime, date

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.backtest import BacktestRun
from app.models.strategy import Strategy

router = APIRouter()


# ---- Pydantic Schemas ----

class BacktestCreate(BaseModel):
    strategy_id: uuid.UUID
    name: str = Field(..., min_length=1, max_length=255)
    start_date: date
    end_date: date
    initial_capital: float = Field(default=100_000_000.0, gt=0)
    commission_rate: float = Field(default=0.0015, ge=0, le=0.05)
    symbols: List[str] = Field(default_factory=list)
    market: str = Field(default="KOSPI")


class BacktestResponse(BaseModel):
    id: uuid.UUID
    strategy_id: uuid.UUID
    name: str
    status: str
    start_date: date
    end_date: date
    initial_capital: float
    commission_rate: float
    symbols: Optional[List[str]]
    market: str
    results: Optional[dict]
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class BacktestListResponse(BaseModel):
    id: uuid.UUID
    strategy_id: uuid.UUID
    name: str
    status: str
    start_date: date
    end_date: date
    market: str
    results: Optional[dict]
    created_at: datetime

    class Config:
        from_attributes = True


# ---- Helper: run backtest in background ----

def _run_backtest_task(backtest_id: str, db: Session):
    """Execute a backtest synchronously (called from background task)."""
    from app.services.backtest_engine import BacktestEngine
    from app.services.strategy_library import get_strategy
    from app.services.data_service import data_service
    import traceback

    try:
        backtest = db.query(BacktestRun).filter(BacktestRun.id == uuid.UUID(backtest_id)).first()
        if not backtest:
            return

        # Mark as running
        backtest.status = "running"
        backtest.updated_at = datetime.utcnow()
        db.commit()

        strategy = db.query(Strategy).filter(Strategy.id == backtest.strategy_id).first()
        if not strategy:
            raise ValueError(f"Strategy {backtest.strategy_id} not found")

        start_str = backtest.start_date.strftime("%Y-%m-%d")
        end_str = backtest.end_date.strftime("%Y-%m-%d")

        # Fetch price data
        symbols = backtest.symbols or []
        prices = data_service.get_price_data(
            symbols=symbols,
            start=start_str,
            end=end_str,
            market=backtest.market,
        )

        if prices.empty:
            raise ValueError("No price data available for the given symbols and date range")

        # Generate signals
        strategy_instance = get_strategy(strategy.strategy_type)
        params = strategy.parameters or {}
        signals = strategy_instance.generate_signals(prices, **params)

        # Run backtest
        engine = BacktestEngine(
            initial_capital=backtest.initial_capital,
            commission_rate=backtest.commission_rate,
        )
        result = engine.run(prices, signals)

        # Serialize equity curve
        equity_curve_data = [
            {"date": str(d), "value": float(v)}
            for d, v in result.equity_curve.items()
            if not __import__("math").isnan(v)
        ]

        # Serialize trades
        trades_data = [
            {
                "symbol": t.symbol,
                "entry_date": t.entry_date,
                "exit_date": t.exit_date,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "quantity": t.quantity,
                "side": t.side,
                "pnl": t.pnl,
                "return_pct": t.return_pct,
            }
            for t in result.trades
        ]

        # Persist results
        backtest.status = "completed"
        backtest.results = result.metrics
        backtest.equity_curve = equity_curve_data
        backtest.trades = trades_data
        backtest.updated_at = datetime.utcnow()
        db.commit()

    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
        try:
            backtest = db.query(BacktestRun).filter(BacktestRun.id == uuid.UUID(backtest_id)).first()
            if backtest:
                backtest.status = "failed"
                backtest.error_message = error_msg[:2000]
                backtest.updated_at = datetime.utcnow()
                db.commit()
        except Exception:
            pass


# ---- Endpoints ----

@router.get("/", response_model=List[BacktestListResponse], summary="List backtests")
def list_backtests(
    strategy_id: Optional[uuid.UUID] = None,
    status_filter: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """List all backtest runs. Optionally filter by strategy or status."""
    query = db.query(BacktestRun)
    if strategy_id:
        query = query.filter(BacktestRun.strategy_id == strategy_id)
    if status_filter:
        query = query.filter(BacktestRun.status == status_filter)
    return query.order_by(BacktestRun.created_at.desc()).all()


@router.post("/", response_model=BacktestResponse, status_code=status.HTTP_202_ACCEPTED, summary="Create and run backtest")
def create_backtest(
    payload: BacktestCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Create a backtest run and execute it asynchronously.
    Returns immediately with status 'pending'. Poll GET /api/backtests/{id} for results.
    """
    # Validate strategy exists
    strategy = db.query(Strategy).filter(Strategy.id == payload.strategy_id).first()
    if not strategy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Strategy {payload.strategy_id} not found.",
        )

    if payload.start_date >= payload.end_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="start_date must be before end_date.",
        )

    backtest = BacktestRun(
        strategy_id=payload.strategy_id,
        name=payload.name,
        status="pending",
        start_date=payload.start_date,
        end_date=payload.end_date,
        initial_capital=payload.initial_capital,
        commission_rate=payload.commission_rate,
        symbols=payload.symbols,
        market=payload.market,
    )
    db.add(backtest)
    db.commit()
    db.refresh(backtest)

    # Try to dispatch via Celery if available, otherwise use BackgroundTasks
    try:
        from app.workers.tasks import run_backtest
        run_backtest.delay(str(backtest.id))
    except Exception:
        # Celery not available, fall back to FastAPI background task
        background_tasks.add_task(_run_backtest_task, str(backtest.id), db)

    return backtest


@router.get("/{backtest_id}", response_model=BacktestResponse, summary="Get backtest result")
def get_backtest(backtest_id: uuid.UUID, db: Session = Depends(get_db)):
    """Get a backtest run by ID, including results when completed."""
    backtest = db.query(BacktestRun).filter(BacktestRun.id == backtest_id).first()
    if not backtest:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backtest not found.")
    return backtest


@router.get("/{backtest_id}/equity-curve", summary="Get equity curve data")
def get_equity_curve(backtest_id: uuid.UUID, db: Session = Depends(get_db)):
    """Get the daily equity curve for a completed backtest."""
    backtest = db.query(BacktestRun).filter(BacktestRun.id == backtest_id).first()
    if not backtest:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backtest not found.")
    if backtest.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Backtest is not completed (status: {backtest.status}).",
        )
    return {
        "backtest_id": str(backtest_id),
        "name": backtest.name,
        "initial_capital": backtest.initial_capital,
        "equity_curve": backtest.equity_curve or [],
    }


@router.get("/{backtest_id}/trades", summary="Get trades list")
def get_trades(
    backtest_id: uuid.UUID,
    symbol: Optional[str] = None,
    side: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Get list of all trades executed in a backtest."""
    backtest = db.query(BacktestRun).filter(BacktestRun.id == backtest_id).first()
    if not backtest:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backtest not found.")
    if backtest.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Backtest is not completed (status: {backtest.status}).",
        )

    trades = backtest.trades or []

    if symbol:
        trades = [t for t in trades if t.get("symbol") == symbol]
    if side:
        trades = [t for t in trades if t.get("side") == side]

    return {
        "backtest_id": str(backtest_id),
        "total_trades": len(trades),
        "trades": trades,
    }


@router.delete("/{backtest_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete backtest")
def delete_backtest(backtest_id: uuid.UUID, db: Session = Depends(get_db)):
    """Delete a backtest run."""
    backtest = db.query(BacktestRun).filter(BacktestRun.id == backtest_id).first()
    if not backtest:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backtest not found.")
    db.delete(backtest)
    db.commit()
    return None
