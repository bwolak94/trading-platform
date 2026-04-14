"""Liquidation Engine — Binance Futures forceOrder ingestion and heatmap generation.

Connects to Binance Futures liquidation stream, aggregates force orders into
price bins with time decay, fetches Open Interest, and calculates theoretical
liquidation zones for various leverage levels.
"""

import asyncio
import json
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx
import websockets
from websockets.exceptions import ConnectionClosed

logger = logging.getLogger(__name__)

WS_LIQUIDATION_URL = "wss://fstream.binance.com/ws/!forceOrder@arr"
FAPI_BASE_URL = "https://fapi.binance.com"
MAX_RETRIES = 10
RETRY_BASE_DELAY = 2.0
MAX_FORCE_ORDERS = 5000
HALF_LIFE_HOURS = 24.0
OI_POLL_INTERVAL = 30.0

# Bin sizes per symbol prefix
BIN_SIZES: dict[str, float] = {
    "BTC": 10.0,
    "ETH": 1.0,
    "SOL": 0.1,
}

DEFAULT_BIN_SIZE = 1.0


def _get_bin_size(symbol: str) -> float:
    """Return the price bin size for a given symbol."""
    symbol_upper = symbol.upper()
    for prefix, size in BIN_SIZES.items():
        if symbol_upper.startswith(prefix):
            return size
    return DEFAULT_BIN_SIZE


