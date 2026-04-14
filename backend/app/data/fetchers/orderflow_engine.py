"""Order Flow Engine — aggTrade ingestion, price clustering, and delta analysis.

Connects to Binance aggTrade WebSocket, aggregates trades into price-level
clusters within configurable time windows, and tracks cumulative delta for
order flow analysis.
"""

import asyncio
import json
import logging
import time
from collections import defaultdict, deque
from decimal import Decimal, ROUND_DOWN
from typing import Any, Optional

import websockets
from websockets.exceptions import ConnectionClosed

logger = logging.getLogger(__name__)

WS_BASE_URL = "wss://stream.binance.com:9443"
MAX_RETRIES = 10
RETRY_BASE_DELAY = 2.0
MAX_HISTORY_WINDOWS = 500
MAX_DELTA_HISTORY = 5000


class PriceCluster:
    """Aggregated volume data at a single price level."""

    __slots__ = ("price", "bid_vol", "ask_vol", "trade_count")

    def __init__(self, price: float) -> None:
        self.price = price
        self.bid_vol: float = 0.0
        self.ask_vol: float = 0.0
        self.trade_count: int = 0

    @property
    def delta(self) -> float:
        """Net delta: ask_vol - bid_vol."""
        return self.ask_vol - self.bid_vol

    def to_dict(self, imbalance_threshold: float = 3.0) -> dict[str, Any]:
        """Serialize cluster to dict with optional imbalance flag."""
        imbalance: Optional[str] = None
        if self.bid_vol > 0 and self.ask_vol / self.bid_vol >= imbalance_threshold:
            imbalance = "BUY"
        elif self.ask_vol > 0 and self.bid_vol / self.ask_vol >= imbalance_threshold:
            imbalance = "SELL"

        return {
            "price": self.price,
            "bid_vol": round(self.bid_vol, 6),
            "ask_vol": round(self.ask_vol, 6),
            "delta": round(self.delta, 6),
            "trades": self.trade_count,
            "imbalance": imbalance,
        }


class TimeWindow:
    """A single time window containing price clusters."""

    __slots__ = ("start_time", "end_time", "clusters", "_open", "_high", "_low", "_close", "_total_volume")

    def __init__(self, start_time: int, end_time: int) -> None:
        self.start_time = start_time
        self.end_time = end_time
        self.clusters: dict[float, PriceCluster] = {}
        self._open: Optional[float] = None
        self._high: Optional[float] = None
        self._low: Optional[float] = None
        self._close: Optional[float] = None
        self._total_volume: float = 0.0

    def add_trade(self, snapped_price: float, raw_price: float, qty: float, is_buy: bool) -> None:
        """Add a trade to this window."""
        if snapped_price not in self.clusters:
            self.clusters[snapped_price] = PriceCluster(snapped_price)

        cluster = self.clusters[snapped_price]
        cluster.trade_count += 1

        if is_buy:
            cluster.ask_vol += qty
        else:
            cluster.bid_vol += qty

        # Track OHLC from raw prices
        if self._open is None:
            self._open = raw_price
        self._close = raw_price
        if self._high is None or raw_price > self._high:
            self._high = raw_price
        if self._low is None or raw_price < self._low:
            self._low = raw_price

        self._total_volume += qty

    @property
    def delta(self) -> float:
        """Total delta for this window."""
        return sum(c.delta for c in self.clusters.values())

    def to_dict(self, imbalance_threshold: float = 3.0) -> dict[str, Any]:
        """Serialize window to API response format."""
        sorted_clusters = sorted(self.clusters.values(), key=lambda c: c.price)
        return {
            "time": self.start_time,
            "open": self._open or 0,
            "high": self._high or 0,
            "low": self._low or 0,
            "close": self._close or 0,
            "total_volume": round(self._total_volume, 6),
            "delta": round(self.delta, 6),
            "clusters": [c.to_dict(imbalance_threshold) for c in sorted_clusters],
        }


