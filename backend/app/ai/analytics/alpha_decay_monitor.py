"""Alpha Decay Monitor — detects when a strategy's edge is deteriorating.

Computes rolling Sharpe ratio and compares recent vs historical performance.
A significant Sharpe ratio decline indicates the strategy's alpha is decaying,
likely due to market regime change or increased competition.

Recommendation tiers:
- HEALTHY: Recent Sharpe >= Historical Sharpe × 0.8
- MONITOR: Recent Sharpe in [0.3, 0.8] × Historical
- REDUCE_SIZE: Recent Sharpe in [0, 0.3] × Historical
- DISABLE: Recent Sharpe < 0
"""

from __future__ import annotations

import math
from collections import deque
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)


class AlphaDecayMonitor:
    """Monitors rolling Sharpe ratio per strategy to detect edge deterioration."""

    def __init__(self, window_size: int = 50, decay_threshold: float = 0.3) -> None:
        """Initialize the alpha decay monitor.

        Args:
            window_size: Total rolling window size for Sharpe computation
            decay_threshold: Sharpe drop fraction triggering decay alert
        """
        self._strategy_returns: dict[str, deque[float]] = {}
        self.window_size = window_size
        self.decay_threshold = decay_threshold

    def record_trade(self, strategy_name: str, pnl_pct: float) -> None:
        """Record a trade outcome for a strategy.

        Args:
            strategy_name: Strategy identifier
            pnl_pct: Trade PnL as percentage of equity
        """
        if strategy_name not in self._strategy_returns:
            self._strategy_returns[strategy_name] = deque(maxlen=self.window_size)
        self._strategy_returns[strategy_name].append(pnl_pct)

    def compute_rolling_sharpe(self, strategy_name: str, window: int | None = None) -> float:
        """Compute annualized Sharpe ratio from rolling returns.

        Args:
            strategy_name: Strategy identifier
            window: Number of recent trades to use (None = full window)

        Returns:
            Annualized Sharpe ratio (0.0 if insufficient data)
        """
        returns = list(self._strategy_returns.get(strategy_name, []))
        if not returns:
            return 0.0

        if window and len(returns) > window:
            returns = returns[-window:]

        if len(returns) < 3:
            return 0.0

        mean = sum(returns) / len(returns)
        variance = sum((r - mean) ** 2 for r in returns) / max(1, len(returns) - 1)
        std = math.sqrt(variance)

        if std == 0:
            return float("inf") if mean > 0 else 0.0

        # Annualized assuming ~252 trading days, each trade = 1 day avg hold
        sharpe = (mean / std) * math.sqrt(252)
        return round(sharpe, 3)

    def detect_decay(self, strategy_name: str) -> dict[str, Any]:
        """Detect alpha decay by comparing recent vs historical Sharpe.

        Args:
            strategy_name: Strategy to analyze

        Returns:
            {strategy, recent_sharpe, historical_sharpe, decay_detected,
             decay_severity, recommendation, trades_analyzed}
        """
        returns = list(self._strategy_returns.get(strategy_name, []))
        n = len(returns)

        if n < 20:
            return {
                "strategy": strategy_name,
                "recent_sharpe": 0.0,
                "historical_sharpe": 0.0,
                "decay_detected": False,
                "decay_severity": 0.0,
                "recommendation": "INSUFFICIENT_DATA",
                "trades_analyzed": n,
            }

        # Split into recent (last 20) and historical (20-50 ago)
        recent_window = 20
        historical_window = min(n - recent_window, 30)

        recent_sharpe = self.compute_rolling_sharpe(strategy_name, recent_window)
        historical_returns = returns[-(recent_window + historical_window):-recent_window]

        if not historical_returns:
            historical_sharpe = recent_sharpe
        else:
            # Compute Sharpe on historical slice
            h_mean = sum(historical_returns) / len(historical_returns)
            h_var = sum((r - h_mean) ** 2 for r in historical_returns) / max(1, len(historical_returns) - 1)
            h_std = math.sqrt(h_var) if h_var > 0 else 1e-9
            historical_sharpe = round((h_mean / h_std) * math.sqrt(252), 3)

        # Decay detection
        if historical_sharpe > 0:
            decay_severity = max(0.0, 1.0 - (recent_sharpe / historical_sharpe))
        elif historical_sharpe <= 0 and recent_sharpe > 0:
            decay_severity = 0.0  # improvement
        else:
            decay_severity = 1.0

        decay_detected = decay_severity > self.decay_threshold

        if recent_sharpe < 0:
            recommendation = "DISABLE"
        elif decay_severity > 0.7:
            recommendation = "REDUCE_SIZE"
        elif decay_severity > self.decay_threshold:
            recommendation = "MONITOR"
        else:
            recommendation = "HEALTHY"

        return {
            "strategy": strategy_name,
            "recent_sharpe": recent_sharpe,
            "historical_sharpe": historical_sharpe,
            "decay_detected": decay_detected,
            "decay_severity": round(decay_severity, 3),
            "recommendation": recommendation,
            "trades_analyzed": n,
        }

    def get_all_strategy_health(self) -> list[dict[str, Any]]:
        """Return health report for all tracked strategies.

        Returns:
            List of decay detection dicts sorted by decay severity
        """
        reports = [self.detect_decay(strategy) for strategy in self._strategy_returns]
        reports.sort(key=lambda x: x["decay_severity"], reverse=True)
        return reports


# Module-level singleton
_monitor: AlphaDecayMonitor | None = None


def get_alpha_decay_monitor() -> AlphaDecayMonitor:
    """Return the global AlphaDecayMonitor singleton.

    Returns:
        Shared AlphaDecayMonitor instance
    """
    global _monitor
    if _monitor is None:
        _monitor = AlphaDecayMonitor()
    return _monitor
