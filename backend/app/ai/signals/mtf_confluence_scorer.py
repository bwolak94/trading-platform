"""Multi-Timeframe Confluence Scorer — scores signal agreement across M15, H1, H4, D1.

Only signals with high confluence (score > 70) across multiple timeframes
should be considered high-probability entries. Lower confluence = lower
conviction, smaller position size or skip entirely.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

_CACHE: dict[str, dict[str, Any]] = {}
_CACHE_TTL = 300  # 5 minutes

_TIMEFRAMES = {
    "M15": "15m",
    "H1": "1h",
    "H4": "4h",
    "D1": "1d",
}


async def get_mtf_confluence_score(symbol: str) -> dict[str, Any]:
    """Compute multi-timeframe confluence score for a symbol.

    Args:
        symbol: Binance trading pair (e.g. BTCUSDT)

    Returns:
        {symbol, score, direction, tf_analysis, recommendation}
    """
    now = time.time()
    cached = _CACHE.get(symbol)
    if cached and now - cached["_ts"] < _CACHE_TTL:
        return {k: v for k, v in cached.items() if k != "_ts"}

    tasks = {label: _analyze_timeframe(symbol, interval) for label, interval in _TIMEFRAMES.items()}
    tf_results = await asyncio.gather(*tasks.values(), return_exceptions=True)

    tf_analysis: dict[str, Any] = {}
    directions: list[int] = []  # +1 long, -1 short, 0 neutral

    for label, result in zip(tasks.keys(), tf_results):
        if isinstance(result, Exception) or result is None:
            tf_analysis[label] = {"direction": "UNKNOWN", "error": str(result)}
            continue
        tf_analysis[label] = result
        dir_val = 1 if result["direction"] == "LONG" else (-1 if result["direction"] == "SHORT" else 0)
        directions.append(dir_val)

    if not directions:
        return {"symbol": symbol, "score": 0, "direction": "NEUTRAL", "tf_analysis": tf_analysis}

    long_count = directions.count(1)
    short_count = directions.count(-1)
    total = len(directions)

    if long_count > short_count:
        direction = "LONG"
        score = round((long_count / total) * 100)
    elif short_count > long_count:
        direction = "SHORT"
        score = round((short_count / total) * 100)
    else:
        direction = "NEUTRAL"
        score = 0

    recommendation = _build_recommendation(score, direction)

    result_data: dict[str, Any] = {
        "symbol": symbol,
        "score": score,
        "direction": direction,
        "tf_analysis": tf_analysis,
        "recommendation": recommendation,
        "timestamp": int(now * 1000),
    }
    _CACHE[symbol] = {**result_data, "_ts": now}
    return result_data


async def _analyze_timeframe(symbol: str, interval: str) -> dict[str, Any]:
    """Analyze a single timeframe for trend direction.

    Args:
        symbol: Trading pair symbol
        interval: Kline interval string

    Returns:
        {interval, direction, ema20, current_price, rsi}
    """
    from app.data.fetchers.binance_fetcher import BinanceFetcher

    fetcher = BinanceFetcher(symbol=symbol, interval=interval)
    candles = await fetcher.fetch_historical_ohlcv(limit=50)
    if not candles or len(candles) < 22:
        return {"interval": interval, "direction": "NEUTRAL", "error": "Insufficient data"}

    closes = [float(c["close"]) for c in candles]
    current = closes[-1]

    # EMA 20
    k = 2 / 21
    ema = sum(closes[:20]) / 20
    for v in closes[20:]:
        ema = v * k + ema * (1 - k)

    # RSI 14
    rsi = _rsi(closes[-16:], 14)

    if current > ema and rsi > 50:
        direction = "LONG"
    elif current < ema and rsi < 50:
        direction = "SHORT"
    else:
        direction = "NEUTRAL"

    return {
        "interval": interval,
        "direction": direction,
        "ema20": round(ema, 4),
        "current_price": round(current, 4),
        "rsi": round(rsi, 2),
        "price_vs_ema_pct": round((current - ema) / ema * 100, 3),
    }


def _rsi(closes: list[float], period: int = 14) -> float:
    """Compute RSI from close prices.

    Args:
        closes: List of closing prices
        period: RSI period

    Returns:
        RSI value [0, 100]
    """
    if len(closes) <= period:
        return 50.0
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = sum(max(d, 0) for d in deltas[-period:]) / period
    losses = sum(-min(d, 0) for d in deltas[-period:]) / period
    rs = gains / losses if losses > 0 else 100.0
    return 100.0 - 100.0 / (1 + rs)


def _build_recommendation(score: int, direction: str) -> str:
    """Generate a human-readable recommendation string.

    Args:
        score: Confluence score 0-100
        direction: LONG, SHORT, or NEUTRAL

    Returns:
        Recommendation string
    """
    if score >= 100:
        return f"STRONG {direction} — all timeframes aligned. Highest conviction entry."
    if score >= 75:
        return f"{direction} — 3/4 timeframes agree. Good conviction, standard sizing."
    if score >= 50:
        return f"WEAK {direction} — only 2/4 timeframes agree. Reduce position size."
    return "NEUTRAL — no clear confluence. Wait for alignment before entering."
