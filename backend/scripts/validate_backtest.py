"""Backtest validation — run strategies on BTC/USDT 2023-2024 and verify metrics.

Usage:
    python -m scripts.validate_backtest

Expected thresholds (from spec):
    - Win rate > 50%
    - Max drawdown < 20%
"""

import asyncio
import logging
from datetime import date

import pandas as pd
from sqlalchemy import select

from app.ai.strategies.mean_reversion import MeanReversionStrategy
from app.ai.strategies.trend_following import TrendFollowingStrategy
from app.ai.strategies.volume_breakout import VolumeBreakoutStrategy
from app.backtesting.monte_carlo import MonteCarloSimulator
from app.backtesting.walk_forward import WalkForwardBacktester
from app.core.database import async_session
from app.data.processors.feature_engineer import compute_features
from app.models.market_data import MarketData

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ASSET = "BTC/USDT"
TIMEFRAME = "4h"
START = date(2023, 1, 1)
END = date(2025, 1, 1)
INITIAL_CAPITAL = 10000.0

# Thresholds from spec
MIN_WIN_RATE = 50.0
MAX_DRAWDOWN = 20.0

STRATEGIES = [
    TrendFollowingStrategy(),
    MeanReversionStrategy(),
    VolumeBreakoutStrategy(),
]


async def load_data() -> pd.DataFrame:
    """Load historical market data from DB."""
    async with async_session() as session:
        result = await session.execute(
            select(MarketData)
            .where(
                MarketData.asset == ASSET,
                MarketData.timeframe == TIMEFRAME,
            )
            .order_by(MarketData.timestamp.asc())
        )
        rows = result.scalars().all()

    if not rows:
        logger.error("No data found for %s %s — run backfill first", ASSET, TIMEFRAME)
        return pd.DataFrame()

    df = pd.DataFrame([{
        "timestamp": r.timestamp,
        "open": float(r.open),
        "high": float(r.high),
        "low": float(r.low),
        "close": float(r.close),
        "volume": float(r.volume),
    } for r in rows])

    logger.info("Loaded %d candles for %s %s", len(df), ASSET, TIMEFRAME)
    return df


async def validate():
    """Run backtests and validate against thresholds."""
    df = await load_data()
    if df.empty:
        return

    backtester = WalkForwardBacktester()
    mc = MonteCarloSimulator()
    all_passed = True

    for strategy in STRATEGIES:
        logger.info("=" * 60)
        logger.info("Testing: %s", strategy.name)
        logger.info("=" * 60)

        result = backtester.run(
            strategy=strategy,
            market_data=df,
            asset=ASSET,
            timeframe=TIMEFRAME,
            start_date=START,
            end_date=END,
            initial_capital=INITIAL_CAPITAL,
        )

        m = result.metrics
        logger.info("Total trades:   %d", m.total_trades)
        logger.info("Win rate:       %.2f%%", m.win_rate)
        logger.info("Profit factor:  %.4f", m.profit_factor)
        logger.info("Max drawdown:   %.2f%%", m.max_drawdown)
        logger.info("Sharpe ratio:   %.4f", m.sharpe_ratio)
        logger.info("Calmar ratio:   %.4f", m.calmar_ratio)
        logger.info("Total return:   %.2f%%", m.total_return_pct)

        # Monte Carlo
        if result.trades:
            mc_result = mc.run(result.trades, iterations=1000, initial_capital=INITIAL_CAPITAL)
            logger.info("MC P(ruin 20%%): %.1f%%", mc_result.prob_ruin_20pct)
            logger.info("MC P(ruin 30%%): %.1f%%", mc_result.prob_ruin_30pct)
            logger.info("MC median final: $%.0f", mc_result.percentile_50)

        # Validate thresholds
        wr_pass = m.win_rate >= MIN_WIN_RATE or m.total_trades == 0
        dd_pass = m.max_drawdown <= MAX_DRAWDOWN or m.total_trades == 0

        if not wr_pass:
            logger.warning(
                "FAIL: Win rate %.2f%% < %.1f%% threshold", m.win_rate, MIN_WIN_RATE
            )
            all_passed = False
        if not dd_pass:
            logger.warning(
                "FAIL: Max drawdown %.2f%% > %.1f%% threshold", m.max_drawdown, MAX_DRAWDOWN
            )
            all_passed = False

        if wr_pass and dd_pass:
            logger.info("PASS: %s meets all thresholds", strategy.name)

        logger.info("")

    if all_passed:
        logger.info("ALL STRATEGIES PASSED VALIDATION")
    else:
        logger.warning(
            "SOME STRATEGIES FAILED — consider adjusting parameters"
        )


if __name__ == "__main__":
    asyncio.run(validate())
