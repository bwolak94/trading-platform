"""User settings endpoints."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db

router = APIRouter(prefix="/settings", tags=["settings"])


class SettingsUpdateRequest(BaseModel):
    """Partial update for user settings."""

    capital: float | None = None
    risk_per_trade_pct: float | None = None
    max_drawdown_pct: float | None = None
    telegram_chat_id: str | None = None
    enabled_assets: list[str] | None = None
    notifications_enabled: bool | None = None


@router.get("")
async def get_settings(
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get current user settings."""
    return {"data": None}


@router.patch("")
async def update_settings(
    request: SettingsUpdateRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Update user settings."""
    return {"data": None}


@router.post("/reset-killswitch")
async def reset_killswitch(
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Reset the drawdown kill switch and resume the system."""
    return {"status": "ok", "system_status": "ACTIVE"}
