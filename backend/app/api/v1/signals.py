"""Signal endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.signal import Signal
from app.schemas.signal import SignalListResponse, SignalResponse

router = APIRouter(prefix="/signals", tags=["signals"])


@router.get("", response_model=SignalListResponse)
async def list_signals(
    asset: str | None = None,
    direction: str | None = None,
    status: str | None = None,
    from_date: str | None = Query(None, alias="from"),
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
) -> SignalListResponse:
    """List signals with optional filtering."""
    query = select(Signal).order_by(Signal.created_at.desc())
    count_query = select(func.count(Signal.id))

    if asset:
        query = query.where(Signal.asset == asset)
        count_query = count_query.where(Signal.asset == asset)
    if direction:
        query = query.where(Signal.direction == direction)
        count_query = count_query.where(Signal.direction == direction)
    if status:
        query = query.where(Signal.status == status)
        count_query = count_query.where(Signal.status == status)
    if from_date:
        query = query.where(Signal.created_at >= from_date)
        count_query = count_query.where(Signal.created_at >= from_date)

    total = (await db.execute(count_query)).scalar() or 0
    result = await db.execute(query.offset(offset).limit(limit))
    signals = result.scalars().all()

    return SignalListResponse(
        data=[SignalResponse.model_validate(s) for s in signals],
        meta={"total": total, "limit": limit, "offset": offset},
    )


@router.get("/active", response_model=SignalListResponse)
async def get_active_signals(
    db: AsyncSession = Depends(get_db),
) -> SignalListResponse:
    """Get all currently active signals."""
    query = (
        select(Signal)
        .where(Signal.status == "ACTIVE")
        .order_by(Signal.confidence.desc())
    )
    result = await db.execute(query)
    signals = result.scalars().all()

    return SignalListResponse(
        data=[SignalResponse.model_validate(s) for s in signals],
        meta={"total": len(signals), "limit": 50, "offset": 0},
    )


@router.get("/{signal_id}", response_model=SignalResponse)
async def get_signal(
    signal_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> SignalResponse:
    """Get signal details by ID."""
    result = await db.execute(select(Signal).where(Signal.id == signal_id))
    signal = result.scalar_one_or_none()
    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found")
    return SignalResponse.model_validate(signal)
