"""Celery task definitions and configuration."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from celery import Celery
from sqlalchemy import select, and_

from app.core.config import settings

logger = logging.getLogger(__name__)

celery_app = Celery(
    "trading_ai",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "fetch-market-data": {
            "task": "app.tasks.fetch_market_data",
            "schedule": 60.0,  # every 1 minute
        },
        "analyze-sentiment": {
            "task": "app.tasks.analyze_sentiment",
            "schedule": 900.0,  # every 15 minutes
        },
        "fetch-onchain": {
            "task": "app.tasks.fetch_onchain",
            "schedule": 60.0,  # every 60 seconds
        },
        "run-signal-pipeline": {
            "task": "app.tasks.run_signal_pipeline",
            "schedule": 300.0,  # every 5 minutes
        },
        "check-signal-status": {
            "task": "app.tasks.check_signal_status",
            "schedule": 900.0,  # every 15 minutes
        },
    },
)

DEFAULT_SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
DEFAULT_INTERVALS = ["1m", "5m", "15m", "1h", "4h", "1D"]


def _run_async(coro):
    """Run an async coroutine from a sync Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _fetch_and_store_market_data():
    """Fetch latest candles from Binance and store in DB."""
    from app.core.database import async_session
    from app.data.fetchers.binance_fetcher import BinanceFetcher
    from app.models.market_data import MarketData

    fetcher = BinanceFetcher()
    now = datetime.now(timezone.utc)

    async with async_session() as session:
        for symbol in DEFAULT_SYMBOLS:
            for interval in DEFAULT_INTERVALS:
                try:
                    candles = await fetcher.fetch_historical_ohlcv(
                        symbol=symbol,
                        interval=interval,
                        start_time=now - timedelta(minutes=2),
                        end_time=now,
                        limit=5,
                    )
                    for c in candles:
                        row = MarketData(
                            asset=c.asset,
                            timeframe=c.timeframe,
                            timestamp=c.timestamp,
                            open=c.open,
                            high=c.high,
                            low=c.low,
                            close=c.close,
                            volume=c.volume,
                        )
                        session.add(row)
                    await session.commit()
                except Exception as exc:
                    await session.rollback()
                    logger.error("Market data fetch failed %s %s: %s", symbol, interval, exc)


async def _analyze_sentiment():
    """Run sentiment analysis for all assets and store results."""
    from app.core.database import async_session
    from app.data.fetchers.sentiment_fetcher import SentimentFetcher
    from app.models.sentiment_data import SentimentData

    fetcher = SentimentFetcher()

    async with async_session() as session:
        for symbol in DEFAULT_SYMBOLS:
            try:
                result = await fetcher.analyze(symbol)
                row = SentimentData(
                    asset=result["asset"],
                    source="aggregated",
                    score=Decimal(str(result["score"])),
                    volume=result["volume"],
                    period_start=result["period_start"],
                    period_end=result["period_end"],
                )
                session.add(row)
                await session.commit()
            except Exception as exc:
                await session.rollback()
                logger.error("Sentiment analysis failed for %s: %s", symbol, exc)


async def _fetch_onchain():
    """Fetch on-chain events and store in DB."""
    from app.core.database import async_session
    from app.data.fetchers.onchain_fetcher import OnChainFetcher
    from app.models.onchain_event import OnChainEvent

    fetcher = OnChainFetcher()

    try:
        events = await fetcher.fetch_recent(lookback_seconds=90)

        async with async_session() as session:
            for event in events:
                row = OnChainEvent(
                    asset=event["asset"],
                    event_type=event["event_type"],
                    amount=Decimal(str(event["amount"])),
                    amount_usd=Decimal(str(event["amount_usd"])),
                    from_address=event.get("from_address"),
                    to_address=event.get("to_address"),
                    direction=event["direction"],
                    source=event["source"],
                    raw_data=event.get("raw_data"),
                    timestamp=event["timestamp"],
                )
                session.add(row)
            await session.commit()
    except Exception as exc:
        logger.error("On-chain fetch failed: %s", exc)


async def _run_signal_pipeline():
    """Execute the full signal generation pipeline."""
    # TODO: Wire up in TASK-306 after strategies and aggregator are built
    logger.info("Signal pipeline run (not yet implemented)")


async def _check_signal_status():
    """Check active signals for TP/SL hits against current prices."""
    from app.core.database import async_session
    from app.data.fetchers.binance_fetcher import BinanceFetcher
    from app.models.signal import Signal

    fetcher = BinanceFetcher()
    now = datetime.now(timezone.utc)

    async with async_session() as session:
        result = await session.execute(
            select(Signal).where(Signal.status == "ACTIVE")
        )
        active_signals = result.scalars().all()

        for signal in active_signals:
            try:
                candles = await fetcher.fetch_historical_ohlcv(
                    symbol=signal.asset,
                    interval="1m",
                    start_time=now - timedelta(minutes=2),
                    end_time=now,
                    limit=1,
                )
                if not candles:
                    continue

                current_price = candles[-1].close

                # Check expiration
                if signal.expires_at and now >= signal.expires_at:
                    signal.status = "EXPIRED"
                    signal.updated_at = now
                    continue

                # Check SL hit
                if signal.stop_loss:
                    sl = signal.stop_loss
                    if signal.direction == "LONG" and current_price <= sl:
                        signal.status = "SL_HIT"
                        signal.updated_at = now
                        continue
                    if signal.direction == "SHORT" and current_price >= sl:
                        signal.status = "SL_HIT"
                        signal.updated_at = now
                        continue

                # Check TP2 hit first (higher priority)
                if signal.take_profit_2:
                    tp2 = signal.take_profit_2
                    if signal.direction == "LONG" and current_price >= tp2:
                        signal.status = "TP2_HIT"
                        signal.updated_at = now
                        continue
                    if signal.direction == "SHORT" and current_price <= tp2:
                        signal.status = "TP2_HIT"
                        signal.updated_at = now
                        continue

                # Check TP1 hit
                if signal.take_profit_1:
                    tp1 = signal.take_profit_1
                    if signal.direction == "LONG" and current_price >= tp1:
                        signal.status = "TP1_HIT"
                        signal.updated_at = now
                        continue
                    if signal.direction == "SHORT" and current_price <= tp1:
                        signal.status = "TP1_HIT"
                        signal.updated_at = now
                        continue

            except Exception as exc:
                logger.error("Status check failed for signal %s: %s", signal.id, exc)

        await session.commit()


@celery_app.task
def fetch_market_data():
    """Fetch OHLCV data from Binance."""
    _run_async(_fetch_and_store_market_data())


@celery_app.task
def analyze_sentiment():
    """Run sentiment analysis on social media data."""
    _run_async(_analyze_sentiment())


@celery_app.task
def fetch_onchain():
    """Fetch on-chain whale activity data."""
    _run_async(_fetch_onchain())


@celery_app.task
def run_signal_pipeline():
    """Run the full signal generation pipeline."""
    _run_async(_run_signal_pipeline())


@celery_app.task
def check_signal_status():
    """Check if active signals hit TP/SL levels."""
    _run_async(_check_signal_status())
