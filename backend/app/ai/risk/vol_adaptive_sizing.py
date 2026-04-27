"""C3: Volatility-adaptive position sizing.

Replaces fixed risk-per-trade with ATR-based dynamic sizing:
    risk_pct = base_risk × (target_vol / current_ATR_pct)

This normalises position size so each trade risks the same *volatility-adjusted*
amount regardless of how choppy the market is.
"""

from dataclasses import dataclass
from typing import Sequence

from app.core.logging import get_logger

logger = get_logger(__name__)

# Default target daily volatility expressed as a percentage of price
DEFAULT_TARGET_VOL_PCT = 1.5
# Floor / cap on the resulting risk percentage
MIN_RISK_PCT = 0.25
MAX_RISK_PCT = 3.0


@dataclass
class VolAdaptiveSizeResult:
    """Result of a volatility-adaptive position sizing calculation."""

    base_risk_pct: float
    current_atr_pct: float
    target_vol_pct: float
    adjusted_risk_pct: float
    scale_factor: float


def compute_atr(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], period: int = 14) -> float:
    """Compute Average True Range as a percentage of the last close.

    Args:
        highs:  Sequence of high prices (most-recent last).
        lows:   Sequence of low prices (most-recent last).
        closes: Sequence of close prices (most-recent last).
        period: ATR look-back period (default 14).

    Returns:
        ATR expressed as a percentage of the last close price.

    Raises:
        ValueError: If there are fewer than ``period + 1`` data points.
    """
    n = len(closes)
    if n < period + 1:
        raise ValueError(f"Need at least {period + 1} candles, got {n}")

    true_ranges: list[float] = []
    for i in range(1, n):
        hl = highs[i] - lows[i]
        hc = abs(highs[i] - closes[i - 1])
        lc = abs(lows[i] - closes[i - 1])
        true_ranges.append(max(hl, hc, lc))

    atr = sum(true_ranges[-period:]) / period
    last_close = closes[-1]
    if last_close <= 0:
        raise ValueError("Last close price must be positive")

    return (atr / last_close) * 100.0


def vol_adaptive_risk_pct(
    base_risk_pct: float,
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    target_vol_pct: float = DEFAULT_TARGET_VOL_PCT,
    atr_period: int = 14,
) -> VolAdaptiveSizeResult:
    """Calculate a volatility-adjusted risk percentage.

    Formula::

        adjusted_risk = base_risk × (target_vol / current_ATR_pct)

    The result is clamped to [MIN_RISK_PCT, MAX_RISK_PCT].

    Args:
        base_risk_pct: Nominal risk per trade as a percentage (e.g. 1.5).
        highs:         Recent candle highs (most-recent last).
        lows:          Recent candle lows (most-recent last).
        closes:        Recent candle closes (most-recent last).
        target_vol_pct: Target daily volatility percentage (default 1.5).
        atr_period:    ATR calculation period (default 14).

    Returns:
        :class:`VolAdaptiveSizeResult` containing the raw and adjusted values.
    """
    current_atr_pct = compute_atr(highs, lows, closes, period=atr_period)
    scale = target_vol_pct / current_atr_pct if current_atr_pct > 0 else 1.0
    adjusted = base_risk_pct * scale
    clamped = max(MIN_RISK_PCT, min(MAX_RISK_PCT, adjusted))

    result = VolAdaptiveSizeResult(
        base_risk_pct=base_risk_pct,
        current_atr_pct=round(current_atr_pct, 4),
        target_vol_pct=target_vol_pct,
        adjusted_risk_pct=round(clamped, 4),
        scale_factor=round(scale, 4),
    )
    logger.debug(
        "VolAdaptiveSizing: base=%.2f%% ATR=%.2f%% target=%.2f%% → adjusted=%.2f%% (scale=%.2f)",
        base_risk_pct,
        current_atr_pct,
        target_vol_pct,
        clamped,
        scale,
    )
    return result
