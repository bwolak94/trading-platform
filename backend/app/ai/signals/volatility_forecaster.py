"""Simplified volatility forecasting using EWMA (GARCH-like approach).

Implements RiskMetrics EWMA (lambda=0.94) for realized volatility estimation
and forecasting. Classifies the vol regime and generates a trading signal.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class VolatilityForecast:
    """Result of volatility forecasting."""

    current_vol_pct: float    # current realized volatility (annualized %)
    forecast_vol_pct: float   # next period forecast
    vol_regime: str           # "low" | "normal" | "high" | "extreme"
    expanding: bool           # volatility trend is expanding
    signal: str               # "risk_off" | "neutral" | "breakout_setup"


def forecast_volatility(closes: list[float], window: int = 20) -> Optional[VolatilityForecast]:
    """Compute EWMA volatility forecast and classify the volatility regime.

    Uses RiskMetrics standard EWMA with lambda=0.94 to estimate realized
    volatility, then compares short-term vs. longer-term variance to detect
    expansion. Volatility is annualized (multiplied by sqrt(252) for daily
    data; callers should adjust window/interpretation for intraday data).

    Args:
        closes: List of closing prices (oldest first), minimum window + 5 required.
        window: Rolling window length for variance comparison (default 20).

    Returns:
        VolatilityForecast dataclass or None if insufficient data.
    """
    if len(closes) < window + 5:
        return None

    # Log returns
    returns: list[float] = [
        math.log(closes[i] / closes[i - 1])
        for i in range(1, len(closes))
        if closes[i - 1] > 0 and closes[i] > 0
    ]

    if len(returns) < window:
        return None

    # EWMA variance with lambda=0.94 (RiskMetrics standard)
    lam = 0.94
    var = returns[-1] ** 2
    for r in returns[-window:]:
        var = lam * var + (1 - lam) * r ** 2

    current_vol = math.sqrt(var) * math.sqrt(252) * 100  # annualized %

    # Short-term (last 5) vs longer-term (last window) variance comparison
    short_returns = returns[-5:]
    long_returns = returns[-window:]

    short_mean = sum(short_returns) / len(short_returns)
    long_mean = sum(long_returns) / len(long_returns)

    short_var = sum((r - short_mean) ** 2 for r in short_returns) / len(short_returns)
    long_var = sum((r - long_mean) ** 2 for r in long_returns) / len(long_returns)

    expanding = short_var > long_var * 1.2

    # Regime classification (annualized vol thresholds for crypto)
    if current_vol < 30:
        regime = "low"
    elif current_vol < 60:
        regime = "normal"
    elif current_vol < 100:
        regime = "high"
    else:
        regime = "extreme"

    # Signal interpretation
    if regime in ("high", "extreme"):
        signal = "risk_off"
    elif not expanding and regime == "low":
        signal = "breakout_setup"
    else:
        signal = "neutral"

    forecast_multiplier = 1.1 if expanding else 0.95

    return VolatilityForecast(
        current_vol_pct=round(current_vol, 2),
        forecast_vol_pct=round(current_vol * forecast_multiplier, 2),
        vol_regime=regime,
        expanding=expanding,
        signal=signal,
    )
