"""Backtesting endpoints."""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.backtest_result import BacktestResult
from app.schemas.signal import BacktestResultResponse

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
    """Start a new backtest run via Celery."""
    from app.tasks import celery_app

    task = celery_app.send_task(
        "app.tasks.run_backtest_task",
        kwargs={
            "strategy_name": request.strategy,
            "asset": request.asset,
            "timeframe": request.timeframe,
            "from_date": request.from_date,
            "to_date": request.to_date,
            "initial_capital": request.initial_capital,
            "risk_per_trade_pct": request.risk_per_trade_pct,
        },
    )
    return {"status": "queued", "task_id": task.id}


@router.get("/results", response_model=list[BacktestResultResponse])
async def list_results(
    db: AsyncSession = Depends(get_db),
) -> list[BacktestResultResponse]:
    """List all backtest results."""
    result = await db.execute(
        select(BacktestResult).order_by(BacktestResult.created_at.desc()).limit(50)
    )
    rows = result.scalars().all()
    return [BacktestResultResponse.model_validate(r) for r in rows]


@router.get("/results/{result_id}", response_model=BacktestResultResponse)
async def get_result(
    result_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> BacktestResultResponse:
    """Get backtest result details by ID."""
    result = await db.execute(
        select(BacktestResult).where(BacktestResult.id == result_id)
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Backtest result not found")
    return BacktestResultResponse.model_validate(row)
