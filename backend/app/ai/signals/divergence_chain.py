"""Divergence Chain Detector — RSI + MACD + OBV triple divergence.

Triple divergence (all three indicators diverging from price) is the
highest-probability reversal signal. Each diverging indicator adds +1
to the chain_score (max 3). Score >= 2 = actionable signal.

Bullish divergence: price makes lower low, indicator makes higher low.
Bearish divergence: price makes higher high, indicator makes lower high.
"""

from __future__ import annotations

import time
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

_CACHE: dict[str, dict[str, Any]] = {}
_CACHE_TTL = 300


async def detect_divergence_chain(symbol: str, interval: str = "1h") -> dict[str, Any]:
    """Detect RSI, MACD, and OBV divergence for the given symbol.

    Args:
        symbol: Binance trading pair (e.g. BTCUSDT)
        interval: Kline interval

    Returns:
        {symbol, interval, rsi_divergence, macd_divergence, obv_divergence, chain_score, signal}
    """
    cache_key = f"{symbol}:{interval}"
    now = time.time()
    cached = _CACHE.get(cache_key)
    if cached and now - cached["_ts"] < _CACHE_TTL:
        return {k: v for k, v in cached.items() if k != "_ts"}

    try:
        from app.data.fetchers.binance_fetcher import BinanceFetcher

        fetcher = BinanceFetcher(symbol=symbol, interval=interval)
        candles = await fetcher.fetch_historical_ohlcv(limit=100)
        if not candles or len(candles) < 35:
            return _empty_result(symbol, interval, "Insufficient data")

        closes = [float(c["close"]) for c in candles]
        volumes = [float(c["volume"]) for c in candles]

        rsi_series = _compute_rsi_series(closes, 14)
        macd_series = _compute_macd_series(closes)
        obv_series = _compute_obv(closes, volumes)

        rsi_div = _detect_divergence(closes[-30:], rsi_series[-30:])
        macd_div = _detect_divergence(closes[-30:], macd_series[-30:])
        obv_div = _detect_divergence(closes[-30:], obv_series[-30:])

        chain_score = sum(1 for d in [rsi_div, macd_div, obv_div] if d in ("BULLISH", "BEARISH"))

        # Determine dominant direction
        bullish_count = sum(1 for d in [rsi_div, macd_div, obv_div] if d == "BULLISH")
        bearish_count = sum(1 for d in [rsi_div, macd_div, obv_div] if d == "BEARISH")

        if chain_score >= 3:
            signal = "STRONG_REVERSAL"
        elif chain_score == 2:
            signal = "MODERATE_REVERSAL"
        else:
            signal = "NONE"

        result: dict[str, Any] = {
            "symbol": symbol,
            "interval": interval,
            "rsi_divergence": rsi_div,
            "macd_divergence": macd_div,
            "obv_divergence": obv_div,
            "chain_score": chain_score,
            "bullish_count": bullish_count,
            "bearish_count": bearish_count,
            "dominant_direction": "BULLISH" if bullish_count > bearish_count else ("BEARISH" if bearish_count > bullish_count else "MIXED"),
            "signal": signal,
            "timestamp": int(now * 1000),
        }
        _CACHE[cache_key] = {**result, "_ts": now}
        return result

    except Exception as exc:
        logger.warning("Divergence chain failed for %s: %s", symbol, exc)
        return _empty_result(symbol, interval, str(exc))


def _detect_divergence(prices: list[float], indicator: list[float]) -> str:
    """Detect bullish or bearish divergence between price and an indicator.

    Looks at the last two significant peaks/troughs.

    Args:
        prices: Recent close prices
        indicator: Corresponding indicator values

    Returns:
        BULLISH, BEARISH, or NONE
    """
    if len(prices) < 10 or len(indicator) < 10:
        return "NONE"

    n = min(len(prices), len(indicator))
    mid = n // 2

    price_first_half = prices[:mid]
    price_second_half = prices[mid:]
    ind_first_half = indicator[:mid]
    ind_second_half = indicator[mid:]

    price_low1 = min(price_first_half)
    price_low2 = min(price_second_half)
    price_high1 = max(price_first_half)
    price_high2 = max(price_second_half)

    ind_low1 = min(ind_first_half)
    ind_low2 = min(ind_second_half)
    ind_high1 = max(ind_first_half)
    ind_high2 = max(ind_second_half)

    # Bullish: price lower low but indicator higher low
    if price_low2 < price_low1 * 0.998 and ind_low2 > ind_low1 * 1.002:
        return "BULLISH"

    # Bearish: price higher high but indicator lower high
    if price_high2 > price_high1 * 1.002 and ind_high2 < ind_high1 * 0.998:
        return "BEARISH"

    return "NONE"


def _compute_rsi_series(closes: list[float], period: int = 14) -> list[float]:
    """Compute RSI values for the entire series.

    Args:
        closes: Close price list
        period: RSI period

    Returns:
        List of RSI values (same length as input, 50.0 for initial period)
    """
    rsi_vals = [50.0] * len(closes)
    if len(closes) <= period:
        return rsi_vals

    for i in range(period + 1, len(closes)):
        deltas = [closes[j] - closes[j - 1] for j in range(i - period, i)]
        gains = sum(max(d, 0) for d in deltas) / period
        losses = sum(-min(d, 0) for d in deltas) / period
        rs = gains / losses if losses > 0 else 100.0
        rsi_vals[i] = 100.0 - 100.0 / (1 + rs)

    return rsi_vals


def _compute_macd_series(closes: list[float], fast: int = 12, slow: int = 26) -> list[float]:
    """Compute MACD line (EMA_fast - EMA_slow) for the series.

    Args:
        closes: Close prices
        fast: Fast EMA period
        slow: Slow EMA period

    Returns:
        List of MACD values
    """
    def ema_series(data: list[float], period: int) -> list[float]:
        k = 2 / (period + 1)
        emas = [data[0]] * len(data)
        for i in range(1, len(data)):
            emas[i] = data[i] * k + emas[i - 1] * (1 - k)
        return emas

    ema_fast = ema_series(closes, fast)
    ema_slow = ema_series(closes, slow)
    return [f - s for f, s in zip(ema_fast, ema_slow)]


def _compute_obv(closes: list[float], volumes: list[float]) -> list[float]:
    """Compute On-Balance Volume series.

    Args:
        closes: Close prices
        volumes: Volume values

    Returns:
        OBV series
    """
    obv = [0.0]
    for i in range(1, len(closes)):
        if closes[i] > closes[i - 1]:
            obv.append(obv[-1] + volumes[i])
        elif closes[i] < closes[i - 1]:
            obv.append(obv[-1] - volumes[i])
        else:
            obv.append(obv[-1])
    return obv


def _empty_result(symbol: str, interval: str, error: str) -> dict[str, Any]:
    """Return empty divergence result on failure.

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
        "rsi_divergence": "NONE",
        "macd_divergence": "NONE",
        "obv_divergence": "NONE",
        "chain_score": 0,
        "signal": "NONE",
        "error": error,
        "timestamp": int(time.time() * 1000),
    }
