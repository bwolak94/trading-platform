"""Backfill historical OHLCV data from Binance for backtesting.

Idempotent: running this script multiple times is safe.  Candles are
inserted with ON CONFLICT DO NOTHING so duplicate rows are never created.

Usage:
    python -m scripts.backfill_historical_data
"""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.database import async_session
from app.data.fetchers.binance_fetcher import BinanceFetcher
from app.models.market_data import MarketData

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
TIMEFRAMES = ["1h", "4h", "1D"]

# 2 years of data for backtesting
START = datetime(2023, 1, 1, tzinfo=timezone.utc)
END = datetime(2025, 1, 1, tzinfo=timezone.utc)

BATCH_SIZE = 500


async def _upsert_batch(session, rows: list[dict]) -> int:
    """Insert a batch of candle rows, ignoring conflicts on (asset, timeframe, timestamp)."""
    stmt = (
        pg_insert(MarketData)
        .values(rows)
        .on_conflict_do_nothing(index_elements=["asset", "timeframe", "timestamp"])
    )
    result = await session.execute(stmt)
    await session.commit()
    return result.rowcount or 0


async def backfill():
    """Fetch and upsert historical data for all symbols and timeframes."""
    fetcher = BinanceFetcher()
    total_inserted = 0

    for symbol in SYMBOLS:
        for tf in TIMEFRAMES:
            logger.info("Backfilling %s %s from %s to %s", symbol, tf, START, END)

            try:
                candles = await fetcher.fetch_historical_ohlcv(
                    symbol=symbol,
                    interval=tf,
                    start_time=START,
                    end_time=END,
                )

                async with async_session() as session:
                    batch: list[dict] = []
                    inserted = 0

                    for c in candles:
                        batch.append({
                            "asset": c.asset,
                            "timeframe": c.timeframe,
                            "timestamp": c.timestamp,
                            "open": c.open,
                            "high": c.high,
                            "low": c.low,
                            "close": c.close,
                            "volume": c.volume,
                        })

                        if len(batch) >= BATCH_SIZE:
                            inserted += await _upsert_batch(session, batch)
                            batch = []

                    if batch:
                        inserted += await _upsert_batch(session, batch)

                total_inserted += inserted
                logger.info(
                    "Stored %d new candle(s) for %s %s (skipped %d duplicate(s))",
                    inserted, symbol, tf, len(candles) - inserted,
                )

            except Exception as exc:
                logger.error("Failed to backfill %s %s: %s", symbol, tf, exc)

    logger.info("Backfill complete — %d total new candle(s) inserted", total_inserted)


if __name__ == "__main__":
    asyncio.run(backfill())
