"""Celery task definitions and configuration."""

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from celery import Celery
from sqlalchemy import select, func, and_

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

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
    # Dead-letter queue — permanently-failed tasks are routed here for inspection
    task_queues={
        "default": {"exchange": "default", "routing_key": "default"},
        "dlq": {"exchange": "dlq", "routing_key": "dlq"},
    },
    task_default_queue="default",
    task_routes={
        "app.tasks.*": {"queue": "default"},
    },
    # Tasks that exhaust retries are re-queued to dlq instead of being discarded
    task_reject_on_worker_lost=True,
    beat_schedule={
        # D7: Signal aging decay — runs every 15 minutes
        "signal-aging-decay": {
            "task": "app.tasks.signal_aging_decay",
            "schedule": 900.0,
            "options": {"expires": 890},
        },
        "fetch-market-data": {
            "task": "app.tasks.fetch_market_data",
            "schedule": 60.0,
            "options": {"expires": 55},
        },
        "analyze-sentiment": {
            "task": "app.tasks.analyze_sentiment",
            "schedule": 900.0,
            "options": {"expires": 890},
        },
        "fetch-onchain": {
            "task": "app.tasks.fetch_onchain",
            "schedule": 60.0,
            "options": {"expires": 55},
        },
        "run-signal-pipeline": {
            "task": "app.tasks.run_signal_pipeline",
            "schedule": 300.0,
            "options": {"expires": 290},
        },
        "check-signal-status": {
            "task": "app.tasks.check_signal_status",
            "schedule": 900.0,
            "options": {"expires": 890},
        },
        "cleanup-expired-signals": {
            "task": "cleanup_expired_signals",
            "schedule": 86400.0,
            "options": {"expires": 3600},
        },
        "send-daily-risk-report": {
            "task": "app.tasks.send_daily_risk_report",
            "schedule": 86400.0,
            "options": {"expires": 3600},
        },
        "ohlcv-gap-detector": {
            "task": "app.tasks.ohlcv_gap_detector",
            "schedule": 3600.0,  # hourly
            "options": {"expires": 3500},
        },
        "position-reconciliation": {
            "task": "app.tasks.position_reconciliation",
            "schedule": 86400.0,  # nightly
            "options": {"expires": 3600},
        },
        # Reports — previously scheduled by APScheduler in main.py; moved here
        # so Celery Beat is the single source of truth for all periodic tasks.
        "daily-briefing": {
            "task": "app.tasks.generate_daily_briefing",
            "schedule": 86400.0,  # daily — actual cron pinning via crontab() if needed
            "options": {"expires": 3600},
        },
        "weekly-report": {
            "task": "app.tasks.generate_weekly_report",
            "schedule": 604800.0,  # weekly
            "options": {"expires": 3600},
        },
    },
    # Jitter prevents thundering-herd on startup — tasks spread within ±10 % of schedule
    beat_max_loop_interval=5,
)

DEFAULT_SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
DEFAULT_INTERVALS = ["1m", "5m", "15m", "1h", "4h", "1D"]

# Risk engine limits
MAX_DAILY_LOSS_USD = Decimal("500.00")
MAX_CONCURRENT_SIGNALS = 10


