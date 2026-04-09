"""Market data endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.market_regime import MarketRegime
from app.models.onchain_event import OnChainEvent
from app.models.sentiment_data import SentimentData
from app.schemas.signal import OnChainEventResponse, RegimeResponse, SentimentResponse

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/regime", response_model=list[RegimeResponse])
async def get_all_regimes(
    db: AsyncSession = Depends(get_db),
) -> list[RegimeResponse]:
    """Get current regime for all assets (latest per asset)."""
    # Subquery: latest regime per asset
    from sqlalchemy import func

    subq = (
        select(
            MarketRegime.asset,
            func.max(MarketRegime.started_at).label("max_started"),
        )
        .where(MarketRegime.ended_at.is_(None))
        .group_by(MarketRegime.asset)
        .subquery()
    )

    query = select(MarketRegime).join(
        subq,
        (MarketRegime.asset == subq.c.asset)
        & (MarketRegime.started_at == subq.c.max_started),
    )

    result = await db.execute(query)
    regimes = result.scalars().all()
    return [RegimeResponse.model_validate(r) for r in regimes]


@router.get("/regime/{asset}", response_model=RegimeResponse)
async def get_asset_regime(
    asset: str,
    db: AsyncSession = Depends(get_db),
) -> RegimeResponse:
    """Get current regime for a specific asset."""
    result = await db.execute(
        select(MarketRegime)
        .where(MarketRegime.asset == asset, MarketRegime.ended_at.is_(None))
        .order_by(MarketRegime.started_at.desc())
        .limit(1)
    )
    regime = result.scalar_one_or_none()
    if not regime:
        raise HTTPException(status_code=404, detail=f"No regime found for {asset}")
    return RegimeResponse.model_validate(regime)


@router.get("/sentiment", response_model=list[SentimentResponse])
async def get_sentiment(
    db: AsyncSession = Depends(get_db),
) -> list[SentimentResponse]:
    """Get latest sentiment scores (most recent per asset)."""
    from sqlalchemy import func

    subq = (
        select(
            SentimentData.asset,
            func.max(SentimentData.created_at).label("max_created"),
        )
        .group_by(SentimentData.asset)
        .subquery()
    )

    query = select(SentimentData).join(
        subq,
        (SentimentData.asset == subq.c.asset)
        & (SentimentData.created_at == subq.c.max_created),
    )

    result = await db.execute(query)
    rows = result.scalars().all()
    return [SentimentResponse.model_validate(r) for r in rows]


@router.get("/onchain", response_model=list[OnChainEventResponse])
async def get_onchain_events(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
) -> list[OnChainEventResponse]:
    """Get recent on-chain events."""
    result = await db.execute(
        select(OnChainEvent)
        .order_by(OnChainEvent.timestamp.desc())
        .limit(limit)
    )
    events = result.scalars().all()
    return [OnChainEventResponse.model_validate(e) for e in events]


@router.get("/calendar")
async def get_macro_calendar() -> dict:
    """Get upcoming macro economic events.

    Placeholder — requires external calendar API integration.
    """
    return {"data": []}
