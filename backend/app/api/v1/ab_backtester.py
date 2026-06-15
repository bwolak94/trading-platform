"""Strategy A/B Backtester — side-by-side comparison of two strategy parameter sets
over a chosen date range. Returns equity curves and key metrics for both variants."""

from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Query

from app.core.logging import get_logger

router = APIRouter(tags=["backtesting"])
logger = get_logger(__name__)

_BINANCE_KLINES = "https://api.binance.com/api/v3/klines"


async def _fetch_klines(symbol: str, interval: str, limit: int = 500) -> list[dict]:
    async with httpx.AsyncClient(timeout=12.0) as client:
        resp = await client.get(
            _BINANCE_KLINES,
            params={"symbol": symbol, "interval": interval, "limit": limit},
        )
        resp.raise_for_status()
    raw = resp.json()
    return [
        {
            "ts": int(r[0]),
            "open": float(r[1]),
            "high": float(r[2]),
            "low": float(r[3]),
            "close": float(r[4]),
            "volume": float(r[5]),
        }
        for r in raw
    ]


def _compute_atr(candles: list[dict], period: int = 14) -> list[float]:
    trs = [candles[0]["high"] - candles[0]["low"]]
    for i in range(1, len(candles)):
        pc = candles[i - 1]["close"]
        tr = max(
            candles[i]["high"] - candles[i]["low"],
            abs(candles[i]["high"] - pc),
            abs(candles[i]["low"] - pc),
        )
        trs.append(tr)
    atrs: list[float] = []
    for i in range(len(trs)):
        window = trs[max(0, i - period + 1): i + 1]
        atrs.append(sum(window) / len(window))
    return atrs


def _run_variant(
    candles: list[dict],
    atrs: list[float],
    atr_mult: float,
    rr_ratio: float,
    confidence_threshold: float,
    initial_capital: float,
) -> dict[str, Any]:
    """Simulate a simple ATR-based trend strategy with given parameters."""
    equity = initial_capital
    peak = equity
    max_dd = 0.0
    trades: list[dict] = []
    equity_curve: list[dict] = []

    for i in range(15, len(candles) - 1):
        entry = candles[i]["close"]
        atr = atrs[i]
        stop_dist = atr * atr_mult
        tp_dist = stop_dist * rr_ratio

        # Entry signal: close above 20-period high (breakout)
        recent_highs = [c["high"] for c in candles[i - 20: i]]
        if not recent_highs:
            continue
        if entry < max(recent_highs) * (confidence_threshold / 100):
            continue

        risk_usd = equity * 0.01  # 1% risk per trade
        risk_usd / stop_dist if stop_dist > 0 else 0

        next_hi = candles[i + 1]["high"]
        next_lo = candles[i + 1]["low"]

        if next_lo <= entry - stop_dist:
            pnl = -risk_usd
        elif next_hi >= entry + tp_dist:
            pnl = risk_usd * rr_ratio
        else:
            continue  # no fill this bar

        equity += pnl
        peak = max(peak, equity)
        dd = (peak - equity) / peak
        max_dd = max(max_dd, dd)
        trades.append({"pnl": round(pnl, 2), "win": pnl > 0})
        equity_curve.append({"ts": candles[i]["ts"], "equity": round(equity, 2)})

    wins = sum(1 for t in trades if t["win"])
    total = len(trades)
    returns = [t["pnl"] / initial_capital for t in trades]
    sharpe = 0.0
    if returns and len(returns) > 1:
        import statistics
        avg_r = sum(returns) / len(returns)
        std_r = statistics.stdev(returns)
        sharpe = (avg_r / std_r) * (252 ** 0.5) if std_r > 0 else 0.0

    return {
        "total_trades": total,
        "wins": wins,
        "win_rate_pct": round(wins / total * 100, 1) if total else 0,
        "net_pnl": round(equity - initial_capital, 2),
        "net_pnl_pct": round((equity - initial_capital) / initial_capital * 100, 2),
        "max_drawdown_pct": round(max_dd * 100, 2),
        "sharpe": round(sharpe, 3),
        "equity_curve": equity_curve[-100:],  # last 100 points
    }


@router.get("/backtest/ab-compare/{symbol}", summary="Strategy A/B Backtester")
async def ab_backtest(
    symbol: str,
    timeframe: str = Query("1h"),
    atr_mult_a: float = Query(1.5, description="ATR multiplier for variant A"),
    atr_mult_b: float = Query(2.5, description="ATR multiplier for variant B"),
    rr_ratio_a: float = Query(1.5, description="R/R ratio for variant A"),
    rr_ratio_b: float = Query(2.0, description="R/R ratio for variant B"),
    confidence_a: float = Query(98.0, description="Confidence threshold % for variant A"),
    confidence_b: float = Query(95.0, description="Confidence threshold % for variant B"),
    initial_capital: float = Query(10000.0),
) -> dict[str, Any]:
    """Compare two strategy variants side-by-side over historical data.

    Returns equity curves, Sharpe ratios, win rates, and a winner declaration
    based on risk-adjusted returns (Sharpe ratio).
    """
    sym = symbol.upper()
    if not sym.endswith("USDT"):
        sym = f"{sym}USDT"

    candles = await _fetch_klines(sym, timeframe, limit=500)
    if len(candles) < 50:
        return {"error": "insufficient_data", "symbol": sym}

    atrs = _compute_atr(candles)

    variant_a = _run_variant(candles, atrs, atr_mult_a, rr_ratio_a, confidence_a, initial_capital)
    variant_b = _run_variant(candles, atrs, atr_mult_b, rr_ratio_b, confidence_b, initial_capital)

    winner = "A" if variant_a["sharpe"] >= variant_b["sharpe"] else "B"
    sharpe_diff = round(abs(variant_a["sharpe"] - variant_b["sharpe"]), 3)

    return {
        "symbol": sym,
        "timeframe": timeframe,
        "candles_analyzed": len(candles),
        "initial_capital": initial_capital,
        "variant_a": {
            "label": "A",
            "params": {"atr_mult": atr_mult_a, "rr_ratio": rr_ratio_a, "confidence_threshold": confidence_a},
            **variant_a,
        },
        "variant_b": {
            "label": "B",
            "params": {"atr_mult": atr_mult_b, "rr_ratio": rr_ratio_b, "confidence_threshold": confidence_b},
            **variant_b,
        },
        "winner": winner,
        "sharpe_diff": sharpe_diff,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