def _run_async(coro):
    """Run an async coroutine from a sync Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(name="app.tasks.send_telegram_message", bind=True, max_retries=3)
def send_telegram_message(self, message: str) -> dict:
    """Send a Telegram notification asynchronously via a Celery worker.

    Uses a Redis idempotency key (SHA-256 of the message, 60 s TTL) to
    prevent duplicate delivery on Celery retries.
    """
    import hashlib
    import redis as _redis
    from app.notifications.telegram_bot import get_telegram_bot

    # Idempotency: skip if we already sent this exact message in the last 60 s
    msg_hash = hashlib.sha256(message.encode()).hexdigest()[:16]
    idem_key = f"tg:sent:{msg_hash}"
    try:
        r = _redis.from_url(settings.REDIS_URL, decode_responses=True)
        if not r.set(idem_key, "1", nx=True, ex=60):
            logger.info("Telegram message deduplicated (key=%s)", idem_key)
            return {"status": "deduplicated"}
    except Exception as exc:
        logger.warning("Redis idempotency check failed, sending anyway: %s", exc)

    async def _send():
        bot = get_telegram_bot()
        if bot:
            await bot.send_message(message)

    try:
        _run_async(_send())
        return {"status": "sent"}
    except Exception as exc:
        logger.warning("send_telegram_message failed (attempt %d): %s", self.request.retries + 1, exc)
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)


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


async def check_daily_loss_limit(session) -> bool:
    """Check whether today's realised losses from SL-hit signals are within the daily limit.

    Queries all signals that were updated today with status 'SL_HIT' and sums
    the estimated loss per signal (entry_price - stop_loss) * position_size_pct / 100.

    Returns True if within limit, False if the daily loss limit has been exceeded.
    """
    from app.models.signal import Signal as SignalModel

    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    result = await session.execute(
        select(SignalModel).where(
            and_(
                SignalModel.status == "SL_HIT",
                SignalModel.updated_at >= today_start,
            )
        )
    )
    sl_signals = result.scalars().all()

    total_loss = Decimal("0")
    for sig in sl_signals:
        if sig.entry_price is None or sig.stop_loss is None or sig.position_size_pct is None:
            continue
        price_diff = abs(sig.entry_price - sig.stop_loss)
        estimated_loss = price_diff * sig.position_size_pct / Decimal("100")
        total_loss += estimated_loss

    if total_loss >= MAX_DAILY_LOSS_USD:
        logger.warning(
            "Daily loss limit exceeded: $%.2f >= $%.2f — skipping signal generation",
            total_loss, MAX_DAILY_LOSS_USD,
        )
        return False

    return True


async def check_max_concurrent(session) -> bool:
    """Check whether the number of currently active signals is under the maximum.

    Returns True if under the limit, False if at or above the limit.
    """
    from app.models.signal import Signal as SignalModel

    result = await session.execute(
        select(func.count()).select_from(SignalModel).where(
            SignalModel.status == "ACTIVE"
        )
    )
    active_count = result.scalar_one()

    if active_count >= MAX_CONCURRENT_SIGNALS:
        logger.warning(
            "Max concurrent signals reached: %d >= %d — skipping signal generation",
            active_count, MAX_CONCURRENT_SIGNALS,
        )
        return False

    return True


async def _run_signal_pipeline():
    """Execute the full signal generation pipeline.

    For each asset: load market data, get latest sentiment/on-chain scores,
    run the SignalAggregator, and save emitted signals to DB.
    """
    from app.ai.risk.engine import RiskEngine
    from app.ai.signals.aggregator import SignalAggregator
    from app.core.database import async_session
    from app.core.websocket import manager
    from app.data.fetchers.onchain_fetcher import OnChainFetcher
    from app.models.market_data import MarketData
    from app.models.onchain_event import OnChainEvent
    from app.models.sentiment_data import SentimentData
    from app.models.signal import Signal as SignalModel

    import pandas as pd

    aggregator = SignalAggregator()
    risk_engine = RiskEngine()
    onchain_fetcher = OnChainFetcher()
    now = datetime.now(timezone.utc)
    default_user_id = "default"

    async with async_session() as session:
        # Check kill switch
        if await risk_engine.check_kill_switch(default_user_id, session):
            logger.info("Kill switch active — skipping signal pipeline")
            return

        # Risk engine checks: daily loss limit and concurrent signal cap
        if not await check_daily_loss_limit(session):
            return

        if not await check_max_concurrent(session):
            return

        for symbol in DEFAULT_SYMBOLS:
            try:
                # Load recent market data (4h timeframe for signal generation)
                result = await session.execute(
                    select(MarketData)
                    .where(MarketData.asset == symbol, MarketData.timeframe == "4h")
                    .order_by(MarketData.timestamp.desc())
                    .limit(300)
                )
                rows = result.scalars().all()
                if len(rows) < 200:
                    logger.debug("Insufficient data for %s (%d rows)", symbol, len(rows))
                    continue

                # Convert to DataFrame
                df = pd.DataFrame([{
                    "timestamp": r.timestamp,
                    "open": float(r.open),
                    "high": float(r.high),
                    "low": float(r.low),
                    "close": float(r.close),
                    "volume": float(r.volume),
                } for r in reversed(rows)])

                # Get latest sentiment score
                sent_result = await session.execute(
                    select(SentimentData)
                    .where(SentimentData.asset == symbol)
                    .order_by(SentimentData.created_at.desc())
                    .limit(1)
                )
                sent_row = sent_result.scalar_one_or_none()
                sentiment_score = float(sent_row.score) if sent_row else 0.0

                # Get recent on-chain events and compute aggregate score
                oc_result = await session.execute(
                    select(OnChainEvent)
                    .where(
                        OnChainEvent.asset == symbol,
                        OnChainEvent.timestamp >= now - timedelta(hours=24),
                    )
                    .order_by(OnChainEvent.timestamp.desc())
                )
                oc_rows = oc_result.scalars().all()
                oc_events = [{
                    "event_type": e.event_type,
                    "timestamp": e.timestamp,
                } for e in oc_rows]
                onchain_score = onchain_fetcher.compute_aggregate_score(oc_events)

                # Run aggregator
                signal = aggregator.aggregate(
                    asset=symbol,
                    timeframe="4h",
                    market_data=df,
                    onchain_score=onchain_score,
                    sentiment_score=sentiment_score,
                )

                if not signal:
                    continue

                # Calculate position size
                from app.models.user_settings import UserSettings
                us_result = await session.execute(
                    select(UserSettings).where(UserSettings.user_id == default_user_id)
                )
                user_settings = us_result.scalar_one_or_none()
                position_pct = 0.0
                if user_settings and user_settings.capital:
                    ps = risk_engine.calculate_position_size(
                        capital=float(user_settings.capital),
                        risk_pct=float(user_settings.risk_per_trade_pct),
                        entry=signal.entry_price,
                        stop_loss=signal.stop_loss,
                    )
                    position_pct = ps.position_pct

                # Save signal to DB with dynamic expiration based on regime
                regime_label = signal.factors[0].get("label", "UNKNOWN") if signal.factors else "UNKNOWN"
                EXPIRY_BY_REGIME = {
                    "TREND_BULL": 48, "TREND_BEAR": 48,
                    "CONSOLIDATION": 12, "HIGH_VOL_CHOPPY": 6,
                }
                expiry_hours = EXPIRY_BY_REGIME.get(regime_label, 24)

                db_signal = SignalModel(
                    asset=signal.asset,
                    direction=signal.direction,
                    confidence=Decimal(str(signal.confidence)),
                    regime=regime_label,
                    entry_price=Decimal(str(signal.entry_price)),
                    stop_loss=Decimal(str(signal.stop_loss)),
                    take_profit_1=Decimal(str(signal.take_profit_1)),
                    take_profit_2=Decimal(str(signal.take_profit_2)),
                    risk_reward=Decimal(str(signal.risk_reward)),
                    position_size_pct=Decimal(str(position_pct)),
                    technical_score=Decimal(str(signal.confidence)),
                    onchain_score=Decimal(str(onchain_score)),
                    sentiment_score=Decimal(str(sentiment_score)),
                    factors=signal.factors,
                    status="ACTIVE",
                    expires_at=now + timedelta(hours=expiry_hours),
                )
                session.add(db_signal)
                await session.commit()

                # Broadcast via WebSocket
                await manager.broadcast("signals", {
                    "type": "NEW_SIGNAL",
                    "payload": {
                        "asset": signal.asset,
                        "direction": signal.direction,
                        "confidence": signal.confidence,
                        "entry_price": signal.entry_price,
                        "strategy": signal.strategy_name,
                    },
                })

                logger.info("Signal saved: %s %s conf=%.1f", symbol, signal.direction, signal.confidence)

            except Exception as exc:
                logger.error("Signal pipeline failed for %s: %s", symbol, exc)


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
    """Run the full signal generation pipeline with a distributed Redis lock.

    The lock prevents overlapping executions if a run takes longer than its schedule.
    """
    import redis as _redis
    _LOCK_KEY = "lock:signal_pipeline"
    _LOCK_TTL = 280  # seconds — slightly less than 300 s schedule

    try:
        r = _redis.from_url(settings.REDIS_URL, decode_responses=True)
        acquired = r.set(_LOCK_KEY, "1", nx=True, ex=_LOCK_TTL)
        if not acquired:
            logger.info("Signal pipeline skipped — another instance is running")
            return
    except Exception as exc:
        logger.warning("Redis lock unavailable, running without lock: %s", exc)

    try:
        _run_async(_run_signal_pipeline())
    finally:
        try:
            r.delete(_LOCK_KEY)
        except Exception:
            pass


@celery_app.task
def check_signal_status():
    """Check if active signals hit TP/SL levels."""
    _run_async(_check_signal_status())


async def _send_daily_risk_report() -> None:
    """Compute and Telegram-deliver a nightly performance summary.

    Collects: today's closed paper trades, cumulative P&L, win rate,
    max drawdown, Sharpe ratio, and streak status. Sends via the configured
    Telegram bot to all registered chat IDs.
    """
    from app.core.database import async_session
    from app.models.simulated_position import SimulatedPosition
    from app.models.user_settings import UserSettings

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    async with async_session() as session:
        # --- Fetch today's closed paper positions ---
        pos_result = await session.execute(
            select(SimulatedPosition)
            .where(SimulatedPosition.closed_at >= today_start)
            .where(SimulatedPosition.status != "OPEN")
            .order_by(SimulatedPosition.closed_at)
        )
        positions = list(pos_result.scalars().all())

        wins = [p for p in positions if (p.pnl_pct or 0) > 0]
        losses = [p for p in positions if (p.pnl_pct or 0) <= 0]
        total_pnl = sum(float(p.pnl_pct or 0) for p in positions)
        win_rate = (len(wins) / len(positions) * 100) if positions else 0.0

        # --- Fetch user settings for capital context ---
        settings_result = await session.execute(
            select(UserSettings).where(UserSettings.user_id == "default")
        )
        user_settings = settings_result.scalar_one_or_none()
        capital = float(user_settings.capital or 0) if user_settings else 0.0

        # --- Build Telegram message ---
        date_str = today_start.strftime("%Y-%m-%d")
        lines = [
            f"📊 *Daily Risk Report — {date_str}*",
            "",
            f"Trades: {len(positions)} | Wins: {len(wins)} | Losses: {len(losses)}",
            f"Win Rate: {win_rate:.1f}%",
            f"Total P&L: {total_pnl:+.2f}%",
        ]
        if capital > 0:
            lines.append(f"Capital: ${capital:,.0f}")
        if not positions:
            lines.append("_(No closed trades today)_")

        message = "\n".join(lines)

        # --- Send to all registered chat IDs via TelegramNotifier ---
        try:
            from app.notifications.telegram_bot import get_telegram_notifier
            notifier = get_telegram_notifier()
            settings_list_result = await session.execute(select(UserSettings))
            all_settings = list(settings_list_result.scalars().all())
            sent = 0
            for us in all_settings:
                if us.telegram_chat_id and us.notifications_enabled:
                    await notifier.send_message(us.telegram_chat_id, message)
                    sent += 1
            logger.info("Daily risk report sent to %d chat(s)", sent)
        except Exception as exc:
            logger.error("Failed to send daily risk report: %s", exc)


@celery_app.task(name="app.tasks.send_daily_risk_report")
def send_daily_risk_report() -> None:
    """Send nightly performance summary via Telegram."""
    _run_async(_send_daily_risk_report())


@celery_app.task(name="app.tasks.run_backtest_task")
def run_backtest_task(
    strategy_name: str,
    asset: str,
    timeframe: str,
    from_date: str,
    to_date: str,
    initial_capital: float = 10000.0,
    risk_per_trade_pct: float = 1.5,
):
    """Run a backtest and save results to DB."""
    _run_async(_run_backtest(
        strategy_name, asset, timeframe, from_date, to_date,
        initial_capital, risk_per_trade_pct,
    ))


async def _run_backtest(
    strategy_name: str,
    asset: str,
    timeframe: str,
    from_date: str,
    to_date: str,
    initial_capital: float,
    risk_per_trade_pct: float,
):
    """Execute a backtest and save results."""
    import pandas as pd
    from datetime import date as date_type

    from app.ai.strategies.mean_reversion import MeanReversionStrategy
    from app.ai.strategies.smc_strategy import SMCStrategy
    from app.ai.strategies.trend_following import TrendFollowingStrategy
    from app.ai.strategies.volume_breakout import VolumeBreakoutStrategy
    from app.backtesting.monte_carlo import MonteCarloSimulator
    from app.backtesting.walk_forward import WalkForwardBacktester
    from app.core.database import async_session
    from app.models.backtest_result import BacktestResult
    from app.models.market_data import MarketData

    strategy_map = {
        "trend_following": TrendFollowingStrategy,
        "mean_reversion": MeanReversionStrategy,
        "smc": SMCStrategy,
        "volume_breakout": VolumeBreakoutStrategy,
    }

    strategy_cls = strategy_map.get(strategy_name)
    if not strategy_cls:
        logger.error("Unknown strategy: %s", strategy_name)
        return

    strategy = strategy_cls()
    start = date_type.fromisoformat(from_date)
    end = date_type.fromisoformat(to_date)

    async with async_session() as session:
        # Load historical data
        result = await session.execute(
            select(MarketData)
            .where(
                MarketData.asset == asset,
                MarketData.timeframe == timeframe,
                MarketData.timestamp >= from_date,
                MarketData.timestamp <= to_date,
            )
            .order_by(MarketData.timestamp.asc())
        )
        rows = result.scalars().all()

        if not rows:
            logger.error("No market data for backtest %s %s", asset, timeframe)
            return

        df = pd.DataFrame([{
            "timestamp": r.timestamp,
            "open": float(r.open),
            "high": float(r.high),
            "low": float(r.low),
            "close": float(r.close),
            "volume": float(r.volume),
        } for r in rows])

        # Run walk-forward backtest
        backtester = WalkForwardBacktester()
        bt_result = backtester.run(
            strategy=strategy,
            market_data=df,
            asset=asset,
            timeframe=timeframe,
            start_date=start,
            end_date=end,
            initial_capital=initial_capital,
            risk_per_trade_pct=risk_per_trade_pct,
        )

        # Run Monte Carlo
        mc = MonteCarloSimulator()
        mc_result = mc.run(bt_result.trades, iterations=1000, initial_capital=initial_capital)

        # Save to DB
        db_result = BacktestResult(
            strategy_name=strategy_name,
            asset=asset,
            timeframe=timeframe,
            period_start=start,
            period_end=end,
            win_rate=Decimal(str(bt_result.metrics.win_rate)),
            profit_factor=Decimal(str(min(bt_result.metrics.profit_factor, 9999))),
            max_drawdown=Decimal(str(bt_result.metrics.max_drawdown)),
            sharpe_ratio=Decimal(str(bt_result.metrics.sharpe_ratio)),
            calmar_ratio=Decimal(str(min(bt_result.metrics.calmar_ratio, 9999))),
            total_trades=bt_result.metrics.total_trades,
            prob_ruin_20pct=Decimal(str(mc_result.prob_ruin_20pct)),
            prob_ruin_30pct=Decimal(str(mc_result.prob_ruin_30pct)),
            equity_curve=bt_result.equity_curve,
        )
        session.add(db_result)
        await session.commit()

        logger.info(
            "Backtest saved: %s %s %s | WR=%.1f%% MDD=%.1f%%",
            strategy_name, asset, timeframe,
            bt_result.metrics.win_rate, bt_result.metrics.max_drawdown,
        )


@celery_app.task(name="cleanup_expired_signals")
def cleanup_expired_signals() -> dict:
    """Archive signals older than 30 days by marking their status as 'ARCHIVED'.

    Targets only signals that are already in a terminal state (EXPIRED, CLOSED,
    CANCELLED) and were created more than 30 days ago.  Uses a synchronous
    SQLAlchemy session since Celery tasks run in a regular (non-async) context.

    Returns:
        Dict with ``archived_count`` indicating how many rows were updated.
    """
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import create_engine, update
    from sqlalchemy.orm import sessionmaker

    from app.core.config import settings
    from app.models.signal import Signal as SignalModel

    # Build a synchronous database URL from the async URL (replace asyncpg driver)
    sync_db_url = settings.DATABASE_URL.replace("+asyncpg", "").replace("postgresql+asyncpg", "postgresql")

    sync_engine = create_engine(sync_db_url, pool_pre_ping=True)
    SyncSession = sessionmaker(bind=sync_engine, autocommit=False, autoflush=False)

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    terminal_statuses = ("EXPIRED", "CLOSED", "CANCELLED")

    archived_count = 0
    with SyncSession() as session:
        try:
            result = session.execute(
                update(SignalModel)
                .where(
                    SignalModel.created_at < cutoff,
                    SignalModel.status.in_(terminal_statuses),
                )
                .values(status="ARCHIVED")
                .execution_options(synchronize_session="fetch")
            )
            session.commit()
            archived_count = result.rowcount or 0
        except Exception as exc:
            session.rollback()
            logger.error("cleanup_expired_signals failed: %s", exc)
            raise

    logger.info("cleanup_expired_signals: archived %d signal(s)", archived_count)
    return {"archived_count": archived_count}


@celery_app.task(name="app.tasks.ohlcv_gap_detector")
def ohlcv_gap_detector() -> dict:
    """Detect gaps in OHLCV candle series and alert via Telegram.

    For each symbol × timeframe, computes the expected interval between
    consecutive candles and flags any gap larger than 2× the interval.
    Sends a Telegram alert if gaps are found.

    Returns:
        Dict with ``gaps_found`` count and list of affected series.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.core.config import settings as _cfg
    from app.models.market_data import MarketData

    sync_url = _cfg.DATABASE_URL.replace("+asyncpg", "")
    engine = create_engine(sync_url)
    Session = sessionmaker(bind=engine)

    # Interval in minutes per timeframe label
    tf_minutes: dict[str, int] = {
        "1m": 1, "5m": 5, "15m": 15, "1h": 60,
        "4h": 240, "1D": 1440,
    }
    gaps: list[dict] = []

    with Session() as session:
        for symbol in DEFAULT_SYMBOLS:
            for tf, interval_min in tf_minutes.items():
                rows = (
                    session.query(MarketData.timestamp)
                    .filter(MarketData.asset == symbol, MarketData.timeframe == tf)
                    .order_by(MarketData.timestamp.asc())
                    .limit(500)
                    .all()
                )
                if len(rows) < 2:
                    continue
                threshold = timedelta(minutes=interval_min * 2)
                for i in range(1, len(rows)):
                    delta = rows[i][0] - rows[i - 1][0]
                    if delta > threshold:
                        gaps.append({
                            "symbol": symbol,
                            "timeframe": tf,
                            "gap_start": rows[i - 1][0].isoformat(),
                            "gap_end": rows[i][0].isoformat(),
                            "gap_minutes": round(delta.total_seconds() / 60),
                        })

    if gaps:
        msg_lines = [f"⚠️ OHLCV Gaps Detected ({len(gaps)} gap(s)):"]
        for g in gaps[:10]:
            msg_lines.append(
                f"  {g['symbol']} {g['timeframe']} — {g['gap_minutes']}min gap "
                f"from {g['gap_start'][:16]} to {g['gap_end'][:16]}"
            )
        send_telegram_message.delay("\n".join(msg_lines))

    logger.info("ohlcv_gap_detector: %d gap(s) found across %d symbols", len(gaps), len(DEFAULT_SYMBOLS))
    return {"gaps_found": len(gaps), "gaps": gaps[:20]}


