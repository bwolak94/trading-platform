"""Statistical Arbitrage — pairs trading using z-score of log price ratio.

Identifies when the spread between two correlated assets deviates significantly
from its historical mean. A z-score > +2.0 suggests the spread will revert
(sell A, buy B), and z-score < -2.0 suggests the opposite.

Default pair: BTC/ETH — historically one of the most cointegrated crypto pairs.
"""

from __future__ import annotations

import math
import time
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

_CACHE: dict[str, dict[str, Any]] = {}
_CACHE_TTL = 900  # 15 minutes
_Z_THRESHOLD = 2.0


async def get_pairs_zscore(
    symbol_a: str = "BTCUSDT",
    symbol_b: str = "ETHUSDT",
    interval: str = "1d",
    lookback: int = 200,
    zscore_window: int = 60,
) -> dict[str, Any]:
    """Compute z-score of the log price ratio for a pair.

    Args:
        symbol_a: First asset (e.g. BTCUSDT)
        symbol_b: Second asset (e.g. ETHUSDT)
        interval: Kline interval for price data
        lookback: Number of candles to fetch
        zscore_window: Rolling window for mean/std calculation

    Returns:
        {pair, zscore, ratio, mean, std, signal, threshold_used}
    """
    cache_key = f"{symbol_a}:{symbol_b}:{interval}"
    now = time.time()
    cached = _CACHE.get(cache_key)
    if cached and now - cached["_ts"] < _CACHE_TTL:
        return {k: v for k, v in cached.items() if k != "_ts"}

    try:
        from app.data.fetchers.binance_fetcher import BinanceFetcher

        fetcher_a = BinanceFetcher(symbol=symbol_a, interval=interval)
        fetcher_b = BinanceFetcher(symbol=symbol_b, interval=interval)

        import asyncio
        candles_a, candles_b = await asyncio.gather(
            fetcher_a.fetch_historical_ohlcv(limit=lookback),
            fetcher_b.fetch_historical_ohlcv(limit=lookback),
        )

        if not candles_a or not candles_b:
            return _empty_result(symbol_a, symbol_b, "Failed to fetch price data")

        min_len = min(len(candles_a), len(candles_b))
        closes_a = [float(c["close"]) for c in candles_a[-min_len:]]
        closes_b = [float(c["close"]) for c in candles_b[-min_len:]]

        # Log price ratio
        log_ratios = [
            math.log(a / b)
            for a, b in zip(closes_a, closes_b)
            if a > 0 and b > 0
        ]

        if len(log_ratios) < zscore_window:
            return _empty_result(symbol_a, symbol_b, "Insufficient data for z-score window")

        # Rolling stats over zscore_window
        window = log_ratios[-zscore_window:]
        mean = sum(window) / len(window)
        variance = sum((x - mean) ** 2 for x in window) / len(window)
        std = math.sqrt(variance) if variance > 0 else 1e-9

        current_ratio = log_ratios[-1]
        zscore = round((current_ratio - mean) / std, 4)

        if zscore > _Z_THRESHOLD:
            signal = "SHORT_A_LONG_B"  # A overvalued relative to B
            signal_desc = f"Short {symbol_a}, Long {symbol_b} — ratio too high"
        elif zscore < -_Z_THRESHOLD:
            signal = "LONG_A_SHORT_B"  # A undervalued relative to B
            signal_desc = f"Long {symbol_a}, Short {symbol_b} — ratio too low"
        else:
            signal = "NEUTRAL"
            signal_desc = "Spread within normal range, no arb opportunity"

        result: dict[str, Any] = {
            "pair": f"{symbol_a.replace('USDT', '')}/{symbol_b.replace('USDT', '')}",
            "symbol_a": symbol_a,
            "symbol_b": symbol_b,
            "zscore": zscore,
            "current_log_ratio": round(current_ratio, 6),
            "mean_log_ratio": round(mean, 6),
            "std_log_ratio": round(std, 6),
            "signal": signal,
            "signal_description": signal_desc,
            "threshold_used": _Z_THRESHOLD,
            "zscore_window": zscore_window,
            "data_points": len(log_ratios),
            "timestamp": int(now * 1000),
        }
        _CACHE[cache_key] = {**result, "_ts": now}
        return result

    except Exception as exc:
        logger.warning("Pairs z-score failed for %s/%s: %s", symbol_a, symbol_b, exc)
        return _empty_result(symbol_a, symbol_b, str(exc))


def _empty_result(symbol_a: str, symbol_b: str, error: str) -> dict[str, Any]:
    """Return empty pairs result on failure.

    Args:
        symbol_a: First symbol
        symbol_b: Second symbol
        error: Error message

    Returns:
        Empty result dict
    """
    return {
        "pair": f"{symbol_a}/{symbol_b}",
        "zscore": 0.0,
        "signal": "NEUTRAL",
        "error": error,
        "timestamp": int(time.time() * 1000),
    }
