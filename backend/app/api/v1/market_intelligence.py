"""Market Intelligence API — funding, OI, exchange flow, dominance, and more."""

from datetime import datetime, timezone
from typing import Any

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


# Threshold above which funding is flagged as an opportunity
_FUNDING_OPPORTUNITY_THRESHOLD = 0.0001  # 0.01% per 8h

# Default watched symbols for the funding scan
_FUNDING_SCAN_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "AVAXUSDT", "ADAUSDT", "DOGEUSDT", "LINKUSDT", "MATICUSDT",
    "DOTUSDT", "LTCUSDT",
]


def _classify_signal_strength(funding_rate: float) -> str:
    """Classify funding-rate signal strength by absolute magnitude."""
    abs_fr = abs(funding_rate)
    if abs_fr >= 0.05:
        return "EXTREME"
    elif abs_fr >= 0.02:
        return "HIGH"
    return "MODERATE"


@router.get("/funding-arbitrage")
async def get_funding_arbitrage_opportunities() -> dict[str, Any]:
    """Scan for funding rate arbitrage opportunities.

    Fetches current funding rates for all watched symbols from the existing
    funding-regime module and flags symbols where abs(funding_rate) > 0.01%
    (0.0001) as potential opportunities.

    Positive funding = longs pay shorts → SHORT side receives funding.
    Negative funding = shorts pay longs → LONG side receives funding.

    Returns:
        {
            "opportunities": [
                {
                    "symbol": str,
                    "funding_rate": float,
                    "annualized_rate": float,
                    "direction": "LONG" | "SHORT",
                    "8h_payment": float,
                    "signal_strength": "EXTREME" | "HIGH" | "MODERATE"
                }
            ],
            "scan_time": str,
            "total_scanned": int,
        }
    """
    opportunities: list[dict[str, Any]] = []

    try:
        from app.ai.market.funding_regime import get_funding_regime

        regime_data = await get_funding_regime(symbols=_FUNDING_SCAN_SYMBOLS)
        rates: dict[str, float] = regime_data.get("funding_rates", {})
    except Exception:
        rates = {}

    for symbol in _FUNDING_SCAN_SYMBOLS:
        funding_rate = float(rates.get(symbol, 0.0))
        if abs(funding_rate) < _FUNDING_OPPORTUNITY_THRESHOLD:
            continue

        # Annualised = per-8h rate × 3 × 365 × 100 (expressed as %)
        annualized_rate = round(funding_rate * 3 * 365 * 100, 4)

        # The direction that RECEIVES funding payment
        # Positive funding → longs pay → SHORT receives
        # Negative funding → shorts pay → LONG receives
        direction = "SHORT" if funding_rate > 0 else "LONG"

        # Estimated 8h payment per $10 000 notional
        payment_8h = round(abs(funding_rate) * 10_000, 4)

        opportunities.append({
            "symbol": symbol,
            "funding_rate": round(funding_rate, 6),
            "annualized_rate": annualized_rate,
            "direction": direction,
            "8h_payment": payment_8h,
            "signal_strength": _classify_signal_strength(funding_rate),
        })

    # Sort by absolute funding rate descending
    opportunities.sort(key=lambda x: abs(x["funding_rate"]), reverse=True)

    return {
        "opportunities": opportunities,
        "scan_time": datetime.now(timezone.utc).isoformat(),
        "total_scanned": len(_FUNDING_SCAN_SYMBOLS),
        "threshold": _FUNDING_OPPORTUNITY_THRESHOLD,
    }
