"""Fear & Greed Index fetcher — alternative.me free API, cached 1h."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)

FNG_URL = "https://api.alternative.me/fng/?limit=1&format=json"

_cache: dict[str, Any] | None = None
_cache_ts: datetime | None = None
_CACHE_TTL_SECONDS = 3600  # 1 hour
_lock = asyncio.Lock()


async def get_fear_greed_index() -> dict[str, Any]:
    """Fetch Fear & Greed Index, cached for 1 hour.

    Returns dict with keys: value (0-100), value_classification, timestamp.
    """
    global _cache, _cache_ts

    async with _lock:
        now = datetime.now(timezone.utc)
        if _cache and _cache_ts and (now - _cache_ts).total_seconds() < _CACHE_TTL_SECONDS:
            return _cache

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(FNG_URL)
                resp.raise_for_status()
                body = resp.json()
                entry = body["data"][0]
                _cache = {
                    "value": int(entry["value"]),
                    "value_classification": entry["value_classification"],
                    "timestamp": entry["timestamp"],
                    "cached_at": now.isoformat(),
                }
                _cache_ts = now
                logger.info("Fear & Greed fetched: %s (%s)", _cache["value"], _cache["value_classification"])
                return _cache
        except Exception as exc:
            logger.warning("Failed to fetch Fear & Greed index: %s", exc)
            if _cache:
                return _cache
            return {
                "value": 50,
                "value_classification": "Neutral",
                "timestamp": str(int(now.timestamp())),
                "cached_at": now.isoformat(),
                "error": str(exc),
            }
