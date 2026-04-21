"""Binance market data fetcher — historical REST + real-time WebSocket."""

import asyncio
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Coroutine

import httpx
import websockets
from websockets.exceptions import ConnectionClosed

from app.core.logging import get_logger
from app.schemas.market import OHLCV

logger = get_logger(__name__)

BASE_REST_URL = "https://api.binance.com"
FUTURES_REST_URL = "https://fapi.binance.com"
WS_BASE_URL = "wss://stream.binance.com:9443"

# Cache for all futures symbols — refreshed every hour
_futures_symbols_cache: list[str] = []
_futures_symbols_fetched_at: float = 0.0
FUTURES_SYMBOLS_CACHE_TTL = 3600  # 1 hour

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


# Module-level shared HTTP client for connection pooling
_shared_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    """Return a shared httpx.AsyncClient with connection pooling.

    Reuses keep-alive connections instead of creating new clients per request.
    """
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        _shared_client = httpx.AsyncClient(
            timeout=30.0,
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
        )
    return _shared_client


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


async def get_all_futures_symbols(min_volume_usd: float = 10_000_000.0) -> list[str]:
    """Fetch all active USDT perpetual futures symbols from Binance.

    Results are cached for FUTURES_SYMBOLS_CACHE_TTL seconds to avoid excessive API calls.

    Args:
        min_volume_usd: Minimum 24h volume in USD to include a symbol (default $10M).

    Returns:
        List of symbols in 'BASE/USDT' format, sorted by 24h volume descending.
    """
    import time

    global _futures_symbols_cache, _futures_symbols_fetched_at

    if _futures_symbols_cache and time.time() - _futures_symbols_fetched_at < FUTURES_SYMBOLS_CACHE_TTL:
        return _futures_symbols_cache

    if not _check_circuit_breaker():
        logger.warning("Circuit breaker open — returning cached futures symbols")
        return _futures_symbols_cache or []

    client = _get_client()
    try:
        resp = await client.get(f"{FUTURES_REST_URL}/fapi/v1/ticker/24hr")
        resp.raise_for_status()
        tickers = resp.json()
        _record_success()
    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
        _record_failure()
        logger.error("Failed to fetch futures symbols: %s", exc)
        return _futures_symbols_cache or []

    symbols = []
    for ticker in tickers:
        sym = ticker.get("symbol", "")
        # Only USDT perpetuals (no quarterly contracts like BTCUSDT_241227)
        if not sym.endswith("USDT") or "_" in sym:
            continue
        try:
            volume_usd = float(ticker.get("quoteVolume", 0))
        except (ValueError, TypeError):
            continue
        if volume_usd >= min_volume_usd:
            base = sym[:-4]  # Strip 'USDT'
            symbols.append((f"{base}/USDT", volume_usd))

    # Sort by volume descending, take top 200
    symbols.sort(key=lambda x: x[1], reverse=True)
    result = [s[0] for s in symbols[:200]]

    _futures_symbols_cache = result
    _futures_symbols_fetched_at = time.time()

    logger.info("Loaded %d USDT perpetual futures symbols from Binance", len(result))
    return result


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

        client = _get_client()
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


async def get_long_short_ratio(symbol: str, period: str = "1h", limit: int = 10) -> list[dict]:
    """Fetch global long/short account ratio for a futures symbol.

    Args:
        symbol: e.g. "BTCUSDT"
        period: "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d"
        limit: Number of data points (max 500)

    Returns:
        List of {timestamp, longShortRatio, longAccount, shortAccount} dicts
    """
    if not _check_circuit_breaker():
        return []
    client = _get_client()
    try:
        resp = await client.get(
            f"{FUTURES_REST_URL}/futures/data/globalLongShortAccountRatio",
            params={"symbol": symbol, "period": period, "limit": limit},
        )
        resp.raise_for_status()
        _record_success()
        data = resp.json()
        return [
            {
                "timestamp": int(item["timestamp"]),
                "long_short_ratio": float(item["longShortRatio"]),
                "long_account": float(item["longAccount"]),
                "short_account": float(item["shortAccount"]),
            }
            for item in data
        ]
    except Exception as exc:
        _record_failure()
        logger.warning("Long/short ratio fetch failed for %s: %s", symbol, exc)
        return []


