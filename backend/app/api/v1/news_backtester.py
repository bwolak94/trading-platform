"""News Event Backtester endpoint.

Shows how price historically moved in the ±4 h window around major macro events
(FOMC, CPI, NFP) for a given asset. Uses OHLCV data from Binance.

Also includes a slippage-aware P&L model: applies spread + market impact cost
to each historical trade to produce realistic return estimates.
"""

import logging
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Query

router = APIRouter(prefix="/backtest", tags=["news-backtester"])
logger = logging.getLogger(__name__)

# Historical macro event timestamps (UTC) — a representative sample.
# Production would pull from an economic calendar API.
_EVENTS: dict[str, list[str]] = {
    "FOMC": [
        "2024-01-31T19:00:00Z",
        "2024-03-20T18:00:00Z",
        "2024-05-01T18:00:00Z",
        "2024-06-12T18:00:00Z",
        "2024-07-31T18:00:00Z",
        "2024-09-18T18:00:00Z",
        "2024-11-07T19:00:00Z",
        "2024-12-18T19:00:00Z",
    ],
    "CPI": [
        "2024-01-11T13:30:00Z",
        "2024-02-13T13:30:00Z",
        "2024-03-12T12:30:00Z",
        "2024-04-10T12:30:00Z",
        "2024-05-15T12:30:00Z",
        "2024-06-12T12:30:00Z",
        "2024-07-11T12:30:00Z",
        "2024-08-14T12:30:00Z",
        "2024-09-11T12:30:00Z",
        "2024-10-10T12:30:00Z",
        "2024-11-13T13:30:00Z",
        "2024-12-11T13:30:00Z",
    ],
    "NFP": [
        "2024-01-05T13:30:00Z",
        "2024-02-02T13:30:00Z",
        "2024-03-08T13:30:00Z",
        "2024-04-05T12:30:00Z",
        "2024-05-03T12:30:00Z",
        "2024-06-07T12:30:00Z",
        "2024-07-05T12:30:00Z",
        "2024-08-02T12:30:00Z",
        "2024-09-06T12:30:00Z",
        "2024-10-04T12:30:00Z",
        "2024-11-01T12:30:00Z",
        "2024-12-06T13:30:00Z",
    ],
}

_SLIPPAGE_BPS: dict[str, float] = {
    "BTCUSDT": 2.0,
    "ETHUSDT": 3.0,
    "SOLUSDT": 5.0,
    "BNBUSDT": 4.0,
}
_DEFAULT_SLIPPAGE_BPS = 6.0
_TAKER_FEE_BPS = 4.0  # 0.04 % taker × 2 sides


async def _fetch_candles_around(symbol: str, event_ts: datetime, window_hours: int = 4) -> list[dict]:
    """Fetch hourly candles ±window_hours around an event timestamp."""
    import httpx
    start = event_ts - timedelta(hours=window_hours)
    end = event_ts + timedelta(hours=window_hours)
    url = "https://fapi.binance.com/fapi/v1/klines"
    params = {
        "symbol": symbol,
        "interval": "1h",
        "startTime": int(start.timestamp() * 1000),
        "endTime": int(end.timestamp() * 1000),
        "limit": window_hours * 2 + 2,
    }
    async with httpx.AsyncClient(timeout=8.0) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        raw = r.json()

    return [
        {
            "ts": int(c[0]),
            "open": float(c[1]),
            "high": float(c[2]),
            "low": float(c[3]),
            "close": float(c[4]),
            "volume": float(c[5]),
        }
        for c in raw
    ]


@router.get("/news-events/{symbol}", summary="News event price impact backtester")
async def backtest_news_events(
    symbol: str,
    event_type: str = Query("CPI", description="FOMC | CPI | NFP"),
    window_hours: int = Query(4, ge=1, le=12),
) -> dict[str, Any]:
    """Return historical price behaviour ±window_hours around past macro events.

    Applies realistic slippage + taker fee so P&L estimates reflect live trading costs.
    """
    sym = symbol.upper().replace("/", "")
    events = _EVENTS.get(event_type.upper(), [])
    if not events:
        return {"status": "unavailable", "data": {"reason": f"Unknown event type: {event_type}"}}

    slippage_bps = _SLIPPAGE_BPS.get(sym, _DEFAULT_SLIPPAGE_BPS)
    round_trip_cost_bps = slippage_bps + _TAKER_FEE_BPS * 2  # entry + exit

    results: list[dict[str, Any]] = []
    for ts_str in events[-8:]:  # last 8 occurrences
        try:
            event_dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            candles = await _fetch_candles_around(sym, event_dt, window_hours)
            if len(candles) < 3:
                continue

            pre_price = candles[0]["open"]
            event_idx = len(candles) // 2
            at_event = candles[event_idx]["open"] if event_idx < len(candles) else pre_price
            post_price = candles[-1]["close"]

            move_pct = (post_price - at_event) / at_event * 100 if at_event else 0
            # Net of round-trip cost
            net_pct = move_pct - (round_trip_cost_bps / 100) * (1 if move_pct > 0 else -1)

            results.append({
                "event_date": ts_str[:10],
                "pre_price": round(pre_price, 2),
                "at_event_price": round(at_event, 2),
                "post_price": round(post_price, 2),
                "gross_move_pct": round(move_pct, 3),
                "net_move_pct": round(net_pct, 3),
                "direction": "UP" if move_pct > 0 else "DOWN",
                "candles": candles,
            })
        except Exception as exc:
            logger.debug("Skipping event %s: %s", ts_str, exc)

    if not results:
        return {"status": "unavailable", "data": {"reason": "No candle data for events"}}

    moves = [r["gross_move_pct"] for r in results]
    net_moves = [r["net_move_pct"] for r in results]
    up_count = sum(1 for m in moves if m > 0)

    return {
        "status": "ok",
        "source": "binance_futures",
        "data": {
            "symbol": sym,
            "event_type": event_type.upper(),
            "window_hours": window_hours,
            "slippage_bps": slippage_bps,
            "round_trip_cost_bps": round_trip_cost_bps,
            "events_analysed": len(results),
            "up_count": up_count,
            "down_count": len(results) - up_count,
            "avg_gross_move_pct": round(sum(moves) / len(moves), 3),
            "avg_net_move_pct": round(sum(net_moves) / len(net_moves), 3),
            "max_move_pct": round(max(moves, key=abs), 3),
            "instances": results,
        },
    }
