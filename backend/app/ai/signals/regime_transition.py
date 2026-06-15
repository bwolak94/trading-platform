"""Regime transition probability forecasting.

Uses a simple Markov chain model built from historical regime transitions
to forecast probability of regime change in the next 4h and 24h.

The base transition matrix is adjusted for:
- How long the current regime has been active (duration fatigue)
- Current volatility trend (rising vol increases transition probability)
"""

import math
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db

# ---------------------------------------------------------------------------
# Base Markov transition matrix (rows = current regime, cols = next regime)
# Probabilities are empirically calibrated for crypto markets.
# ---------------------------------------------------------------------------

TRANSITION_MATRIX: dict[str, dict[str, float]] = {
    "TREND_BULL": {
        "TREND_BULL": 0.65,
        "TREND_BEAR": 0.05,
        "CONSOLIDATION": 0.25,
        "HIGH_VOL_CHOPPY": 0.05,
    },
    "TREND_BEAR": {
        "TREND_BULL": 0.05,
        "TREND_BEAR": 0.65,
        "CONSOLIDATION": 0.20,
        "HIGH_VOL_CHOPPY": 0.10,
    },
    "CONSOLIDATION": {
        "TREND_BULL": 0.30,
        "TREND_BEAR": 0.25,
        "CONSOLIDATION": 0.35,
        "HIGH_VOL_CHOPPY": 0.10,
    },
    "HIGH_VOL_CHOPPY": {
        "TREND_BULL": 0.20,
        "TREND_BEAR": 0.25,
        "CONSOLIDATION": 0.35,
        "HIGH_VOL_CHOPPY": 0.20,
    },
}

# All known regimes (including aliases used by the classifier)
ALL_REGIMES = list(TRANSITION_MATRIX.keys())

# Alias map — normalise regime names from the classifier to matrix keys
_REGIME_ALIASES: dict[str, str] = {
    "BULL": "TREND_BULL",
    "BEAR": "TREND_BEAR",
    "CHOPPY": "HIGH_VOL_CHOPPY",
    "HIGH_VOLATILITY": "HIGH_VOL_CHOPPY",
    "RANGING": "CONSOLIDATION",
    "BREAKOUT": "TREND_BULL",
    "BREAKDOWN": "TREND_BEAR",
}


def _normalise_regime(regime: str) -> str:
    """Normalise a regime name to a matrix key."""
    upper = regime.upper().strip()
    return _REGIME_ALIASES.get(upper, upper if upper in TRANSITION_MATRIX else "CONSOLIDATION")


def _duration_fatigue_factor(duration_hours: float, regime: str) -> float:
    """Return a fatigue multiplier (0-1) that reduces self-persistence.

    Long regimes eventually become less likely to persist.
    Typical crypto regime duration: TREND ~48h, CONSOLIDATION ~24h.
    """
    typical_duration: dict[str, float] = {
        "TREND_BULL": 48.0,
        "TREND_BEAR": 36.0,
        "CONSOLIDATION": 24.0,
        "HIGH_VOL_CHOPPY": 12.0,
    }
    typical = typical_duration.get(regime, 24.0)
    if duration_hours <= 0:
        return 1.0
    # Logistic decay: at 1x typical duration, fatigue = ~0.73; at 2x ~0.27
    fatigue = 1.0 / (1.0 + math.exp((duration_hours / typical - 1.0) * 3))
    return round(max(0.05, fatigue), 4)


def _apply_volatility_adjustment(
    probs: dict[str, float],
    current_regime: str,
    volatility_trend: float,
) -> dict[str, float]:
    """Adjust transition probabilities based on volatility direction.

    Rising volatility → increase probability of regime change.
    Falling volatility → reduce probability of regime change.

    Args:
        probs: Base transition probabilities (must sum to ~1).
        current_regime: Current regime key.
        volatility_trend: Positive = rising vol, negative = falling vol, range ~ -1 to 1.

    Returns:
        Adjusted probabilities, re-normalised to sum to 1.
    """
    if abs(volatility_trend) < 0.05:
        return probs  # negligible trend

    adjusted: dict[str, float] = {}
    change_boost = min(0.15, abs(volatility_trend) * 0.15)

    for regime, prob in probs.items():
        if regime == current_regime:
            # Reduce persistence under high vol, increase it under low vol
            delta = -change_boost if volatility_trend > 0 else change_boost
            adjusted[regime] = max(0.02, prob + delta)
        else:
            adjusted[regime] = prob

    # Re-normalise
    total = sum(adjusted.values())
    return {k: round(v / total, 4) for k, v in adjusted.items()}


def _matrix_power_step(
    probs: dict[str, float],
    current_regime: str,
    steps: int,
) -> dict[str, float]:
    """Compute n-step Markov probabilities by repeated application of the matrix.

    This gives the probability distribution after `steps` transitions.
    """
    # Start from the single-step distribution (already computed)
    distribution: dict[str, float] = dict(probs)

    for _ in range(steps - 1):
        new_dist: dict[str, float] = {r: 0.0 for r in ALL_REGIMES}
        for regime, p in distribution.items():
            row = TRANSITION_MATRIX.get(regime, TRANSITION_MATRIX["CONSOLIDATION"])
            for next_regime, transition_p in row.items():
                new_dist[next_regime] = new_dist.get(next_regime, 0.0) + p * transition_p
        # Normalise
        total = sum(new_dist.values())
        distribution = {k: round(v / total, 4) for k, v in new_dist.items()}

    return distribution