def _snap_to_bin(price: float, bin_size: float) -> float:
    """Snap a price down to the nearest bin boundary."""
    return (price // bin_size) * bin_size


def _decay_weight(hours_ago: float) -> float:
    """Calculate time decay weight: 0.5^(hours_ago / 24)."""
    if hours_ago <= 0:
        return 1.0
    return 0.5 ** (hours_ago / HALF_LIFE_HOURS)


@dataclass
class ForceOrder:
    """A single forced liquidation event."""

    symbol: str
    side: str  # "BUY" or "SELL" — BUY means short was liquidated, SELL means long was liquidated
    price: float
    quantity: float
    usd_value: float
    timestamp: float  # unix seconds

    def to_dict(self) -> dict[str, Any]:
        """Serialize to API response format."""
        return {
            "symbol": self.symbol,
            "side": self.side,
            "price": self.price,
            "quantity": self.quantity,
            "usd_value": round(self.usd_value, 2),
            "timestamp": self.timestamp,
        }


@dataclass
class LiquidationBin:
    """Aggregated liquidation data at a price bin."""

    price_low: float
    price_high: float
    long_usd: float = 0.0   # USD of long liquidations (SELL force orders)
    short_usd: float = 0.0  # USD of short liquidations (BUY force orders)
    count: int = 0
    last_updated: float = 0.0
    # Raw entries with timestamps for decay calculation
    _entries: list[tuple[float, float, str]] = field(default_factory=list)  # (timestamp, usd, side)

    @property
    def total_usd(self) -> float:
        """Total USD value of liquidations in this bin."""
        return self.long_usd + self.short_usd

    @property
    def price_mid(self) -> float:
        """Midpoint price of this bin."""
        return (self.price_low + self.price_high) / 2

    def add_entry(self, usd_value: float, side: str, timestamp: float) -> None:
        """Add a liquidation entry to this bin."""
        self._entries.append((timestamp, usd_value, side))
        if side == "SELL":
            # SELL force order = long position liquidated
            self.long_usd += usd_value
        else:
            # BUY force order = short position liquidated
            self.short_usd += usd_value
        self.count += 1
        self.last_updated = timestamp

    def get_decayed_values(self, now: float) -> tuple[float, float]:
        """Return (long_usd, short_usd) with time decay applied."""
        decayed_long = 0.0
        decayed_short = 0.0
        for ts, usd, side in self._entries:
            hours_ago = (now - ts) / 3600.0
            weight = _decay_weight(hours_ago)
            if side == "SELL":
                decayed_long += usd * weight
            else:
                decayed_short += usd * weight
        return decayed_long, decayed_short

    def to_dict(self, intensity: float = 0.0, now: float = 0.0) -> dict[str, Any]:
        """Serialize to API response format with decay."""
        if now > 0:
            d_long, d_short = self.get_decayed_values(now)
        else:
            d_long, d_short = self.long_usd, self.short_usd

        return {
            "price_low": round(self.price_low, 2),
            "price_high": round(self.price_high, 2),
            "price_mid": round(self.price_mid, 2),
            "long_usd": round(d_long, 2),
            "short_usd": round(d_short, 2),
            "total_usd": round(d_long + d_short, 2),
            "count": self.count,
            "intensity": round(intensity, 4),
            "last_updated": self.last_updated,
        }


class LiquidationEngine:
    """Ingests Binance Futures liquidation stream and builds heatmap data.

    Connects to !forceOrder@arr WebSocket, aggregates liquidations into
    price bins, polls Open Interest, and calculates theoretical liquidation
    zones for various leverage levels.
    """

    def __init__(self) -> None:
        # symbol -> price_low -> LiquidationBin
        self._bins: dict[str, dict[float, LiquidationBin]] = defaultdict(dict)
        # Recent force orders (bounded)
        self._force_orders: deque[ForceOrder] = deque(maxlen=MAX_FORCE_ORDERS)
        # Open Interest per symbol
        self._open_interest: dict[str, float] = {}
        # Long/Short account ratio per symbol (longAccount / shortAccount)
        self._long_short_ratios: dict[str, float] = {}
        # Current prices per symbol
        self._current_prices: dict[str, float] = {}
        # Control
        self._running: bool = False
        self._ws_task: Optional[asyncio.Task] = None
        self._oi_task: Optional[asyncio.Task] = None
        # Tracked symbols for OI polling
        self._tracked_symbols: list[str] = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
        # Stats
        self._order_count: int = 0

    async def start(self) -> None:
        """Connect to forceOrder WS and start OI polling."""
        self._running = True
        logger.info("LiquidationEngine starting...")

        # Start OI polling in background
        self._oi_task = asyncio.create_task(self._poll_open_interest())

        # Start WebSocket connection with auto-reconnect
        attempt = 0
        while self._running and attempt < MAX_RETRIES:
            attempt += 1
            try:
                await self._run_ws()
                if not self._running:
                    break
            except ConnectionClosed as exc:
                logger.warning(
                    "LiquidationEngine WS closed: %s (attempt %d/%d)",
                    exc, attempt, MAX_RETRIES,
                )
            except Exception as exc:
                logger.error(
                    "LiquidationEngine WS error: %s (attempt %d/%d)",
                    exc, attempt, MAX_RETRIES,
                )

            if self._running and attempt < MAX_RETRIES:
                delay = min(RETRY_BASE_DELAY * (2 ** (attempt - 1)), 60.0)
                logger.info("LiquidationEngine reconnecting in %.1fs...", delay)
                await asyncio.sleep(delay)
            elif self._running:
                logger.error(
                    "LiquidationEngine all %d reconnect attempts exhausted — "
                    "running in theoretical-only mode",
                    MAX_RETRIES,
                )
                # Keep running for theoretical calculations via OI polling
                # Just wait and retry periodically
                while self._running:
                    await asyncio.sleep(60.0)
                    attempt = 0  # Reset for next retry cycle
                    break

    async def _run_ws(self) -> None:
        """Internal WebSocket loop — processes forceOrder messages."""
        async with websockets.connect(
            WS_LIQUIDATION_URL, ping_interval=30, ping_timeout=10,
        ) as ws:
            logger.info("LiquidationEngine WebSocket connected to %s", WS_LIQUIDATION_URL)
            while self._running:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=30.0)
                except asyncio.TimeoutError:
                    continue

                try:
                    data = json.loads(raw)
                    self._process_force_order(data)
                except Exception as exc:
                    logger.debug("LiquidationEngine failed to process message: %s", exc)

    def _process_force_order(self, data: dict) -> None:
        """Parse force order event and add to bins with timestamp for decay.

        Binance forceOrder format:
        {
            "e": "forceOrder",
            "o": {
                "s": "BTCUSDT",       # Symbol
                "S": "SELL",           # Side (SELL = long liq, BUY = short liq)
                "o": "LIMIT",          # Order type
                "f": "IOC",            # Time in force
                "q": "0.014",          # Quantity
                "p": "9910.08",        # Price
                "ap": "9910.08",       # Average price
                "X": "FILLED",         # Status
                "l": "0.014",          # Last filled qty
                "z": "0.014",          # Cumulative filled qty
                "T": 1568014460893     # Trade time ms
            }
        }
        """
        # Handle both single event and array format
        if isinstance(data, list):
            for item in data:
                self._process_force_order(item)
            return

        order_data = data.get("o")
        if order_data is None:
            return

        symbol = order_data.get("s", "")
        side = order_data.get("S", "")
        price = float(order_data.get("ap", order_data.get("p", 0)))
        quantity = float(order_data.get("z", order_data.get("q", 0)))
        timestamp_ms = order_data.get("T", int(time.time() * 1000))
        timestamp_s = timestamp_ms / 1000.0

        if price <= 0 or quantity <= 0:
            return

        usd_value = price * quantity

        # Update current price
        self._current_prices[symbol] = price

        # Create ForceOrder record
        force_order = ForceOrder(
            symbol=symbol,
            side=side,
            price=price,
            quantity=quantity,
            usd_value=usd_value,
            timestamp=timestamp_s,
        )
        self._force_orders.append(force_order)

        # Add to price bin
        bin_size = _get_bin_size(symbol)
        price_low = _snap_to_bin(price, bin_size)

        symbol_bins = self._bins[symbol]
        if price_low not in symbol_bins:
            symbol_bins[price_low] = LiquidationBin(
                price_low=price_low,
                price_high=price_low + bin_size,
            )

        symbol_bins[price_low].add_entry(usd_value, side, timestamp_s)

        self._order_count += 1
        if self._order_count % 100 == 0:
            logger.info(
                "LiquidationEngine processed %d force orders", self._order_count,
            )

    def _calculate_theoretical_levels(
        self, symbol: str, current_price: float, oi: float,
    ) -> list[dict[str, Any]]:
        """Calculate where liquidations would occur at various leverage levels.

        Uses the long/short ratio to produce asymmetric USD estimates.
        """
        if current_price <= 0:
            return []

        leverage_levels = [10, 25, 50, 100]
        levels: list[dict[str, Any]] = []
        oi_usd = oi * current_price

        # Get long/short ratio — defaults to 50/50 if unknown
        ls_ratio = self._long_short_ratios.get(symbol, 1.0)
        # ls_ratio = longAccount / shortAccount
        # If ratio=1.5, 60% long / 40% short
        long_pct = ls_ratio / (1.0 + ls_ratio)
        short_pct = 1.0 - long_pct

        for leverage in leverage_levels:
            long_liq_price = current_price * (1 - 1 / leverage)
            short_liq_price = current_price * (1 + 1 / leverage)

            # Higher leverage = less OI typically
            leverage_weight = {10: 0.30, 25: 0.25, 50: 0.15, 100: 0.05}.get(leverage, 0.1)

            # Apply long/short split to get different values per side
            long_usd = oi_usd * leverage_weight * long_pct
            short_usd = oi_usd * leverage_weight * short_pct

            levels.append({
                "price": round(long_liq_price, 2),
                "leverage": leverage,
                "side": "long",
                "estimated_usd": round(long_usd, 2),
            })
            levels.append({
                "price": round(short_liq_price, 2),
                "leverage": leverage,
                "side": "short",
                "estimated_usd": round(short_usd, 2),
            })

        return levels

    def get_heatmap_data(self, symbol: str, price_range_pct: float = 5.0) -> dict[str, Any]:
        """Return heatmap data: bins with decayed intensity within price range.

        Args:
            symbol: Trading pair symbol (e.g. "BTCUSDT").
            price_range_pct: Percentage above/below current price to include.

        Returns:
            Dict with bins, recent_liquidations, theoretical_levels,
            open_interest, current_price, and summary stats.
        """
        symbol = symbol.upper()
        now = time.time()

        # Get current price (from force orders or OI polling fallback)
        current_price = self._current_prices.get(symbol, 0.0)
        if current_price <= 0:
            # Try to fetch synchronously from recent force orders
            for fo in reversed(self._force_orders):
                if fo.symbol == symbol:
                    current_price = fo.price
                    break

        # Calculate price range
        price_low_bound = current_price * (1 - price_range_pct / 100) if current_price > 0 else 0
        price_high_bound = current_price * (1 + price_range_pct / 100) if current_price > 0 else float("inf")

        # Collect bins within range with decay
        symbol_bins = self._bins.get(symbol, {})
        bin_data: list[dict[str, Any]] = []
        max_total = 0.0
        total_long_liq = 0.0
        total_short_liq = 0.0

        for price_low_key, liq_bin in symbol_bins.items():
            if liq_bin.price_mid < price_low_bound or liq_bin.price_mid > price_high_bound:
                continue

            d_long, d_short = liq_bin.get_decayed_values(now)
            d_total = d_long + d_short
            total_long_liq += d_long
            total_short_liq += d_short

            if d_total > max_total:
                max_total = d_total

            bin_data.append({
                "_bin": liq_bin,
                "_decayed_total": d_total,
            })

        # Normalize intensity 0-1
        bins_output: list[dict[str, Any]] = []
        for bd in bin_data:
            liq_bin: LiquidationBin = bd["_bin"]
            d_total: float = bd["_decayed_total"]
            intensity = d_total / max_total if max_total > 0 else 0.0
            bins_output.append(liq_bin.to_dict(intensity=intensity, now=now))

        # Sort by price
        bins_output.sort(key=lambda b: b["price_mid"])

        # Recent liquidations for this symbol
        recent_liqs = [
            fo.to_dict()
            for fo in reversed(self._force_orders)
            if fo.symbol == symbol
        ][:50]

        # Open interest
        oi = self._open_interest.get(symbol, 0.0)

        # Theoretical levels
        theoretical = self._calculate_theoretical_levels(symbol, current_price, oi)

        return {
            "bins": bins_output,
            "recent_liquidations": recent_liqs,
            "theoretical_levels": theoretical,
            "open_interest": round(oi, 4),
            "current_price": current_price,
            "total_long_liq_usd": round(total_long_liq, 2),
            "total_short_liq_usd": round(total_short_liq, 2),
        }

    def get_recent_liquidations(self, symbol: str, limit: int = 50) -> list[dict[str, Any]]:
        """Return recent force orders for a given symbol.

        Args:
            symbol: Trading pair symbol.
            limit: Maximum number of results.

        Returns:
            List of force order dicts, most recent first.
        """
        symbol = symbol.upper()
        result: list[dict[str, Any]] = []
        for fo in reversed(self._force_orders):
            if fo.symbol == symbol:
                result.append(fo.to_dict())
                if len(result) >= limit:
                    break
        return result

    async def _poll_open_interest(self) -> None:
        """Fetch Open Interest from Binance Futures API every 30 seconds."""
        logger.info("LiquidationEngine OI polling started for %s", self._tracked_symbols)
        while self._running:
            for symbol in self._tracked_symbols:
                try:
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        resp = await client.get(
                            f"{FAPI_BASE_URL}/fapi/v1/openInterest",
                            params={"symbol": symbol},
                        )
                        resp.raise_for_status()
                        data = resp.json()
                        oi = float(data.get("openInterest", 0))
                        self._open_interest[symbol] = oi

                        # Also fetch current price via ticker
                        price_resp = await client.get(
                            f"{FAPI_BASE_URL}/fapi/v1/ticker/price",
                            params={"symbol": symbol},
                        )
                        price_resp.raise_for_status()
                        price_data = price_resp.json()
                        price = float(price_data.get("price", 0))
                        if price > 0:
                            self._current_prices[symbol] = price

                        # Fetch long/short account ratio
                        ls_resp = await client.get(
                            f"{FAPI_BASE_URL}/futures/data/globalLongShortAccountRatio",
                            params={"symbol": symbol, "period": "5m", "limit": 1},
                        )
                        if ls_resp.status_code == 200:
                            ls_data = ls_resp.json()
                            if ls_data:
                                ratio = float(ls_data[0].get("longShortRatio", 1.0))
                                self._long_short_ratios[symbol] = ratio

                except httpx.HTTPStatusError as exc:
                    logger.warning(
                        "LiquidationEngine OI fetch HTTP error for %s: %s",
                        symbol, exc,
                    )
                except httpx.RequestError as exc:
                    logger.warning(
                        "LiquidationEngine OI fetch request error for %s: %s",
                        symbol, exc,
                    )
                except Exception as exc:
                    logger.debug(
                        "LiquidationEngine OI fetch failed for %s: %s",
                        symbol, exc,
                    )

            await asyncio.sleep(OI_POLL_INTERVAL)

    async def stop(self) -> None:
        """Stop the engine gracefully."""
        logger.info("LiquidationEngine stopping...")
        self._running = False

        if self._oi_task and not self._oi_task.done():
            self._oi_task.cancel()
            try:
                await self._oi_task
            except asyncio.CancelledError:
                pass

        logger.info(
            "LiquidationEngine stopped. Total force orders processed: %d",
            self._order_count,
        )

    @property
    def is_running(self) -> bool:
        """Whether the engine is currently running."""
        return self._running