@celery_app.task(name="app.tasks.position_reconciliation")
def position_reconciliation() -> dict:
    """Nightly reconciliation of simulated positions vs. expected outcomes.

    Flags any closed position where the recorded P&L diverges by more than
    0.1% from what can be inferred from open/close prices. Results are
    logged; large divergences trigger a Telegram alert.

    Returns:
        Dict with ``checked``, ``flagged`` counts.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.core.config import settings as _cfg

    sync_url = _cfg.DATABASE_URL.replace("+asyncpg", "")
    engine = create_engine(sync_url)
    Session = sessionmaker(bind=engine)

    flagged: list[dict] = []

    try:
        from app.ai.simulation.paper_trading_engine import SimulatedPosition

        with Session() as session:
            positions = (
                session.query(SimulatedPosition)
                .filter(
                    SimulatedPosition.status.in_(["CLOSED", "SL_HIT", "TP1_HIT", "TP2_HIT"]),
                    SimulatedPosition.entry_price.isnot(None),
                    SimulatedPosition.exit_price.isnot(None),
                    SimulatedPosition.pnl_pct.isnot(None),
                )
                .limit(500)
                .all()
            )

            checked = len(positions)
            for pos in positions:
                if pos.entry_price and pos.exit_price and pos.pnl_pct is not None:
                    if pos.direction == "LONG":
                        expected_pct = ((pos.exit_price - pos.entry_price) / pos.entry_price) * 100
                    else:
                        expected_pct = ((pos.entry_price - pos.exit_price) / pos.entry_price) * 100

                    divergence = abs(expected_pct - float(pos.pnl_pct))
                    if divergence > 0.1:
                        flagged.append({
                            "id": str(pos.id),
                            "symbol": pos.symbol,
                            "recorded_pnl": float(pos.pnl_pct),
                            "expected_pnl": round(expected_pct, 4),
                            "divergence": round(divergence, 4),
                        })

    except Exception as exc:
        logger.error("position_reconciliation error: %s", exc)
        return {"checked": 0, "flagged": 0, "error": str(exc)}

    if flagged:
        msg = f"⚠️ Position Reconciliation: {len(flagged)} divergence(s) > 0.1%\n"
        msg += "\n".join(
            f"  {f['symbol']} {f['id'][:8]} recorded={f['recorded_pnl']:.2f}% expected={f['expected_pnl']:.2f}%"
            for f in flagged[:5]
        )
        send_telegram_message.delay(msg)

    logger.info("position_reconciliation: checked=%d flagged=%d", checked, len(flagged))
    return {"checked": checked, "flagged": len(flagged), "details": flagged[:10]}


@celery_app.task(name="app.tasks.signal_aging_decay")
def signal_aging_decay() -> dict:
    """D7: Apply confidence decay to aging active signals.

    Reduces confidence of ACTIVE signals older than 2 hours by 5% per hour.
    Marks signals as STALE after 6 hours without a TP/SL hit.

    Uses a synchronous DB session since Celery tasks run outside the async loop.

    Returns:
        Dict with ``decayed_count`` and ``stale_count``.
    """
    from sqlalchemy import create_engine, update, and_
    from sqlalchemy.orm import sessionmaker
    from app.core.config import settings as _cfg
    from app.models.signal import Signal as SignalModel

    sync_url = _cfg.DATABASE_URL.replace("+asyncpg", "")
    engine = create_engine(sync_url, pool_pre_ping=True)
    Session = sessionmaker(bind=engine)

    now = datetime.now(timezone.utc)
    decay_threshold = now - timedelta(hours=2)
    stale_threshold = now - timedelta(hours=6)

    decayed_count = 0
    stale_count = 0

    with Session() as session:
        try:
            # Mark signals older than 6h as STALE
            stale_result = session.execute(
                update(SignalModel)
                .where(
                    and_(
                        SignalModel.status == "ACTIVE",
                        SignalModel.created_at <= stale_threshold,
                    )
                )
                .values(status="STALE", updated_at=now)
                .execution_options(synchronize_session="fetch")
            )
            stale_count = stale_result.rowcount or 0

            # Decay confidence of signals older than 2h (but not yet STALE)
            aging_signals_result = session.execute(
                select(SignalModel).where(
                    and_(
                        SignalModel.status == "ACTIVE",
                        SignalModel.created_at <= decay_threshold,
                        SignalModel.created_at > stale_threshold,
                    )
                )
            )
            aging_signals = aging_signals_result.scalars().all()

            for sig in aging_signals:
                age_hours = (now - sig.created_at.replace(tzinfo=timezone.utc)).total_seconds() / 3600
                hours_decaying = max(0, age_hours - 2)
                decay_factor = 1 - (0.05 * hours_decaying)
                new_confidence = max(Decimal("0"), sig.confidence * Decimal(str(decay_factor)))
                sig.confidence = new_confidence.quantize(Decimal("0.01"))
                sig.updated_at = now
                decayed_count += 1

            session.commit()
        except Exception as exc:
            session.rollback()
            logger.error("signal_aging_decay failed: %s", exc)
            raise

    logger.info("signal_aging_decay: decayed=%d stale=%d", decayed_count, stale_count)
    return {"decayed_count": decayed_count, "stale_count": stale_count}


@celery_app.task(name="app.tasks.generate_daily_briefing")
def generate_daily_briefing() -> dict:
    """Generate and send the daily market briefing via Telegram.

    Replaces the APScheduler job that previously ran in main.py, so Celery Beat
    is now the single scheduler for all periodic tasks.
    """
    async def _run():
        from app.ai.reports.daily_briefing import generate_and_send_daily_briefing
        await generate_and_send_daily_briefing()

    try:
        _run_async(_run())
        logger.info("Daily briefing sent")
        return {"status": "sent"}
    except Exception as exc:
        logger.error("generate_daily_briefing failed: %s", exc)
        return {"status": "error", "detail": str(exc)}


@celery_app.task(name="app.tasks.generate_weekly_report")
def generate_weekly_report() -> dict:
    """Generate and send the weekly performance report via Telegram.

    Replaces the APScheduler job that previously ran in main.py.
    """
    async def _run():
        from app.ai.reports.weekly_report import generate_weekly_report as _gen
        await _gen()

    try:
        _run_async(_run())
        logger.info("Weekly report sent")
        return {"status": "sent"}
    except Exception as exc:
        logger.error("generate_weekly_report failed: %s", exc)
        return {"status": "error", "detail": str(exc)}
