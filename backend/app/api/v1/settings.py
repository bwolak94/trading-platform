"""User settings endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.user_settings import UserSettings
from app.schemas.market import SettingsUpdateRequest
from app.schemas.signal import UserSettingsResponse

router = APIRouter(prefix="/settings", tags=["settings"])

# Default user ID for single-user MVP
DEFAULT_USER_ID = "default"


@router.get("", response_model=UserSettingsResponse)
async def get_settings(
    db: AsyncSession = Depends(get_db),
) -> UserSettingsResponse:
    """Get current user settings."""
    user_settings = await _get_or_create_settings(db)
    return UserSettingsResponse.model_validate(user_settings)


@router.patch("", response_model=UserSettingsResponse)
async def update_settings(
    request: SettingsUpdateRequest,
    db: AsyncSession = Depends(get_db),
) -> UserSettingsResponse:
    """Update user settings (partial update)."""
    user_settings = await _get_or_create_settings(db)

    update_data = request.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(user_settings, field, value)

    await db.commit()
    await db.refresh(user_settings)
    return UserSettingsResponse.model_validate(user_settings)


@router.post("/reset-killswitch", response_model=UserSettingsResponse)
async def reset_killswitch(
    db: AsyncSession = Depends(get_db),
) -> UserSettingsResponse:
    """Reset the drawdown kill switch and resume the system."""
    user_settings = await _get_or_create_settings(db)

    if user_settings.system_status != "PAUSED":
        raise HTTPException(status_code=400, detail="System is not paused")

    user_settings.system_status = "ACTIVE"
    await db.commit()
    await db.refresh(user_settings)
    return UserSettingsResponse.model_validate(user_settings)


async def _get_or_create_settings(db: AsyncSession) -> UserSettings:
    """Get user settings, creating default if not found."""
    result = await db.execute(
        select(UserSettings).where(UserSettings.user_id == DEFAULT_USER_ID)
    )
    settings = result.scalar_one_or_none()

    if not settings:
        settings = UserSettings(user_id=DEFAULT_USER_ID)
        db.add(settings)
        await db.commit()
        await db.refresh(settings)

    return settings
