"""Open Interest Momentum endpoint.

Computes OI rate-of-change over multiple lookback windows to detect
trend strength: rising OI + rising price = strong trend.
"""

import logging
from typing import Any

import httpx
from fastapi import APIRouter

router = APIRouter(prefix="/market", tags=["oi-momentum"])
logger = logging.getLogger(__name__)


async def _fetch_oi_history(symbol: str, limit: int = 96) -> list[dict]:
    """Fetch OI snapshots from Binance futures (15-min intervals, ~24 h)."""
    url = "https://fapi.binance.com/futures/data/openInterestHist"
    async with httpx.AsyncClient(timeout=6.0) as client:
        r = await client.get(url, params={"symbol": symbol, "period": "15m", "limit": limit})
        r.raise_for_status()
        return r.json()


@router.get("/oi-momentum/{symbol}", summary="Open interest momentum (rate-of-change)")
async def get_oi_momentum(symbol: str) -> dict[str, Any]:
    """Return OI and OI rate-of-change for 1 h, 4 h, and 24 h windows.

    Interpretation:
    - OI rising + price rising  → strong bullish trend
    - OI rising + price falling → strong bearish trend
    - OI falling + price rising → short covering rally (weak)
    - OI falling + price falling → long liquidation (weak)
    """
    sym = symbol.upper().replace("/", "")
    try:
        history = await _fetch_oi_history(sym)
    except Exception as exc:
        logger.warning("OI history fetch failed [%s]: %s", sym, exc)
        return {"status": "unavailable", "data": {}}

    if not history:
        return {"status": "unavailable", "data": {}}

    # Each entry: {"symbol", "sumOpenInterest", "sumOpenInterestValue", "timestamp"}
    snapshots = [
        {"oi": float(e["sumOpenInterest"]), "oi_usd": float(e["sumOpenInterestValue"]), "ts": int(e["timestamp"])}
        for e in history
    ]

    def _roc(lookback_periods: int) -> dict[str, float]:
        if len(snapshots) < lookback_periods + 1:
            return {"roc_pct": 0.0, "oi_now": 0.0, "oi_then": 0.0}
        now = snapshots[-1]
        then = snapshots[-lookback_periods - 1]
        roc = (now["oi"] - then["oi"]) / then["oi"] * 100 if then["oi"] else 0
        return {"roc_pct": round(roc, 3), "oi_now": round(now["oi_usd"] / 1e6, 2), "oi_then": round(then["oi_usd"] / 1e6, 2)}

    oi_now = snapshots[-1]["oi_usd"]
    roc_1h = _roc(4)    # 4 × 15 min
    roc_4h = _roc(16)   # 16 × 15 min
    roc_24h = _roc(96)  # 96 × 15 min

    def _signal(roc: float) -> str:
        if roc > 2: return "STRONG_BULLISH"
        if roc > 0.5: return "BULLISH"
        if roc < -2: return "STRONG_BEARISH"
        if roc < -0.5: return "BEARISH"
        return "NEUTRAL"

    return {
        "status": "ok",
        "source": "binance_futures",
        "data": {
            "symbol": sym,
            "oi_usd_million": round(oi_now / 1e6, 2),
            "1h": {**roc_1h, "signal": _signal(roc_1h["roc_pct"])},
            "4h": {**roc_4h, "signal": _signal(roc_4h["roc_pct"])},
            "24h": {**roc_24h, "signal": _signal(roc_24h["roc_pct"])},
            "snapshots": snapshots[-24:],  # last 6 h for charting
        },
    }