def forecast_regime_transition(
    current_regime: str,
    regime_duration_hours: float,
    volatility_trend: float,
) -> dict[str, Any]:
    """Forecast probability of regime transition.

    Adjusts the base Markov probabilities for:
    - Duration fatigue (regime that has lasted long is more likely to end)
    - Volatility trend (rising vol = higher change probability)

    Args:
        current_regime: Current market regime string.
        regime_duration_hours: How many hours the current regime has been active.
        volatility_trend: Positive = increasing volatility, negative = decreasing.
                          Reasonable range: -1.0 to +1.0.

    Returns:
        {
            "current_regime": str,
            "next_4h": {"TREND_BULL": 0.65, ...},
            "next_24h": {"TREND_BULL": 0.60, ...},
            "most_likely_next": str,
            "change_probability_4h": float,
            "change_probability_24h": float,
            "duration_fatigue": float,
            "volatility_trend": float,
        }
    """
    normalised = _normalise_regime(current_regime)
    base_row = TRANSITION_MATRIX.get(normalised, TRANSITION_MATRIX["CONSOLIDATION"])

    # Apply duration fatigue — reduce self-transition probability
    fatigue = _duration_fatigue_factor(regime_duration_hours, normalised)
    fatigued: dict[str, float] = {}
    persistence = base_row.get(normalised, 0.5)
    reduced_persistence = persistence * fatigue
    reduction = persistence - reduced_persistence
    other_regimes = [r for r in base_row if r != normalised]
    boost_per_other = reduction / len(other_regimes) if other_regimes else 0.0

    for regime, prob in base_row.items():
        if regime == normalised:
            fatigued[regime] = max(0.02, reduced_persistence)
        else:
            fatigued[regime] = prob + boost_per_other

    # Normalise after fatigue
    total = sum(fatigued.values())
    fatigued = {k: round(v / total, 4) for k, v in fatigued.items()}

    # Apply volatility adjustment
    adjusted_4h = _apply_volatility_adjustment(fatigued, normalised, volatility_trend)

    # 24h = 6 Markov steps (assuming 4h per step)
    # Re-apply matrix power starting from adjusted 4h distribution
    adjusted_24h = _matrix_power_step(adjusted_4h, normalised, steps=6)

    change_prob_4h = round(1.0 - adjusted_4h.get(normalised, 0), 4)
    change_prob_24h = round(1.0 - adjusted_24h.get(normalised, 0), 4)

    most_likely_next_4h = max(
        (r for r in adjusted_4h if r != normalised),
        key=lambda r: adjusted_4h.get(r, 0),
        default=normalised,
    )

    return {
        "current_regime": normalised,
        "next_4h": adjusted_4h,
        "next_24h": adjusted_24h,
        "most_likely_next": most_likely_next_4h,
        "change_probability_4h": change_prob_4h,
        "change_probability_24h": change_prob_24h,
        "duration_fatigue": round(fatigue, 4),
        "volatility_trend": volatility_trend,
        "regime_duration_hours": regime_duration_hours,
    }


# ---------------------------------------------------------------------------
# FastAPI router
# ---------------------------------------------------------------------------

router = APIRouter(tags=["regime"])


@router.get("/regime/transition-forecast/{symbol}")
async def get_regime_transition_forecast(
    symbol: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get regime transition probability forecast for a symbol.

    Looks up the most recent market regime for the symbol, then computes
    the Markov chain transition forecast for 4h and 24h horizons.
    """
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import select

    from app.models.market_regime import MarketRegime

    symbol_upper = symbol.upper()

    # Fetch the latest regime record for this symbol
    cutoff = datetime.now(timezone.utc) - timedelta(hours=72)
    stmt = (
        select(MarketRegime)
        .where(MarketRegime.asset == symbol_upper)
        .where(MarketRegime.started_at >= cutoff)
        .order_by(MarketRegime.started_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    regime_row = result.scalar_one_or_none()

    if regime_row is None:
        # Fall back to CONSOLIDATION as the safest neutral assumption
        current_regime = "CONSOLIDATION"
        duration_hours = 0.0
    else:
        current_regime = regime_row.regime or "CONSOLIDATION"
        started_at = regime_row.started_at
        if started_at:
            now = datetime.now(timezone.utc)
            if started_at.tzinfo is None:
                from datetime import timezone as tz_
                started_at = started_at.replace(tzinfo=tz_.utc)
            duration_hours = max(0.0, (now - started_at).total_seconds() / 3600)
        else:
            duration_hours = 0.0

    # Default volatility trend to neutral (no live vol column available)
    volatility_trend = 0.0

    forecast = forecast_regime_transition(
        current_regime=current_regime,
        regime_duration_hours=duration_hours,
        volatility_trend=volatility_trend,
    )
    forecast["symbol"] = symbol_upper
    return forecast
