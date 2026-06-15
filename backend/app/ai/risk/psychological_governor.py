"""Psychological Risk Governor — reduces risk during historically weak time periods.

Rather than relying purely on technical analysis, this module incorporates
time-of-day and day-of-week performance patterns. Crypto markets exhibit
strong session effects (London/NYSE open, weekend illiquidity) that a
naive signal system ignores.

Two modes of operation:
1. Default mode:  evidence-based multipliers for crypto markets (UTC)
2. Personalized:  user's own win-rate statistics override the defaults when
                  sufficient history is available (MIN_TRADES_FOR_CUSTOM = 30)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import numpy as np

from app.core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Default multiplier tables — evidence-based crypto trading patterns (UTC)
# ---------------------------------------------------------------------------

DEFAULT_HOUR_MULTIPLIERS: dict[int, float] = {
    0:  0.85,   # Midnight UTC — low liquidity
    1:  0.85,
    2:  0.80,   # Dead zone — minimal institutional activity
    3:  0.80,
    4:  0.85,
    5:  0.90,
    6:  0.95,
    7:  1.00,   # London pre-open
    8:  1.10,   # London open — HIGH quality
    9:  1.10,
    10: 1.05,
    11: 1.05,
    12: 1.00,
    13: 1.15,   # NYSE open — PRIME TIME
    14: 1.15,
    15: 1.10,
    16: 1.05,
    17: 1.00,
    18: 0.95,
    19: 0.90,
    20: 0.90,
    21: 0.85,   # NYSE close — fading liquidity
    22: 0.80,
    23: 0.80,
}

DEFAULT_DOW_MULTIPLIERS: dict[int, float] = {
    0: 1.00,   # Monday
    1: 1.05,   # Tuesday — historically strong trending day
    2: 1.05,   # Wednesday
    3: 1.00,   # Thursday
    4: 0.85,   # Friday — weekend risk-off, position squaring
    5: 0.70,   # Saturday — low institutional participation
    6: 0.75,   # Sunday — low liquidity, wide spreads
}


@dataclass
class GovernorDecision:
    """Time-based risk multiplier decision."""

    current_hour_utc: int
    current_dow: int              # 0 = Monday … 6 = Sunday
    hour_multiplier: float
    dow_multiplier: float
    combined_multiplier: float
    should_reduce_risk: bool
    reason: str
    custom_stats_applied: bool    # True if user's own historical stats were used


class PsychologicalGovernor:
    """Adjusts signal confidence based on time period performance patterns.

    Initialization::

        # Default (evidence-based) mode
        gov = PsychologicalGovernor()

        # Personalized mode — provide per-hour and per-DOW win rates
        gov = PsychologicalGovernor(
            custom_hour_stats={8: 0.65, 13: 0.68, ...},
            custom_dow_stats={0: 0.52, 1: 0.59, ...},
        )

    Usage::

        decision = gov.get_decision()
        adjusted_confidence = gov.apply_to_confidence(raw_confidence)
    """

    MAX_MULTIPLIER: float = 1.2   # never boost confidence above this
    MIN_MULTIPLIER: float = 0.5   # never reduce below this
    MIN_TRADES_FOR_CUSTOM: int = 30  # need 30+ trades per period for custom stats

    def __init__(
        self,
        custom_hour_stats: Optional[dict[int, float]] = None,
        custom_dow_stats: Optional[dict[int, float]] = None,
    ) -> None:
        """Initialise the governor with optional personalised win-rate statistics.

        Args:
            custom_hour_stats: Mapping of UTC hour → win rate (0.0–1.0) for
                at least 12 distinct hours. When provided, overrides the default
                hour multipliers.
            custom_dow_stats: Mapping of day-of-week → win rate (0.0–1.0).
                Optional even when ``custom_hour_stats`` is supplied.
        """
        self.hour_multipliers: dict[int, float] = DEFAULT_HOUR_MULTIPLIERS.copy()
        self.dow_multipliers: dict[int, float] = DEFAULT_DOW_MULTIPLIERS.copy()
        self._custom_applied: bool = False

        if custom_hour_stats and len(custom_hour_stats) >= 12:
            self._apply_custom_stats(custom_hour_stats, custom_dow_stats)
            self._custom_applied = True
            logger.info(
                "PsychologicalGovernor: personalised stats applied for %d hours",
                len(custom_hour_stats),
            )

    # --------------------------------------------------------------------- public

    def get_decision(self) -> GovernorDecision:
        """Return a risk multiplier decision for the current UTC moment.

        Returns:
            :class:`GovernorDecision` containing the combined multiplier and
            human-readable reasoning.
        """
        now = datetime.now(timezone.utc)
        hour = now.hour
        dow = now.weekday()  # 0 = Monday

        hour_mult = self.hour_multipliers.get(hour, 1.0)
        dow_mult = self.dow_multipliers.get(dow, 1.0)

        # Geometric mean avoids extreme compounding while preserving both signals
        combined = float(np.sqrt(hour_mult * dow_mult))
        combined = float(np.clip(combined, self.MIN_MULTIPLIER, self.MAX_MULTIPLIER))

        should_reduce = combined < 1.0
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

        reason_parts: list[str] = [
            f"Hour {hour:02d}UTC ({hour_mult:.2f}x)",
            f"{day_names[dow]} ({dow_mult:.2f}x)",
            f"→ combined {combined:.2f}x",
        ]
        if self._custom_applied:
            reason_parts.append("[personalised stats]")

        reason = " | ".join(reason_parts)

        logger.debug("GovernorDecision: %s", reason)

        return GovernorDecision(
            current_hour_utc=hour,
            current_dow=dow,
            hour_multiplier=round(hour_mult, 4),
            dow_multiplier=round(dow_mult, 4),
            combined_multiplier=round(combined, 4),
            should_reduce_risk=should_reduce,
            reason=reason,
            custom_stats_applied=self._custom_applied,
        )

    def apply_to_confidence(self, confidence: float) -> float:
        """Apply the current time multiplier to a signal confidence score.

        Args:
            confidence: Raw signal confidence value (any unit; commonly 0–100).

        Returns:
            Adjusted confidence, capped so that multiplier never exceeds
            MAX_MULTIPLIER and never drops below MIN_MULTIPLIER.
        """
        decision = self.get_decision()
        adjusted = confidence * decision.combined_multiplier
        return round(adjusted, 4)

    def get_upcoming_prime_times(self, hours_ahead: int = 8) -> list[dict]:
        """Return next prime trading windows within the next N hours.

        A "prime time" window is defined as combined_multiplier >= 1.05.

        Args:
            hours_ahead: How many hours into the future to check.

        Returns:
            List of dicts with keys: ``hour_utc``, ``day_name``,
            ``combined_multiplier``, ``description``.
        """
        now = datetime.now(timezone.utc)
        prime_windows: list[dict] = []
        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday",
                     "Friday", "Saturday", "Sunday"]

        for offset in range(1, hours_ahead + 1):
            future = now.replace(minute=0, second=0, microsecond=0)
            import datetime as dt_module
            future = future + dt_module.timedelta(hours=offset)

            h = future.hour
            dow = future.weekday()
            hour_mult = self.hour_multipliers.get(h, 1.0)
            dow_mult = self.dow_multipliers.get(dow, 1.0)
            combined = float(np.clip(
                np.sqrt(hour_mult * dow_mult),
                self.MIN_MULTIPLIER,
                self.MAX_MULTIPLIER,
            ))

            if combined >= 1.05:
                prime_windows.append({
                    "hour_utc": h,
                    "day_name": day_names[dow],
                    "combined_multiplier": round(combined, 4),
                    "description": (
                        f"{day_names[dow]} {h:02d}:00 UTC — "
                        f"{combined:.0%} confidence boost"
                    ),
                })

        return prime_windows

    # --------------------------------------------------------------------- private

    def _apply_custom_stats(
        self,
        hour_stats: dict[int, float],
        dow_stats: Optional[dict[int, float]],
    ) -> None:
        """Replace default multipliers with user-personalised win-rate tables.

        For hours without custom data, the default multiplier is preserved.

        Args:
            hour_stats: Per-hour win rates to convert to multipliers.
            dow_stats: Per-DOW win rates to convert to multipliers; optional.
        """
        baseline_wr = float(np.mean(list(hour_stats.values())))

        for hour, win_rate in hour_stats.items():
            self.hour_multipliers[hour] = self._winrate_to_multiplier(
                win_rate, baseline=baseline_wr
            )

        if dow_stats:
            baseline_dow = float(np.mean(list(dow_stats.values())))
            for dow, win_rate in dow_stats.items():
                self.dow_multipliers[dow] = self._winrate_to_multiplier(
                    win_rate, baseline=baseline_dow
                )

    def _winrate_to_multiplier(
        self, win_rate: float, baseline: float = 0.50
    ) -> float:
        """Convert an absolute win rate to a relative confidence multiplier.

        Formula:
            multiplier = 1.0 + (win_rate - baseline) / baseline

        Examples:
            win_rate=0.60, baseline=0.50 → 1.20 (boost by 20%)
            win_rate=0.40, baseline=0.50 → 0.80 (reduce by 20%)

        Args:
            win_rate: Observed win rate for the period [0, 1].
            baseline: Reference win rate to compare against.

        Returns:
            Multiplier clamped to [MIN_MULTIPLIER, MAX_MULTIPLIER].
        """
        if baseline <= 0:
            return 1.0

        multiplier = 1.0 + (win_rate - baseline) / max(baseline, 1e-8)
        return float(
            np.clip(multiplier, self.MIN_MULTIPLIER, self.MAX_MULTIPLIER)
        )


# Module-level singleton
_governor: PsychologicalGovernor | None = None


def get_psychological_governor() -> PsychologicalGovernor:
    """Return the global :class:`PsychologicalGovernor` singleton.

    Returns:
        Shared PsychologicalGovernor instance (default, evidence-based mode).
    """
    global _governor
    if _governor is None:
        _governor = PsychologicalGovernor()
    return _governor
