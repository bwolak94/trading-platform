"""Kelly Criterion Position Sizer — optimal bet sizing from win rate and R-ratio.

Uses fractional Kelly (default 1/4 Kelly) for practical safety. Full Kelly is
mathematically optimal but creates unacceptably large drawdowns in practice.

Kelly formula: f* = W - (L / R)
  W = win rate
  L = loss rate (1 - W)
  R = win/loss ratio (avg_win_r / avg_loss_r)
"""

from __future__ import annotations

from collections import deque
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)


class KellyCriterion:
    """Computes Kelly-optimal position sizes and tracks rolling trade statistics."""

    def __init__(self, history_size: int = 100) -> None:
        """Initialize Kelly criterion tracker.

        Args:
            history_size: Number of recent trades to track for rolling stats
        """
        self._trades: deque[float] = deque(maxlen=history_size)  # R-multiples

    def compute_kelly_fraction(
        self,
        win_rate: float,
        avg_win_r: float,
        avg_loss_r: float,
    ) -> float:
        """Compute the full Kelly fraction.

        Args:
            win_rate: Historical win rate [0, 1]
            avg_win_r: Average win in R-multiples
            avg_loss_r: Average loss in R-multiples (positive value)

        Returns:
            Kelly fraction [0, 1] — clamped to avoid negative values
        """
        if avg_loss_r <= 0 or avg_win_r <= 0:
            return 0.0
        loss_rate = 1.0 - win_rate
        r_ratio = avg_win_r / avg_loss_r
        kelly = win_rate - (loss_rate / r_ratio)
        return max(0.0, round(kelly, 4))

    def compute_position_size(
        self,
        account_equity: float,
        win_rate: float,
        avg_win_r: float,
        avg_loss_r: float,
        kelly_fraction: float = 0.25,
        max_risk_pct: float = 2.0,
    ) -> dict[str, Any]:
        """Compute position size using fractional Kelly criterion.

        Args:
            account_equity: Total account value in USD
            win_rate: Estimated win rate [0, 1]
            avg_win_r: Average win in R-multiples
            avg_loss_r: Average loss in R-multiples
            kelly_fraction: Fraction of full Kelly to use (0.25 = quarter Kelly)
            max_risk_pct: Hard cap on risk percentage

        Returns:
            {kelly_full_pct, kelly_fractional_pct, position_size_usd, risk_amount_usd, r_ratio}
        """
        full_kelly = self.compute_kelly_fraction(win_rate, avg_win_r, avg_loss_r)
        fractional_kelly_pct = min(full_kelly * kelly_fraction * 100, max_risk_pct)
        risk_amount = account_equity * (fractional_kelly_pct / 100)

        r_ratio = avg_win_r / avg_loss_r if avg_loss_r > 0 else 1.0

        return {
            "kelly_full_pct": round(full_kelly * 100, 2),
            "kelly_fractional_pct": round(fractional_kelly_pct, 2),
            "kelly_fraction_used": kelly_fraction,
            "risk_amount_usd": round(risk_amount, 2),
            "position_size_usd": round(risk_amount * r_ratio, 2),
            "r_ratio": round(r_ratio, 3),
            "win_rate": win_rate,
            "avg_win_r": avg_win_r,
            "avg_loss_r": avg_loss_r,
            "max_risk_pct": max_risk_pct,
        }

    def update_stats(self, pnl_r: float) -> None:
        """Record a trade outcome in R-multiples.

        Args:
            pnl_r: Trade P&L as R-multiple (positive = win, negative = loss)
        """
        self._trades.append(pnl_r)

    def get_current_stats(self) -> dict[str, Any]:
        """Compute current rolling statistics.

        Returns:
            {win_rate, avg_win_r, avg_loss_r, trades_count, recommended_kelly_pct}
        """
        if not self._trades:
            return {
                "win_rate": 0.5,
                "avg_win_r": 2.0,
                "avg_loss_r": 1.0,
                "trades_count": 0,
                "recommended_kelly_pct": 12.5,
                "note": "Using default priors — no trade history yet",
            }

        trades = list(self._trades)
        wins = [t for t in trades if t > 0]
        losses = [abs(t) for t in trades if t < 0]

        win_rate = len(wins) / len(trades)
        avg_win_r = sum(wins) / len(wins) if wins else 2.0
        avg_loss_r = sum(losses) / len(losses) if losses else 1.0

        full_kelly = self.compute_kelly_fraction(win_rate, avg_win_r, avg_loss_r)
        recommended = round(full_kelly * 0.25 * 100, 2)  # quarter Kelly

        return {
            "win_rate": round(win_rate, 3),
            "avg_win_r": round(avg_win_r, 3),
            "avg_loss_r": round(avg_loss_r, 3),
            "trades_count": len(trades),
            "full_kelly_pct": round(full_kelly * 100, 2),
            "recommended_kelly_pct": recommended,
            "expectancy_r": round(win_rate * avg_win_r - (1 - win_rate) * avg_loss_r, 4),
        }


# Module-level singleton
_kelly: KellyCriterion | None = None


def get_kelly_criterion() -> KellyCriterion:
    """Return the global KellyCriterion singleton.

    Returns:
        Shared KellyCriterion instance
    """
    global _kelly
    if _kelly is None:
        _kelly = KellyCriterion()
    return _kelly
