"""Binance market data fetcher — historical REST + real-time WebSocket."""

import asyncio
import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Coroutine

import httpx
import websockets
from websockets.exceptions import ConnectionClosed

from app.schemas.market import OHLCV

logger = logging.getLogger(__name__)

BASE_REST_URL = "https://api.binance.com"
WS_BASE_URL = "wss://stream.binance.com:9443"

# Binance uses lowercase symbols without slash
SYMBOL_MAP = {
    "BTC/USDT": "BTCUSDT",
    "ETH/USDT": "ETHUSDT",
    "SOL/USDT": "SOLUSDT",
}

INTERVAL_MAP = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "1h": "1h",
    "4h": "4h",
    "1D": "1d",
}

DEFAULT_SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
DEFAULT_INTERVALS = ["1m", "5m", "15m", "1h", "4h", "1D"]

MAX_RETRIES = 5
RETRY_BASE_DELAY = 2.0

_circuit_breaker = {"failures": 0, "open_until": 0.0}
CIRCUIT_BREAKER_THRESHOLD = 5
CIRCUIT_BREAKER_COOLDOWN = 300  # 5 minutes


def _check_circuit_breaker() -> bool:
    """Returns True if requests should proceed, False if circuit is open."""
    import time
    if _circuit_breaker["failures"] >= CIRCUIT_BREAKER_THRESHOLD:
        if time.time() < _circuit_breaker["open_until"]:
            return False
        # Reset after cooldown
        _circuit_breaker["failures"] = 0
    return True


def _record_failure():
    import time
    _circuit_breaker["failures"] += 1
    if _circuit_breaker["failures"] >= CIRCUIT_BREAKER_THRESHOLD:
        _circuit_breaker["open_until"] = time.time() + CIRCUIT_BREAKER_COOLDOWN
        logger.warning("Circuit breaker OPEN: pausing Binance requests for %ds", CIRCUIT_BREAKER_COOLDOWN)


def _record_success():
    _circuit_breaker["failures"] = 0


def _to_binance_symbol(symbol: str) -> str:
    """Convert 'BTC/USDT' to 'BTCUSDT'."""
    return SYMBOL_MAP.get(symbol, symbol.replace("/", ""))


def _to_binance_interval(interval: str) -> str:
    """Convert interval to Binance format."""
    return INTERVAL_MAP.get(interval, interval.lower())


def _parse_kline(symbol: str, timeframe: str, kline: list[Any]) -> OHLCV:
    """Parse a Binance kline array into an OHLCV object."""
    return OHLCV(
        asset=symbol,
        timeframe=timeframe,
        timestamp=datetime.fromtimestamp(kline[0] / 1000, tz=timezone.utc),
        open=Decimal(str(kline[1])),
        high=Decimal(str(kline[2])),
        low=Decimal(str(kline[3])),
        close=Decimal(str(kline[4])),
        volume=Decimal(str(kline[5])),
    )


