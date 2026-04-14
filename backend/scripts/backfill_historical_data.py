"""Backfill historical OHLCV data from Binance for backtesting.

Usage:
    python -m scripts.backfill_historical_data
"""

import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal

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


async def backfill():
    """Fetch and store historical data for all symbols and timeframes."""
    fetcher = BinanceFetcher()

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
                    batch = []
                    for c in candles:
                        batch.append(MarketData(
                            asset=c.asset,
                            timeframe=c.timeframe,
                            timestamp=c.timestamp,
                            open=c.open,
                            high=c.high,
                            low=c.low,
                            close=c.close,
                            volume=c.volume,
                        ))

                        if len(batch) >= 500:
                            session.add_all(batch)
                            await session.commit()
                            batch = []

                    if batch:
                        session.add_all(batch)
                        await session.commit()

                logger.info(
                    "Stored %d candles for %s %s", len(candles), symbol, tf
                )

            except Exception as exc:
                logger.error("Failed to backfill %s %s: %s", symbol, tf, exc)

    logger.info("Backfill complete")


if __name__ == "__main__":
    asyncio.run(backfill())
