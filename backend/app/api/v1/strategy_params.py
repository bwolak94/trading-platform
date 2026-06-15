"""Strategy parameters CRUD endpoints."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.strategy_params import DEFAULT_STRATEGY_PARAMS, StrategyParams

router = APIRouter(prefix="/strategy-params", tags=["strategy-params"])


# --- Pydantic schemas ---


class StrategyParamsResponse(BaseModel):
    """Response schema for strategy parameters."""

    strategy_name: str
    params: dict[str, Any]
    description: str | None = None
    updated_at: str
    created_at: str

    model_config = {"from_attributes": True}


class StrategyParamsUpdateRequest(BaseModel):
    """Partial update for strategy parameters (merged into existing JSONB)."""

    params: dict[str, Any]


class StrategyParamsListResponse(BaseModel):
    """Response schema for listing all strategy parameters."""

    items: list[StrategyParamsResponse]


# --- Helpers ---


async def _get_or_create_strategy(
    db: AsyncSession, strategy_name: str
) -> StrategyParams:
    """Get strategy params by name, creating from defaults if not found."""
    result = await db.execute(
        select(StrategyParams).where(StrategyParams.strategy_name == strategy_name)
    )
    strategy = result.scalar_one_or_none()

    if strategy:
        return strategy

    if strategy_name not in DEFAULT_STRATEGY_PARAMS:
        raise HTTPException(
            status_code=404,
            detail=f"Strategy '{strategy_name}' not found and has no defaults",
        )

    strategy = StrategyParams(
        strategy_name=strategy_name,
        params=DEFAULT_STRATEGY_PARAMS[strategy_name],
        description=f"Default parameters for {strategy_name} strategy",
    )
    db.add(strategy)
    await db.commit()
    await db.refresh(strategy)
    return strategy


def _to_response(strategy: StrategyParams) -> StrategyParamsResponse:
    """Convert ORM model to response schema."""
    return StrategyParamsResponse(
        strategy_name=strategy.strategy_name,
        params=strategy.params,
        description=strategy.description,
        updated_at=strategy.updated_at.isoformat(),
        created_at=strategy.created_at.isoformat(),
    )


# --- Endpoints ---


@router.get("", response_model=StrategyParamsListResponse)
async def list_strategy_params(
    db: AsyncSession = Depends(get_db),
) -> StrategyParamsListResponse:
    """List all strategy parameters, creating defaults for any missing strategies."""
    # Ensure all default strategies exist in the database
    for name in DEFAULT_STRATEGY_PARAMS:
        await _get_or_create_strategy(db, name)

    result = await db.execute(
        select(StrategyParams).order_by(StrategyParams.strategy_name)
    )
    strategies = result.scalars().all()
    return StrategyParamsListResponse(
        items=[_to_response(s) for s in strategies]
    )


@router.get("/{strategy_name}", response_model=StrategyParamsResponse)
async def get_strategy_params(
    strategy_name: str,
    db: AsyncSession = Depends(get_db),
) -> StrategyParamsResponse:
    """Get parameters for a specific strategy."""
    strategy = await _get_or_create_strategy(db, strategy_name)
    return _to_response(strategy)


@router.patch("/{strategy_name}", response_model=StrategyParamsResponse)
async def update_strategy_params(
    strategy_name: str,
    request: StrategyParamsUpdateRequest,
    db: AsyncSession = Depends(get_db),
) -> StrategyParamsResponse:
    """Update strategy parameters (merges into existing JSONB)."""
    strategy = await _get_or_create_strategy(db, strategy_name)

    # Merge new params into existing params
    merged_params = {**strategy.params, **request.params}
    strategy.params = merged_params

    await db.commit()
    await db.refresh(strategy)
    return _to_response(strategy)


@router.post("/{strategy_name}/reset", response_model=StrategyParamsResponse)
async def reset_strategy_params(
    strategy_name: str,
    db: AsyncSession = Depends(get_db),
) -> StrategyParamsResponse:
    """Reset strategy parameters to their defaults."""
    if strategy_name not in DEFAULT_STRATEGY_PARAMS:
        raise HTTPException(
            status_code=404,
            detail=f"Strategy '{strategy_name}' has no default parameters",
        )

    strategy = await _get_or_create_strategy(db, strategy_name)
    strategy.params = DEFAULT_STRATEGY_PARAMS[strategy_name]

    await db.commit()
    await db.refresh(strategy)
    return _to_response(strategy)
