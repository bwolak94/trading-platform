"""Backtesting endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db

router = APIRouter(prefix="/backtest", tags=["backtest"])


class BacktestRunRequest(BaseModel):
    """Request body for running a backtest."""

    strategy: str
    asset: str
    timeframe: str
    from_date: str
    to_date: str
    initial_capital: float = 10000.0
    risk_per_trade_pct: float = 1.5


@router.post("/run")
async def run_backtest(
    request: BacktestRunRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Start a new backtest run."""
    # TODO: Dispatch to Celery worker
    return {"status": "queued", "id": None}


@router.get("/results")
async def list_results(
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List all backtest results."""
    return {"data": []}


@router.get("/results/{result_id}")
async def get_result(
    result_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get backtest result details by ID."""
    return {"data": None}
