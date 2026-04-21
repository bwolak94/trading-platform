"""Liquidity Grab Detector — identifies sweep-and-reverse patterns.

A liquidity grab (also called a "stop hunt") occurs when price:
1. Sweeps ABOVE a recent swing high (triggering buy stops), then
2. Closes BACK BELOW the swing high within the same or next candle

This signals that smart money has taken liquidity and may reverse.
Inverse pattern works for bearish grabs below swing lows.
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)


def detect_liquidity_grabs(
    candles: list[dict[str, float]],
    lookback_swing: int = 20,
    min_sweep_pct: float = 0.05,
) -> list[dict[str, Any]]:
    """Detect liquidity grab patterns in a candle series.

    Args:
        candles: List of OHLCV dicts with keys: open, high, low, close, volume
                 Ordered oldest → newest
        lookback_swing: How many bars to look back for swing high/low reference
        min_sweep_pct: Minimum sweep distance as % of price to count as a grab

    Returns:
        List of detected grabs with type, level, bar_index, and description
    """
    if len(candles) < lookback_swing + 5:
        return []

    grabs: list[dict[str, Any]] = []
    n = len(candles)

    for i in range(lookback_swing, n):
        candle = candles[i]
        prev_candles = candles[i - lookback_swing : i]

        # Reference levels: swing high/low of the lookback window
        swing_high = max(c["high"] for c in prev_candles)
        swing_low = min(c["low"] for c in prev_candles)

        # --- Bullish Liquidity Grab ---
        # Wick sweeps BELOW swing low but candle CLOSES ABOVE it
        if (
            candle["low"] < swing_low
            and candle["close"] > swing_low
            and (swing_low - candle["low"]) / swing_low >= min_sweep_pct / 100
        ):
            sweep_pct = (swing_low - candle["low"]) / swing_low * 100
            grabs.append({
                "type": "bullish",
                "bar_index": i,
                "swept_level": round(swing_low, 6),
                "low_of_grab": round(candle["low"], 6),
                "close": round(candle["close"], 6),
                "sweep_pct": round(sweep_pct, 3),
                "direction": "LONG",
                "description": (
                    f"Liquidity grab below {swing_low:.4f} — "
                    f"swept {sweep_pct:.2f}% below swing low, closed back above. "
                    f"Potential LONG reversal."
                ),
            })

        # --- Bearish Liquidity Grab ---
        # Wick sweeps ABOVE swing high but candle CLOSES BELOW it
        elif (
            candle["high"] > swing_high
            and candle["close"] < swing_high
            and (candle["high"] - swing_high) / swing_high >= min_sweep_pct / 100
        ):
            sweep_pct = (candle["high"] - swing_high) / swing_high * 100
            grabs.append({
                "type": "bearish",
                "bar_index": i,
                "swept_level": round(swing_high, 6),
                "high_of_grab": round(candle["high"], 6),
                "close": round(candle["close"], 6),
                "sweep_pct": round(sweep_pct, 3),
                "direction": "SHORT",
                "description": (
                    f"Liquidity grab above {swing_high:.4f} — "
                    f"swept {sweep_pct:.2f}% above swing high, closed back below. "
                    f"Potential SHORT reversal."
                ),
            })

    # Return only the most recent grabs (last 3)
    return grabs[-3:]