class InMemoryStorage:
    """In-memory fallback storage when Redis is not available.

    Stores finalized windows in a deque with a maximum size to prevent
    unbounded memory growth.
    """

    def __init__(self, max_windows: int = MAX_HISTORY_WINDOWS) -> None:
        self._store: dict[str, deque[dict[str, Any]]] = defaultdict(
            lambda: deque(maxlen=max_windows)
        )

    async def store_window(self, key: str, window_data: dict[str, Any]) -> None:
        """Store a finalized window."""
        self._store[key].append(window_data)

    async def get_windows(self, key: str, limit: int = 30) -> list[dict[str, Any]]:
        """Retrieve recent windows."""
        data = self._store.get(key)
        if not data:
            return []
        items = list(data)
        return items[-limit:]


class RedisStorage:
    """Redis-backed storage for finalized order flow windows."""

    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url
        self._redis: Any = None

    async def connect(self) -> bool:
        """Attempt to connect to Redis. Returns True on success."""
        try:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(
                self._redis_url, decode_responses=True
            )
            await self._redis.ping()
            logger.info("RedisStorage connected to %s", self._redis_url)
            return True
        except Exception as exc:
            logger.warning("Redis not available, will use in-memory storage: %s", exc)
            self._redis = None
            return False

    async def store_window(self, key: str, window_data: dict[str, Any]) -> None:
        """Store window data in a Redis sorted set keyed by timestamp."""
        if self._redis is None:
            return
        try:
            score = window_data["time"]
            value = json.dumps(window_data)
            await self._redis.zadd(key, {value: score})
            # Trim to keep only the most recent windows
            await self._redis.zremrangebyrank(key, 0, -(MAX_HISTORY_WINDOWS + 1))
        except Exception as exc:
            logger.warning("Redis store failed: %s", exc)

    async def get_windows(self, key: str, limit: int = 30) -> list[dict[str, Any]]:
        """Retrieve recent windows from Redis sorted set."""
        if self._redis is None:
            return []
        try:
            raw = await self._redis.zrange(key, -limit, -1)
            return [json.loads(item) for item in raw]
        except Exception as exc:
            logger.warning("Redis get failed: %s", exc)
            return []

    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis is not None:
            await self._redis.close()


