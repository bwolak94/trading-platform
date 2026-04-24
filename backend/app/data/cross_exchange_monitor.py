"""Cross-Exchange Spread Monitor — tracks price divergences across exchanges."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import AsyncGenerator

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Exchange REST endpoint templates
# ---------------------------------------------------------------------------
EXCHANGE_ENDPOINTS: dict[str, str] = {
    "binance": "https://fapi.binance.com/fapi/v1/ticker/price?symbol={symbol}",
    "okx": "https://www.okx.com/api/v5/market/ticker?instId={symbol}-USDT-SWAP",
    "bybit": "https://api.bybit.com/v5/market/tickers?category=linear&symbol={symbol}USDT",
}

# Shared HTTP client for connection pooling
_shared_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    """Return a shared httpx.AsyncClient with connection pooling."""
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        _shared_client = httpx.AsyncClient(
            timeout=8.0,
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
        )
    return _shared_client


@dataclass
class CrossExchangeSnapshot:
    """A point-in-time snapshot of prices across multiple exchanges."""

    symbol: str
    prices: dict[str, float]          # {"binance": 45000.0, "okx": 45050.0, ...}
    max_spread_pct: float             # max price difference as % across all exchanges
    leading_exchange: str             # exchange with highest price
    lagging_exchange: str             # exchange with lowest price
    spread_alert: bool                # True if spread > SIGNIFICANT_SPREAD_PCT
    volume_weighted_price: float      # simple average as "true price" estimate
    timestamp: datetime
    signal: str                       # "VOLATILITY_INCOMING", "ARBITRAGE_OPPORTUNITY", "NORMAL"


class CrossExchangeMonitor:
    """Monitors price discrepancies across Binance Futures, OKX, and Bybit.

    Cross-exchange spread widening often precedes significant price moves as
    market makers reprice risk across venues.  A sustained spread > 0.15%
    indicates incoming volatility; > 0.25% signals potential arbitrage.
    """

    SIGNIFICANT_SPREAD_PCT: float = 0.15   # alert threshold
    ARBITRAGE_SPREAD_PCT: float = 0.25     # arbitrage opportunity threshold
    MIN_EXCHANGES: int = 2                  # minimum responsive exchanges to produce a result

    async def snapshot(self, symbol: str) -> CrossExchangeSnapshot | None:
        """Fetch current prices from all exchanges concurrently and analyse the spread.

        Calls all exchange APIs in parallel using ``asyncio.gather``.  If fewer
        than ``MIN_EXCHANGES`` respond successfully, returns ``None``.

        Args:
            symbol: Base currency without USDT suffix, e.g. ``"BTC"`` for BTCUSDT.

        Returns:
            :class:`CrossExchangeSnapshot` or ``None`` if insufficient exchange data.
        """
        binance_price, okx_price, bybit_price = await asyncio.gather(
            self._fetch_binance(symbol),
            self._fetch_okx(symbol),
            self._fetch_bybit(symbol),
            return_exceptions=False,
        )

        prices: dict[str, float] = {}
        if binance_price is not None:
            prices["binance"] = binance_price
        if okx_price is not None:
            prices["okx"] = okx_price
        if bybit_price is not None:
            prices["bybit"] = bybit_price

        if len(prices) < self.MIN_EXCHANGES:
            logger.warning(
                "CrossExchangeMonitor: only %d exchange(s) responded for %s — skipping snapshot",
                len(prices), symbol,
            )
            return None

        price_values = list(prices.values())
        max_price = max(price_values)
        min_price = min(price_values)
        avg_price = sum(price_values) / len(price_values)

        max_spread_pct = (
            (max_price - min_price) / min_price * 100.0 if min_price > 0 else 0.0
        )

        leading_exchange = max(prices, key=lambda k: prices[k])
        lagging_exchange = min(prices, key=lambda k: prices[k])

        spread_alert = max_spread_pct >= self.SIGNIFICANT_SPREAD_PCT

        if max_spread_pct >= self.ARBITRAGE_SPREAD_PCT:
            signal = "ARBITRAGE_OPPORTUNITY"
        elif max_spread_pct >= self.SIGNIFICANT_SPREAD_PCT:
            signal = "VOLATILITY_INCOMING"
        else:
            signal = "NORMAL"

        snapshot = CrossExchangeSnapshot(
            symbol=symbol,
            prices={k: round(v, 8) for k, v in prices.items()},
            max_spread_pct=round(max_spread_pct, 6),
            leading_exchange=leading_exchange,
            lagging_exchange=lagging_exchange,
            spread_alert=spread_alert,
            volume_weighted_price=round(avg_price, 8),
            timestamp=datetime.now(timezone.utc),
            signal=signal,
        )

        if spread_alert:
            logger.info(
                "CrossExchange alert: %s spread=%.4f%% signal=%s leading=%s(%s) lagging=%s(%s)",
                symbol, max_spread_pct, signal,
                leading_exchange, max_price,
                lagging_exchange, min_price,
            )
        else:
            logger.debug(
                "CrossExchange normal: %s spread=%.4f%% exchanges=%s",
                symbol, max_spread_pct, list(prices.keys()),
            )

        return snapshot

    async def _fetch_binance(self, symbol: str) -> float | None:
        """Fetch Binance Futures mark price for *symbol*.

        ``GET https://fapi.binance.com/fapi/v1/ticker/price?symbol=BTCUSDT``

        Args:
            symbol: Base currency, e.g. ``"BTC"``.

        Returns:
            Mark price as float or ``None`` on failure.
        """
        client = _get_client()
        binance_symbol = f"{symbol.upper()}USDT"
        try:
            resp = await client.get(
                "https://fapi.binance.com/fapi/v1/ticker/price",
                params={"symbol": binance_symbol},
            )
            resp.raise_for_status()
            data = resp.json()
            return float(data["price"])
        except httpx.HTTPStatusError as exc:
            logger.debug("CrossExchange Binance HTTP %d for %s", exc.response.status_code, symbol)
            return None
        except Exception as exc:
            logger.debug("CrossExchange Binance error for %s: %s", symbol, exc)
            return None

    async def _fetch_okx(self, symbol: str) -> float | None:
        """Fetch OKX perpetual swap mark price for *symbol*.

        Converts ``"BTC"`` → ``"BTC-USDT-SWAP"`` for OKX's API format.
        ``GET https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT-SWAP``

        Args:
            symbol: Base currency, e.g. ``"BTC"``.

        Returns:
            Last traded price as float or ``None`` on failure.
        """
        client = _get_client()
        inst_id = f"{symbol.upper()}-USDT-SWAP"
        try:
            resp = await client.get(
                "https://www.okx.com/api/v5/market/ticker",
                params={"instId": inst_id},
            )
            resp.raise_for_status()
            data = resp.json()
            tickers = data.get("data", [])
            if not tickers:
                return None
            return float(tickers[0]["last"])
        except httpx.HTTPStatusError as exc:
            logger.debug("CrossExchange OKX HTTP %d for %s", exc.response.status_code, symbol)
            return None
        except Exception as exc:
            logger.debug("CrossExchange OKX error for %s: %s", symbol, exc)
            return None

    async def _fetch_bybit(self, symbol: str) -> float | None:
        """Fetch Bybit linear perpetual last price for *symbol*.

        ``GET https://api.bybit.com/v5/market/tickers?category=linear&symbol=BTCUSDT``

        Args:
            symbol: Base currency, e.g. ``"BTC"``.

        Returns:
            Last price as float or ``None`` on failure.
        """
        client = _get_client()
        bybit_symbol = f"{symbol.upper()}USDT"
        try:
            resp = await client.get(
                "https://api.bybit.com/v5/market/tickers",
                params={"category": "linear", "symbol": bybit_symbol},
            )
            resp.raise_for_status()
            data = resp.json()
            result_list = data.get("result", {}).get("list", [])
            if not result_list:
                return None
            return float(result_list[0]["lastPrice"])
        except httpx.HTTPStatusError as exc:
            logger.debug("CrossExchange Bybit HTTP %d for %s", exc.response.status_code, symbol)
            return None
        except Exception as exc:
            logger.debug("CrossExchange Bybit error for %s: %s", symbol, exc)
            return None

    async def monitor_continuous(
        self,
        symbols: list[str],
        interval_seconds: int = 10,
    ) -> AsyncGenerator[CrossExchangeSnapshot, None]:
        """Async generator that yields ``CrossExchangeSnapshot`` for significant events.

        Polls all symbols every *interval_seconds* seconds.  Only yields snapshots
        where ``spread_alert`` is ``True`` (i.e. spread >= ``SIGNIFICANT_SPREAD_PCT``).

        Args:
            symbols: List of base currency symbols to monitor, e.g. ``["BTC", "ETH"]``.
            interval_seconds: Polling interval in seconds (default 10).

        Yields:
            :class:`CrossExchangeSnapshot` instances for events with notable spreads.

        Example::

            monitor = CrossExchangeMonitor()
            async for event in monitor.monitor_continuous(["BTC", "ETH"], interval_seconds=5):
                print(event.symbol, event.signal, event.max_spread_pct)
        """
        logger.info(
            "CrossExchangeMonitor: starting continuous monitoring for %s every %ds",
            symbols, interval_seconds,
        )

        while True:
            tasks = [self.snapshot(sym) for sym in symbols]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, Exception):
                    logger.warning("CrossExchangeMonitor: snapshot error: %s", result)
                    continue
                if result is None:
                    continue
                if result.spread_alert:
                    yield result

            await asyncio.sleep(interval_seconds)
