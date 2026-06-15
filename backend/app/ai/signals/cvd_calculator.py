"""CVD — Cumulative Volume Delta from OHLCV candle data.

True CVD requires tick data. We approximate using taker buy volume from Binance
if available, otherwise fall back to the close-based heuristic:
  - If close > open: buy_vol = total_vol (bullish candle)
  - If close < open: sell_vol = total_vol (bearish candle)
  - Neutral: buy_vol = sell_vol = total_vol / 2

CVD = cumulative sum of (buy_vol - sell_vol)

Rising CVD with rising price = trend confirmation
Rising price with falling CVD = bearish divergence
Falling price with rising CVD = bullish divergence
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)


def calculate_cvd_from_ohlcv(candles: list[dict[str, float]]) -> list[dict[str, Any]]:
    """Calculate Cumulative Volume Delta from OHLCV candles.

    Args:
        candles: List of dicts with keys: time, open, high, low, close, volume
                 Ordered oldest → newest

    Returns:
        List of {time, cvd, delta, buy_vol, sell_vol} dicts
    """
    cvd_series: list[dict[str, Any]] = []
    cumulative = 0.0

    for candle in candles:
        o = candle.get("open", 0)
        c = candle.get("close", 0)
        vol = candle.get("volume", 0)
        t = candle.get("time", 0)

        # Approximate buy/sell split from candle body
        body = abs(c - o)
        high_wick = candle.get("high", c) - max(c, o)
        low_wick = min(c, o) - candle.get("low", c)

        if c > o:  # Bullish candle
            # Estimate: more volume was buying
            buy_ratio = 0.6 + 0.2 * (body / (body + high_wick + 0.0001))
        elif c < o:  # Bearish candle
            buy_ratio = 0.4 - 0.2 * (body / (body + low_wick + 0.0001))
        else:  # Doji
            buy_ratio = 0.5

        buy_ratio = max(0.1, min(0.9, buy_ratio))
        buy_vol = vol * buy_ratio
        sell_vol = vol * (1 - buy_ratio)
        delta = buy_vol - sell_vol
        cumulative += delta

        cvd_series.append({
            "time": int(t),
            "cvd": round(cumulative, 2),
            "delta": round(delta, 2),
            "buy_vol": round(buy_vol, 2),
            "sell_vol": round(sell_vol, 2),
        })

    return cvd_series


def detect_cvd_divergence(
    candles: list[dict[str, float]],
    cvd_series: list[dict[str, Any]],
    lookback: int = 20,
) -> list[dict[str, Any]]:
    """Detect CVD divergences with price.

    Args:
        candles: OHLCV candles
        cvd_series: CVD series from calculate_cvd_from_ohlcv()
        lookback: Bars to look back for divergence

    Returns:
        List of detected divergences
    """
    if len(candles) < lookback or len(cvd_series) < lookback:
        return []

    closes = [c["close"] for c in candles[-lookback:]]
    cvds = [d["cvd"] for d in cvd_series[-lookback:]]
    n = len(closes)

    # Find pivot points
    def is_high(i: int, data: list[float]) -> bool:
        return i > 1 and i < n - 2 and data[i] > data[i-1] and data[i] > data[i-2] and data[i] > data[i+1] and data[i] > data[i+2]

    def is_low(i: int, data: list[float]) -> bool:
        return i > 1 and i < n - 2 and data[i] < data[i-1] and data[i] < data[i-2] and data[i] < data[i+1] and data[i] < data[i+2]

    price_highs = [i for i in range(2, n - 2) if is_high(i, closes)]
    price_lows = [i for i in range(2, n - 2) if is_low(i, closes)]
    cvd_highs = [i for i in range(2, n - 2) if is_high(i, cvds)]
    cvd_lows = [i for i in range(2, n - 2) if is_low(i, cvds)]

    divergences = []

    # Bearish: price higher high, CVD lower high
    if len(price_highs) >= 2 and len(cvd_highs) >= 2:
        ph1, ph2 = price_highs[-2], price_highs[-1]
        ch_near = [i for i in cvd_highs if abs(i - ph2) <= 3]
        if ch_near and closes[ph2] > closes[ph1] and cvds[ch_near[-1]] < cvds[ph1]:
            divergences.append({
                "type": "bearish_cvd_divergence",
                "direction": "SHORT",
                "description": "Price making higher high but CVD making lower high — bearish divergence",
            })

    # Bullish: price lower low, CVD higher low
    if len(price_lows) >= 2 and len(cvd_lows) >= 2:
        pl1, pl2 = price_lows[-2], price_lows[-1]
        cl_near = [i for i in cvd_lows if abs(i - pl2) <= 3]
        if cl_near and closes[pl2] < closes[pl1] and cvds[cl_near[-1]] > cvds[pl1]:
            divergences.append({
                "type": "bullish_cvd_divergence",
                "direction": "LONG",
                "description": "Price making lower low but CVD making higher low — bullish divergence",
            })

    return divergences
