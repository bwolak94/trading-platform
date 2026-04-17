"""Order book fetcher for Binance spot market depth data.

Fetches bid/ask price levels from the Binance REST API ``GET /api/v3/depth``
and returns a structured snapshot with timestamp.
"""

from typing import Any

from app.core.logging import get_logger
from app.data.fetchers.base_fetcher import BaseFetcher

logger = get_logger(__name__)

BINANCE_BASE_URL = "https://api.binance.com"


class OrderBookFetcher(BaseFetcher):
    """Fetch order book (depth) snapshots from Binance.

    Usage::

        async with OrderBookFetcher() as fetcher:
            snapshot = await fetcher.fetch_orderbook("BTCUSDT", limit=100)
    """

    def __init__(self, timeout: float = 15.0) -> None:
        """Initialise the fetcher pointing at the Binance REST API.

        Args:
            timeout: HTTP request timeout in seconds.
        """
        super().__init__(base_url=BINANCE_BASE_URL, timeout=timeout)

    async def fetch(self, **kwargs: Any) -> dict[str, Any]:
        """Generic fetch interface required by ``BaseFetcher``.

        Delegates to :meth:`fetch_orderbook`.

        Args:
            **kwargs: Forwarded to ``fetch_orderbook``.
                Expected keys: ``symbol`` (str), ``limit`` (int, optional).

        Returns:
            Order book snapshot dictionary.
        """
        symbol: str = kwargs.get("symbol", "BTCUSDT")
        limit: int = kwargs.get("limit", 100)
        return await self.fetch_orderbook(symbol=symbol, limit=limit)

    async def fetch_orderbook(
        self,
        symbol: str,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Fetch an order book snapshot from Binance.

        Args:
            symbol: Trading pair symbol, e.g. ``BTCUSDT``.
            limit: Number of price levels per side. Valid Binance values
                   are 5, 10, 20, 50, 100, 500, 1000. Clamped to [5, 1000].

        Returns:
            A dict with the following shape::

                {
                    "bids": [[price: str, qty: str], ...],
                    "asks": [[price: str, qty: str], ...],
                    "timestamp": int,   # server time in ms
                    "symbol": str,
                }

        Raises:
            httpx.HTTPStatusError: On non-2xx responses after retries.
            httpx.RequestError: On connection failures after retries.
        """
        clamped_limit = max(5, min(limit, 1000))

        logger.info(
            "Fetching order book for %s (limit=%d)",
            symbol,
            clamped_limit,
            extra={"symbol": symbol, "limit": clamped_limit},
        )

        raw: dict[str, Any] = await self._request(
            "GET",
            "/api/v3/depth",
            params={"symbol": symbol.upper(), "limit": clamped_limit},
        )

        import time

        bids: list[list[str]] = raw.get("bids", [])
        asks: list[list[str]] = raw.get("asks", [])
        last_update_id: int = raw.get("lastUpdateId", 0)

        logger.info(
            "Order book fetched for %s: %d bids, %d asks (lastUpdateId=%d)",
            symbol,
            len(bids),
            len(asks),
            last_update_id,
            extra={
                "symbol": symbol,
                "bid_levels": len(bids),
                "ask_levels": len(asks),
                "last_update_id": last_update_id,
            },
        )

        return {
            "bids": bids,
            "asks": asks,
            "timestamp": int(time.time() * 1000),
            "symbol": symbol.upper(),
        }
