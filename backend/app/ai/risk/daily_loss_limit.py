"""C5: Max daily loss circuit breaker.

Tracks intraday realised P&L.  When the daily loss exceeds a configurable
threshold (default 3 % of capital) a ``DAILY_LIMIT_HIT`` event is emitted
and new signals are suppressed.

This module is complementary to the existing ``check_daily_loss_limit`` helper
in ``app/tasks.py``, providing a dedicated class with richer state and event
emission for use in FastAPI request handlers and the WebSocket broadcaster.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Callable, Coroutine, Any

from app.core.logging import get_logger

logger = get_logger(__name__)

# Default daily loss threshold as a fraction of capital (3 %)
DEFAULT_DAILY_LOSS_THRESHOLD_PCT = 3.0


@dataclass
class DailyLossState:
    """Mutable state tracked by :class:`DailyLossCircuitBreaker`."""

    date: date = field(default_factory=lambda: datetime.now(timezone.utc).date())
    realised_loss_pct: float = 0.0
    limit_hit: bool = False
    limit_hit_at: datetime | None = None


EventCallback = Callable[[DailyLossState], Coroutine[Any, Any, None]]


class DailyLossCircuitBreaker:
    """Circuit breaker that suppresses signals after the daily loss limit is hit.

    Usage::

        breaker = DailyLossCircuitBreaker(capital=10_000, threshold_pct=3.0)

        # Call on each realised trade:
        await breaker.record_loss(trade_pnl_pct=1.2)

        # Check before emitting a signal:
        if breaker.is_open:
            return  # signals suppressed

    Attributes:
        capital:        Reference capital in USD (used for informational purposes).
        threshold_pct:  Daily loss limit as a percentage of capital.
    """

    def __init__(
        self,
        capital: float = 0.0,
        threshold_pct: float = DEFAULT_DAILY_LOSS_THRESHOLD_PCT,
        on_limit_hit: EventCallback | None = None,
    ) -> None:
        self.capital = capital
        self.threshold_pct = threshold_pct
        self._on_limit_hit = on_limit_hit
        self._state = DailyLossState()

    @property
    def is_open(self) -> bool:
        """True when the daily limit is hit and new signals are suppressed."""
        self._maybe_reset()
        return self._state.limit_hit

    @property
    def realised_loss_pct(self) -> float:
        """Cumulative realised loss percentage for today."""
        self._maybe_reset()
        return self._state.realised_loss_pct

    def _maybe_reset(self) -> None:
        """Reset state at the start of a new UTC day."""
        today = datetime.now(timezone.utc).date()
        if self._state.date != today:
            logger.info("DailyLossCircuitBreaker: new day — resetting state")
            self._state = DailyLossState(date=today)

    async def record_loss(self, trade_pnl_pct: float) -> None:
        """Record a trade result and trip the breaker if the limit is reached.

        Args:
            trade_pnl_pct: Trade P&L as a percentage of position size.
                           Positive = profit, negative = loss.
        """
        self._maybe_reset()
        if self._state.limit_hit:
            return

        if trade_pnl_pct < 0:
            self._state.realised_loss_pct += abs(trade_pnl_pct)

        if self._state.realised_loss_pct >= self.threshold_pct:
            self._state.limit_hit = True
            self._state.limit_hit_at = datetime.now(timezone.utc)
            logger.warning(
                "DAILY_LIMIT_HIT: cumulative loss %.2f%% >= threshold %.2f%%",
                self._state.realised_loss_pct,
                self.threshold_pct,
            )
            if self._on_limit_hit is not None:
                try:
                    await self._on_limit_hit(self._state)
                except Exception as exc:
                    logger.error("DailyLossCircuitBreaker callback error: %s", exc)

    def status(self) -> dict:
        """Return a JSON-serialisable status dict for monitoring endpoints."""
        self._maybe_reset()
        return {
            "date": self._state.date.isoformat(),
            "realised_loss_pct": round(self._state.realised_loss_pct, 4),
            "threshold_pct": self.threshold_pct,
            "limit_hit": self._state.limit_hit,
            "limit_hit_at": (
                self._state.limit_hit_at.isoformat() if self._state.limit_hit_at else None
            ),
            "signals_suppressed": self._state.limit_hit,
        }


# Module-level singleton for use across the application
_breaker: DailyLossCircuitBreaker | None = None


def get_daily_loss_breaker(
    capital: float = 0.0,
    threshold_pct: float = DEFAULT_DAILY_LOSS_THRESHOLD_PCT,
) -> DailyLossCircuitBreaker:
    """Return the module-level :class:`DailyLossCircuitBreaker` singleton."""
    global _breaker
    if _breaker is None:
        _breaker = DailyLossCircuitBreaker(capital=capital, threshold_pct=threshold_pct)
    return _breaker
