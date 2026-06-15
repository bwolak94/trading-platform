"""Benchmark comparison endpoints.

Compares paper trading performance against:
- BTC Buy & Hold
- ETH Buy & Hold
- Equal-weight crypto portfolio (BTC + ETH + SOL + BNB)
"""

import math
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db

router = APIRouter(tags=["benchmark"])

# Symbols used in equal-weight benchmark
_EW_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]


def _compute_returns_and_sharpe(
    equity_curve: list[dict[str, Any]],
) -> tuple[float, float, float]:
    """Compute total return %, Sharpe ratio, and max drawdown % from equity curve.

    Args:
        equity_curve: List of {"date": str, "value": float} sorted ascending.

    Returns:
        (total_return_pct, sharpe_ratio, max_drawdown_pct)
    """
    if len(equity_curve) < 2:
        return 0.0, 0.0, 0.0

    values = [p["value"] for p in equity_curve]
    start = values[0]
    end = values[-1]

    if start <= 0:
        return 0.0, 0.0, 0.0

    total_return_pct = round((end / start - 1) * 100, 4)

    # Daily returns for Sharpe
    daily_returns: list[float] = []
    for i in range(1, len(values)):
        if values[i - 1] > 0:
            daily_returns.append(values[i] / values[i - 1] - 1)

    if len(daily_returns) < 2:
        return total_return_pct, 0.0, 0.0

    mean_r = sum(daily_returns) / len(daily_returns)
    variance = sum((r - mean_r) ** 2 for r in daily_returns) / (len(daily_returns) - 1)
    std_r = math.sqrt(variance) if variance > 0 else 0.0
    sharpe = round((mean_r / std_r * math.sqrt(365)) if std_r > 0 else 0.0, 4)

    # Max drawdown
    peak = values[0]
    max_dd = 0.0
    for v in values[1:]:
        if v > peak:
            peak = v
        dd = (peak - v) / peak * 100 if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd

    return total_return_pct, sharpe, round(max_dd, 4)


def _build_price_curve(
    prices: list[tuple[datetime, float]],
    start_value: float = 100.0,
) -> list[dict[str, Any]]:
    """Convert a list of (timestamp, price) pairs into an indexed equity curve.

    The curve is normalised so the first point = start_value (default 100).
    """
    if not prices:
        return []
    base = prices[0][1]
    if base <= 0:
        return []
    return [
        {
            "date": ts.date().isoformat(),
            "value": round(start_value * price / base, 4),
        }
        for ts, price in prices
    ]


