import uuid
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.strategy import Strategy
from app.services.strategy_library import STRATEGY_PARAMETER_SCHEMAS

router = APIRouter()


# ---- Pydantic Schemas ----

class StrategyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    strategy_type: str = Field(..., description="sma_crossover, rsi_mean_reversion, bollinger_band, momentum, dual_momentum, pairs_trading, macd, breakout, factor_model, custom")
    parameters: Optional[dict] = Field(default_factory=dict)
    market: str = Field(default="KOSPI", description="KOSPI, KOSDAQ, US, ALL")


class StrategyUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    strategy_type: Optional[str] = None
    parameters: Optional[dict] = None
    market: Optional[str] = None


class StrategyResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str]
    strategy_type: str
    parameters: Optional[dict]
    market: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ---- Endpoints ----

@router.get("/types", summary="List available strategy types with parameter schemas")
def list_strategy_types():
    """Returns all built-in strategy types with their parameter definitions."""
    return {
        "strategy_types": [
            {
                "type": strategy_type,
                "description": schema["description"],
                "parameters": schema["parameters"],
            }
            for strategy_type, schema in STRATEGY_PARAMETER_SCHEMAS.items()
        ]
    }


@router.get("/", response_model=List[StrategyResponse], summary="List all strategies")
def list_strategies(
    market: Optional[str] = None,
    strategy_type: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """List all saved strategies. Optionally filter by market or strategy_type."""
    query = db.query(Strategy)
    if market:
        query = query.filter(Strategy.market == market)
    if strategy_type:
        query = query.filter(Strategy.strategy_type == strategy_type)
    return query.order_by(Strategy.created_at.desc()).all()


@router.post("/", response_model=StrategyResponse, status_code=status.HTTP_201_CREATED, summary="Create a strategy")
def create_strategy(payload: StrategyCreate, db: Session = Depends(get_db)):
    """Create a new trading strategy."""
    existing = db.query(Strategy).filter(Strategy.name == payload.name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Strategy with name '{payload.name}' already exists.",
        )

    strategy = Strategy(
        name=payload.name,
        description=payload.description,
        strategy_type=payload.strategy_type,
        parameters=payload.parameters or {},
        market=payload.market,
    )
    db.add(strategy)
    db.commit()
    db.refresh(strategy)
    return strategy


@router.get("/{strategy_id}", response_model=StrategyResponse, summary="Get strategy detail")
def get_strategy(strategy_id: uuid.UUID, db: Session = Depends(get_db)):
    """Get a strategy by ID."""
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if not strategy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found.")
    return strategy


@router.put("/{strategy_id}", response_model=StrategyResponse, summary="Update a strategy")
def update_strategy(
    strategy_id: uuid.UUID,
    payload: StrategyUpdate,
    db: Session = Depends(get_db),
):
    """Update an existing strategy."""
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if not strategy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found.")

    if payload.name is not None:
        # Check for name collision
        existing = (
            db.query(Strategy)
            .filter(Strategy.name == payload.name, Strategy.id != strategy_id)
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Strategy with name '{payload.name}' already exists.",
            )
        strategy.name = payload.name

    if payload.description is not None:
        strategy.description = payload.description
    if payload.strategy_type is not None:
        strategy.strategy_type = payload.strategy_type
    if payload.parameters is not None:
        strategy.parameters = payload.parameters
    if payload.market is not None:
        strategy.market = payload.market

    strategy.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(strategy)
    return strategy


@router.delete("/{strategy_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a strategy")
def delete_strategy(strategy_id: uuid.UUID, db: Session = Depends(get_db)):
    """Delete a strategy by ID."""
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if not strategy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found.")
    db.delete(strategy)
    db.commit()
    return None
