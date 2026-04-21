"""Order Flow Imbalance — real-time buy/sell imbalance score from order book deltas.

Measures the ratio of bid volume to ask volume in the top N levels of the order book.
A positive imbalance (more bids) suggests buying pressure; negative suggests selling pressure.
Cached for 30 seconds to avoid excessive API calls.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)

_CACHE: dict[str, dict[str, Any]] = {}
_CACHE_TTL = 30  # seconds


async def get_order_flow_imbalance(symbol: str, depth: int = 20) -> dict[str, Any]:
    """Fetch order book and compute buy/sell imbalance ratio.

    Args:
        symbol: Binance trading pair (e.g. BTCUSDT)
        depth: Number of order book levels to analyze (max 20)

    Returns:
        {symbol, imbalance_ratio, bias, bid_volume, ask_volume, timestamp}
    """
    now = time.time()
    cached = _CACHE.get(symbol)
    if cached and now - cached["_ts"] < _CACHE_TTL:
        return {k: v for k, v in cached.items() if k != "_ts"}

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                "https://api.binance.com/api/v3/depth",
                params={"symbol": symbol, "limit": min(depth, 20)},
            )
            resp.raise_for_status()
            data = resp.json()

        bid_volume = sum(float(b[1]) for b in data.get("bids", []))
        ask_volume = sum(float(a[1]) for a in data.get("asks", []))
        total = bid_volume + ask_volume

        if total == 0:
            imbalance_ratio = 0.0
        else:
            imbalance_ratio = round((bid_volume - ask_volume) / total, 4)

        if imbalance_ratio > 0.15:
            bias = "BUY"
        elif imbalance_ratio < -0.15:
            bias = "SELL"
        else:
            bias = "NEUTRAL"

        result: dict[str, Any] = {
            "symbol": symbol,
            "imbalance_ratio": imbalance_ratio,
            "bias": bias,
            "bid_volume": round(bid_volume, 4),
            "ask_volume": round(ask_volume, 4),
            "depth_levels": depth,
            "timestamp": int(now * 1000),
        }
        _CACHE[symbol] = {**result, "_ts": now}
        return result

    except Exception as exc:
        logger.warning("OFI fetch failed for %s: %s", symbol, exc)
        return {
            "symbol": symbol,
            "imbalance_ratio": 0.0,
            "bias": "NEUTRAL",
            "bid_volume": 0.0,
            "ask_volume": 0.0,
            "depth_levels": depth,
            "error": str(exc),
            "timestamp": int(now * 1000),
        }
