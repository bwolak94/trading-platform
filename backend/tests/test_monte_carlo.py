"""Tests for Monte Carlo simulator — deterministic results with seed."""

import datetime
import pytest
from app.backtesting.monte_carlo import MonteCarloSimulator
from app.backtesting.walk_forward import Trade


def _make_trade(pnl_pct: float, direction: str = "LONG") -> Trade:
    """Build a minimal Trade with all required fields."""
    today = datetime.date(2024, 1, 1)
    return Trade(
        asset="BTCUSDT",
        direction=direction,
        entry_price=50_000.0,
        exit_price=50_000.0 * (1 + pnl_pct / 100),
        stop_loss=48_000.0,
        take_profit_1=52_000.0,
        take_profit_2=54_000.0,
        entry_date=today,
        exit_date=today,
        pnl_pct=pnl_pct,
        result="WIN" if pnl_pct > 0 else "LOSS",
        strategy_name="trend_following",
    )


def _make_trades(win_rate: float = 0.5, n: int = 100) -> list[Trade]:
    """Generate synthetic trades for testing."""
    trades = []
    for i in range(n):
        pnl = 2.0 if (i % max(1, int(1 / win_rate))) == 0 else -1.0
        trades.append(_make_trade(pnl))
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

    def test_different_seeds_produce_different_drawdown_paths(self):
        """Different seeds should produce different path-dependent drawdown distributions.

        Note: in a multiplicative equity model all permutations of the same trade
        set yield the same *final* equity, so percentile_50 is seed-invariant.
        Max drawdown IS path-dependent and therefore varies across seeds.
        """
        trades = _make_trades(win_rate=0.5, n=50)
        sim = MonteCarloSimulator()
        results = [
            sim.run(trades, iterations=200, seed=seed)
            for seed in range(5)
        ]
        dd_values = [r.max_dd_percentile_50 for r in results]
        assert len(set(dd_values)) > 1, (
            "All seeds produced identical max_dd_percentile_50 — seeding may not work"
        )

    def test_no_trades_returns_empty_result(self):
        sim = MonteCarloSimulator()
        result = sim.run([], iterations=100, seed=0)
        assert result.iterations == 100
        assert result.prob_ruin_20pct == 0.0

    def test_positive_edge_has_low_ruin_probability(self):
        """Strategy with strong positive edge should have low ruin probability."""
        trades = [_make_trade(1.0)] * 80 + [_make_trade(-0.5)] * 20
        sim = MonteCarloSimulator()
        result = sim.run(trades, iterations=500, initial_capital=10000.0, seed=99)
        assert result.prob_ruin_20pct < 5.0  # < 5% ruin probability
