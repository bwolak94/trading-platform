"""Forex data provider — free sources for EUR/USD, GBP/USD, XAU/USD.

Uses multiple free sources with fallback chain:
1. Twelve Data API (free tier: 800 req/day)
2. Yahoo Finance (yfinance-style via httpx)
3. ExchangeRate API (for spot rates)

Stores ticks in memory (deque) for M1/M5 aggregation.
Calculates Tick Delta as order flow proxy.
"""

import asyncio
import logging
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

FOREX_PAIRS = {
    "EUR/USD": {"yahoo": "EURUSD=X", "twelve": "EUR/USD"},
    "GBP/USD": {"yahoo": "GBPUSD=X", "twelve": "GBP/USD"},
    "XAU/USD": {"yahoo": "GC=F", "twelve": "XAU/USD"},
    "GBP/JPY": {"yahoo": "GBPJPY=X", "twelve": "GBP/JPY"},
}

MAX_TICKS = 10000
POLL_INTERVAL = 5  # seconds between price fetches
CANDLE_INTERVALS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600}


@dataclass
class Tick:
    """Single price tick."""
    symbol: str
    price: float
    timestamp: datetime
    tick_delta: int  # +1 if price up, -1 if down, 0 if unchanged


@dataclass
class ForexCandle:
    """Aggregated candle from ticks."""
    symbol: str
    timeframe: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    tick_volume: int
    tick_delta: int  # sum of tick deltas (proxy for real delta)


