"""Drawdown Waterfall — tiered response system to protect capital during drawdowns.

Three tiers trigger progressively stronger responses:
  Tier 1 (5% DD)  → Reduce position size by 50%
  Tier 2 (8% DD)  → Switch to paper trading only
  Tier 3 (12% DD) → Full trading halt

This prevents catastrophic losses during adverse market conditions by
automatically reducing exposure as drawdown deepens.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

DRAWDOWN_TIERS: list[dict[str, Any]] = [
    {
        "tier": 1,
        "threshold": 5.0,
        "action": "REDUCE_SIZE_50PCT",
        "description": "Reduce position size by 50%",
        "size_multiplier": 0.5,
    },
    {
        "tier": 2,
        "threshold": 8.0,
        "action": "PAPER_ONLY",
        "description": "Switch to paper trading only — no real positions",
        "size_multiplier": 0.0,
    },
    {
        "tier": 3,
        "threshold": 12.0,
        "action": "FULL_STOP",
        "description": "Full trading halt — all signal generation paused",
        "size_multiplier": 0.0,
    },
]


class DrawdownWaterfall:
    """Monitors equity drawdown and enforces tiered protective responses."""

    def __init__(self, peak_equity: float = 10_000.0) -> None:
        """Initialize the drawdown waterfall.

        Args:
            peak_equity: Starting peak equity value in USD
        """
        self._peak_equity: float = peak_equity
        self._current_equity: float = peak_equity
        self._current_tier: int = 0  # 0 = normal trading
        self._tier_history: list[dict[str, Any]] = []
        self._halt_until: datetime | None = None

    def update_equity(self, new_equity: float) -> dict[str, Any]:
        """Update current equity and evaluate drawdown tiers.

        Args:
            new_equity: Current account equity value in USD

        Returns:
            {tier_changed, new_tier, action, drawdown_pct, size_multiplier}
        """
        self._current_equity = new_equity
        if new_equity > self._peak_equity:
            self._peak_equity = new_equity

        drawdown_pct = self.get_current_drawdown_pct()
        prev_tier = self._current_tier

        # Find the applicable tier
        new_tier = 0
        for tier_def in reversed(DRAWDOWN_TIERS):
            if drawdown_pct >= tier_def["threshold"]:
                new_tier = tier_def["tier"]
                break

        tier_changed = new_tier != prev_tier
        if tier_changed:
            self._current_tier = new_tier
            tier_info = self.get_current_tier()
            event = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "from_tier": prev_tier,
                "to_tier": new_tier,
                "drawdown_pct": drawdown_pct,
                "equity": new_equity,
                "action": tier_info.get("action", "NORMAL"),
            }
            self._tier_history.append(event)
            logger.warning(
                "DrawdownWaterfall | Tier changed %d→%d at DD=%.2f%% equity=%.2f",
                prev_tier, new_tier, drawdown_pct, new_equity,
            )

        tier_info = self.get_current_tier()
        return {
            "tier_changed": tier_changed,
            "new_tier": new_tier,
            "action": tier_info.get("action", "NORMAL"),
            "description": tier_info.get("description", "Normal trading"),
            "drawdown_pct": round(drawdown_pct, 2),
            "size_multiplier": self.get_size_multiplier(),
            "peak_equity": self._peak_equity,
            "current_equity": new_equity,
        }

    def get_current_drawdown_pct(self) -> float:
        """Compute current drawdown from peak equity.

        Returns:
            Drawdown percentage (positive value, e.g. 5.0 = 5% down from peak)
        """
        if self._peak_equity <= 0:
            return 0.0
        return round((self._peak_equity - self._current_equity) / self._peak_equity * 100, 4)

    def get_current_tier(self) -> dict[str, Any]:
        """Return the current active tier definition.

        Returns:
            Tier dict with {tier, threshold, action, description, size_multiplier}
        """
        if self._current_tier == 0:
            return {
                "tier": 0,
                "threshold": 0.0,
                "action": "NORMAL",
                "description": "Normal trading — no restrictions",
                "size_multiplier": 1.0,
            }
        for t in DRAWDOWN_TIERS:
            if t["tier"] == self._current_tier:
                return t
        return DRAWDOWN_TIERS[-1]

    def get_size_multiplier(self) -> float:
        """Return the current position size multiplier.

        Returns:
            Multiplier: 1.0 = full size, 0.5 = half, 0.0 = no trading
        """
        return self.get_current_tier().get("size_multiplier", 1.0)

    def get_state(self) -> dict[str, Any]:
        """Return full state for API/UI display.

        Returns:
            Complete state dict
        """
        return {
            "current_tier": self._current_tier,
            "current_action": self.get_current_tier().get("action", "NORMAL"),
            "drawdown_pct": self.get_current_drawdown_pct(),
            "peak_equity": round(self._peak_equity, 2),
            "current_equity": round(self._current_equity, 2),
            "size_multiplier": self.get_size_multiplier(),
            "tiers": DRAWDOWN_TIERS,
            "tier_history": self._tier_history[-10:],  # last 10 events
            "trading_allowed": self._current_tier < 3,
        }

    def reset_peak(self) -> None:
        """Reset peak equity to current equity (manual override)."""
        self._peak_equity = self._current_equity
        self._current_tier = 0
        logger.info("DrawdownWaterfall | Peak equity reset to %.2f", self._peak_equity)


# Module-level singleton
_waterfall: DrawdownWaterfall | None = None


def get_drawdown_waterfall() -> DrawdownWaterfall:
    """Return the global DrawdownWaterfall singleton.

    Returns:
        Shared DrawdownWaterfall instance
    """
    global _waterfall
    if _waterfall is None:
        _waterfall = DrawdownWaterfall()
    return _waterfall
