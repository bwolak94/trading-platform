"""Volatility Surface — realized vol term structure across multiple timeframes.

Models the volatility term structure (short-term vs long-term vol) to identify:
- Volatility compression (short-term vol << long-term vol) → breakout expected
- Volatility expansion (short-term vol >> long-term vol) → regime change
- Contango (vol rising with time) vs Backwardation (vol falling with time)

Uses the Parkinson estimator (high-low range) for more accurate intraday vol.
"""

from __future__ import annotations

import asyncio
import math
import time
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

_CACHE: dict[str, dict[str, Any]] = {}
_CACHE_TTL = 900  # 15 minutes

# Annualization factors (periods per year)
_ANNUALIZATION: dict[str, int] = {
    "15m": 35_040,
    "1h": 8_760,
    "4h": 2_190,
    "1d": 365,
}

_TIMEFRAMES = list(_ANNUALIZATION.keys())


async def compute_volatility_surface(symbol: str) -> dict[str, Any]:
    """Compute realized volatility surface across 4 timeframes.

    Args:
        symbol: Binance trading pair (e.g. BTCUSDT)

    Returns:
        {symbol, surface, term_structure, vol_compression, breakout_probability, current_regime}
    """
    now = time.time()
    cached = _CACHE.get(symbol)
    if cached and now - cached.get("_ts", 0) < _CACHE_TTL:
        return {k: v for k, v in cached.items() if k != "_ts"}

    try:
        from app.data.fetchers.binance_fetcher import BinanceFetcher

        tasks = {
            tf: BinanceFetcher(symbol=symbol, interval=tf).fetch_historical_ohlcv(limit=60)
            for tf in _TIMEFRAMES
        }
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)

        surface: dict[str, Any] = {}
        vol_values: list[float] = []

        for tf, candles in zip(tasks.keys(), results):
            if isinstance(candles, Exception) or not candles or len(candles) < 5:
                surface[tf] = {"realized_vol_annualized": None, "error": str(candles)}
                continue

            highs = [float(c["high"]) for c in candles]
            lows = [float(c["low"]) for c in candles]
            [float(c["close"]) for c in candles]

            # Parkinson estimator
            parkinson_vol = compute_parkinson_vol(highs, lows)
            annualized = parkinson_vol * math.sqrt(_ANNUALIZATION[tf])

            surface[tf] = {
                "realized_vol_annualized": round(annualized * 100, 2),
                "parkinson_vol_per_period": round(parkinson_vol * 100, 4),
                "sample_size": len(candles),
            }
            vol_values.append(annualized)

        # Term structure shape
        short_vol = surface.get("15m", {}).get("realized_vol_annualized") or (vol_values[0] * 100 if vol_values else None)
        long_vol = surface.get("1d", {}).get("realized_vol_annualized") or (vol_values[-1] * 100 if len(vol_values) > 1 else None)

        if short_vol and long_vol:
            if long_vol > short_vol * 1.1:
                term_structure = "CONTANGO"
                vol_compression = True
            elif short_vol > long_vol * 1.1:
                term_structure = "BACKWARDATION"
                vol_compression = False
            else:
                term_structure = "FLAT"
                vol_compression = False

            compression_ratio = short_vol / long_vol if long_vol > 0 else 1.0
            breakout_probability = round(max(0.0, 1.0 - compression_ratio), 2) if vol_compression else 0.1
        else:
            term_structure = "UNKNOWN"
            vol_compression = False
            breakout_probability = 0.0

        # Current vol regime based on short-term vol
        if short_vol:
            if short_vol < 30:
                vol_regime = "LOW_VOL"
            elif short_vol < 60:
                vol_regime = "NORMAL_VOL"
            elif short_vol < 100:
                vol_regime = "HIGH_VOL"
            else:
                vol_regime = "EXTREME_VOL"
        else:
            vol_regime = "UNKNOWN"

        result: dict[str, Any] = {
            "symbol": symbol,
            "surface": surface,
            "term_structure": term_structure,
            "vol_compression": vol_compression,
            "breakout_probability": breakout_probability,
            "current_regime": vol_regime,
            "short_term_vol_pct": short_vol,
            "long_term_vol_pct": long_vol,
            "timestamp": int(now * 1000),
        }
        _CACHE[symbol] = {**result, "_ts": now}
        return result

    except Exception as exc:
        logger.warning("Volatility surface failed for %s: %s", symbol, exc)
        return {
            "symbol": symbol,
            "surface": {},
            "term_structure": "UNKNOWN",
            "vol_compression": False,
            "breakout_probability": 0.0,
            "current_regime": "UNKNOWN",
            "error": str(exc),
            "timestamp": int(time.time() * 1000),
        }


def compute_parkinson_vol(highs: list[float], lows: list[float]) -> float:
    """Compute Parkinson volatility estimator using high-low range.

    More accurate than close-to-close for intraday volatility estimation.

    Args:
        highs: List of candle highs
        lows: List of candle lows

    Returns:
        Parkinson volatility estimate (per period, unannualized)
    """
    if not highs or not lows:
        return 0.0
    factor = 1.0 / (4.0 * math.log(2))
    sq_sum = sum(
        (math.log(h / l)) ** 2
        for h, l in zip(highs, lows)
        if h > 0 and l > 0 and h >= l
    )
    return math.sqrt(factor * sq_sum / len(highs))