class BinanceFetcher:
    """Fetches OHLCV data from Binance via REST and WebSocket."""

    def __init__(self) -> None:
        self._ws_running = False
        self._ws_task: asyncio.Task | None = None

    async def fetch_historical_ohlcv(
        self,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: datetime,
        limit: int = 1000,
    ) -> list[OHLCV]:
        """Fetch historical OHLCV candles via REST API with pagination."""
        if not _check_circuit_breaker():
            logger.warning("Circuit breaker is open — skipping Binance request for %s %s", symbol, interval)
            return []

        binance_symbol = _to_binance_symbol(symbol)
        binance_interval = _to_binance_interval(interval)
        all_candles: list[OHLCV] = []
        current_start = int(start_time.timestamp() * 1000)
        end_ms = int(end_time.timestamp() * 1000)

        async with httpx.AsyncClient(timeout=30.0) as client:
            while current_start < end_ms:
                for attempt in range(1, MAX_RETRIES + 1):
                    try:
                        resp = await client.get(
                            f"{BASE_REST_URL}/api/v3/klines",
                            params={
                                "symbol": binance_symbol,
                                "interval": binance_interval,
                                "startTime": current_start,
                                "endTime": end_ms,
                                "limit": limit,
                            },
                        )
                        resp.raise_for_status()
                        data = resp.json()
                        break
                    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                        _record_failure()
                        if attempt == MAX_RETRIES:
                            logger.error(
                                "Failed to fetch %s %s after %d retries: %s",
                                symbol, interval, MAX_RETRIES, exc,
                            )
                            raise
                        delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
                        logger.warning(
                            "Retry %d/%d for %s %s in %.1fs: %s",
                            attempt, MAX_RETRIES, symbol, interval, delay, exc,
                        )
                        await asyncio.sleep(delay)

                _record_success()

                if not data:
                    break

                candles = [_parse_kline(symbol, interval, k) for k in data]
                all_candles.extend(candles)

                # Move start to after the last candle's open time
                current_start = int(data[-1][0]) + 1

                if len(data) < limit:
                    break

        logger.info(
            "Fetched %d historical candles for %s %s", len(all_candles), symbol, interval
        )
        return all_candles

    async def start_stream(
        self,
        symbols: list[str] | None = None,
        intervals: list[str] | None = None,
        callback: Callable[[OHLCV], Coroutine] | None = None,
    ) -> None:
        """Start a WebSocket stream for real-time kline data."""
        symbols = symbols or DEFAULT_SYMBOLS
        intervals = intervals or ["1m"]

        streams = []
        for symbol in symbols:
            bs = _to_binance_symbol(symbol).lower()
            for interval in intervals:
                bi = _to_binance_interval(interval)
                streams.append(f"{bs}@kline_{bi}")

        url = f"{WS_BASE_URL}/stream?streams={'/'.join(streams)}"
        self._ws_running = True

        for attempt in range(1, MAX_RETRIES + 1):
            if not self._ws_running:
                return
            try:
                await self._run_ws(url, symbols, callback)
            except ConnectionClosed as exc:
                logger.warning("WebSocket closed: %s (attempt %d/%d)", exc, attempt, MAX_RETRIES)
            except Exception as exc:
                logger.error("WebSocket error: %s (attempt %d/%d)", exc, attempt, MAX_RETRIES)

            if attempt < MAX_RETRIES and self._ws_running:
                delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
                logger.info("Reconnecting in %.1fs...", delay)
                await asyncio.sleep(delay)

        if self._ws_running:
            logger.error("WebSocket: all %d reconnect attempts exhausted", MAX_RETRIES)
            self._ws_running = False

    async def _run_ws(
        self,
        url: str,
        symbols: list[str],
        callback: Callable[[OHLCV], Coroutine] | None,
    ) -> None:
        """Internal WebSocket connection loop."""
        # Build reverse symbol map for incoming messages
        reverse_map = {v.lower(): k for k, v in SYMBOL_MAP.items()}

        async with websockets.connect(url, ping_interval=30) as ws:
            logger.info("WebSocket connected to Binance")
            while self._ws_running:
                raw = await ws.recv()
                msg = json.loads(raw)
                data = msg.get("data", {})

                if data.get("e") != "kline":
                    continue

                kline_data = data["k"]
                binance_sym = data["s"].lower()
                symbol = reverse_map.get(binance_sym, data["s"])
                interval_key = kline_data["i"]

                # Map back to our interval format
                reverse_interval = {v: k for k, v in INTERVAL_MAP.items()}
                timeframe = reverse_interval.get(interval_key, interval_key)

                candle = OHLCV(
                    asset=symbol,
                    timeframe=timeframe,
                    timestamp=datetime.fromtimestamp(
                        kline_data["t"] / 1000, tz=timezone.utc
                    ),
                    open=Decimal(kline_data["o"]),
                    high=Decimal(kline_data["h"]),
                    low=Decimal(kline_data["l"]),
                    close=Decimal(kline_data["c"]),
                    volume=Decimal(kline_data["v"]),
                )

                if callback:
                    await callback(candle)

    def stop_stream(self) -> None:
        """Signal the WebSocket stream to stop."""
        self._ws_running = False
        logger.info("WebSocket stream stop requested")
