"""Binance Futures funding rate fetcher."""

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

FUTURES_BASE_URL = "https://fapi.binance.com"

DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

# Shared HTTP client for connection pooling
_shared_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    """Return a shared httpx.AsyncClient with connection pooling."""
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        _shared_client = httpx.AsyncClient(
            timeout=15.0,
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
        )
    return _shared_client


class FundingRateFetcher:
    """Fetches funding rate data from Binance Futures API (/fapi/v1/premiumIndex)."""

    async def fetch_funding_rates(
        self, symbols: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """Fetch current funding rates for the given symbols.

        Args:
            symbols: List of trading pair symbols (e.g. ["BTCUSDT", "ETHUSDT"]).
                     Defaults to DEFAULT_SYMBOLS if not provided.

        Returns:
            List of dicts with keys: symbol, funding_rate, next_funding_time, mark_price.
        """
        symbols = symbols or DEFAULT_SYMBOLS
        client = _get_client()
        results: list[dict[str, Any]] = []

        for symbol in symbols:
            try:
                resp = await client.get(
                    f"{FUTURES_BASE_URL}/fapi/v1/premiumIndex",
                    params={"symbol": symbol.upper()},
                )
                resp.raise_for_status()
                data = resp.json()

                results.append({
                    "symbol": data["symbol"],
                    "funding_rate": float(data["lastFundingRate"]),
                    "next_funding_time": datetime.fromtimestamp(
                        data["nextFundingTime"] / 1000, tz=timezone.utc
                    ).isoformat(),
                    "mark_price": float(data["markPrice"]),
                })
            except httpx.HTTPStatusError as exc:
                logger.error(
                    "Binance Futures API error for %s: %s (status %d)",
                    symbol,
                    exc.response.text,
                    exc.response.status_code,
                )
            except httpx.RequestError as exc:
                logger.error(
                    "Failed to reach Binance Futures API for %s: %s",
                    symbol,
                    exc,
                )
            except (KeyError, ValueError) as exc:
                logger.error(
                    "Unexpected response format for %s: %s",
                    symbol,
                    exc,
                )

        logger.info("Fetched funding rates for %d/%d symbols", len(results), len(symbols))
        return results
