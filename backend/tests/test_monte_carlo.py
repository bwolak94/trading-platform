"""Tests for Monte Carlo simulator — deterministic results with seed."""

import pytest
from app.backtesting.monte_carlo import MonteCarloSimulator
from app.backtesting.walk_forward import Trade


def _make_trades(win_rate: float = 0.5, n: int = 100) -> list[Trade]:
    """Generate synthetic trades for testing."""
    trades = []
    for i in range(n):
        pnl = 2.0 if (i % int(1 / win_rate)) == 0 else -1.0
        trades.append(Trade(pnl_pct=pnl))
    return trades


class TestMonteCarloSimulator:
    def test_reproducible_with_seed(self):
        """Same seed produces identical results — critical for test determinism."""
        trades = _make_trades(win_rate=0.5, n=50)
        sim = MonteCarloSimulator()
        r1 = sim.run(trades, iterations=200, seed=42)
        r2 = sim.run(trades, iterations=200, seed=42)
        assert r1.prob_ruin_20pct == r2.prob_ruin_20pct
        assert r1.percentile_50 == r2.percentile_50

    def test_different_seeds_differ(self):
        """Different seeds should (almost certainly) produce different results."""
        trades = _make_trades(win_rate=0.5, n=50)
        sim = MonteCarloSimulator()
        r1 = sim.run(trades, iterations=500, seed=1)
        r2 = sim.run(trades, iterations=500, seed=2)
        # Not deterministically different, but overwhelmingly likely to be
        assert r1.percentile_50 != r2.percentile_50

    def test_no_trades_returns_empty_result(self):
        sim = MonteCarloSimulator()
        result = sim.run([], iterations=100, seed=0)
        assert result.iterations == 100
        assert result.prob_ruin_20pct == 0.0

    def test_positive_edge_has_low_ruin_probability(self):
        """Strategy with strong positive edge should have low ruin probability."""
        trades = [Trade(pnl_pct=1.0)] * 80 + [Trade(pnl_pct=-0.5)] * 20
        sim = MonteCarloSimulator()
        result = sim.run(trades, iterations=500, initial_capital=10000.0, seed=99)
        assert result.prob_ruin_20pct < 5.0  # < 5% ruin probability
