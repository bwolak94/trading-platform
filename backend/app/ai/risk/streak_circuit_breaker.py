"""Consecutive Loss Circuit Breaker — separate from the drawdown kill switch."""

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class CircuitBreakerState:
    """Snapshot of the circuit breaker's current state."""

    consecutive_losses: int
    consecutive_wins: int
    is_triggered: bool
    trigger_reason: str           # empty string when not triggered
    trigger_time: Optional[datetime]
    cool_off_until: Optional[datetime]  # when trading may resume
    position_scale: float         # 1.0 = normal, 0.5 = reduced, 0.0 = stopped
    min_confidence_required: float
    message: str


class StreakCircuitBreaker:
    """Triggers on consecutive losses (streak-based), NOT total drawdown.

    Complements the drawdown kill switch in ``app.ai.risk.engine``.

    Rules
    -----
    - 3 consecutive losses : reduce position size to 50 %, require 70 %+ confidence
    - 5 consecutive losses : PAUSE trading for 2 hours
    - 7 consecutive losses : PAUSE trading for 6 hours, require manual reset

    Recovery
    --------
    - 2 consecutive wins after a cool-off period restore normal operation.
    - Manual reset via ``manual_reset()`` is required after a Level 3 trigger.

    Rationale
    ---------
    Three or more losses in a row suggests a regime mismatch or data issue,
    not merely bad luck.  Forcing a pause allows the human trader to reassess.
    """

    LEVEL_1_LOSSES = 3    # reduce position size
    LEVEL_2_LOSSES = 5    # 2-hour auto-pause
    LEVEL_3_LOSSES = 7    # 6-hour pause + manual reset required

    WINS_TO_RECOVER = 2   # consecutive wins needed to restore full operation

    def __init__(self) -> None:
        self._losses: int = 0
        self._wins: int = 0
        self._trigger_time: Optional[datetime] = None
        self._cool_off_hours: float = 0.0
        self._manual_reset_required: bool = False
        self._last_result: Optional[str] = None  # "WIN" or "LOSS"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_state(self) -> CircuitBreakerState:
        """Return the current circuit breaker state (non-mutating).

        Automatically checks whether any cool-off period has expired so
        that the returned state is always up-to-date without requiring
        an explicit ``record_result`` call.
        """
        self._check_cooloff_expired()
        return self._build_state()

    def record_result(self, is_win: bool) -> CircuitBreakerState:
        """Record a trade outcome and update circuit-breaker state.

        Wins break a losing streak immediately (and vice versa).  Streaks
        are strictly sequential — a win resets the loss counter to zero.

        Args:
            is_win: ``True`` for a winning trade, ``False`` for a loss.

        Returns:
            Updated CircuitBreakerState.
        """
        # Check whether cool-off has expired before processing a new result
        self._check_cooloff_expired()

        if is_win:
            self._losses = 0
            self._wins += 1
            logger.info(
                "CircuitBreaker: WIN recorded — consecutive wins=%d losses=%d",
                self._wins,
                self._losses,
            )
            # Recovery: 2 consecutive wins restore normal state
            if self._wins >= self.WINS_TO_RECOVER and not self._manual_reset_required:
                if self._trigger_time is not None:
                    logger.info(
                        "CircuitBreaker: %d consecutive wins — restoring normal operation",
                        self._wins,
                    )
                    self._trigger_time = None
                    self._cool_off_hours = 0.0
        else:
            self._wins = 0
            self._losses += 1
            logger.warning(
                "CircuitBreaker: LOSS recorded — consecutive losses=%d",
                self._losses,
            )
            self._apply_rules()

        self._last_result = "WIN" if is_win else "LOSS"
        return self._build_state()

    def can_trade(self) -> tuple[bool, str]:
        """Check whether trading is currently permitted.

        Also auto-expires cool-off periods so callers always get a fresh answer.

        Returns:
            Tuple of (``can_trade``: bool, ``reason``: str).
        """
        self._check_cooloff_expired()

        if self._manual_reset_required:
            return (
                False,
                "Manual reset required after 7 consecutive losses. Call manual_reset().",
            )

        if self._trigger_time is not None:
            cool_off_until = self._trigger_time + timedelta(hours=self._cool_off_hours)
            now = datetime.now(timezone.utc)
            if now < cool_off_until:
                remaining = (cool_off_until - now).total_seconds() / 60
                return (
                    False,
                    f"Cool-off active — {remaining:.0f} minutes remaining.",
                )

        if self._losses >= self.LEVEL_1_LOSSES:
            return (
                True,
                f"Trading permitted at reduced size (50%) — {self._losses} consecutive losses.",
            )

        return (True, "Normal operation.")

    def manual_reset(self) -> bool:
        """Manually reset after a Level 3 (7-loss) trigger.

        Returns:
            ``True`` if the reset was accepted; ``False`` if Level 3 was not
            the active trigger (no manual reset was required).
        """
        if not self._manual_reset_required:
            logger.info("CircuitBreaker.manual_reset: no manual reset required — ignored")
            return False

        logger.warning(
            "CircuitBreaker: MANUAL RESET performed after %d consecutive losses",
            self._losses,
        )
        self._losses = 0
        self._wins = 0
        self._trigger_time = None
        self._cool_off_hours = 0.0
        self._manual_reset_required = False
        return True

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _apply_rules(self) -> None:
        """Apply the circuit-breaker rule that matches the current loss streak."""
        if self._losses >= self.LEVEL_3_LOSSES:
            if self._cool_off_hours < 6.0:  # only escalate, never de-escalate
                self._trigger_time = datetime.now(timezone.utc)
                self._cool_off_hours = 6.0
                self._manual_reset_required = True
                logger.critical(
                    "CircuitBreaker LEVEL 3: %d consecutive losses — 6-hour pause + manual reset required",
                    self._losses,
                )
        elif self._losses >= self.LEVEL_2_LOSSES:
            if self._cool_off_hours < 2.0:
                self._trigger_time = datetime.now(timezone.utc)
                self._cool_off_hours = 2.0
                logger.error(
                    "CircuitBreaker LEVEL 2: %d consecutive losses — 2-hour pause",
                    self._losses,
                )
        elif self._losses >= self.LEVEL_1_LOSSES:
            # Level 1 does not set a cool-off; it just reduces size
            if self._trigger_time is None:
                self._trigger_time = datetime.now(timezone.utc)
                self._cool_off_hours = 0.0
                logger.warning(
                    "CircuitBreaker LEVEL 1: %d consecutive losses — 50%% position size, 70%% min confidence",
                    self._losses,
                )

    def _check_cooloff_expired(self) -> bool:
        """Auto-expire the cool-off period if sufficient time has passed.

        Does NOT clear a manual-reset requirement — that always needs an
        explicit ``manual_reset()`` call.

        Returns:
            ``True`` if the cool-off was cleared in this call, otherwise ``False``.
        """
        if self._trigger_time is None or self._cool_off_hours <= 0:
            return False
        if self._manual_reset_required:
            return False  # manual reset required regardless

        cool_off_until = self._trigger_time + timedelta(hours=self._cool_off_hours)
        if datetime.now(timezone.utc) >= cool_off_until:
            logger.info(
                "CircuitBreaker: cool-off period expired — resuming with reduced position scale"
            )
            self._cool_off_hours = 0.0
            # Keep _trigger_time so we still enforce Level 1 size reduction
            # until WINS_TO_RECOVER wins accumulate.
            return True
        return False

    def _build_state(self) -> CircuitBreakerState:
        """Construct a CircuitBreakerState from current internal values."""
        is_triggered = self._trigger_time is not None
        cool_off_until: Optional[datetime] = None

        if is_triggered and self._cool_off_hours > 0:
            cool_off_until = self._trigger_time + timedelta(hours=self._cool_off_hours)  # type: ignore[operator]

        # Determine position_scale and min_confidence based on active level
        if self._manual_reset_required or (
            cool_off_until is not None and datetime.now(timezone.utc) < cool_off_until
        ):
            position_scale = 0.0
            min_confidence = 100.0  # effectively blocks all signals
            trigger_reason = (
                "LEVEL_3: 7 consecutive losses — manual reset required"
                if self._losses >= self.LEVEL_3_LOSSES
                else "LEVEL_2: 5 consecutive losses — 2-hour pause"
            )
        elif self._losses >= self.LEVEL_1_LOSSES:
            position_scale = 0.5
            min_confidence = 70.0
            trigger_reason = "LEVEL_1: 3+ consecutive losses — reduced size"
        else:
            position_scale = 1.0
            min_confidence = 50.0
            trigger_reason = ""

        # Build a human-readable message
        if not is_triggered:
            message = f"Normal operation. Losses={self._losses} Wins={self._wins}."
        elif position_scale == 0.0:
            remaining = ""
            if cool_off_until is not None:
                secs = (cool_off_until - datetime.now(timezone.utc)).total_seconds()
                if secs > 0:
                    remaining = f" ({secs / 60:.0f} min remaining)"
            message = f"Trading PAUSED{remaining}. {trigger_reason}"
        else:
            message = (
                f"Trading at 50% size. Require >=70% confidence. {trigger_reason}"
            )

        return CircuitBreakerState(
            consecutive_losses=self._losses,
            consecutive_wins=self._wins,
            is_triggered=is_triggered,
            trigger_reason=trigger_reason,
            trigger_time=self._trigger_time,
            cool_off_until=cool_off_until,
            position_scale=position_scale,
            min_confidence_required=min_confidence,
            message=message,
        )
