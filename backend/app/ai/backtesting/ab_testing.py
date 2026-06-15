"""A/B testing framework for strategy variants.

Provides deterministic hash-based assignment of signals to control/treatment
groups, result recording, and simple win-rate comparison to declare a winner
once a minimum number of trades has been reached.
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import logging

logger = logging.getLogger(__name__)


class VariantAssignment(Enum):
    """Variant identifiers for A/B test groups."""

    CONTROL = "control"
    TREATMENT = "treatment"


@dataclass
class VariantStats:
    """Accumulated statistics for a single A/B test variant."""

    variant: str
    trades: int = 0
    wins: int = 0
    total_pnl_pct: float = 0.0
    sharpe_ratio: float = 0.0

    @property
    def win_rate(self) -> float:
        """Win rate as a fraction (0-1). Returns 0 when no trades recorded."""
        return self.wins / self.trades if self.trades > 0 else 0.0

    @property
    def avg_pnl(self) -> float:
        """Average PnL per trade. Returns 0 when no trades recorded."""
        return self.total_pnl_pct / self.trades if self.trades > 0 else 0.0


@dataclass
class ABTest:
    """Configuration and live stats for a single A/B test."""

    test_id: str
    strategy_name: str
    description: str
    control_params: dict
    treatment_params: dict
    started_at: float = field(default_factory=time.time)
    min_trades: int = 50
    control_stats: VariantStats = field(default_factory=lambda: VariantStats("control"))
    treatment_stats: VariantStats = field(default_factory=lambda: VariantStats("treatment"))
    active: bool = True


# Module-level storage (in-memory for the lifetime of the process)
_active_tests: dict[str, ABTest] = {}
_assignment_log: list[dict] = []


def create_ab_test(
    test_id: str,
    strategy_name: str,
    description: str,
    control_params: dict,
    treatment_params: dict,
    min_trades: int = 50,
) -> ABTest:
    """Create and register a new A/B test.

    Args:
        test_id: Unique identifier for this test.
        strategy_name: Name of the strategy being tested.
        description: Human-readable description of what is being varied.
        control_params: Parameter dict for the control (baseline) variant.
        treatment_params: Parameter dict for the treatment (experimental) variant.
        min_trades: Minimum completed trades before a winner can be declared.

    Returns:
        The newly created ABTest instance.
    """
    test = ABTest(
        test_id=test_id,
        strategy_name=strategy_name,
        description=description,
        control_params=control_params,
        treatment_params=treatment_params,
        min_trades=min_trades,
    )
    _active_tests[test_id] = test
    logger.info("A/B test created: %s (%s)", test_id, strategy_name)
    return test


def get_variant_for_signal(test_id: str, signal_id: str) -> Optional[tuple[str, dict]]:
    """Deterministically assign a signal to control or treatment.

    Uses a hash of (test_id, signal_id) for a reproducible 50/50 split so
    the same signal always lands in the same bucket regardless of order.

    Args:
        test_id: The A/B test to assign against.
        signal_id: Unique identifier for the signal being assigned.

    Returns:
        A (variant_name, params) tuple, or None if the test is not found / inactive.
    """
    test = _active_tests.get(test_id)
    if not test or not test.active:
        return None

    # Hash-based 50/50 split — deterministic per (test_id, signal_id) pair
    hash_val = hash(f"{test_id}:{signal_id}") % 2
    variant = "treatment" if hash_val == 0 else "control"
    params = test.treatment_params if variant == "treatment" else test.control_params

    _assignment_log.append(
        {
            "test_id": test_id,
            "signal_id": signal_id,
            "variant": variant,
            "timestamp": time.time(),
        }
    )

    return variant, params


def record_ab_trade_result(test_id: str, variant: str, pnl_pct: float, won: bool) -> None:
    """Record a closed trade result against an A/B test variant.

    Args:
        test_id: The A/B test the trade belongs to.
        variant: Either "control" or "treatment".
        pnl_pct: Percentage PnL for the closed trade.
        won: True if the trade was profitable.
    """
    test = _active_tests.get(test_id)
    if not test:
        return

    stats = test.control_stats if variant == "control" else test.treatment_stats
    stats.trades += 1
    stats.total_pnl_pct += pnl_pct
    if won:
        stats.wins += 1


def get_ab_test_results(test_id: str) -> Optional[dict]:
    """Return serializable results for an A/B test, including a winner determination.

    A winner is only declared once both variants have reached min_trades.
    Treatment is considered better when its win rate exceeds the control by 5%.

    Args:
        test_id: The A/B test to query.

    Returns:
        A result dict, or None if the test does not exist.
    """
    test = _active_tests.get(test_id)
    if not test:
        return None

    c = test.control_stats
    t = test.treatment_stats

    winner: Optional[str] = None
    can_determine = c.trades >= test.min_trades and t.trades >= test.min_trades
    if can_determine:
        if t.win_rate > c.win_rate * 1.05:
            winner = "treatment"
        elif c.win_rate > t.win_rate * 1.05:
            winner = "control"
        else:
            winner = "tie"

    return {
        "test_id": test_id,
        "strategy_name": test.strategy_name,
        "description": test.description,
        "active": test.active,
        "winner": winner,
        "control": {
            "trades": c.trades,
            "win_rate": round(c.win_rate, 3),
            "avg_pnl": round(c.avg_pnl, 2),
            "total_pnl": round(c.total_pnl_pct, 2),
        },
        "treatment": {
            "trades": t.trades,
            "win_rate": round(t.win_rate, 3),
            "avg_pnl": round(t.avg_pnl, 2),
            "total_pnl": round(t.total_pnl_pct, 2),
        },
        "min_trades_required": test.min_trades,
        "can_determine_winner": can_determine,
    }


def get_all_ab_tests() -> list[dict]:
    """Return serializable results for all registered A/B tests."""
    return [get_ab_test_results(tid) for tid in _active_tests]
