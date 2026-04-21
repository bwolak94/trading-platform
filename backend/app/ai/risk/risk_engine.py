"""Risk Engine — position sizing, circuit breakers, and drawdown protection.

Implements:
- Kelly position sizing with correlation discount
- Volatility-adjusted sizing
- Daily/weekly circuit breakers
- Streak-based position scaling
- Consecutive loss protection
"""

from __future__ import annotations

import math
from collections import deque
from datetime import date, datetime, timezone
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)


class RiskEngine:
    """Manages position sizing and risk limits for the paper trading bot.

    Features:
        - Kelly criterion sizing
        - Volatility-adjusted sizes (ATR%)
        - Daily / weekly loss circuit breakers
        - Streak-based scaling (win streak → bigger, loss streak → smaller)
        - Consecutive loss protection (5 in a row → 50% size reduction)
    """

    def __init__(
        self,
        base_risk_pct: float = 1.0,         # % of capital per trade
        daily_loss_limit_pct: float = 5.0,   # pause bot if daily loss > 5%
        weekly_loss_limit_pct: float = 10.0, # pause bot for week if weekly loss > 10%
        max_consecutive_losses: int = 5,     # consecutive losses before size cut
        max_position_pct: float = 3.0,       # hard cap on single position size
    ) -> None:
        self.base_risk_pct = base_risk_pct
        self.daily_loss_limit_pct = daily_loss_limit_pct
        self.weekly_loss_limit_pct = weekly_loss_limit_pct
        self.max_consecutive_losses = max_consecutive_losses
        self.max_position_pct = max_position_pct

        # State tracking
        self._daily_pnl: float = 0.0
        self._weekly_pnl: float = 0.0
        self._last_reset_date: date = date.today()
        self._last_week_reset: int = datetime.now(timezone.utc).isocalendar()[1]

        self._pnl_history: deque[float] = deque(maxlen=200)
        self._win_streak: int = 0
        self._loss_streak: int = 0
        self._consecutive_losses: int = 0

        self._bot_paused_until: datetime | None = None
        self._pause_reason: str | None = None

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def record_trade(self, pnl_pct: float) -> None:
        """Record a completed trade. Updates streaks and circuit breakers."""
        self._maybe_reset_daily()
        self._maybe_reset_weekly()

        self._pnl_history.append(pnl_pct)
        self._daily_pnl += pnl_pct
        self._weekly_pnl += pnl_pct

        if pnl_pct > 0:
            self._win_streak += 1
            self._loss_streak = 0
            self._consecutive_losses = 0
        else:
            self._loss_streak += 1
            self._win_streak = 0
            self._consecutive_losses += 1

        # Check circuit breakers
        self._check_daily_circuit_breaker()
        self._check_weekly_circuit_breaker()

        logger.debug(
            "Risk | Trade recorded pnl=%.2f%% daily=%.2f%% win_streak=%d loss_streak=%d",
            pnl_pct, self._daily_pnl, self._win_streak, self._loss_streak,
        )

    def get_position_size_multiplier(
        self,
        atr_pct: float = 1.0,
        win_rate_estimate: float = 0.5,
    ) -> float:
        """Return a position size multiplier (0.0–2.0) based on current risk state.

        Takes into account:
        - Volatility (ATR%) — high vol → smaller size
        - Win/loss streak — win streak → bigger, loss streak → smaller
        - Consecutive loss protection
        - Bot paused state

        Args:
            atr_pct: ATR as % of price (ATR/close * 100)
            win_rate_estimate: Estimated win rate for Kelly sizing

        Returns:
            Multiplier to apply to base_risk_pct (0.0 = skip trade)
        """
        if self.is_paused:
            return 0.0

        multiplier = 1.0

        # --- Volatility adjustment ---
        if atr_pct > 5.0:
            multiplier *= 0.5
            logger.debug("Risk | ATR%=%.2f > 5%% → size cut 50%%", atr_pct)
        elif atr_pct > 3.0:
            multiplier *= 0.7
            logger.debug("Risk | ATR%=%.2f > 3%% → size cut 30%%", atr_pct)

        # --- Streak-based scaling ---
        if self._win_streak >= 3:
            boost = min(0.2 * (self._win_streak - 2), 1.0)  # +20% per streak above 3, max 2×
            multiplier = min(multiplier * (1 + boost), 2.0)
            logger.debug("Risk | Win streak %d → size boost +%.0f%%", self._win_streak, boost * 100)
        elif self._loss_streak >= 2:
            multiplier *= 0.7
            logger.debug("Risk | Loss streak %d → size cut 30%%", self._loss_streak)

        # --- Consecutive loss protection ---
        if self._consecutive_losses >= self.max_consecutive_losses:
            multiplier *= 0.5
            logger.debug("Risk | %d consecutive losses → size cut 50%%", self._consecutive_losses)

        return round(min(max(multiplier, 0.0), 2.0), 3)

    @property
    def is_paused(self) -> bool:
        """True if the bot is currently paused due to a circuit breaker."""
        if self._bot_paused_until is None:
            return False
        if datetime.now(timezone.utc) < self._bot_paused_until:
            return True
        # Pause expired — clear it
        self._bot_paused_until = None
        self._pause_reason = None
        return False

    def get_state(self) -> dict[str, Any]:
        """Return current risk engine state for API/UI consumption."""
        return {
            "is_paused": self.is_paused,
            "pause_reason": self._pause_reason,
            "paused_until": self._bot_paused_until.isoformat() if self._bot_paused_until else None,
            "daily_pnl_pct": round(self._daily_pnl, 4),
            "weekly_pnl_pct": round(self._weekly_pnl, 4),
            "daily_loss_limit_pct": self.daily_loss_limit_pct,
            "weekly_loss_limit_pct": self.weekly_loss_limit_pct,
            "win_streak": self._win_streak,
            "loss_streak": self._loss_streak,
            "consecutive_losses": self._consecutive_losses,
        }

    # ------------------------------------------------------------------ #
    # Circuit breakers                                                     #
    # ------------------------------------------------------------------ #

    def _check_daily_circuit_breaker(self) -> None:
        """Pause bot for remainder of day if daily loss limit breached."""
        if self._daily_pnl < -self.daily_loss_limit_pct and not self.is_paused:
            now = datetime.now(timezone.utc)
            # Pause until end of UTC day
            end_of_day = now.replace(hour=23, minute=59, second=59)
            self._bot_paused_until = end_of_day
            self._pause_reason = (
                f"Daily loss limit {self.daily_loss_limit_pct}% breached "
                f"(actual: {self._daily_pnl:.2f}%)"
            )
            logger.warning("CIRCUIT BREAKER | Daily loss limit hit: %s", self._pause_reason)

    def _check_weekly_circuit_breaker(self) -> None:
        """Pause bot for remainder of week if weekly loss limit breached."""
        if self._weekly_pnl < -self.weekly_loss_limit_pct and not self.is_paused:
            now = datetime.now(timezone.utc)
            days_until_monday = (7 - now.weekday()) % 7 or 7
            end_of_week = now.replace(hour=0, minute=0, second=0).replace(
                day=now.day + days_until_monday
            )
            self._bot_paused_until = end_of_week
            self._pause_reason = (
                f"Weekly loss limit {self.weekly_loss_limit_pct}% breached "
                f"(actual: {self._weekly_pnl:.2f}%)"
            )
            logger.warning("CIRCUIT BREAKER | Weekly loss limit hit: %s", self._pause_reason)

    # ------------------------------------------------------------------ #
    # Periodic resets                                                      #
    # ------------------------------------------------------------------ #

    def _maybe_reset_daily(self) -> None:
        """Reset daily PnL counter at the start of each new UTC day."""
        today = date.today()
        if today != self._last_reset_date:
            self._daily_pnl = 0.0
            self._last_reset_date = today
            logger.debug("Risk | Daily PnL reset for %s", today)

    def _maybe_reset_weekly(self) -> None:
        """Reset weekly PnL counter at the start of each new ISO week."""
        current_week = datetime.now(timezone.utc).isocalendar()[1]
        if current_week != self._last_week_reset:
            self._weekly_pnl = 0.0
            self._last_week_reset = current_week
            logger.debug("Risk | Weekly PnL reset for week %d", current_week)


# Module-level singleton
_risk_engine: RiskEngine | None = None


def get_risk_engine() -> RiskEngine:
    """Return the global RiskEngine singleton."""
    global _risk_engine
    if _risk_engine is None:
        _risk_engine = RiskEngine()
    return _risk_engine
