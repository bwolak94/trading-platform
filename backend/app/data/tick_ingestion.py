"""D3: Tick data ingestion pipeline.

Celery task that fetches 1-minute OHLCV from Binance for the top 5 assets
and stores them in a Redis sorted set for microstructure calculations.

The sorted set key is ``ticks:{symbol}`` and each member is a JSON-encoded
candle; the score is the UNIX timestamp in milliseconds.  Entries older than
24 hours are pruned on each write.

This data powers:
  - Tick-by-tick replay in the frontend (TickByTickReplay)
  - Order flow imbalance calculations
  - Short-term volatility estimates
"""

import json
import time as _time
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

TOP_SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"]
REDIS_KEY_PREFIX = "ticks:"
# Keep 24 hours of 1m candles (1 440 per symbol)
MAX_CANDLE_AGE_HOURS = 24


async def ingest_ticks() -> dict[str, int]:
    """Fetch the latest 1m candles for TOP_SYMBOLS and store them in Redis.

    Returns:
        Dict mapping symbol to number of new candles ingested.
    """
    from app.core.config import settings
    from app.data.fetchers.binance_fetcher import BinanceFetcher
    import redis as _redis

    fetcher = BinanceFetcher()
    r = _redis.from_url(settings.REDIS_URL, decode_responses=True)
    now = datetime.now(timezone.utc)
    cutoff_ms = int((now - timedelta(hours=MAX_CANDLE_AGE_HOURS)).timestamp() * 1000)

    results: dict[str, int] = {}

    for symbol in TOP_SYMBOLS:
        try:
            candles = await fetcher.fetch_historical_ohlcv(
                symbol=symbol,
                interval="1m",
                start_time=now - timedelta(minutes=5),
                end_time=now,
                limit=5,
            )
            if not candles:
                results[symbol] = 0
                continue

            key = REDIS_KEY_PREFIX + symbol.replace("/", "")
            pipe = r.pipeline()

            for candle in candles:
                ts_ms = int(candle.timestamp.timestamp() * 1000)
                member = json.dumps({
                    "t": ts_ms,
                    "o": float(candle.open),
                    "h": float(candle.high),
                    "l": float(candle.low),
                    "c": float(candle.close),
                    "v": float(candle.volume),
                })
                pipe.zadd(key, {member: ts_ms})

            # Prune entries older than 24 h
            pipe.zremrangebyscore(key, "-inf", cutoff_ms)
            # Expire the entire key after 25 h to prevent orphaned keys
            pipe.expire(key, MAX_CANDLE_AGE_HOURS * 3600 + 3600)
            pipe.execute()

            results[symbol] = len(candles)
            logger.debug("Ingested %d tick candles for %s", len(candles), symbol)

        except Exception as exc:
            logger.error("Tick ingestion failed for %s: %s", symbol, exc)
            results[symbol] = 0

    return results


def get_recent_ticks(symbol: str, limit: int = 60) -> list[dict[str, Any]]:
    """Retrieve the most-recent ``limit`` 1m candles for ``symbol`` from Redis.

    Args:
        symbol: Trading symbol, e.g. ``"BTC/USDT"``.
        limit:  Maximum number of candles to return (default 60).

    Returns:
        List of candle dicts sorted newest-first, each with keys
        ``t``, ``o``, ``h``, ``l``, ``c``, ``v``.
    """
    from app.core.config import settings
    import redis as _redis

    try:
        r = _redis.from_url(settings.REDIS_URL, decode_responses=True)
        key = REDIS_KEY_PREFIX + symbol.replace("/", "")
        raw = r.zrevrange(key, 0, limit - 1)
        return [json.loads(m) for m in raw]
    except Exception as exc:
        logger.warning("get_recent_ticks failed for %s: %s", symbol, exc)
        return []
