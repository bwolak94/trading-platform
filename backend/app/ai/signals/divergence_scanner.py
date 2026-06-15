"""Divergence Scanner — detects RSI and MACD divergences.

Supports:
- Regular Bullish Divergence: price lower low, RSI higher low → potential reversal UP
- Regular Bearish Divergence: price higher high, RSI lower high → potential reversal DOWN
- Hidden Bullish: price higher low, RSI lower low → continuation UP
- Hidden Bearish: price lower high, RSI higher high → continuation DOWN
"""

from __future__ import annotations

from typing import Any, Literal

from app.core.logging import get_logger

logger = get_logger(__name__)

DivergenceType = Literal[
    "regular_bullish", "regular_bearish", "hidden_bullish", "hidden_bearish"
]


def scan_divergences(
    closes: list[float],
    rsi_values: list[float],
    lookback: int = 30,
) -> list[dict[str, Any]]:
    """Scan for RSI divergences in the last `lookback` candles.

    Args:
        closes: List of close prices (most recent last)
        rsi_values: Corresponding RSI values
        lookback: Number of candles to scan

    Returns:
        List of detected divergences with type, strength, and bar indices
    """
    if len(closes) < lookback + 5 or len(rsi_values) < lookback + 5:
        return []

    closes = closes[-lookback:]
    rsi_values = rsi_values[-lookback:]

    divergences: list[dict[str, Any]] = []

    # Find local swing highs and lows (simple: higher/lower than 2 bars each side)
    def is_swing_high(i: int, vals: list[float], n: int = 2) -> bool:
        return all(vals[i] > vals[i - j] and vals[i] > vals[i + j] for j in range(1, n + 1))

    def is_swing_low(i: int, vals: list[float], n: int = 2) -> bool:
        return all(vals[i] < vals[i - j] and vals[i] < vals[i + j] for j in range(1, n + 1))

    n = len(closes)
    swing_highs = [i for i in range(2, n - 2) if is_swing_high(i, closes)]
    swing_lows = [i for i in range(2, n - 2) if is_swing_low(i, closes)]

    # Check divergences at last swing
    # Regular Bearish: price higher high, RSI lower high
    if len(swing_highs) >= 2:
        i2, i1 = swing_highs[-1], swing_highs[-2]
        if closes[i2] > closes[i1] and rsi_values[i2] < rsi_values[i1]:
            strength = abs(rsi_values[i1] - rsi_values[i2]) / rsi_values[i1]
            divergences.append({
                "type": "regular_bearish",
                "bar_left": i1,
                "bar_right": i2,
                "price_left": closes[i1],
                "price_right": closes[i2],
                "rsi_left": round(rsi_values[i1], 2),
                "rsi_right": round(rsi_values[i2], 2),
                "strength": round(strength, 3),
                "direction": "SHORT",
                "description": f"Regular bearish divergence: price higher high, RSI lower high (strength {strength:.1%})",
            })

    # Regular Bullish: price lower low, RSI higher low
    if len(swing_lows) >= 2:
        i2, i1 = swing_lows[-1], swing_lows[-2]
        if closes[i2] < closes[i1] and rsi_values[i2] > rsi_values[i1]:
            strength = abs(rsi_values[i2] - rsi_values[i1]) / rsi_values[i1]
            divergences.append({
                "type": "regular_bullish",
                "bar_left": i1,
                "bar_right": i2,
                "price_left": closes[i1],
                "price_right": closes[i2],
                "rsi_left": round(rsi_values[i1], 2),
                "rsi_right": round(rsi_values[i2], 2),
                "strength": round(strength, 3),
                "direction": "LONG",
                "description": f"Regular bullish divergence: price lower low, RSI higher low (strength {strength:.1%})",
            })

    # Hidden Bullish: price higher low (uptrend), RSI lower low → continuation
    if len(swing_lows) >= 2:
        i2, i1 = swing_lows[-1], swing_lows[-2]
        if closes[i2] > closes[i1] and rsi_values[i2] < rsi_values[i1]:
            strength = abs(rsi_values[i1] - rsi_values[i2]) / rsi_values[i1]
            divergences.append({
                "type": "hidden_bullish",
                "bar_left": i1,
                "bar_right": i2,
                "price_left": closes[i1],
                "price_right": closes[i2],
                "rsi_left": round(rsi_values[i1], 2),
                "rsi_right": round(rsi_values[i2], 2),
                "strength": round(strength, 3),
                "direction": "LONG",
                "description": "Hidden bullish divergence: price higher low, RSI lower low — uptrend continuation",
            })

    # Hidden Bearish: price lower high (downtrend), RSI higher high → continuation
    if len(swing_highs) >= 2:
        i2, i1 = swing_highs[-1], swing_highs[-2]
        if closes[i2] < closes[i1] and rsi_values[i2] > rsi_values[i1]:
            strength = abs(rsi_values[i2] - rsi_values[i1]) / rsi_values[i1]
            divergences.append({
                "type": "hidden_bearish",
                "bar_left": i1,
                "bar_right": i2,
                "price_left": closes[i1],
                "price_right": closes[i2],
                "rsi_left": round(rsi_values[i1], 2),
                "rsi_right": round(rsi_values[i2], 2),
                "strength": round(strength, 3),
                "direction": "SHORT",
                "description": "Hidden bearish divergence: price lower high, RSI higher high — downtrend continuation",
            })

    return sorted(divergences, key=lambda d: d["strength"], reverse=True)


def calculate_rsi(closes: list[float], period: int = 14) -> list[float]:
    """Calculate RSI for entire series, returns array of same length (first period values are 50).

    Args:
        closes: List of close prices
        period: RSI period (default 14)

    Returns:
        List of RSI values, same length as input
    """
    if len(closes) <= period:
        return [50.0] * len(closes)

    rsi_values = [50.0] * period
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(d, 0) for d in deltas]
    losses = [-min(d, 0) for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        rs = avg_gain / avg_loss if avg_loss > 0 else 100
        rsi_values.append(100 - 100 / (1 + rs))

    return rsi_values