class OrderFlowEngine:
    """Connects to Binance aggTrade WebSocket, aggregates trades into
    price clusters within time windows, and tracks cumulative delta.

    Args:
        symbol: Trading pair symbol (e.g. "BTCUSDT").
        tick_size: Price bucketing precision (e.g. 1.0 for BTC, 0.01 for SOL).
        window_seconds: Duration of each aggregation window in seconds.
        redis_url: Optional Redis URL. Falls back to in-memory if unavailable.
    """

    def __init__(
        self,
        symbol: str,
        tick_size: float = 1.0,
        window_seconds: int = 60,
        redis_url: Optional[str] = None,
    ) -> None:
        self.symbol = symbol.upper()
        self.tick_size = Decimal(str(tick_size))
        self.window_seconds = window_seconds
        self._redis_url = redis_url

        # Current window
        self._current_window: Optional[TimeWindow] = None
        self._current_window_start: int = 0

        # Cumulative delta tracking
        self.cumulative_delta: float = 0.0
        self.session_delta_history: deque[dict[str, Any]] = deque(maxlen=MAX_DELTA_HISTORY)

        # Finalized windows kept in memory for fast API access
        self._finalized_windows: deque[dict[str, Any]] = deque(maxlen=MAX_HISTORY_WINDOWS)

        # Storage backend
        self._storage: InMemoryStorage | RedisStorage = InMemoryStorage()

        # Control
        self._running = False
        self._ws_task: Optional[asyncio.Task] = None
        self._current_price: float = 0.0

        # Trade counter for logging
        self._trade_count: int = 0

    async def _init_storage(self) -> None:
        """Initialize storage backend — try Redis first, fall back to in-memory."""
        if self._redis_url:
            redis_storage = RedisStorage(self._redis_url)
            connected = await redis_storage.connect()
            if connected:
                self._storage = redis_storage
                return
        self._storage = InMemoryStorage()
        logger.info("OrderFlowEngine[%s] using in-memory storage", self.symbol)

    def _get_window_start(self, timestamp_s: float) -> int:
        """Compute the start of the time window containing the given timestamp."""
        return int(timestamp_s // self.window_seconds) * self.window_seconds

    def _snap_price(self, price: float) -> float:
        """Round price down to the nearest tick size.

        Uses Decimal arithmetic for precision.
        """
        d_price = Decimal(str(price))
        snapped = (d_price / self.tick_size).to_integral_value(rounding=ROUND_DOWN) * self.tick_size
        return float(snapped)

    def _ensure_window(self, timestamp_s: float) -> None:
        """Ensure the current window covers the given timestamp.

        If the timestamp falls outside the current window, finalize the
        current window and start a new one.
        """
        window_start = self._get_window_start(timestamp_s)

        if self._current_window is None or window_start != self._current_window_start:
            # Finalize existing window if any
            if self._current_window is not None and self._current_window.clusters:
                self._finalize_current_window()

            # Start new window
            self._current_window_start = window_start
            self._current_window = TimeWindow(
                start_time=window_start,
                end_time=window_start + self.window_seconds,
            )

    def _finalize_current_window(self) -> None:
        """Finalize the current window: store it and schedule async persistence."""
        if self._current_window is None:
            return

        window_data = self._current_window.to_dict()
        self._finalized_windows.append(window_data)

        # Record delta in session history
        self.session_delta_history.append({
            "time": self._current_window.start_time,
            "value": round(self.cumulative_delta, 6),
        })

        # Schedule async storage (fire and forget)
        storage_key = f"orderflow:{self.symbol}:{self.window_seconds}:{self._current_window.start_time}"
        asyncio.create_task(self._storage.store_window(storage_key, window_data))

        logger.debug(
            "OrderFlowEngine[%s] finalized window %d: delta=%.4f, clusters=%d",
            self.symbol,
            self._current_window.start_time,
            self._current_window.delta,
            len(self._current_window.clusters),
        )

    def _process_trade(self, trade: dict[str, Any]) -> None:
        """Bucket a single aggTrade into the current price cluster.

        Binance aggTrade fields:
            p: price
            q: quantity
            T: trade time (ms)
            m: is buyer the maker? True = SELL (maker is buyer, taker sells),
               False = BUY (maker is seller, taker buys)
        """
        price = float(trade["p"])
        qty = float(trade["q"])
        timestamp_s = trade["T"] / 1000.0
        # m=True means buyer is maker, which means the trade was initiated
        # by a seller (market sell) — this is a SELL.
        # m=False means buyer is taker (market buy) — this is a BUY.
        is_buy = not trade["m"]

        snapped = self._snap_price(price)
        self._current_price = price

        self._ensure_window(timestamp_s)

        if self._current_window is not None:
            self._current_window.add_trade(snapped, price, qty, is_buy)

        # Update cumulative delta
        delta_change = qty if is_buy else -qty
        self.cumulative_delta += delta_change

        self._trade_count += 1

    async def start(self) -> None:
        """Connect to aggTrade WebSocket and start processing trades."""
        await self._init_storage()
        self._running = True
        symbol_lower = self.symbol.lower()
        url = f"{WS_BASE_URL}/ws/{symbol_lower}@aggTrade"

        logger.info(
            "OrderFlowEngine[%s] starting (tick=%.4f, window=%ds)",
            self.symbol, float(self.tick_size), self.window_seconds,
        )

        attempt = 0
        while self._running and attempt < MAX_RETRIES:
            attempt += 1
            try:
                await self._run_ws(url)
                # If _run_ws returns normally (stopped), break
                if not self._running:
                    break
            except ConnectionClosed as exc:
                logger.warning(
                    "OrderFlowEngine[%s] WS closed: %s (attempt %d/%d)",
                    self.symbol, exc, attempt, MAX_RETRIES,
                )
            except Exception as exc:
                logger.error(
                    "OrderFlowEngine[%s] WS error: %s (attempt %d/%d)",
                    self.symbol, exc, attempt, MAX_RETRIES,
                )

            if self._running and attempt < MAX_RETRIES:
                delay = min(RETRY_BASE_DELAY * (2 ** (attempt - 1)), 60.0)
                logger.info(
                    "OrderFlowEngine[%s] reconnecting in %.1fs...",
                    self.symbol, delay,
                )
                await asyncio.sleep(delay)
                # Reset attempt counter on successful long-running connection
            elif self._running:
                logger.error(
                    "OrderFlowEngine[%s] all %d reconnect attempts exhausted",
                    self.symbol, MAX_RETRIES,
                )
                self._running = False

    async def _run_ws(self, url: str) -> None:
        """Internal WebSocket loop — processes aggTrade messages."""
        async with websockets.connect(url, ping_interval=30, ping_timeout=10) as ws:
            logger.info("OrderFlowEngine[%s] WebSocket connected", self.symbol)
            # Reset retry counter on successful connection
            while self._running:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=30.0)
                except asyncio.TimeoutError:
                    # No trade in 30s — send ping to keep alive
                    continue

                trade = json.loads(raw)

                if trade.get("e") != "aggTrade":
                    continue

                self._process_trade(trade)

                # Periodic logging
                if self._trade_count % 1000 == 0:
                    logger.info(
                        "OrderFlowEngine[%s] processed %d trades, cumDelta=%.4f",
                        self.symbol, self._trade_count, self.cumulative_delta,
                    )

    async def stop(self) -> None:
        """Stop the engine and finalize the current window."""
        logger.info("OrderFlowEngine[%s] stopping...", self.symbol)
        self._running = False

        # Finalize current window
        if self._current_window is not None and self._current_window.clusters:
            self._finalize_current_window()

        # Close storage
        if isinstance(self._storage, RedisStorage):
            await self._storage.close()

        logger.info(
            "OrderFlowEngine[%s] stopped. Total trades processed: %d",
            self.symbol, self._trade_count,
        )

    def get_current_window(self) -> Optional[dict[str, Any]]:
        """Return the current (in-progress) window's clusters."""
        if self._current_window is None:
            return None
        return self._current_window.to_dict()

    def get_cumulative_delta(self) -> float:
        """Return running total delta since session start."""
        return round(self.cumulative_delta, 6)

    def get_recent_windows(self, limit: int = 30) -> list[dict[str, Any]]:
        """Return recent finalized windows from in-memory buffer."""
        items = list(self._finalized_windows)
        windows = items[-limit:]

        # Append current window if it has data
        current = self.get_current_window()
        if current and current["total_volume"] > 0:
            windows.append(current)

        return windows

    def detect_imbalances(self, threshold: float = 3.0) -> list[dict[str, Any]]:
        """Find price levels where ask > bid*threshold or vice versa.

        Scans the current window for significant order flow imbalances.

        Args:
            threshold: Ratio threshold for detecting imbalances.

        Returns:
            List of imbalance dicts with price, type, and ratio.
        """
        imbalances: list[dict[str, Any]] = []

        if self._current_window is None:
            return imbalances

        for cluster in self._current_window.clusters.values():
            if cluster.bid_vol > 0 and cluster.ask_vol / cluster.bid_vol >= threshold:
                imbalances.append({
                    "price": cluster.price,
                    "type": "BUY",
                    "ratio": round(cluster.ask_vol / cluster.bid_vol, 2),
                })
            elif cluster.ask_vol > 0 and cluster.bid_vol / cluster.ask_vol >= threshold:
                imbalances.append({
                    "price": cluster.price,
                    "type": "SELL",
                    "ratio": round(cluster.bid_vol / cluster.ask_vol, 2),
                })

        return sorted(imbalances, key=lambda x: x["ratio"], reverse=True)

    @property
    def current_price(self) -> float:
        """Last observed trade price."""
        return self._current_price

    @property
    def is_running(self) -> bool:
        """Whether the engine is currently running."""
        return self._running


