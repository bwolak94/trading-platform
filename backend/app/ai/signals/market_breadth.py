"""Market Breadth Indicator — % of crypto futures above key EMAs.

Scans all active Binance USDT perpetual futures and calculates what
percentage are trading above their 20/50/200 EMA. This gives a high-level
view of overall market health.

Cached for 5 minutes to avoid hammering Binance.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.logging import get_logger
from app.core.symbols import get_active_crypto_symbols

logger = get_logger(__name__)

_CACHE_TTL = 300  # 5 minutes
_cache: dict[str, Any] | None = None
_cache_ts: datetime | None = None


async def get_market_breadth() -> dict[str, Any]:
    """Return % of pairs above 20/50/200 EMA.

    Returns:
        dict with above_ema20_pct, above_ema50_pct, above_ema200_pct,
        total_symbols, scanned_symbols, cached_at
    """
    global _cache, _cache_ts

    now = datetime.now(timezone.utc)
    if _cache and _cache_ts and (now - _cache_ts).total_seconds() < _CACHE_TTL:
        return _cache

    symbols = list(get_active_crypto_symbols())[:50]  # limit to top 50 for speed
    results = await asyncio.gather(
        *[_check_symbol_ema(sym) for sym in symbols],
        return_exceptions=True,
    )

    above_20 = above_50 = above_200 = scanned = 0
    for r in results:
        if isinstance(r, Exception) or r is None:
            continue
        scanned += 1
        above_20 += int(r.get("above_20", False))
        above_50 += int(r.get("above_50", False))
        above_200 += int(r.get("above_200", False))

    base = scanned or 1
    _cache = {
        "above_ema20_pct": round(above_20 / base * 100, 1),
        "above_ema50_pct": round(above_50 / base * 100, 1),
        "above_ema200_pct": round(above_200 / base * 100, 1),
        "total_symbols": len(symbols),
        "scanned_symbols": scanned,
        "cached_at": now.isoformat(),
    }
    _cache_ts = now
    logger.info(
        "Market breadth: %d/%d above EMA20=%.1f%% EMA50=%.1f%% EMA200=%.1f%%",
        above_20,
        scanned,
        _cache["above_ema20_pct"],
        _cache["above_ema50_pct"],
        _cache["above_ema200_pct"],
    )
    return _cache


async def _check_symbol_ema(symbol: str) -> dict[str, bool] | None:
    """Check if a symbol's current price is above 20/50/200 EMA."""
    try:
        from app.data.fetchers.binance_fetcher import BinanceFetcher

        fetcher = BinanceFetcher()
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=210)
        candles = await fetcher.fetch_historical_ohlcv(
            symbol=symbol, interval="1d", start_time=start_time, end_time=end_time, limit=500
        )
        if not candles or len(candles) < 55:
            return None

        closes = [float(c.close) for c in candles]
        current = closes[-1]

        return {
            "above_20": current > _ema(closes, 20),
            "above_50": current > _ema(closes, 50),
            "above_200": current > _ema(closes, 200) if len(closes) >= 200 else False,
        }
    except Exception:
        return None


def _ema(values: list[float], period: int) -> float:
    """Calculate EMA for the final value in the series."""
    k = 2 / (period + 1)
    ema = sum(values[:period]) / period
    for v in values[period:]:
        ema = v * k + ema * (1 - k)
    return ema
