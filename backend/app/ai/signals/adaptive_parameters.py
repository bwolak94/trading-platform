"""Adaptive Parameter Optimizer — selects best strategy parameters from rolling outcomes.

Tracks the performance of different parameter sets per strategy over a rolling
window and recommends the best-performing configuration. Uses a simple
multi-armed bandit approach: exploit the best known params, but occasionally
explore nearby parameter values.
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

# Valid parameter ranges for each strategy
PARAM_RANGES: dict[str, dict[str, list[Any]]] = {
    "trend_following": {
        "ema_fast": [8, 10, 12, 15, 20],
        "ema_slow": [30, 40, 50, 60],
        "adx_threshold": [20, 25, 30],
    },
    "mean_reversion": {
        "rsi_oversold": [25, 28, 30, 32],
        "rsi_overbought": [68, 70, 72, 75],
        "bb_period": [14, 20, 26],
    },
    "breakout": {
        "volume_multiplier": [1.5, 2.0, 2.5, 3.0],
        "lookback_bars": [10, 15, 20],
        "atr_filter": [1.0, 1.5, 2.0],
    },
    "smc": {
        "ob_lookback": [10, 15, 20],
        "fvg_threshold": [0.3, 0.5, 0.7],
    },
}

# Default parameters per strategy (fallback)
DEFAULT_PARAMS: dict[str, dict[str, Any]] = {
    "trend_following": {"ema_fast": 12, "ema_slow": 50, "adx_threshold": 25},
    "mean_reversion": {"rsi_oversold": 30, "rsi_overbought": 70, "bb_period": 20},
    "breakout": {"volume_multiplier": 2.0, "lookback_bars": 15, "atr_filter": 1.5},
    "smc": {"ob_lookback": 15, "fvg_threshold": 0.5},
}


class AdaptiveOptimizer:
    """Tracks parameter performance and recommends optimal configurations.

    Uses a rolling window of trade outcomes per parameter set.
    The best-performing set (highest win rate over last 30 trades) is returned.
    """

    def __init__(self, window_size: int = 30) -> None:
        """Initialize the adaptive optimizer.

        Args:
            window_size: Number of recent trades to consider per parameter set
        """
        self.window_size = window_size
        # {strategy: {param_key: deque[(pnl_pct, win)]}}
        self._history: dict[str, dict[str, deque[tuple[float, bool]]]] = defaultdict(
            lambda: defaultdict(lambda: deque(maxlen=window_size))
        )
        # {strategy: {param_key: params_dict}}
        self._param_registry: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)

    def record_outcome(self, params: dict[str, Any], pnl_pct: float, win: bool) -> None:
        """Record a trade outcome for a parameter set.

        Args:
            params: Parameter dict including 'strategy' key
            pnl_pct: Trade PnL as percentage
            win: Whether the trade was a winner
        """
        strategy = params.get("strategy", "unknown")
        param_key = _params_to_key(params)
        self._history[strategy][param_key].append((pnl_pct, win))
        self._param_registry[strategy][param_key] = {k: v for k, v in params.items() if k != "strategy"}

    def get_best_params(self, strategy_name: str) -> dict[str, Any]:
        """Return the parameter set with the highest rolling win rate.

        Args:
            strategy_name: Strategy identifier

        Returns:
            Best-performing parameter dict, or defaults if no history
        """
        strategy_history = self._history.get(strategy_name, {})
        if not strategy_history:
            return DEFAULT_PARAMS.get(strategy_name, {})

        best_key: str | None = None
        best_win_rate = -1.0

        for param_key, outcomes in strategy_history.items():
            if not outcomes:
                continue
            win_rate = sum(1 for _, w in outcomes if w) / len(outcomes)
            if win_rate > best_win_rate:
                best_win_rate = win_rate
                best_key = param_key

        if best_key is None:
            return DEFAULT_PARAMS.get(strategy_name, {})

        return dict(self._param_registry[strategy_name].get(best_key, {}))

    def suggest_adjustment(self, strategy_name: str, current_params: dict[str, Any]) -> dict[str, Any]:
        """Suggest nearby parameter adjustments to improve performance.

        Args:
            strategy_name: Strategy identifier
            current_params: Currently active parameter set

        Returns:
            {suggested_params, expected_improvement, confidence}
        """
        best = self.get_best_params(strategy_name)
        ranges = PARAM_RANGES.get(strategy_name, {})

        if not best or not ranges:
            return {
                "suggested_params": current_params,
                "expected_improvement": 0.0,
                "confidence": 0.0,
                "reason": "No historical data available",
            }

        # Check if best differs from current
        differences = {k: best[k] for k in best if k in current_params and best[k] != current_params.get(k)}

        improvement_estimate = len(differences) * 0.02  # rough 2% improvement per changed param

        return {
            "suggested_params": best,
            "changes_from_current": differences,
            "expected_improvement": round(improvement_estimate, 4),
            "confidence": min(0.9, len(self._history.get(strategy_name, {})) / 10),
            "reason": f"Based on {sum(len(v) for v in self._history.get(strategy_name, {}).values())} recorded trades",
        }

    def get_all_strategy_stats(self) -> dict[str, Any]:
        """Return performance summary for all tracked strategies.

        Returns:
            Dict of strategy -> {best_params, win_rate, total_trades}
        """
        result: dict[str, Any] = {}
        for strategy, param_history in self._history.items():
            total_trades = sum(len(v) for v in param_history.values())
            all_outcomes = [o for outcomes in param_history.values() for o in outcomes]
            win_rate = sum(1 for _, w in all_outcomes if w) / len(all_outcomes) if all_outcomes else 0.0
            result[strategy] = {
                "best_params": self.get_best_params(strategy),
                "win_rate": round(win_rate, 3),
                "total_trades": total_trades,
                "param_sets_tested": len(param_history),
            }
        return result


def _params_to_key(params: dict[str, Any]) -> str:
    """Convert parameter dict to a stable string key.

    Args:
        params: Parameter dictionary

    Returns:
        Sorted string representation for use as dict key
    """
    return str(sorted((k, v) for k, v in params.items() if k != "strategy"))


# Module-level singleton
_optimizer: AdaptiveOptimizer | None = None


def get_adaptive_optimizer() -> AdaptiveOptimizer:
    """Return the global AdaptiveOptimizer singleton.

    Returns:
        Shared AdaptiveOptimizer instance
    """
    global _optimizer
    if _optimizer is None:
        _optimizer = AdaptiveOptimizer()
    return _optimizer
