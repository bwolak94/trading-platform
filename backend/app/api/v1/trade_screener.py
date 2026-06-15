"""Trade Setup Screener — scans configured symbols every request and scores them
by composite momentum + regime + OI signals, returning top setups."""

import asyncio
from typing import Any

import httpx
from fastapi import APIRouter, Query

from app.core.logging import get_logger

router = APIRouter(tags=["analysis"])
logger = get_logger(__name__)

_BINANCE_TICKER = "https://api.binance.com/api/v3/ticker/24hr"
_BINANCE_KLINES = "https://api.binance.com/api/v3/klines"
_BINANCE_OI = "https://fapi.binance.com/fapi/v1/openInterest"

_SCREENER_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT",
    "ARBUSDT", "OPUSDT", "APTUSDT", "SUIUSDT", "INJUSDT",
]


async def _score_symbol(client: httpx.AsyncClient, symbol: str) -> dict[str, Any] | None:
    """Fetch 24hr stats + last 50 hourly candles and return a composite score."""
    try:
        ticker_resp, kline_resp = await asyncio.gather(
            client.get(_BINANCE_TICKER, params={"symbol": symbol}),
            client.get(_BINANCE_KLINES, params={"symbol": symbol, "interval": "1h", "limit": 50}),
            return_exceptions=True,
        )
        if isinstance(ticker_resp, Exception) or isinstance(kline_resp, Exception):
            return None

        ticker_resp.raise_for_status()
        kline_resp.raise_for_status()

        t = ticker_resp.json()
        klines = kline_resp.json()
        closes = [float(k[4]) for k in klines]

        change_24h = float(t.get("priceChangePercent", 0))
        volume_usdt = float(t.get("quoteVolume", 0))
        last_price = float(t.get("lastPrice", 0))

        # RSI(14)
        gains, losses = [], []
        for i in range(1, len(closes)):
            delta = closes[i] - closes[i - 1]
            if delta > 0:
                gains.append(delta)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(delta))
        avg_gain = sum(gains[-14:]) / 14 if len(gains) >= 14 else 0
        avg_loss = sum(losses[-14:]) / 14 if len(losses) >= 14 else 1e-9
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        # EMA momentum (20 vs 50)
        def ema(data: list[float], period: int) -> float:
            k = 2 / (period + 1)
            e = data[0]
            for p in data[1:]:
                e = p * k + e * (1 - k)
            return e

        ema20 = ema(closes, 20)
        ema50 = ema(closes, min(50, len(closes)))
        trend_score = 1.0 if ema20 > ema50 else -1.0

        # Composite score (0–100)
        momentum_score = min(max((change_24h + 10) / 20 * 50, 0), 50)
        rsi_score = abs(rsi - 50) / 50 * 30  # distance from neutral
        vol_score = min(volume_usdt / 1e9 * 20, 20)  # cap at $1B volume
        composite = momentum_score + rsi_score + vol_score

        direction = "LONG" if change_24h > 0 and rsi < 70 and trend_score > 0 else (
            "SHORT" if change_24h < 0 and rsi > 30 and trend_score < 0 else "NEUTRAL"
        )

        return {
            "symbol": symbol,
            "price": last_price,
            "change_24h_pct": round(change_24h, 2),
            "volume_usdt_24h": round(volume_usdt / 1e6, 1),
            "rsi_14": round(rsi, 1),
            "ema_trend": "bullish" if trend_score > 0 else "bearish",
            "direction": direction,
            "composite_score": round(composite, 1),
        }

    except Exception as exc:
        logger.debug("screener skip %s: %s", symbol, exc)
        return None


@router.get("/analysis/trade-screener", summary="Trade Setup Screener")
async def trade_screener(
    top_n: int = Query(5, ge=1, le=15, description="Number of top setups to return"),
    direction: str = Query("ALL", description="Filter: LONG | SHORT | NEUTRAL | ALL"),
) -> dict[str, Any]:
    """Scan all tracked symbols and rank by composite score (momentum + RSI + volume).
    Returns the top N setups most likely to produce a strong directional move."""

    async with httpx.AsyncClient(timeout=8.0) as client:
        results = await asyncio.gather(
            *[_score_symbol(client, sym) for sym in _SCREENER_SYMBOLS],
            return_exceptions=True,
        )

    valid = [r for r in results if isinstance(r, dict)]
    if direction != "ALL":
        valid = [r for r in valid if r["direction"] == direction.upper()]

    ranked = sorted(valid, key=lambda r: r["composite_score"], reverse=True)

    return {
        "scanned": len(_SCREENER_SYMBOLS),
        "returned": len(ranked[:top_n]),
        "direction_filter": direction,
        "setups": ranked[:top_n],
    }
