"""Multi-Asset Scanner — scans all active assets and surfaces top setups.

Runs a fast scoring algorithm across all tracked symbols to find the highest
conviction long and short setups. Results are cached for 60 seconds to
balance freshness with API rate limits.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from app.core.logging import get_logger
from app.core.symbols import get_active_crypto_symbols

logger = get_logger(__name__)

_CACHE: dict[str, Any] = {}
_CACHE_TTL = 60  # 1 minute


async def scan_all_assets(top_n: int = 5) -> dict[str, Any]:
    """Scan all active assets and return top long and short setups.

    Args:
        top_n: Number of top setups to return per direction

    Returns:
        {timestamp, top_longs, top_shorts, total_scanned, scan_duration_ms}
    """
    now = time.time()
    cached = _CACHE.get("last_scan")
    if cached and now - cached.get("_ts", 0) < _CACHE_TTL:
        return {k: v for k, v in cached.items() if k != "_ts"}

    start_ts = time.time()
    symbols = list(get_active_crypto_symbols())[:40]  # limit for API rate

    results = await asyncio.gather(
        *[quick_score_symbol(sym) for sym in symbols],
        return_exceptions=True,
    )

    scored: list[dict[str, Any]] = []
    for sym, result in zip(symbols, results):
        if isinstance(result, Exception) or result is None:
            continue
        scored.append(result)

    top_longs = sorted(
        [s for s in scored if s["long_score"] > s["short_score"]],
        key=lambda x: x["long_score"],
        reverse=True,
    )[:top_n]

    top_shorts = sorted(
        [s for s in scored if s["short_score"] > s["long_score"]],
        key=lambda x: x["short_score"],
        reverse=True,
    )[:top_n]

    scan_duration_ms = round((time.time() - start_ts) * 1000)

    output: dict[str, Any] = {
        "timestamp": int(now * 1000),
        "top_longs": top_longs,
        "top_shorts": top_shorts,
        "total_scanned": len(scored),
        "scan_duration_ms": scan_duration_ms,
    }
    _CACHE["last_scan"] = {**output, "_ts": now}
    return output


async def quick_score_symbol(symbol: str) -> dict[str, Any] | None:
    """Compute a fast directional score for a single symbol.

    Args:
        symbol: Binance futures symbol (e.g. BTCUSDT)

    Returns:
        {symbol, long_score, short_score, bias, signals} or None on failure
    """
    try:
        from app.data.fetchers.binance_fetcher import BinanceFetcher

        fetcher = BinanceFetcher(symbol=symbol, interval="1h")
        candles = await fetcher.fetch_historical_ohlcv(limit=30)
        if not candles or len(candles) < 20:
            return None

        closes = [float(c["close"]) for c in candles]
        highs = [float(c["high"]) for c in candles]
        lows = [float(c["low"]) for c in candles]
        volumes = [float(c["volume"]) for c in candles]

        current = closes[-1]
        long_score = 0
        short_score = 0
        signals: list[str] = []

        # RSI
        rsi = _rsi(closes[-15:])
        if rsi < 30:
            long_score += 2
            signals.append(f"RSI oversold ({rsi:.0f})")
        elif rsi > 70:
            short_score += 2
            signals.append(f"RSI overbought ({rsi:.0f})")

        # EMA trend
        ema20 = _ema(closes, 20)
        if current > ema20 * 1.005:
            long_score += 1
            signals.append("Price above EMA20")
        elif current < ema20 * 0.995:
            short_score += 1
            signals.append("Price below EMA20")

        # Volume
        avg_vol = sum(volumes[-10:]) / 10
        if volumes[-1] > avg_vol * 1.5:
            if closes[-1] > closes[-2]:
                long_score += 1
                signals.append(f"High volume up ({volumes[-1]/avg_vol:.1f}x)")
            else:
                short_score += 1
                signals.append(f"High volume down ({volumes[-1]/avg_vol:.1f}x)")

        # ATR compression
        current_range = highs[-1] - lows[-1]
        avg_range = sum(highs[i] - lows[i] for i in range(-7, -1)) / 6
        if avg_range > 0 and current_range < avg_range * 0.5:
            long_score += 1
            short_score += 1  # compression is directionally neutral
            signals.append("ATR compression (breakout imminent)")

        bias = "LONG" if long_score > short_score else ("SHORT" if short_score > long_score else "NEUTRAL")

        return {
            "symbol": symbol,
            "long_score": long_score,
            "short_score": short_score,
            "bias": bias,
            "current_price": current,
            "rsi": round(rsi, 1),
            "signals": signals,
            "reason": signals[0] if signals else "No clear signal",
            "strategy_hint": _suggest_strategy(long_score, short_score, rsi),
        }

    except Exception as exc:
        logger.debug("Quick score failed for %s: %s", symbol, exc)
        return None


def _rsi(closes: list[float], period: int = 14) -> float:
    """Compute RSI value.

    Args:
        closes: Close prices
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


def _ema(data: list[float], period: int) -> float:
    """Compute single EMA value.

    Args:
        data: Price series
        period: EMA period

    Returns:
        EMA value
    """
    if len(data) < period:
        return data[-1] if data else 0.0
    k = 2 / (period + 1)
    ema = sum(data[:period]) / period
    for v in data[period:]:
        ema = v * k + ema * (1 - k)
    return ema


def _suggest_strategy(long_score: int, short_score: int, rsi: float) -> str:
    """Suggest a strategy based on signal scores.

    Args:
        long_score: Long signal score
        short_score: Short signal score
        rsi: RSI value

    Returns:
        Strategy suggestion string
    """
    if rsi < 35 or rsi > 65:
        return "mean_reversion"
    if long_score >= 3 or short_score >= 3:
        return "trend_following"
    return "breakout"
