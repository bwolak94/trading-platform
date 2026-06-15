"""Multi-exchange price aggregator endpoint.

Fetches the same symbol price from Binance, Bybit, and OKX simultaneously,
returning the spread and premium/discount between exchanges.
"""

import asyncio
import logging
from typing import Any

import httpx
from fastapi import APIRouter, Query

router = APIRouter(prefix="/market", tags=["multi-exchange"])
logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(5.0)


async def _fetch_binance(symbol: str, client: httpx.AsyncClient) -> dict[str, Any]:
    url = f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={symbol}"
    r = await client.get(url, timeout=_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    return {"exchange": "Binance", "price": float(data["price"]), "symbol": symbol}


async def _fetch_bybit(symbol: str, client: httpx.AsyncClient) -> dict[str, Any]:
    url = f"https://api.bybit.com/v5/market/tickers?category=linear&symbol={symbol}"
    r = await client.get(url, timeout=_TIMEOUT)
    r.raise_for_status()
    item = r.json()["result"]["list"][0]
    return {"exchange": "Bybit", "price": float(item["lastPrice"]), "symbol": symbol}


async def _fetch_okx(symbol: str, client: httpx.AsyncClient) -> dict[str, Any]:
    # OKX uses SWAP format: BTC-USDT-SWAP
    base = symbol.replace("USDT", "")
    inst_id = f"{base}-USDT-SWAP"
    url = f"https://www.okx.com/api/v5/market/ticker?instId={inst_id}"
    r = await client.get(url, timeout=_TIMEOUT)
    r.raise_for_status()
    item = r.json()["data"][0]
    return {"exchange": "OKX", "price": float(item["last"]), "symbol": symbol}


@router.get("/multi-exchange/{symbol}", summary="Multi-exchange price aggregator")
async def get_multi_exchange_prices(
    symbol: str,
    exchanges: str = Query("binance,bybit,okx", description="Comma-separated exchanges"),
) -> dict[str, Any]:
    """Fetch the same futures symbol price from multiple exchanges in parallel.

    Returns prices, spread (max-min), and premium/discount vs Binance reference.
    """
    sym = symbol.upper().replace("/", "")
    requested = {e.strip().lower() for e in exchanges.split(",")}

    async with httpx.AsyncClient() as client:
        tasks: list[asyncio.Task] = []
        if "binance" in requested:
            tasks.append(asyncio.create_task(_fetch_binance(sym, client)))
        if "bybit" in requested:
            tasks.append(asyncio.create_task(_fetch_bybit(sym, client)))
        if "okx" in requested:
            tasks.append(asyncio.create_task(_fetch_okx(sym, client)))

        results = await asyncio.gather(*tasks, return_exceptions=True)

    prices: list[dict[str, Any]] = []
    for res in results:
        if isinstance(res, Exception):
            logger.warning("Multi-exchange fetch error: %s", res)
        else:
            prices.append(res)

    if not prices:
        return {"status": "unavailable", "data": {"prices": [], "spread_pct": 0, "reference": sym}}

    price_vals = [p["price"] for p in prices]
    spread = max(price_vals) - min(price_vals)
    reference = next((p["price"] for p in prices if p["exchange"] == "Binance"), price_vals[0])
    spread_pct = (spread / reference * 100) if reference else 0

    for p in prices:
        p["premium_pct"] = round((p["price"] - reference) / reference * 100, 4) if reference else 0

    return {
        "status": "ok",
        "source": "live",
        "data": {
            "symbol": sym,
            "prices": sorted(prices, key=lambda x: x["exchange"]),
            "spread_usd": round(spread, 4),
            "spread_pct": round(spread_pct, 4),
            "reference_exchange": "Binance",
        },
    }
