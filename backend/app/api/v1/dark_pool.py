"""Dark Pool / Block Trade Detector.

Identifies abnormally large single trades vs recent average trade size.
Uses Binance aggTrades endpoint to look for institutional-sized prints.
"""

import logging
import statistics
from typing import Any

import httpx
from fastapi import APIRouter, Query

router = APIRouter(prefix="/market", tags=["dark-pool"])
logger = logging.getLogger(__name__)

_BLOCK_SIGMA = 3.0   # stddev multiplier to classify a print as "block trade"
_MIN_BLOCK_USD = 250_000  # minimum notional value to report


async def _fetch_agg_trades(symbol: str, limit: int = 500) -> list[dict]:
    url = "https://fapi.binance.com/fapi/v1/aggTrades"
    async with httpx.AsyncClient(timeout=6.0) as client:
        r = await client.get(url, params={"symbol": symbol, "limit": limit})
        r.raise_for_status()
        return r.json()


@router.get("/dark-pool/{symbol}", summary="Dark pool / block trade detector")
async def get_dark_pool_activity(
    symbol: str,
    sigma: float = Query(_BLOCK_SIGMA, ge=1.0, le=10.0, description="Stddev threshold for block classification"),
) -> dict[str, Any]:
    """Scan recent aggTrades for unusually large prints that may indicate institutional activity.

    A trade is classified as a 'block' when its notional value exceeds
    (mean + sigma × stddev) of the sample.
    """
    sym = symbol.upper().replace("/", "")
    try:
        trades = await _fetch_agg_trades(sym)
    except Exception as exc:
        logger.warning("aggTrades fetch failed [%s]: %s", sym, exc)
        return {"status": "unavailable", "data": {}}

    notionals = [float(t["p"]) * float(t["q"]) for t in trades]
    if len(notionals) < 20:
        return {"status": "unavailable", "data": {"reason": "insufficient trades"}}

    mean_n = statistics.mean(notionals)
    stdev_n = statistics.stdev(notionals)
    threshold = mean_n + sigma * stdev_n

    blocks: list[dict[str, Any]] = []
    for t in trades:
        notional = float(t["p"]) * float(t["q"])
        if notional >= threshold and notional >= _MIN_BLOCK_USD:
            blocks.append({
                "price": float(t["p"]),
                "qty": float(t["q"]),
                "notional_usd": round(notional, 0),
                "side": "SELL" if t["m"] else "BUY",
                "timestamp": t["T"],
                "sigma_from_mean": round((notional - mean_n) / stdev_n, 2),
            })

    blocks.sort(key=lambda x: x["notional_usd"], reverse=True)

    buy_volume = sum(b["notional_usd"] for b in blocks if b["side"] == "BUY")
    sell_volume = sum(b["notional_usd"] for b in blocks if b["side"] == "SELL")
    total_volume = buy_volume + sell_volume
    bias = "BUY" if buy_volume > sell_volume else "SELL" if sell_volume > buy_volume else "NEUTRAL"

    return {
        "status": "ok",
        "source": "binance_futures",
        "data": {
            "symbol": sym,
            "block_count": len(blocks),
            "mean_trade_usd": round(mean_n, 2),
            "threshold_usd": round(threshold, 2),
            "institutional_bias": bias,
            "buy_block_usd": round(buy_volume, 0),
            "sell_block_usd": round(sell_volume, 0),
            "total_block_usd": round(total_volume, 0),
            "blocks": blocks[:20],
        },
    }