class OrderFlowManager:
    """Manages multiple OrderFlowEngine instances for different symbols.

    Provides a centralized registry for starting/stopping engines and
    querying order flow data across symbols.
    """

    def __init__(self, redis_url: Optional[str] = None) -> None:
        self._engines: dict[str, OrderFlowEngine] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._redis_url = redis_url

    # Default tick sizes per symbol
    TICK_SIZES: dict[str, float] = {
        "BTCUSDT": 1.0,
        "ETHUSDT": 0.1,
        "SOLUSDT": 0.01,
    }

    def get_engine(self, symbol: str) -> Optional[OrderFlowEngine]:
        """Get an engine by symbol."""
        return self._engines.get(symbol.upper())

    async def start_engine(
        self,
        symbol: str,
        tick_size: Optional[float] = None,
        window_seconds: int = 60,
    ) -> OrderFlowEngine:
        """Start an OrderFlowEngine for the given symbol.

        Args:
            symbol: Trading pair (e.g. "BTCUSDT").
            tick_size: Price bucketing size. Defaults based on symbol.
            window_seconds: Aggregation window duration.

        Returns:
            The started OrderFlowEngine instance.
        """
        symbol = symbol.upper()
        if symbol in self._engines and self._engines[symbol].is_running:
            logger.info("OrderFlowEngine[%s] already running", symbol)
            return self._engines[symbol]

        if tick_size is None:
            tick_size = self.TICK_SIZES.get(symbol, 1.0)

        engine = OrderFlowEngine(
            symbol=symbol,
            tick_size=tick_size,
            window_seconds=window_seconds,
            redis_url=self._redis_url,
        )
        self._engines[symbol] = engine

        task = asyncio.create_task(engine.start())
        self._tasks[symbol] = task

        # Handle task exceptions without crashing the application
        task.add_done_callback(lambda t: self._handle_task_done(symbol, t))

        logger.info("OrderFlowManager started engine for %s", symbol)
        return engine

    def _handle_task_done(self, symbol: str, task: asyncio.Task) -> None:
        """Callback for when an engine task completes."""
        try:
            exc = task.exception()
            if exc:
                logger.error(
                    "OrderFlowEngine[%s] task failed: %s", symbol, exc,
                )
        except asyncio.CancelledError:
            logger.info("OrderFlowEngine[%s] task cancelled", symbol)

    async def stop_engine(self, symbol: str) -> None:
        """Stop an engine for the given symbol."""
        symbol = symbol.upper()
        engine = self._engines.get(symbol)
        if engine:
            await engine.stop()

        task = self._tasks.pop(symbol, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        self._engines.pop(symbol, None)
        logger.info("OrderFlowManager stopped engine for %s", symbol)

    async def stop_all(self) -> None:
        """Stop all running engines."""
        symbols = list(self._engines.keys())
        for symbol in symbols:
            await self.stop_engine(symbol)
        logger.info("OrderFlowManager stopped all engines")

    def list_engines(self) -> dict[str, bool]:
        """Return dict of symbol -> is_running for all registered engines."""
        return {
            symbol: engine.is_running
            for symbol, engine in self._engines.items()
        }


# Singleton manager instance
_manager: Optional[OrderFlowManager] = None


def get_orderflow_manager() -> OrderFlowManager:
    """Get or create the singleton OrderFlowManager."""
    global _manager
    if _manager is None:
        from app.core.config import settings
        _manager = OrderFlowManager(redis_url=settings.REDIS_URL)
    return _manager