async def get_taker_buysell_ratio(symbol: str, period: str = "1h", limit: int = 10) -> list[dict]:
    """Fetch taker buy/sell volume ratio for a futures symbol.

    Ratio > 1 means buyers are more aggressive.

    Args:
        symbol: e.g. "BTCUSDT"
        period: "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d"
        limit: Number of data points (max 500)

    Returns:
        List of {timestamp, buy_sell_ratio, buy_vol, sell_vol} dicts
    """
    if not _check_circuit_breaker():
        return []
    client = _get_client()
    try:
        resp = await client.get(
            f"{FUTURES_REST_URL}/futures/data/takerlongshortRatio",
            params={"symbol": symbol, "period": period, "limit": limit},
        )
        resp.raise_for_status()
        _record_success()
        data = resp.json()
        return [
            {
                "timestamp": int(item["timestamp"]),
                "buy_sell_ratio": float(item["buySellRatio"]),
                "buy_vol": float(item["buyVol"]),
                "sell_vol": float(item["sellVol"]),
            }
            for item in data
        ]
    except Exception as exc:
        _record_failure()
        logger.warning("Taker buy/sell ratio fetch failed for %s: %s", symbol, exc)
        return []


async def get_top_trader_position_ratio(
    symbol: str, period: str = "1h", limit: int = 50
) -> list[dict]:
    """Top 20% traders long/short position count ratio.

    Endpoint: GET fapi.binance.com/futures/data/topLongShortPositionRatio

    Args:
        symbol: e.g. "BTCUSDT"
        period: "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d"
        limit: Number of data points (max 500)

    Returns:
        List of {timestamp, long_short_ratio, long_account, short_account} dicts.
        Returns [] for illiquid symbols that Binance returns 400 for.
    """
    if not _check_circuit_breaker():
        return []
    client = _get_client()
    try:
        resp = await client.get(
            f"{FUTURES_REST_URL}/futures/data/topLongShortPositionRatio",
            params={"symbol": symbol, "period": period, "limit": limit},
        )
        resp.raise_for_status()
        _record_success()
        data = resp.json()
        return [
            {
                "timestamp": int(item["timestamp"]),
                "long_short_ratio": float(item["longShortRatio"]),
                "long_account": float(item["longAccount"]),
                "short_account": float(item["shortAccount"]),
            }
            for item in data
        ]
    except httpx.HTTPStatusError as exc:
        # Binance returns 400 for illiquid symbols — not a circuit-breaker event
        if exc.response.status_code == 400:
            logger.debug("Top trader position ratio unavailable for %s (400)", symbol)
            return []
        _record_failure()
        logger.warning("Top trader position ratio fetch failed for %s: %s", symbol, exc)
        return []
    except httpx.RequestError as exc:
        _record_failure()
        logger.warning("Top trader position ratio request error for %s: %s", symbol, exc)
        return []


async def get_top_trader_account_ratio(
    symbol: str, period: str = "1h", limit: int = 50
) -> list[dict]:
    """Top 20% traders long/short account count ratio.

    Endpoint: GET fapi.binance.com/futures/data/topLongShortAccountRatio

    Args:
        symbol: e.g. "BTCUSDT"
        period: "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d"
        limit: Number of data points (max 500)

    Returns:
        List of {timestamp, long_short_ratio, long_account, short_account} dicts.
        Returns [] for illiquid symbols that Binance returns 400 for.
    """
    if not _check_circuit_breaker():
        return []
    client = _get_client()
    try:
        resp = await client.get(
            f"{FUTURES_REST_URL}/futures/data/topLongShortAccountRatio",
            params={"symbol": symbol, "period": period, "limit": limit},
        )
        resp.raise_for_status()
        _record_success()
        data = resp.json()
        return [
            {
                "timestamp": int(item["timestamp"]),
                "long_short_ratio": float(item["longShortRatio"]),
                "long_account": float(item["longAccount"]),
                "short_account": float(item["shortAccount"]),
            }
            for item in data
        ]
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 400:
            logger.debug("Top trader account ratio unavailable for %s (400)", symbol)
            return []
        _record_failure()
        logger.warning("Top trader account ratio fetch failed for %s: %s", symbol, exc)
        return []
    except httpx.RequestError as exc:
        _record_failure()
        logger.warning("Top trader account ratio request error for %s: %s", symbol, exc)
        return []


async def get_open_interest_history(symbol: str, period: str = "1h", limit: int = 50) -> list[dict]:
    """Fetch open interest history for a futures symbol.

    Args:
        symbol: e.g. "BTCUSDT"
        period: "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d"
        limit: Number of data points (max 500)

    Returns:
        List of {timestamp, open_interest, open_interest_value} dicts
    """
    if not _check_circuit_breaker():
        return []
    client = _get_client()
    try:
        resp = await client.get(
            f"{FUTURES_REST_URL}/futures/data/openInterestHist",
            params={"symbol": symbol, "period": period, "limit": limit},
        )
        resp.raise_for_status()
        _record_success()
        return [
            {
                "timestamp": int(item["timestamp"]),
                "open_interest": float(item["sumOpenInterest"]),
                "open_interest_value": float(item["sumOpenInterestValue"]),
            }
            for item in resp.json()
        ]
    except Exception as exc:
        _record_failure()
        logger.warning("Open interest fetch failed for %s: %s", symbol, exc)
        return []
