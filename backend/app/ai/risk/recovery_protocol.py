"""Drawdown Recovery Protocol — systematic staged approach to recovering from drawdowns.

Rather than binary "trade / don't trade", this module implements five graduated
stages that progressively restrict position size, minimum confidence, allowed
strategies, and daily trade count as drawdown deepens.

The protocol also includes a limited recovery path: after accumulating
CONSECUTIVE_WINS_TO_UPGRADE consecutive wins in a stage, the system may
*suggest* moving to a less restrictive stage — but the final decision always
belongs to the human operator.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Stage definitions
# ---------------------------------------------------------------------------

@dataclass
class RecoveryStage:
    """Rules for a specific drawdown severity stage."""

    stage_name: str
    dd_min_pct: float         # drawdown % threshold to enter this stage (inclusive)
    dd_max_pct: float         # drawdown % threshold to exit this stage (exclusive)
    position_scale: float     # multiply base position size by this
    min_confidence: float     # minimum signal confidence required to trade
    allowed_strategies: list[str]  # empty list means all strategies are allowed
    max_trades_per_day: int   # 0 = no limit
    description: str


# Ordered from least to most severe — evaluated from bottom up when classifying
RECOVERY_STAGES: list[RecoveryStage] = [
    RecoveryStage(
        stage_name="NORMAL",
        dd_min_pct=0.0, dd_max_pct=5.0,
        position_scale=1.0,
        min_confidence=50.0,
        allowed_strategies=[],
        max_trades_per_day=0,
        description="Normal trading — full size, all strategies",
    ),
    RecoveryStage(
        stage_name="CAUTION",
        dd_min_pct=5.0, dd_max_pct=10.0,
        position_scale=0.75,
        min_confidence=60.0,
        allowed_strategies=[],
        max_trades_per_day=5,
        description="5–10% drawdown — reduce to 75%, require 60%+ confidence",
    ),
    RecoveryStage(
        stage_name="DEFENSIVE",
        dd_min_pct=10.0, dd_max_pct=15.0,
        position_scale=0.50,
        min_confidence=70.0,
        allowed_strategies=["trend_following", "trend_trader", "smc"],
        max_trades_per_day=3,
        description="10–15% drawdown — half size, only top strategies",
    ),
    RecoveryStage(
        stage_name="EMERGENCY",
        dd_min_pct=15.0, dd_max_pct=20.0,
        position_scale=0.25,
        min_confidence=80.0,
        allowed_strategies=["trend_following"],
        max_trades_per_day=1,
        description="15–20% drawdown — 25% size, only best strategy, 1 trade/day",
    ),
    RecoveryStage(
        stage_name="KILL_SWITCH",
        dd_min_pct=20.0, dd_max_pct=100.0,
        position_scale=0.0,
        min_confidence=100.0,
        allowed_strategies=[],
        max_trades_per_day=0,
        description="20%+ drawdown — STOP TRADING, manual review required",
    ),
]

# Lookup by name for convenience
_STAGE_BY_NAME: dict[str, RecoveryStage] = {s.stage_name: s for s in RECOVERY_STAGES}


# ---------------------------------------------------------------------------
# Decision dataclass
# ---------------------------------------------------------------------------

@dataclass
class RecoveryDecision:
    """Full protocol evaluation for a candidate signal."""

    current_drawdown_pct: float
    stage: RecoveryStage
    position_scale: float
    min_confidence: float
    is_strategy_allowed: bool     # True if strategy is permitted in this stage
    can_trade_today: bool         # True if daily trade limit has not been reached
    trades_today: int
    action: str                   # "TRADE", "SKIP_CONFIDENCE", "SKIP_STRATEGY", "DAILY_LIMIT", "KILL_SWITCH"
    message: str


# ---------------------------------------------------------------------------
# Protocol implementation
# ---------------------------------------------------------------------------

class RecoveryProtocol:
    """Implements systematic drawdown recovery stages.

    State that is tracked per instance:
    - ``_consecutive_wins``: wins accumulated since last loss in current stage
    - ``_last_drawdown_pct``: drawdown at last evaluation (for stage-change logic)

    Stage upgrade rule:
        After CONSECUTIVE_WINS_TO_UPGRADE wins without a loss, ``can_upgrade_stage``
        returns True. The upgrade itself is NOT automatic — it is advisory.
    """

    CONSECUTIVE_WINS_TO_UPGRADE: int = 2

    def __init__(self) -> None:
        """Initialise the recovery protocol with zero state."""
        self._consecutive_wins: int = 0
        self._last_drawdown_pct: float = 0.0

    # ----------------------------------------------------------------------- public

    def get_current_stage(self, drawdown_pct: float) -> RecoveryStage:
        """Determine the current stage based on drawdown percentage.

        Args:
            drawdown_pct: Current drawdown as a percentage (positive = loss from peak).

        Returns:
            The matching :class:`RecoveryStage`.
        """
        for stage in reversed(RECOVERY_STAGES):
            if drawdown_pct >= stage.dd_min_pct:
                return stage

        # Should never reach here; default to NORMAL
        return RECOVERY_STAGES[0]

    def evaluate(
        self,
        drawdown_pct: float,
        strategy_name: str,
        signal_confidence: float,
        trades_today: int = 0,
    ) -> RecoveryDecision:
        """Full protocol evaluation — should this signal be taken?

        Args:
            drawdown_pct: Current peak-to-trough drawdown in percent.
            strategy_name: Identifier of the strategy generating the signal.
            signal_confidence: Signal confidence score (e.g. 0–100).
            trades_today: Number of trades already taken today.

        Returns:
            :class:`RecoveryDecision` with ``action`` and detailed ``message``.
        """
        self._last_drawdown_pct = drawdown_pct
        stage = self.get_current_stage(drawdown_pct)

        # --- Kill switch ---
        if stage.stage_name == "KILL_SWITCH":
            logger.warning(
                "RecoveryProtocol: KILL_SWITCH active at %.2f%% drawdown",
                drawdown_pct,
            )
            return RecoveryDecision(
                current_drawdown_pct=drawdown_pct,
                stage=stage,
                position_scale=0.0,
                min_confidence=100.0,
                is_strategy_allowed=False,
                can_trade_today=False,
                trades_today=trades_today,
                action="KILL_SWITCH",
                message=(
                    f"KILL SWITCH: drawdown {drawdown_pct:.1f}% exceeds 20% "
                    f"threshold. All trading suspended. "
                    f"Manual review required before resuming."
                ),
            )

        # --- Strategy allowlist ---
        is_strategy_allowed = (
            not stage.allowed_strategies
            or strategy_name.lower() in [s.lower() for s in stage.allowed_strategies]
        )

        # --- Daily trade limit ---
        can_trade_today = (
            stage.max_trades_per_day == 0
            or trades_today < stage.max_trades_per_day
        )

        # --- Confidence gate ---
        confidence_ok = signal_confidence >= stage.min_confidence

        # --- Determine action ---
        if stage.stage_name == "KILL_SWITCH":
            action = "KILL_SWITCH"
        elif not is_strategy_allowed:
            action = "SKIP_STRATEGY"
        elif not can_trade_today:
            action = "DAILY_LIMIT"
        elif not confidence_ok:
            action = "SKIP_CONFIDENCE"
        else:
            action = "TRADE"

        # --- Build message ---
        message = self._build_message(
            stage=stage,
            drawdown_pct=drawdown_pct,
            action=action,
            strategy_name=strategy_name,
            signal_confidence=signal_confidence,
            trades_today=trades_today,
        )

        logger.info(
            "RecoveryProtocol: stage=%s action=%s dd=%.2f%% "
            "strategy=%s confidence=%.1f trades_today=%d",
            stage.stage_name,
            action,
            drawdown_pct,
            strategy_name,
            signal_confidence,
            trades_today,
        )

        return RecoveryDecision(
            current_drawdown_pct=drawdown_pct,
            stage=stage,
            position_scale=stage.position_scale,
            min_confidence=stage.min_confidence,
            is_strategy_allowed=is_strategy_allowed,
            can_trade_today=can_trade_today,
            trades_today=trades_today,
            action=action,
            message=message,
        )

    def record_trade_result(self, is_win: bool) -> None:
        """Update the consecutive win counter for stage upgrade logic.

        Args:
            is_win: True if the most recent trade closed as a winner.
        """
        if is_win:
            self._consecutive_wins += 1
            logger.debug(
                "RecoveryProtocol: consecutive wins now %d/%d",
                self._consecutive_wins,
                self.CONSECUTIVE_WINS_TO_UPGRADE,
            )
        else:
            self._consecutive_wins = 0
            logger.debug("RecoveryProtocol: loss recorded — consecutive wins reset")

    def can_upgrade_stage(self, drawdown_pct: float) -> bool:
        """Check whether conditions allow upgrading to a less restrictive stage.

        Upgrade is advisory only; the caller decides whether to honour it.

        Args:
            drawdown_pct: Current drawdown percentage.

        Returns:
            True if the consecutive win streak meets the threshold and the
            system is not in the NORMAL stage already.
        """
        current_stage = self.get_current_stage(drawdown_pct)

        if current_stage.stage_name == "NORMAL":
            return False  # already at best stage

        return self._consecutive_wins >= self.CONSECUTIVE_WINS_TO_UPGRADE

    def format_status(self, drawdown_pct: float) -> str:
        """Human-readable summary of the current protocol status.

        Args:
            drawdown_pct: Current drawdown percentage.

        Returns:
            Multi-line status string.
        """
        stage = self.get_current_stage(drawdown_pct)
        can_upgrade = self.can_upgrade_stage(drawdown_pct)

        lines = [
            f"Recovery Protocol Status",
            f"========================",
            f"Current Drawdown : {drawdown_pct:.2f}%",
            f"Stage            : {stage.stage_name}",
            f"Position Scale   : {stage.position_scale:.0%}",
            f"Min Confidence   : {stage.min_confidence:.0f}%",
            f"Max Trades/Day   : {'unlimited' if stage.max_trades_per_day == 0 else stage.max_trades_per_day}",
            f"Description      : {stage.description}",
        ]

        if stage.allowed_strategies:
            lines.append(
                f"Allowed Strategies: {', '.join(stage.allowed_strategies)}"
            )

        lines.append(
            f"Consecutive Wins : {self._consecutive_wins} "
            f"(need {self.CONSECUTIVE_WINS_TO_UPGRADE} to upgrade)"
        )

        if can_upgrade:
            lines.append(">> Stage upgrade available — manual confirmation required")

        return "\n".join(lines)

    # ----------------------------------------------------------------------- private

    def _build_message(
        self,
        stage: RecoveryStage,
        drawdown_pct: float,
        action: str,
        strategy_name: str,
        signal_confidence: float,
        trades_today: int,
    ) -> str:
        """Build a descriptive message for a :class:`RecoveryDecision`.

        Args:
            stage: Active recovery stage.
            drawdown_pct: Current drawdown percentage.
            action: Resolved action string.
            strategy_name: Strategy name for context.
            signal_confidence: Signal confidence for context.
            trades_today: Trades already taken today.

        Returns:
            Explanation string appropriate for logging / UI display.
        """
        prefix = f"[{stage.stage_name}] DD={drawdown_pct:.1f}%"

        if action == "TRADE":
            return (
                f"{prefix}: Signal ACCEPTED. "
                f"strategy={strategy_name} confidence={signal_confidence:.1f}% "
                f"(min={stage.min_confidence:.0f}%). "
                f"Apply {stage.position_scale:.0%} position scale."
            )
        elif action == "SKIP_CONFIDENCE":
            return (
                f"{prefix}: Signal SKIPPED — confidence {signal_confidence:.1f}% "
                f"below required {stage.min_confidence:.0f}% for {stage.stage_name} stage."
            )
        elif action == "SKIP_STRATEGY":
            allowed = ", ".join(stage.allowed_strategies) or "all"
            return (
                f"{prefix}: Signal SKIPPED — strategy '{strategy_name}' not "
                f"permitted in {stage.stage_name} stage. "
                f"Allowed: [{allowed}]."
            )
        elif action == "DAILY_LIMIT":
            return (
                f"{prefix}: Signal SKIPPED — daily trade limit reached "
                f"({trades_today}/{stage.max_trades_per_day} trades today)."
            )
        else:
            return f"{prefix}: Unknown action '{action}'."
