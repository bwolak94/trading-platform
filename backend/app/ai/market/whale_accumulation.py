"""Whale Accumulation Pattern Detector — sustained large spot buys signal.

Uses Binance taker buy/sell volume as a proxy for institutional buying pressure.
A sustained taker buy ratio > 0.60 over 48 hours indicates accumulation by large players.

Data source: Binance futures taker buy/sell volume API.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)

_CACHE: dict[str, dict[str, Any]] = {}
_CACHE_TTL = 900  # 15 minutes


async def get_whale_accumulation_signal(symbol: str = "BTCUSDT") -> dict[str, Any]:
    """Detect whale accumulation or distribution patterns.

    Args:
        symbol: Binance futures symbol (e.g. BTCUSDT)

    Returns:
        {symbol, avg_taker_buy_ratio_48h, recent_taker_buy_ratio_6h,
         is_accumulating, is_distributing, signal, confidence}
    """
    now = time.time()
    cached = _CACHE.get(symbol)
    if cached and now - cached["_ts"] < _CACHE_TTL:
        return {k: v for k, v in cached.items() if k != "_ts"}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://fapi.binance.com/futures/data/takerBuySellVol",
                params={"symbol": symbol, "period": "1h", "limit": 48},
            )
            resp.raise_for_status()
            data = resp.json()

        if not data:
            return _fallback(symbol, "No taker volume data")

        buy_vols = [float(d.get("buyVol", 0)) for d in data]
        sell_vols = [float(d.get("sellVol", 0)) for d in data]

        def safe_ratio(buys: list[float], sells: list[float]) -> float:
            total_buy = sum(buys)
            total_sell = sum(sells)
            total = total_buy + total_sell
            return round(total_buy / total, 4) if total > 0 else 0.5

        ratio_48h = safe_ratio(buy_vols, sell_vols)
        ratio_6h = safe_ratio(buy_vols[-6:], sell_vols[-6:])

        # Classify signal
        is_accumulating = ratio_48h > 0.60 and ratio_6h > 0.58
        is_distributing = ratio_48h < 0.40 and ratio_6h < 0.42

        if is_accumulating and ratio_48h > 0.70:
            signal = "STRONG_ACCUMULATION"
        elif is_accumulating:
            signal = "ACCUMULATION"
        elif is_distributing and ratio_48h < 0.30:
            signal = "STRONG_DISTRIBUTION"
        elif is_distributing:
            signal = "DISTRIBUTION"
        else:
            signal = "NEUTRAL"

        # Confidence based on sustained nature of signal
        recent_consistent = sum(
            1 for b, s in zip(buy_vols[-12:], sell_vols[-12:])
            if (b + s > 0) and (b / (b + s) > 0.55 if is_accumulating else b / (b + s) < 0.45)
        )
        confidence = round(recent_consistent / 12, 2)

        result: dict[str, Any] = {
            "symbol": symbol,
            "avg_taker_buy_ratio_48h": ratio_48h,
            "recent_taker_buy_ratio_6h": ratio_6h,
            "is_accumulating": is_accumulating,
            "is_distributing": is_distributing,
            "signal": signal,
            "confidence": confidence,
            "periods_analyzed": len(data),
            "timestamp": int(now * 1000),
        }
        _CACHE[symbol] = {**result, "_ts": now}
        return result

    except Exception as exc:
        logger.warning("Whale accumulation fetch failed for %s: %s", symbol, exc)
        return _fallback(symbol, str(exc))


def _fallback(symbol: str, error: str) -> dict[str, Any]:
    """Return neutral fallback on error.

    Args:
        symbol: Trading pair symbol
        error: Error message

    Returns:
        Neutral result dict
    """
    return {
        "symbol": symbol,
        "avg_taker_buy_ratio_48h": 0.5,
        "recent_taker_buy_ratio_6h": 0.5,
        "is_accumulating": False,
        "is_distributing": False,
        "signal": "NEUTRAL",
        "confidence": 0.0,
        "error": error,
        "timestamp": int(time.time() * 1000),
    }
