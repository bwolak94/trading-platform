"""Market data endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/regime")
async def get_all_regimes(
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get current regime for all assets."""
    return {"data": []}


@router.get("/regime/{asset}")
async def get_asset_regime(
    asset: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get current regime for a specific asset."""
    return {"data": None}


@router.get("/sentiment")
async def get_sentiment(
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get current sentiment scores."""
    return {"data": []}


@router.get("/onchain")
async def get_onchain_events(
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get recent on-chain events."""
    return {"data": []}


@router.get("/calendar")
async def get_macro_calendar() -> dict:
    """Get upcoming macro economic events."""
    return {"data": []}
