"""Market Mode — manual override of market conditions that adjusts all parameters."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from app.core.logging import get_logger

logger = get_logger(__name__)


class MarketMode(str, Enum):
    """Global market mode choices."""

    AUTO = "AUTO"                          # system auto-detects (default)
    TRENDING = "TRENDING"                  # manually set: trend-following mode
    RANGING = "RANGING"                    # manually set: mean-reversion mode
    HIGH_VOLATILITY = "HIGH_VOLATILITY"    # manually set: defensive mode
    ACCUMULATION = "ACCUMULATION"          # manually set: breakout-prep mode


@dataclass
class MarketModeConfig:
    """Configuration multipliers and constraints for a specific market mode."""

    mode: MarketMode
    # Strategy weight multipliers applied by the aggregator
    trend_strategy_weight: float
    reversion_strategy_weight: float
    # Signal quality thresholds
    min_confidence: float
    # Position sizing scale factor (1.0 = full size)
    position_scale: float
    # Which strategy names are permitted (empty list = all allowed)
    active_strategies: list[str]
    description: str


MODE_CONFIGS: dict[MarketMode, MarketModeConfig] = {
    MarketMode.AUTO: MarketModeConfig(
        mode=MarketMode.AUTO,
        trend_strategy_weight=1.0,
        reversion_strategy_weight=1.0,
        min_confidence=50.0,
        position_scale=1.0,
        active_strategies=[],  # empty = all
        description="Auto-detection active — system chooses based on regime classifier",
    ),
    MarketMode.TRENDING: MarketModeConfig(
        mode=MarketMode.TRENDING,
        trend_strategy_weight=1.5,
        reversion_strategy_weight=0.5,
        min_confidence=55.0,
        position_scale=1.0,
        active_strategies=[
            "trend_following",
            "trend_trader",
            "dual_momentum",
            "volume_breakout",
        ],
        description="Trend mode: maximize trend strategies, wider stops, full size",
    ),
    MarketMode.RANGING: MarketModeConfig(
        mode=MarketMode.RANGING,
        trend_strategy_weight=0.5,
        reversion_strategy_weight=1.5,
        min_confidence=60.0,
        position_scale=0.85,
        active_strategies=[
            "mean_reversion",
            "rsi_scalping",
            "breakout_failure",
            "basis_arbitrage",
        ],
        description="Range mode: mean reversion, tighter stops, slightly reduced size",
    ),
    MarketMode.HIGH_VOLATILITY: MarketModeConfig(
        mode=MarketMode.HIGH_VOLATILITY,
        trend_strategy_weight=0.8,
        reversion_strategy_weight=0.8,
        min_confidence=70.0,
        position_scale=0.50,
        active_strategies=[
            "funding_mean_reversion",
            "flash_crash_sniper",
            "basis_arbitrage",
        ],
        description="High vol: defensive, only highest confidence, half size",
    ),
    MarketMode.ACCUMULATION: MarketModeConfig(
        mode=MarketMode.ACCUMULATION,
        trend_strategy_weight=1.2,
        reversion_strategy_weight=1.0,
        min_confidence=62.0,
        position_scale=0.90,
        active_strategies=[
            "wyckoff_phases",
            "supply_demand",
            "breakout_failure",
            "dual_momentum",
        ],
        description="Accumulation: watching for range breakout, building positions",
    ),
}


class MarketModeManager:
    """Manages the global market mode override with audit trail.

    Thread-safe reads; writes are expected only from the API handler
    which runs in a single asyncio event loop.
    """

    def __init__(self) -> None:
        self._current_mode: MarketMode = MarketMode.AUTO
        self._set_by: str = "system"
        self._reason: str = ""

    def get_current_mode(self) -> MarketMode:
        """Return the current market mode."""
        return self._current_mode

    def get_config(self) -> MarketModeConfig:
        """Return the full configuration for the current mode."""
        return MODE_CONFIGS[self._current_mode]

    def set_mode(self, mode: MarketMode, reason: str = "", set_by: str = "user") -> None:
        """Set market mode with audit logging.

        Args:
            mode: Target MarketMode enum value.
            reason: Human-readable reason for the change (stored for display).
            set_by: Actor that requested the change ("user", "system", "api").
        """
        old = self._current_mode
        self._current_mode = mode
        self._set_by = set_by
        self._reason = reason
        logger.info(
            "Market mode changed: %s -> %s (by=%s, reason=%s)",
            old.value, mode.value, set_by, reason,
        )

    def reset_to_auto(self) -> None:
        """Reset to auto-detection mode."""
        self.set_mode(MarketMode.AUTO, reason="manual reset", set_by="user")

    def is_strategy_allowed(self, strategy_name: str) -> bool:
        """Check if a strategy is permitted in the current mode.

        Returns True when the active_strategies list is empty (all allowed).
        Normalises strategy names by lowercasing and replacing spaces with underscores.
        """
        config = self.get_config()
        if not config.active_strategies:
            return True  # empty list = all strategies allowed

        normalised = strategy_name.lower().replace(" ", "_")
        allowed_normalised = [s.lower().replace(" ", "_") for s in config.active_strategies]
        return normalised in allowed_normalised

    def get_min_confidence(self, base_confidence: float) -> float:
        """Return the effective minimum confidence, taking the mode's floor into account.

        Args:
            base_confidence: The caller's own minimum confidence threshold.

        Returns:
            The higher of base_confidence and the mode's minimum confidence requirement.
        """
        return max(base_confidence, self.get_config().min_confidence)

    def apply_strategy_weight(self, strategy_name: str, raw_confidence: float) -> float:
        """Scale a strategy's confidence contribution by the mode's weight multiplier.

        Trend strategies receive trend_strategy_weight; all others receive
        reversion_strategy_weight.  The result is clamped to [0, 100].

        Args:
            strategy_name: The strategy identifier.
            raw_confidence: The base confidence score (0-100).

        Returns:
            Adjusted confidence value clamped to [0, 100].
        """
        config = self.get_config()
        TREND_STRATEGIES = {
            "trend_following", "trend_trader", "dual_momentum",
            "volume_breakout", "smc_strategy",
        }
        normalised = strategy_name.lower().replace(" ", "_")
        if normalised in TREND_STRATEGIES:
            weight = config.trend_strategy_weight
        else:
            weight = config.reversion_strategy_weight

        adjusted = raw_confidence * weight
        return min(max(adjusted, 0.0), 100.0)

    def status_dict(self) -> dict:
        """Return current mode status as a serialisable dict for API responses."""
        config = self.get_config()
        return {
            "mode": self._current_mode.value,
            "set_by": self._set_by,
            "reason": self._reason,
            "config": {
                "min_confidence": config.min_confidence,
                "position_scale": config.position_scale,
                "trend_strategy_weight": config.trend_strategy_weight,
                "reversion_strategy_weight": config.reversion_strategy_weight,
                "active_strategies": config.active_strategies,
                "description": config.description,
            },
        }


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_manager: Optional[MarketModeManager] = None


def get_market_mode_manager() -> MarketModeManager:
    """Return the process-wide MarketModeManager singleton."""
    global _manager
    if _manager is None:
        _manager = MarketModeManager()
    return _manager
