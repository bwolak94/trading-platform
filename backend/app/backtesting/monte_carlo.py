"""Monte Carlo Simulator — randomized trade sequence analysis."""

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from app.backtesting.walk_forward import Trade

logger = logging.getLogger(__name__)


@dataclass
class MonteCarloResult:
    """Result of a Monte Carlo simulation."""

    iterations: int = 0
    initial_capital: float = 0.0

    # Probability of ruin at various drawdown thresholds
    prob_ruin_20pct: float = 0.0
    prob_ruin_30pct: float = 0.0
    prob_ruin_50pct: float = 0.0

    # Equity curve percentiles (final equity values)
    percentile_5: float = 0.0
    percentile_25: float = 0.0
    percentile_50: float = 0.0
    percentile_75: float = 0.0
    percentile_95: float = 0.0

    # Max drawdown percentiles
    max_dd_percentile_5: float = 0.0
    max_dd_percentile_50: float = 0.0
    max_dd_percentile_95: float = 0.0

    # Full percentile equity curves for visualization
    equity_curves: dict[str, list[float]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "iterations": self.iterations,
            "initial_capital": self.initial_capital,
            "prob_ruin_20pct": round(self.prob_ruin_20pct, 2),
            "prob_ruin_30pct": round(self.prob_ruin_30pct, 2),
            "prob_ruin_50pct": round(self.prob_ruin_50pct, 2),
            "percentiles": {
                "5th": round(self.percentile_5, 2),
                "25th": round(self.percentile_25, 2),
                "50th": round(self.percentile_50, 2),
                "75th": round(self.percentile_75, 2),
                "95th": round(self.percentile_95, 2),
            },
            "max_drawdown_percentiles": {
                "5th": round(self.max_dd_percentile_5, 2),
                "50th": round(self.max_dd_percentile_50, 2),
                "95th": round(self.max_dd_percentile_95, 2),
            },
        }


class MonteCarloSimulator:
    """Monte Carlo simulation by randomizing trade order."""

    def run(
        self,
        trades: list[Trade],
        iterations: int = 1000,
        initial_capital: float = 10000.0,
    ) -> MonteCarloResult:
        """Run Monte Carlo simulation.

        Shuffles the order of trades N times, builds an equity curve
        for each iteration, and calculates probability of ruin
        and percentile distributions.
        """
        if not trades:
            logger.warning("No trades provided for Monte Carlo simulation")
            return MonteCarloResult(
                iterations=iterations, initial_capital=initial_capital
            )

        pnl_pcts = np.array([t.pnl_pct for t in trades])
        num_trades = len(pnl_pcts)

        final_equities = np.zeros(iterations)
        max_drawdowns = np.zeros(iterations)
        ruin_20 = 0
        ruin_30 = 0
        ruin_50 = 0

        # Store sampled equity curves for percentile visualization
        all_curves = np.zeros((iterations, num_trades + 1))

        for i in range(iterations):
            # Shuffle trade order
            shuffled = np.random.permutation(pnl_pcts)

            # Build equity curve
            equity_curve = self._build_equity_curve(shuffled, initial_capital)
            all_curves[i] = equity_curve

            final_equity = equity_curve[-1]
            final_equities[i] = final_equity

            # Max drawdown for this iteration
            max_dd = self._max_drawdown(equity_curve)
            max_drawdowns[i] = max_dd

            # Check ruin thresholds
            if max_dd >= 20.0:
                ruin_20 += 1
            if max_dd >= 30.0:
                ruin_30 += 1
            if max_dd >= 50.0:
                ruin_50 += 1

        # Percentile equity curves (take value at each trade step)
        curve_p5 = np.percentile(all_curves, 5, axis=0).tolist()
        curve_p25 = np.percentile(all_curves, 25, axis=0).tolist()
        curve_p50 = np.percentile(all_curves, 50, axis=0).tolist()
        curve_p75 = np.percentile(all_curves, 75, axis=0).tolist()
        curve_p95 = np.percentile(all_curves, 95, axis=0).tolist()

        result = MonteCarloResult(
            iterations=iterations,
            initial_capital=initial_capital,
            prob_ruin_20pct=(ruin_20 / iterations) * 100,
            prob_ruin_30pct=(ruin_30 / iterations) * 100,
            prob_ruin_50pct=(ruin_50 / iterations) * 100,
            percentile_5=float(np.percentile(final_equities, 5)),
            percentile_25=float(np.percentile(final_equities, 25)),
            percentile_50=float(np.percentile(final_equities, 50)),
            percentile_75=float(np.percentile(final_equities, 75)),
            percentile_95=float(np.percentile(final_equities, 95)),
            max_dd_percentile_5=float(np.percentile(max_drawdowns, 5)),
            max_dd_percentile_50=float(np.percentile(max_drawdowns, 50)),
            max_dd_percentile_95=float(np.percentile(max_drawdowns, 95)),
            equity_curves={
                "p5": curve_p5,
                "p25": curve_p25,
                "p50": curve_p50,
                "p75": curve_p75,
                "p95": curve_p95,
            },
        )

        logger.info(
            "Monte Carlo complete: %d iterations, %d trades | "
            "P(ruin 20%%)=%.1f%%, median final=$%.0f",
            iterations, num_trades, result.prob_ruin_20pct, result.percentile_50,
        )

        return result

    def _build_equity_curve(
        self, pnl_pcts: np.ndarray, initial_capital: float
    ) -> np.ndarray:
        """Build equity curve from shuffled trade P&L percentages."""
        curve = np.empty(len(pnl_pcts) + 1)
        curve[0] = initial_capital
        equity = initial_capital

        for i, pnl in enumerate(pnl_pcts):
            equity += equity * (pnl / 100)
            curve[i + 1] = equity

        return curve

    def _max_drawdown(self, equity_curve: np.ndarray) -> float:
        """Calculate maximum drawdown percentage from an equity curve."""
        peak = np.maximum.accumulate(equity_curve)
        drawdowns = np.where(peak > 0, (peak - equity_curve) / peak * 100, 0)
        return float(np.max(drawdowns))
