"""Smart Stop Loss Optimizer — scans historical candles to find the ATR multiplier
that maximises win rate while keeping max drawdown below a configurable threshold."""

from typing import Any

import httpx
from fastapi import APIRouter, Query

from app.core.logging import get_logger

router = APIRouter(tags=["analysis"])
logger = get_logger(__name__)

_BINANCE_KLINES = "https://api.binance.com/api/v3/klines"


async def _fetch_klines(symbol: str, interval: str, limit: int = 200) -> list[dict]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            _BINANCE_KLINES,
            params={"symbol": symbol, "interval": interval, "limit": limit},
        )
        resp.raise_for_status()
    raw = resp.json()
    return [
        {
            "high": float(r[2]),
            "low": float(r[3]),
            "close": float(r[4]),
        }
        for r in raw
    ]


def _compute_atr(candles: list[dict], period: int = 14) -> list[float]:
    trs = []
    for i in range(1, len(candles)):
        prev_close = candles[i - 1]["close"]
        h, l, c = candles[i]["high"], candles[i]["low"], prev_close
        tr = max(h - l, abs(h - c), abs(l - c))
        trs.append(tr)
    atrs: list[float] = []
    for i in range(len(trs)):
        window = trs[max(0, i - period + 1) : i + 1]
        atrs.append(sum(window) / len(window))
    return atrs


def _backtest_multiplier(
    candles: list[dict],
    atrs: list[float],
    mult: float,
    max_dd_threshold: float,
) -> dict:
    wins = losses = 0
    equity = 1.0
    peak = 1.0
    max_dd = 0.0

    for i in range(len(atrs) - 1):
        entry = candles[i + 1]["close"]
        stop = atrs[i] * mult
        tp = stop * 1.5  # fixed 1.5 R/R target

        # Simulate long trade on next candle
        hi = candles[i + 1]["high"]
        lo = candles[i + 1]["low"]

        if lo <= entry - stop:
            losses += 1
            equity *= 1 - (stop / entry)
        elif hi >= entry + tp:
            wins += 1
            equity *= 1 + (tp / entry)

        peak = max(peak, equity)
        dd = (peak - equity) / peak
        max_dd = max(max_dd, dd)

    total = wins + losses
    win_rate = wins / total if total else 0.0
    return {
        "multiplier": round(mult, 2),
        "win_rate": round(win_rate * 100, 1),
        "max_drawdown_pct": round(max_dd * 100, 2),
        "total_trades": total,
        "wins": wins,
        "losses": losses,
        "feasible": max_dd * 100 < max_dd_threshold,
    }


@router.get("/analysis/stop-loss-optimizer/{symbol}", summary="Smart Stop Loss Optimizer")
async def stop_loss_optimizer(
    symbol: str,
    timeframe: str = Query("1h", description="Candle timeframe"),
    max_drawdown_pct: float = Query(5.0, description="Max acceptable drawdown %"),
) -> dict[str, Any]:
    """Scan ATR multipliers 0.5–3.0 and recommend the one that maximises win rate
    while keeping max drawdown below the specified threshold.

    Returns a ranked list of tested multipliers with their stats and a recommended value.
    """
    sym = symbol.upper()
    if not sym.endswith("USDT"):
        sym = f"{sym}USDT"

    candles = await _fetch_klines(sym, timeframe, limit=200)
    if len(candles) < 30:
        return {"error": "insufficient_data", "symbol": sym}

    atrs = _compute_atr(candles)

    results = []
    for mult_x10 in range(5, 31):  # 0.5 to 3.0 in 0.1 steps
        mult = mult_x10 / 10
        r = _backtest_multiplier(candles, atrs, mult, max_drawdown_pct)
        results.append(r)

    feasible = [r for r in results if r["feasible"]]
    recommendation = max(feasible, key=lambda r: r["win_rate"]) if feasible else None

    return {
        "symbol": sym,
        "timeframe": timeframe,
        "max_drawdown_threshold_pct": max_drawdown_pct,
        "candles_analyzed": len(candles),
        "recommendation": recommendation,
        "all_results": results,
    }