class LiquidationManager:
    """Manages the singleton LiquidationEngine instance.

    Since the !forceOrder@arr stream covers all symbols, only one engine
    is needed globally.
    """

    def __init__(self) -> None:
        self._engine: Optional[LiquidationEngine] = None
        self._task: Optional[asyncio.Task] = None

    @property
    def engine(self) -> Optional[LiquidationEngine]:
        """Get the running engine instance."""
        return self._engine

    async def start(self) -> LiquidationEngine:
        """Start the LiquidationEngine if not already running."""
        if self._engine is not None and self._engine.is_running:
            logger.info("LiquidationEngine already running")
            return self._engine

        self._engine = LiquidationEngine()
        self._task = asyncio.create_task(self._engine.start())
        self._task.add_done_callback(self._handle_task_done)

        logger.info("LiquidationManager started engine")
        return self._engine

    def _handle_task_done(self, task: asyncio.Task) -> None:
        """Callback for when the engine task completes."""
        try:
            exc = task.exception()
            if exc:
                logger.error("LiquidationEngine task failed: %s", exc)
        except asyncio.CancelledError:
            logger.info("LiquidationEngine task cancelled")

    async def stop(self) -> None:
        """Stop the engine."""
        if self._engine:
            await self._engine.stop()

        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        self._engine = None
        self._task = None
        logger.info("LiquidationManager stopped engine")


# Singleton manager instance
_liq_manager: Optional[LiquidationManager] = None


def get_liquidation_manager() -> LiquidationManager:
    """Get or create the singleton LiquidationManager."""
    global _liq_manager
    if _liq_manager is None:
        _liq_manager = LiquidationManager()
    return _liq_manager
