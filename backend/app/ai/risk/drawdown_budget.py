"""Drawdown budget management system.

Tracks a monthly drawdown budget and adjusts position sizing as budget is consumed.
Budget: configurable max drawdown % per month (default 5%).

As budget is consumed the position size multiplier decreases:
- 100% remaining → 1.0x
- 75%  remaining → 0.8x
- 50%  remaining → 0.5x
- 25%  remaining → 0.2x
-  0%  remaining → 0.0x  (no new positions)
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter

# Breakpoints mapping (budget_remaining_fraction → multiplier)
# Applied as piecewise-linear interpolation between anchor points.
_MULTIPLIER_TABLE: list[tuple[float, float]] = [
    (1.00, 1.0),
    (0.75, 0.8),
    (0.50, 0.5),
    (0.25, 0.2),
    (0.00, 0.0),
]


def _interpolate_multiplier(remaining_fraction: float) -> float:
    """Piecewise-linear interpolation of position size multiplier.

    Args:
        remaining_fraction: Budget remaining as a fraction (0 = exhausted, 1 = full).

    Returns:
        Position size multiplier in [0, 1].
    """
    remaining_fraction = max(0.0, min(1.0, remaining_fraction))
    for i in range(len(_MULTIPLIER_TABLE) - 1):
        x1, y1 = _MULTIPLIER_TABLE[i]
        x2, y2 = _MULTIPLIER_TABLE[i + 1]
        if x2 <= remaining_fraction <= x1:
            if x1 == x2:
                return y1
            t = (remaining_fraction - x2) / (x1 - x2)
            return round(y2 + t * (y1 - y2), 4)
    return 0.0


@dataclass
class DrawdownBudget:
    """Monthly drawdown budget tracker with position-size scaling."""

    monthly_budget_pct: float = 5.0
    """Maximum allowed drawdown per calendar month, in percent."""

    consumed_pct: float = 0.0
    """Drawdown consumed so far this month, in percent."""

    month_start: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
    )
    """Start of the current monthly budget window."""

    def _ensure_monthly_reset(self) -> None:
        """Reset budget if a new calendar month has started."""
        now = datetime.now(timezone.utc)
        current_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if current_month_start > self.month_start:
            self.month_start = current_month_start
            self.consumed_pct = 0.0

    @property
    def remaining_pct(self) -> float:
        """Remaining budget in percent."""
        self._ensure_monthly_reset()
        return max(0.0, self.monthly_budget_pct - self.consumed_pct)

    @property
    def remaining_fraction(self) -> float:
        """Remaining budget as a fraction of the monthly budget (0–1)."""
        if self.monthly_budget_pct <= 0:
            return 0.0
        return max(0.0, min(1.0, self.remaining_pct / self.monthly_budget_pct))

    def get_position_size_multiplier(self) -> float:
        """Return position sizing multiplier based on remaining budget.

        Uses piecewise-linear interpolation:
        - 100% budget remaining → 1.0x (full sizing)
        - 75%  remaining → 0.8x
        - 50%  remaining → 0.5x
        - 25%  remaining → 0.2x
        -  0%  remaining → 0.0x (no new positions)
        """
        self._ensure_monthly_reset()
        return _interpolate_multiplier(self.remaining_fraction)

    def record_drawdown(self, drawdown_pct: float) -> None:
        """Record a drawdown event and update consumed budget.

        Negative values are ignored (only drawdowns reduce budget).
        Resets monthly budget if we have crossed into a new calendar month.

        Args:
            drawdown_pct: The drawdown in percent (positive = loss, negative = ignored).
        """
        self._ensure_monthly_reset()
        if drawdown_pct > 0:
            self.consumed_pct = min(
                self.monthly_budget_pct,
                self.consumed_pct + drawdown_pct,
            )

    def get_status(self) -> dict[str, Any]:
        """Return current budget status as a serialisable dict."""
        self._ensure_monthly_reset()
        multiplier = self.get_position_size_multiplier()
        remaining = self.remaining_pct
        fraction = self.remaining_fraction

        if fraction >= 0.75:
            status_label = "HEALTHY"
        elif fraction >= 0.50:
            status_label = "CAUTION"
        elif fraction >= 0.25:
            status_label = "WARNING"
        elif fraction > 0.0:
            status_label = "CRITICAL"
        else:
            status_label = "EXHAUSTED"

        return {
            "monthly_budget_pct": self.monthly_budget_pct,
            "consumed_pct": round(self.consumed_pct, 4),
            "remaining_pct": round(remaining, 4),
            "remaining_fraction": round(fraction, 4),
            "position_size_multiplier": multiplier,
            "status": status_label,
            "month_start": self.month_start.isoformat(),
            "no_new_positions": multiplier == 0.0,
        }


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_budget = DrawdownBudget()


def get_drawdown_budget() -> DrawdownBudget:
    """Return the module-level DrawdownBudget singleton."""
    return _budget


# ---------------------------------------------------------------------------
# FastAPI router
# ---------------------------------------------------------------------------

router = APIRouter(tags=["risk"])


@router.get("/risk/drawdown-budget")
async def get_drawdown_budget_status() -> dict[str, Any]:
    """Get current drawdown budget status and position sizing multiplier.

    Returns the current monthly budget consumption, remaining budget,
    and the resulting position size multiplier.
    """
    budget = get_drawdown_budget()
    return budget.get_status()


@router.post("/risk/drawdown-budget/record")
async def record_drawdown_event(drawdown_pct: float) -> dict[str, Any]:
    """Record a drawdown event to update monthly budget consumption.

    Args:
        drawdown_pct: The drawdown in percent (positive values only; negative ignored).

    Returns:
        Updated budget status.
    """
    budget = get_drawdown_budget()
    before = budget.consumed_pct
    budget.record_drawdown(drawdown_pct)
    after = budget.consumed_pct
    status = budget.get_status()
    status["recorded_drawdown_pct"] = round(drawdown_pct, 4)
    status["consumed_before"] = round(before, 4)
    status["consumed_after"] = round(after, 4)
    return status
