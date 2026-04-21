"""Market Intelligence API — funding, OI, exchange flow, dominance, and more."""

from fastapi import APIRouter, Query

router = APIRouter(prefix="/market-intel", tags=["market-intelligence"])


@router.get("/funding-regime")
async def get_funding_regime(
    symbols: str = Query(default="", description="Comma-separated symbols (empty = defaults)"),
) -> dict:
    """Get funding rate regime for major crypto perpetuals."""
    from app.ai.market.funding_regime import get_funding_regime
    sym_list = [s.strip() for s in symbols.split(",") if s.strip()] or None
    return await get_funding_regime(symbols=sym_list)


@router.get("/funding-alert")
async def get_funding_alert(
    symbol: str = Query(default="BTCUSDT"),
) -> dict:
    """Get funding rate alert and recommendation for a specific symbol."""
    from app.ai.market.funding_regime import get_funding_alert
    return await get_funding_alert(symbol=symbol)


@router.get("/fear-greed-contrarian")
async def get_fear_greed_contrarian() -> dict:
    """Get Fear & Greed Index with contrarian trading signal."""
    from app.ai.market.fear_greed_signal import get_contrarian_signal
    return await get_contrarian_signal()


@router.get("/btc-dominance")
async def get_btc_dominance() -> dict:
    """Get BTC dominance regime and altcoin rotation signal."""
    from app.ai.market.btc_dominance_signal import get_dominance_signal
    return await get_dominance_signal()


@router.get("/whale-accumulation")
async def get_whale_accumulation(
    symbol: str = Query(default="BTCUSDT"),
) -> dict:
    """Detect whale accumulation or distribution patterns using taker volume."""
    from app.ai.market.whale_accumulation import get_whale_accumulation_signal
    return await get_whale_accumulation_signal(symbol=symbol)


@router.get("/sentiment-velocity")
async def get_sentiment_velocity() -> dict:
    """Get sentiment velocity (rate of change) for all tracked symbols."""
    from app.ai.market.sentiment_velocity import get_sentiment_tracker
    tracker = get_sentiment_tracker()
    return {
        "velocities": tracker.get_all_velocities(),
        "total_symbols": len(tracker._history),
    }
