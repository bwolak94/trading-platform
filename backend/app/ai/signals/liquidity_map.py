"""Smart Liquidity Map — aggregates stop-loss clusters and swing levels.

Identifies price levels where large numbers of stop-loss orders are likely
clustered, based on swing highs and swing lows from recent price action.
These levels act as magnets for price (liquidity grabs) before continuation.
"""

from __future__ import annotations

import time
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

_CACHE: dict[str, dict[str, Any]] = {}
_CACHE_TTL = 600  # 10 minutes


async def get_liquidity_map(symbol: str, interval: str = "1h", lookback: int = 100) -> dict[str, Any]:
    """Build a liquidity map for the given symbol.

    Swing highs and lows are identified as price levels where stop-losses cluster.
    Strength (1-10) is proportional to how many nearby candles confirm the level.

    Args:
        symbol: Binance trading pair (e.g. BTCUSDT)
        interval: Kline interval
        lookback: Number of candles to analyze

    Returns:
        {symbol, current_price, liquidity_zones, high_liquidity_above, high_liquidity_below}
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
        if not candles or len(candles) < 10:
            return {"symbol": symbol, "liquidity_zones": [], "error": "Insufficient data"}

        highs = [float(c["high"]) for c in candles]
        lows = [float(c["low"]) for c in candles]
        current_price = float(candles[-1]["close"])

        zones: list[dict[str, Any]] = []
        neighbors = 2  # candles on each side to confirm swing

        # Detect swing highs
        for i in range(neighbors, len(highs) - neighbors):
            if all(highs[i] > highs[i - j] for j in range(1, neighbors + 1)) and \
               all(highs[i] > highs[i + j] for j in range(1, neighbors + 1)):
                strength = _compute_strength(highs[i], highs, lows)
                zones.append({
                    "level": round(highs[i], 4),
                    "type": "SWING_HIGH",
                    "sub_type": "STOP_CLUSTER",
                    "strength": strength,
                    "description": "Sell stops above swing high",
                })

        # Detect swing lows
        for i in range(neighbors, len(lows) - neighbors):
            if all(lows[i] < lows[i - j] for j in range(1, neighbors + 1)) and \
               all(lows[i] < lows[i + j] for j in range(1, neighbors + 1)):
                strength = _compute_strength(lows[i], highs, lows)
                zones.append({
                    "level": round(lows[i], 4),
                    "type": "SWING_LOW",
                    "sub_type": "STOP_CLUSTER",
                    "strength": strength,
                    "description": "Buy stops below swing low",
                })

        # Sort zones by strength
        zones.sort(key=lambda z: z["strength"], reverse=True)

        above = [z for z in zones if z["level"] > current_price]
        below = [z for z in zones if z["level"] < current_price]

        high_liq_above = above[0]["level"] if above else None
        high_liq_below = below[0]["level"] if below else None

        result: dict[str, Any] = {
            "symbol": symbol,
            "interval": interval,
            "current_price": current_price,
            "liquidity_zones": zones[:20],  # top 20 zones
            "high_liquidity_above": high_liq_above,
            "high_liquidity_below": high_liq_below,
            "zones_above_count": len(above),
            "zones_below_count": len(below),
            "timestamp": int(now * 1000),
        }
        _CACHE[cache_key] = {**result, "_ts": now}
        return result

    except Exception as exc:
        logger.warning("Liquidity map failed for %s: %s", symbol, exc)
        return {"symbol": symbol, "liquidity_zones": [], "error": str(exc)}


def _compute_strength(level: float, highs: list[float], lows: list[float]) -> int:
    """Compute zone strength (1-10) based on how many candles tested this level.

    Args:
        level: Price level to evaluate
        highs: List of candle highs
        lows: List of candle lows

    Returns:
        Strength score from 1 to 10
    """
    threshold = level * 0.002  # within 0.2%
    touches = sum(
        1 for h, l in zip(highs, lows)
        if abs(h - level) < threshold or abs(l - level) < threshold
    )
    return min(10, max(1, touches))