@router.get("/benchmark/comparison")
async def get_benchmark_comparison(
    lookback_days: int = Query(default=30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Compare paper trading equity curve vs benchmark strategies.

    Fetches:
    1. Paper trading equity curve from SimulatedPosition (closed P&L cumulated).
    2. BTC and ETH price history from the market_data table.
    3. Computes returns, Sharpe ratio, and max drawdown for each benchmark.

    Returns:
        {
            "period_days": int,
            "paper_trading": {"total_return_pct": float, "sharpe": float, "max_drawdown_pct": float},
            "benchmarks": {
                "btc_hold": {"total_return_pct": float, "sharpe": float},
                "eth_hold": {"total_return_pct": float, "sharpe": float},
                "equal_weight": {"total_return_pct": float, "sharpe": float},
            },
            "alpha": float,
            "equity_curves": {
                "paper_trading": [{"date": str, "value": float}],
                "btc_hold": [{"date": str, "value": float}],
                "eth_hold": [{"date": str, "value": float}],
            }
        }
    """
    from app.models.market_data import MarketData
    from app.models.simulated_position import SimulatedPosition

    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)

    # ----------------------------------------------------------------
    # 1. Paper trading equity curve
    # ----------------------------------------------------------------
    pos_stmt = (
        select(SimulatedPosition)
        .where(SimulatedPosition.opened_at >= cutoff)
        .where(SimulatedPosition.status != "OPEN")
        .order_by(SimulatedPosition.closed_at)
    )
    pos_result = await db.execute(pos_stmt)
    positions = list(pos_result.scalars().all())

    # Cumulate PnL as equity growth starting at 100
    paper_curve: list[dict[str, Any]] = []
    equity = 100.0
    for pos in positions:
        pnl = float(pos.pnl_pct or 0)
        equity = equity * (1 + pnl / 100)
        date = (pos.closed_at or pos.opened_at)
        if date:
            paper_curve.append({
                "date": date.date().isoformat(),
                "value": round(equity, 4),
            })

    # Ensure we have at least a start point
    if not paper_curve:
        paper_curve = [
            {"date": cutoff.date().isoformat(), "value": 100.0},
            {"date": datetime.now(timezone.utc).date().isoformat(), "value": 100.0},
        ]

    # ----------------------------------------------------------------
    # 2. BTC and ETH price histories (daily close from market_data)
    # ----------------------------------------------------------------
    async def _fetch_prices(asset: str) -> list[tuple[datetime, float]]:
        stmt = (
            select(MarketData.timestamp, MarketData.close)
            .where(MarketData.asset == asset)
            .where(MarketData.timeframe == "1d")
            .where(MarketData.timestamp >= cutoff)
            .order_by(MarketData.timestamp)
        )
        result = await db.execute(stmt)
        rows = result.all()
        return [(row[0], float(row[1])) for row in rows]

    btc_prices = await _fetch_prices("BTCUSDT")
    eth_prices = await _fetch_prices("ETHUSDT")
    sol_prices = await _fetch_prices("SOLUSDT")
    bnb_prices = await _fetch_prices("BNBUSDT")

    btc_curve = _build_price_curve(btc_prices)
    eth_curve = _build_price_curve(eth_prices)

    # Equal-weight curve: average daily return across BTC / ETH / SOL / BNB
    def _prices_to_returns(prices: list[tuple[datetime, float]]) -> list[float]:
        if len(prices) < 2:
            return []
        return [
            prices[i][1] / prices[i - 1][1] - 1
            for i in range(1, len(prices))
        ]

    ew_dates: list[datetime] = []
    ew_values: list[dict[str, Any]] = []
    all_series = [btc_prices, eth_prices, sol_prices, bnb_prices]
    series_with_data = [s for s in all_series if len(s) >= 2]

    if series_with_data:
        min_len = min(len(s) for s in series_with_data)
        ew_equity = 100.0
        for i in range(1, min_len):
            avg_return = sum(
                (s[i][1] / s[i - 1][1] - 1) for s in series_with_data
            ) / len(series_with_data)
            ew_equity *= 1 + avg_return
            ew_dates.append(series_with_data[0][i][0])
            ew_values.append({
                "date": series_with_data[0][i][0].date().isoformat(),
                "value": round(ew_equity, 4),
            })

    # ----------------------------------------------------------------
    # 3. Compute statistics
    # ----------------------------------------------------------------
    pt_ret, pt_sharpe, pt_dd = _compute_returns_and_sharpe(paper_curve)
    btc_ret, btc_sharpe, btc_dd = _compute_returns_and_sharpe(btc_curve)
    eth_ret, eth_sharpe, eth_dd = _compute_returns_and_sharpe(eth_curve)
    ew_ret, ew_sharpe, ew_dd = _compute_returns_and_sharpe(ew_values)

    alpha = round(pt_ret - btc_ret, 4)

    return {
        "period_days": lookback_days,
        "paper_trading": {
            "total_return_pct": pt_ret,
            "sharpe": pt_sharpe,
            "max_drawdown_pct": pt_dd,
        },
        "benchmarks": {
            "btc_hold": {
                "total_return_pct": btc_ret,
                "sharpe": btc_sharpe,
                "max_drawdown_pct": btc_dd,
            },
            "eth_hold": {
                "total_return_pct": eth_ret,
                "sharpe": eth_sharpe,
                "max_drawdown_pct": eth_dd,
            },
            "equal_weight": {
                "total_return_pct": ew_ret,
                "sharpe": ew_sharpe,
                "max_drawdown_pct": ew_dd,
            },
        },
        "alpha": alpha,
        "equity_curves": {
            "paper_trading": paper_curve,
            "btc_hold": btc_curve,
            "eth_hold": eth_curve,
            "equal_weight": ew_values,
        },
    }
