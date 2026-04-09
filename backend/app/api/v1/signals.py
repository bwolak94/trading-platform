"""Signal endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db

router = APIRouter(prefix="/signals", tags=["signals"])


@router.get("")
async def list_signals(
    asset: str | None = None,
    direction: str | None = None,
    status: str | None = None,
    from_date: str | None = Query(None, alias="from"),
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List signals with optional filtering."""
    # TODO: Implement in TASK-103+ with repository pattern
    return {"data": [], "meta": {"total": 0, "limit": limit, "offset": offset}}


@router.get("/active")
async def get_active_signals(
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get all currently active signals."""
    return {"data": [], "meta": {"total": 0, "limit": 50, "offset": 0}}


@router.get("/{signal_id}")
async def get_signal(
    signal_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get signal details by ID."""
    # TODO: Implement with repository pattern
    return {"data": None}
