"""Volume Profile (VPVR) — identifies high-volume nodes, POC, VAH, and VAL.

Divides the price range into 20 buckets and sums volume in each to find:
- POC  (Point of Control): price level with the highest volume
- VAH  (Value Area High): upper boundary of 70% value area
- VAL  (Value Area Low): lower boundary of 70% value area

These levels act as strong support/resistance and entry/exit zones.
"""

from __future__ import annotations

import time
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

_CACHE: dict[str, dict[str, Any]] = {}
_CACHE_TTL = 300  # 5 minutes


async def get_volume_profile(
    symbol: str,
    interval: str = "1h",
    limit: int = 100,
    buckets: int = 20,
) -> dict[str, Any]:
    """Compute Volume Profile for a symbol.

    Args:
        symbol: Binance trading pair (e.g. BTCUSDT)
        interval: Kline interval string
        limit: Number of candles to analyze
        buckets: Number of price buckets in the profile

    Returns:
        {symbol, poc, vah, val, value_area_pct, profile, timestamp}
    """
    cache_key = f"{symbol}:{interval}"
    now = time.time()
    cached = _CACHE.get(cache_key)
    if cached and now - cached["_ts"] < _CACHE_TTL:
        return {k: v for k, v in cached.items() if k != "_ts"}

    try:
        from app.data.fetchers.binance_fetcher import BinanceFetcher

        fetcher = BinanceFetcher(symbol=symbol, interval=interval)
        candles = await fetcher.fetch_historical_ohlcv(limit=limit)
        if not candles or len(candles) < 10:
            return _empty_profile(symbol)

        highs = [float(c["high"]) for c in candles]
        lows = [float(c["low"]) for c in candles]
        volumes = [float(c["volume"]) for c in candles]

        price_min = min(lows)
        price_max = max(highs)
        bucket_size = (price_max - price_min) / buckets if price_max > price_min else 1.0

        # Initialize buckets
        profile_volumes = [0.0] * buckets
        profile_prices = [
            round(price_min + (i + 0.5) * bucket_size, 4)
            for i in range(buckets)
        ]

        # Distribute candle volume across price buckets
        for i, candle in enumerate(candles):
            candle_low = float(candle["low"])
            candle_high = float(candle["high"])
            candle_vol = volumes[i]

            candle_range = candle_high - candle_low
            for b in range(buckets):
                bucket_low = price_min + b * bucket_size
                bucket_high = bucket_low + bucket_size
                overlap = max(0.0, min(candle_high, bucket_high) - max(candle_low, bucket_low))
                if candle_range > 0:
                    profile_volumes[b] += candle_vol * (overlap / candle_range)
                else:
                    profile_volumes[b] += candle_vol / buckets

        # POC: bucket with highest volume
        poc_idx = profile_volumes.index(max(profile_volumes))
        poc = profile_prices[poc_idx]

        # Value Area: 70% of total volume centered around POC
        total_vol = sum(profile_volumes)
        target_vol = total_vol * 0.70
        va_vol = profile_volumes[poc_idx]
        lower_idx, upper_idx = poc_idx, poc_idx

        while va_vol < target_vol and (lower_idx > 0 or upper_idx < buckets - 1):
            can_go_lower = lower_idx > 0
            can_go_upper = upper_idx < buckets - 1
            lower_vol = profile_volumes[lower_idx - 1] if can_go_lower else -1
            upper_vol = profile_volumes[upper_idx + 1] if can_go_upper else -1

            if lower_vol >= upper_vol and can_go_lower:
                lower_idx -= 1
                va_vol += lower_vol
            elif can_go_upper:
                upper_idx += 1
                va_vol += upper_vol
            elif can_go_lower:
                lower_idx -= 1
                va_vol += lower_vol
            else:
                break

        vah = profile_prices[upper_idx]
        val = profile_prices[lower_idx]

        profile = [
            {"price": profile_prices[i], "volume": round(profile_volumes[i], 2)}
            for i in range(buckets)
        ]

        result: dict[str, Any] = {
            "symbol": symbol,
            "interval": interval,
            "poc": round(poc, 4),
            "vah": round(vah, 4),
            "val": round(val, 4),
            "value_area_pct": 70,
            "profile": profile,
            "price_min": round(price_min, 4),
            "price_max": round(price_max, 4),
            "candles_analyzed": len(candles),
            "timestamp": int(now * 1000),
        }
        _CACHE[cache_key] = {**result, "_ts": now}
        return result

    except Exception as exc:
        logger.warning("Volume profile failed for %s: %s", symbol, exc)
        return _empty_profile(symbol, error=str(exc))


def _empty_profile(symbol: str, error: str | None = None) -> dict[str, Any]:
    """Return an empty profile structure on failure."""
    result: dict[str, Any] = {
        "symbol": symbol,
        "poc": 0.0,
        "vah": 0.0,
        "val": 0.0,
        "value_area_pct": 70,
        "profile": [],
        "timestamp": int(time.time() * 1000),
    }
    if error:
        result["error"] = error
    return result
