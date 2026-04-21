"""Compression Detector — NR7, inside bars, and ATR compression.

Detects price action compression patterns that precede explosive breakouts:
- NR7: current candle range is the smallest of the last 7 candles
- Inside Bar: current candle is contained within the previous candle
- ATR Compression: current ATR < 50% of the 20-period ATR average

Multiple consecutive compression signals indicate a high-probability breakout setup.
"""

from __future__ import annotations

import time
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

_CACHE: dict[str, dict[str, Any]] = {}
_CACHE_TTL = 300


async def detect_compression(
    symbol: str,
    interval: str = "1h",
    lookback: int = 50,
) -> dict[str, Any]:
    """Detect compression patterns for a symbol.

    Args:
        symbol: Binance trading pair (e.g. BTCUSDT)
        interval: Kline interval
        lookback: Number of candles to analyze

    Returns:
        {symbol, is_nr7, is_inside_bar, consecutive_compressions,
         atr_compression_pct, breakout_expected, bias}
    """
    cache_key = f"{symbol}:{interval}"
    now = time.time()
    cached = _CACHE.get(cache_key)
    if cached and now - cached["_ts"] < _CACHE_TTL:
        return {k: v for k, v in cached.items() if k != "_ts"}

    try:
        from app.data.fetchers.binance_fetcher import BinanceFetcher

        fetcher = BinanceFetcher(symbol=symbol, interval=interval)
        candles = await fetcher.fetch_historical_ohlcv(limit=lookback)
        if not candles or len(candles) < 25:
            return _empty_result(symbol, interval, "Insufficient data")

        highs = [float(c["high"]) for c in candles]
        lows = [float(c["low"]) for c in candles]
        closes = [float(c["close"]) for c in candles]

        ranges = [highs[i] - lows[i] for i in range(len(candles))]

        # NR7: current range is smallest of last 7
        current_range = ranges[-1]
        last_7 = ranges[-7:]
        is_nr7 = current_range == min(last_7)

        # Inside bar: current candle within previous candle's H-L
        is_inside_bar = highs[-1] <= highs[-2] and lows[-1] >= lows[-2]

        # Count consecutive compression candles
        consecutive = 0
        for i in range(len(ranges) - 1, max(0, len(ranges) - 15) - 1, -1):
            if ranges[i] < sum(ranges[max(0, i - 7):i]) / max(1, min(7, i)):
                consecutive += 1
            else:
                break

        # ATR compression
        atr_period = 14
        atr_values = _compute_atr(highs, lows, closes, atr_period)
        if len(atr_values) >= 20:
            current_atr = atr_values[-1]
            avg_atr_20 = sum(atr_values[-20:]) / 20
            atr_compression_pct = round(
                (1 - current_atr / avg_atr_20) * 100 if avg_atr_20 > 0 else 0, 2
            )
        else:
            current_atr = atr_values[-1] if atr_values else 0.0
            avg_atr_20 = current_atr
            atr_compression_pct = 0.0

        # Determine breakout bias from trend context
        ema20 = _ema(closes, 20)
        current_price = closes[-1]
        if current_price > ema20 * 1.005:
            bias = "UP"
        elif current_price < ema20 * 0.995:
            bias = "DOWN"
        else:
            bias = "UNKNOWN"

        compression_signals = sum([is_nr7, is_inside_bar, atr_compression_pct > 30])
        breakout_expected = compression_signals >= 2 or consecutive >= 3

        result: dict[str, Any] = {
            "symbol": symbol,
            "interval": interval,
            "is_nr7": is_nr7,
            "is_inside_bar": is_inside_bar,
            "consecutive_compressions": consecutive,
            "atr_compression_pct": atr_compression_pct,
            "current_atr": round(current_atr, 6),
            "avg_atr_20": round(avg_atr_20, 6),
            "compression_signals": compression_signals,
            "breakout_expected": breakout_expected,
            "bias": bias,
            "current_price": current_price,
            "ema20": round(ema20, 4),
            "timestamp": int(now * 1000),
        }
        _CACHE[cache_key] = {**result, "_ts": now}
        return result

    except Exception as exc:
        logger.warning("Compression detector failed for %s: %s", symbol, exc)
        return _empty_result(symbol, interval, str(exc))


def _compute_atr(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 14,
) -> list[float]:
    """Compute Average True Range series.

    Args:
        highs: Candle highs
        lows: Candle lows
        closes: Candle closes
        period: ATR period

    Returns:
        ATR values list
    """
    tr_values = [highs[0] - lows[0]]
    for i in range(1, len(highs)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        tr_values.append(tr)

    if len(tr_values) < period:
        return tr_values

    atr_values = [sum(tr_values[:period]) / period]
    for i in range(period, len(tr_values)):
        atr_values.append((atr_values[-1] * (period - 1) + tr_values[i]) / period)

    return atr_values


def _ema(data: list[float], period: int) -> float:
    """Compute single EMA value.

    Args:
        data: Price series
        period: EMA period

    Returns:
        Current EMA value
    """
    if len(data) < period:
        return data[-1] if data else 0.0
    k = 2 / (period + 1)
    ema = sum(data[:period]) / period
    for v in data[period:]:
        ema = v * k + ema * (1 - k)
    return ema


def _empty_result(symbol: str, interval: str, error: str) -> dict[str, Any]:
    """Return empty compression result.

    Args:
        symbol: Trading pair
        interval: Timeframe
        error: Error message

    Returns:
        Empty result dict
    """
    return {
        "symbol": symbol,
        "interval": interval,
        "is_nr7": False,
        "is_inside_bar": False,
        "consecutive_compressions": 0,
        "atr_compression_pct": 0.0,
        "breakout_expected": False,
        "bias": "UNKNOWN",
        "error": error,
        "timestamp": int(time.time() * 1000),
    }
