"""Advanced Analytics API — Bayesian updates, HMM regime, volatility surface, XAI."""

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

router = APIRouter(prefix="/analytics", tags=["analytics"])


class BayesianUpdateRequest(BaseModel):
    """Request body for Bayesian signal update."""

    prior_probability: float = Field(..., ge=0.0, le=1.0)
    evidence: list[str]


class MarketImpactRequest(BaseModel):
    """Request body for market impact estimation."""

    symbol: str
    position_size_usd: float = Field(..., gt=0)
    direction: str = "LONG"


class AttributionRequest(BaseModel):
    """Request body for performance attribution."""

    trades: list[dict]


@router.post("/bayesian-update")
async def bayesian_update(body: BayesianUpdateRequest) -> dict:
    """Update signal probability using Bayesian inference with new market evidence."""
    from app.ai.analytics.bayesian_updater import get_bayesian_updater
    updater = get_bayesian_updater()
    return updater.update_probability(
        prior_probability=body.prior_probability,
        evidence_list=body.evidence,
    )


@router.get("/bayesian-evidence-types")
async def get_evidence_types() -> dict:
    """Get list of valid evidence types for Bayesian updates."""
    from app.ai.analytics.bayesian_updater import EVIDENCE_LIKELIHOOD
    return {
        "evidence_types": list(EVIDENCE_LIKELIHOOD.keys()),
        "descriptions": {k: v for k, v in EVIDENCE_LIKELIHOOD.items()},
    }


@router.get("/hmm-regime")
async def get_hmm_regime(
    symbol: str = Query(default="BTCUSDT"),
    interval: str = Query(default="1d"),
    lookback: int = Query(default=60, ge=20, le=200),
) -> dict:
    """Get HMM-based market regime with smoother transitions than rule-based classifier."""
    from app.ai.analytics.hmm_regime import get_hmm_regime
    return await get_hmm_regime(symbol=symbol, interval=interval, lookback=lookback)


@router.get("/volatility-surface")
async def get_volatility_surface(
    symbol: str = Query(default="BTCUSDT"),
) -> dict:
    """Get realized volatility surface across M15, H1, H4, D1 timeframes."""
    from app.ai.analytics.volatility_surface import compute_volatility_surface
    return await compute_volatility_surface(symbol=symbol)


@router.get("/alpha-decay")
async def get_alpha_decay() -> dict:
    """Get alpha decay health report for all tracked strategies."""
    from app.ai.analytics.alpha_decay_monitor import get_alpha_decay_monitor
    monitor = get_alpha_decay_monitor()
    return {
        "strategy_health": monitor.get_all_strategy_health(),
        "strategies_tracked": len(monitor._strategy_returns),
    }


@router.post("/market-impact")
async def estimate_market_impact(body: MarketImpactRequest) -> dict:
    """Estimate slippage and market impact for a given position size."""
    import httpx
    from app.core.logging import get_logger

    logger = get_logger(__name__)
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                "https://api.binance.com/api/v3/depth",
                params={"symbol": body.symbol, "limit": 20},
            )
            resp.raise_for_status()
            book = resp.json()

        levels = book.get("asks" if body.direction == "LONG" else "bids", [])
        remaining = body.position_size_usd
        filled = 0.0
        levels_consumed = 0
        last_price = float(levels[0][0]) if levels else 0.0

        for price_str, qty_str in levels:
            if remaining <= 0:
                break
            price = float(price_str)
            qty = float(qty_str)
            level_value = price * qty
            fill_value = min(remaining, level_value)
            filled += fill_value
            remaining -= fill_value
            levels_consumed += 1
            last_price = price

        entry_price = float(levels[0][0]) if levels else 0.0
        slippage_pct = abs(last_price - entry_price) / entry_price * 100 if entry_price > 0 else 0.0
        depth_consumed = levels_consumed / len(levels) * 100 if levels else 0.0

        if slippage_pct < 0.05:
            impact_score = "NEGLIGIBLE"
        elif slippage_pct < 0.15:
            impact_score = "LOW"
        elif slippage_pct < 0.5:
            impact_score = "MEDIUM"
        elif slippage_pct < 1.0:
            impact_score = "HIGH"
        else:
            impact_score = "EXTREME"

        return {
            "symbol": body.symbol,
            "position_size_usd": body.position_size_usd,
            "direction": body.direction,
            "entry_price": entry_price,
            "avg_fill_price": round(last_price, 6),
            "slippage_pct": round(slippage_pct, 4),
            "slippage_usd": round(body.position_size_usd * slippage_pct / 100, 2),
            "market_impact_score": impact_score,
            "depth_consumed_pct": round(depth_consumed, 2),
            "levels_consumed": levels_consumed,
            "recommendation": f"{'Acceptable' if slippage_pct < 0.3 else 'Reduce position size'} — slippage estimated at {slippage_pct:.3f}%",
        }
    except Exception as exc:
        logger.warning("Market impact estimate failed: %s", exc)
        return {"error": str(exc), "symbol": body.symbol}


@router.get("/ev-leaderboard")
async def get_ev_leaderboard() -> dict:
    """Get strategy Expected Value leaderboard."""
    from app.ai.analytics.alpha_decay_monitor import get_alpha_decay_monitor
    monitor = get_alpha_decay_monitor()
    return {
        "leaderboard": monitor.get_all_strategy_health(),
        "note": "Sorted by decay severity (most concerning first)",
    }


@router.post("/attribution")
async def get_performance_attribution(body: AttributionRequest) -> dict:
    """Break down P&L by strategy, regime, time-of-day, and holding period."""
    from app.ai.automation.performance_attribution import attribute_performance
    return attribute_performance(trades=body.trades)