class ForexProvider:
    """Provides real-time forex data from free sources."""

    def __init__(self) -> None:
        self._ticks: dict[str, deque[Tick]] = defaultdict(lambda: deque(maxlen=MAX_TICKS))
        self._last_prices: dict[str, float] = {}
        self._running = False
        self._task: asyncio.Task | None = None
        self._cumulative_delta: dict[str, float] = defaultdict(float)

    async def start(self) -> None:
        """Start polling forex prices."""
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("ForexProvider started for %s", list(FOREX_PAIRS.keys()))

    async def stop(self) -> None:
        """Stop polling."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("ForexProvider stopped")

    async def _poll_loop(self) -> None:
        """Main polling loop — fetch prices every POLL_INTERVAL seconds."""
        while self._running:
            for symbol in FOREX_PAIRS:
                try:
                    price = await self._fetch_price(symbol)
                    if price > 0:
                        self._record_tick(symbol, price)
                except Exception as exc:
                    logger.debug("Forex fetch failed for %s: %s", symbol, exc)
            await asyncio.sleep(POLL_INTERVAL)

    async def _fetch_price(self, symbol: str) -> float:
        """Fetch current price from free sources with fallback."""
        # Try Twelve Data first (if API key configured)
        twelve_key = getattr(settings, "TWELVE_DATA_API_KEY", "")
        if twelve_key and twelve_key != "your_key":
            price = await self._fetch_twelve_data(symbol, twelve_key)
            if price > 0:
                return price

        # Fallback: Yahoo Finance chart API (no key needed)
        price = await self._fetch_yahoo(symbol)
        if price > 0:
            return price

        # Fallback: ExchangeRate API for forex (not gold)
        if "XAU" not in symbol:
            price = await self._fetch_exchangerate(symbol)
            if price > 0:
                return price

        return 0.0

    async def _fetch_twelve_data(self, symbol: str, api_key: str) -> float:
        """Fetch from Twelve Data free tier."""
        pair_info = FOREX_PAIRS.get(symbol, {})
        td_symbol = pair_info.get("twelve", symbol)
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    "https://api.twelvedata.com/price",
                    params={"symbol": td_symbol, "apikey": api_key},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return float(data.get("price", 0))
        except Exception:
            pass
        return 0.0

    async def _fetch_yahoo(self, symbol: str) -> float:
        """Fetch from Yahoo Finance chart endpoint (free, no key)."""
        pair_info = FOREX_PAIRS.get(symbol, {})
        yahoo_sym = pair_info.get("yahoo", symbol.replace("/", "") + "=X")
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_sym}",
                    params={"interval": "1m", "range": "1d"},
                    headers={"User-Agent": "Mozilla/5.0"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    result = data.get("chart", {}).get("result", [])
                    if result:
                        meta = result[0].get("meta", {})
                        price = meta.get("regularMarketPrice", 0)
                        if price > 0:
                            return float(price)
        except Exception:
            pass
        return 0.0

    async def _fetch_exchangerate(self, symbol: str) -> float:
        """Fetch from ExchangeRate API (free, no key, forex only)."""
        parts = symbol.split("/")
        if len(parts) != 2:
            return 0.0
        base, quote = parts
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"https://open.er-api.com/v6/latest/{base}",
                )
                if resp.status_code == 200:
                    data = resp.json()
                    rates = data.get("rates", {})
                    return float(rates.get(quote, 0))
        except Exception:
            pass
        return 0.0

    def _record_tick(self, symbol: str, price: float) -> None:
        """Record a price tick and calculate tick delta."""
        last = self._last_prices.get(symbol, price)
        if price > last:
            delta = 1
        elif price < last:
            delta = -1
        else:
            delta = 0

        tick = Tick(
            symbol=symbol,
            price=price,
            timestamp=datetime.now(timezone.utc),
            tick_delta=delta,
        )
        self._ticks[symbol].append(tick)
        self._last_prices[symbol] = price
        self._cumulative_delta[symbol] += delta

    def get_ticks(self, symbol: str, limit: int = 1000) -> list[dict[str, Any]]:
        """Get recent ticks for a symbol."""
        ticks = list(self._ticks.get(symbol, []))[-limit:]
        return [
            {
                "price": t.price,
                "timestamp": t.timestamp.isoformat(),
                "time": int(t.timestamp.timestamp()),
                "tick_delta": t.tick_delta,
            }
            for t in ticks
        ]

    def get_candles(self, symbol: str, timeframe: str = "1m", limit: int = 100) -> list[dict[str, Any]]:
        """Aggregate ticks into OHLCV candles."""
        ticks = list(self._ticks.get(symbol, []))
        if not ticks:
            return []

        interval_seconds = CANDLE_INTERVALS.get(timeframe, 60)
        candles: list[dict[str, Any]] = []

        # Group ticks by time window
        if not ticks:
            return []

        start = ticks[0].timestamp
        window_start = start.replace(second=0, microsecond=0)

        current_candle: dict[str, Any] | None = None

        for tick in ticks:
            # Calculate which window this tick belongs to
            elapsed = (tick.timestamp - window_start).total_seconds()
            window_idx = int(elapsed // interval_seconds)
            candle_time = window_start + timedelta(seconds=window_idx * interval_seconds)

            if current_candle is None or current_candle["time"] != int(candle_time.timestamp()):
                if current_candle:
                    candles.append(current_candle)
                current_candle = {
                    "time": int(candle_time.timestamp()),
                    "timestamp": candle_time.isoformat(),
                    "open": tick.price,
                    "high": tick.price,
                    "low": tick.price,
                    "close": tick.price,
                    "volume": 1,
                    "tick_delta": tick.tick_delta,
                }
            else:
                current_candle["high"] = max(current_candle["high"], tick.price)
                current_candle["low"] = min(current_candle["low"], tick.price)
                current_candle["close"] = tick.price
                current_candle["volume"] += 1
                current_candle["tick_delta"] += tick.tick_delta

        if current_candle:
            candles.append(current_candle)

        return candles[-limit:]

    def get_cumulative_delta(self, symbol: str) -> float:
        """Get cumulative tick delta for a symbol."""
        return self._cumulative_delta.get(symbol, 0)

    def get_current_price(self, symbol: str) -> float:
        """Get last known price."""
        return self._last_prices.get(symbol, 0.0)

    def get_status(self) -> dict[str, Any]:
        """Get provider status."""
        return {
            "running": self._running,
            "pairs": {
                symbol: {
                    "price": self._last_prices.get(symbol, 0),
                    "ticks": len(self._ticks.get(symbol, [])),
                    "cumulative_delta": round(self._cumulative_delta.get(symbol, 0), 1),
                }
                for symbol in FOREX_PAIRS
            },
        }


# Singleton
_provider: ForexProvider | None = None


def get_forex_provider() -> ForexProvider:
    """Get or create the singleton ForexProvider."""
    global _provider
    if _provider is None:
        _provider = ForexProvider()
    return _provider
