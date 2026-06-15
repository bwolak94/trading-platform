"""Pattern Performance Tracker — tracks which patterns are working in current market."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional

import numpy as np

from app.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# All pattern names supported by the tracker.
# Extend this list as new pattern detectors are added.
# ---------------------------------------------------------------------------
TRACKED_PATTERNS: list[str] = [
    "wyckoff_spring",
    "wyckoff_sc",
    "wyckoff_bc",
    "wyckoff_sos",
    "gartley",
    "butterfly",
    "bat",
    "crab",
    "elliott_impulse",
    "elliott_correction",
    "bull_trap",
    "bear_trap",
    "breakout_failure",
    "divergence_bullish",
    "divergence_bearish",
    "cvd_divergence",
    "supply_zone_test",
    "demand_zone_test",
    "fib_confluence",
]


@dataclass
class PatternStats:
    """Performance statistics for a single pattern."""

    pattern_name: str
    win_rate: float
    avg_return_pct: float
    sample_size: int
    last_updated: datetime
    is_active: bool                        # True when WR > 45% and sample >= 10
    recent_streak: int                     # positive = consecutive wins, negative = losses
    regime_performance: dict[str, float]   # {regime: win_rate}


@dataclass
class PatternPerformanceReport:
    """Aggregated pattern performance report."""

    top_patterns: list[PatternStats]           # best performing (is_active=True)
    disabled_patterns: list[PatternStats]      # WR < 45% → auto-disabled
    regime_recommendations: dict[str, list[str]]  # {regime: [top pattern names]}
    total_tracked: int
    last_analysis: datetime


class PatternPerformanceTracker:
    """Tracks observed win/loss outcomes for each pattern type.

    Behaviour
    ---------
    - Records outcome, regime, and return % for each pattern occurrence.
    - Auto-disables patterns whose win rate drops below 45 % over 20+ observations.
    - Generates per-regime pattern recommendations.
    - Keeps only the last ``MAX_HISTORY`` observations per pattern to stay current.

    Thread safety
    -------------
    Not thread-safe.  Wrap with a lock if called from multiple async tasks.
    """

    MIN_SAMPLE: int = 10          # minimum observations for a reliability estimate
    DISABLE_WINRATE: float = 0.45  # patterns below this WR get auto-disabled
    MAX_HISTORY: int = 200         # per-pattern history cap

    def __init__(self) -> None:
        # {pattern_name: [{"result": "WIN"/"LOSS", "regime": str,
        #                   "return_pct": float, "timestamp": datetime}]}
        self._history: dict[str, list[dict]] = defaultdict(list)

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record_outcome(
        self,
        pattern_name: str,
        result: str,
        regime: str,
        return_pct: float,
        timestamp: Optional[datetime] = None,
    ) -> None:
        """Record a single pattern trade outcome.

        Args:
            pattern_name: Must be one of ``TRACKED_PATTERNS`` (unknown names are
                          accepted but will not appear in recommendations).
            result: ``"WIN"`` or ``"LOSS"``.
            regime: Market regime at the time (e.g. ``"TREND_BULL"``).
            return_pct: Actual return percentage for this trade (can be negative).
            timestamp: Observation time (defaults to ``datetime.now(UTC)``).
        """
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)

        record = {
            "result": result.upper(),
            "regime": regime,
            "return_pct": float(return_pct),
            "timestamp": timestamp,
        }

        history = self._history[pattern_name]
        history.append(record)

        # Trim to MAX_HISTORY (keep newest)
        if len(history) > self.MAX_HISTORY:
            self._history[pattern_name] = history[-self.MAX_HISTORY :]

        logger.debug(
            "PatternPerformanceTracker: recorded %s %s regime=%s return=%.2f%%",
            pattern_name,
            result,
            regime,
            return_pct,
        )

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def get_stats(
        self, pattern_name: str, lookback_days: int = 30
    ) -> PatternStats:
        """Retrieve performance statistics for a specific pattern.

        Args:
            pattern_name: Pattern to query.
            lookback_days: Consider only observations within this many days.

        Returns:
            PatternStats dataclass (with zero values if no history exists).
        """
        history = self._filter_recent(
            self._history.get(pattern_name, []), lookback_days
        )

        if not history:
            return PatternStats(
                pattern_name=pattern_name,
                win_rate=0.0,
                avg_return_pct=0.0,
                sample_size=0,
                last_updated=datetime.now(timezone.utc),
                is_active=False,
                recent_streak=0,
                regime_performance={},
            )

        wins = [r for r in history if r["result"] == "WIN"]
        win_rate = len(wins) / len(history)
        avg_return = float(np.mean([r["return_pct"] for r in history]))

        is_active = (
            win_rate >= self.DISABLE_WINRATE and len(history) >= self.MIN_SAMPLE
        ) or len(history) < self.MIN_SAMPLE  # not enough data → assume active

        # Recent streak: walk backwards to count consecutive identical results
        streak = self._calc_streak(history)

        # Per-regime win rates
        regime_performance = self._regime_win_rates(history)

        last_ts = max(
            (r["timestamp"] for r in history),
            default=datetime.now(timezone.utc),
        )

        return PatternStats(
            pattern_name=pattern_name,
            win_rate=round(win_rate, 4),
            avg_return_pct=round(avg_return, 4),
            sample_size=len(history),
            last_updated=last_ts,
            is_active=is_active,
            recent_streak=streak,
            regime_performance={k: round(v, 4) for k, v in regime_performance.items()},
        )

    def generate_report(self, lookback_days: int = 30) -> PatternPerformanceReport:
        """Generate a full performance report for all tracked patterns.

        Args:
            lookback_days: Analysis window (default 30 days).

        Returns:
            PatternPerformanceReport.
        """
        all_stats = [
            self.get_stats(p, lookback_days)
            for p in TRACKED_PATTERNS
        ]

        # Also include any patterns recorded but not in TRACKED_PATTERNS
        extra = set(self._history.keys()) - set(TRACKED_PATTERNS)
        for p in sorted(extra):
            all_stats.append(self.get_stats(p, lookback_days))

        active = sorted(
            [s for s in all_stats if s.is_active and s.sample_size >= self.MIN_SAMPLE],
            key=lambda s: s.win_rate,
            reverse=True,
        )
        disabled = sorted(
            [s for s in all_stats if not s.is_active and s.sample_size >= self.MIN_SAMPLE],
            key=lambda s: s.win_rate,
            reverse=True,
        )

        # Per-regime recommendations
        regimes = {"TREND_BULL", "TREND_BEAR", "CONSOLIDATION", "HIGH_VOL_CHOPPY"}
        regime_recommendations: dict[str, list[str]] = {}
        for regime in regimes:
            regime_recommendations[regime] = self.get_best_patterns_for_regime(
                regime, top_n=3
            )

        logger.info(
            "PatternPerformanceReport: %d active, %d disabled patterns",
            len(active),
            len(disabled),
        )

        return PatternPerformanceReport(
            top_patterns=active,
            disabled_patterns=disabled,
            regime_recommendations=regime_recommendations,
            total_tracked=len(all_stats),
            last_analysis=datetime.now(timezone.utc),
        )

    def is_pattern_active(self, pattern_name: str) -> bool:
        """Check whether a pattern should be used based on recent performance.

        Patterns with insufficient history (< MIN_SAMPLE) are considered active
        (benefit of the doubt).

        Args:
            pattern_name: Pattern to check.

        Returns:
            ``True`` if the pattern should be used; ``False`` if auto-disabled.
        """
        stats = self.get_stats(pattern_name, lookback_days=30)
        return stats.is_active

    def get_best_patterns_for_regime(
        self, regime: str, top_n: int = 3
    ) -> list[str]:
        """Return the top N performing pattern names for a given regime.

        Only patterns with at least ``MIN_SAMPLE`` occurrences in that regime
        are included.  Patterns with no regime-specific data are excluded.

        Args:
            regime: Market regime string.
            top_n: Number of top patterns to return.

        Returns:
            List of pattern name strings, best first.
        """
        scored: list[tuple[str, float]] = []

        for pattern_name in list(TRACKED_PATTERNS) + sorted(
            set(self._history.keys()) - set(TRACKED_PATTERNS)
        ):
            history = self._history.get(pattern_name, [])
            regime_history = [r for r in history if r.get("regime") == regime]
            if len(regime_history) < self.MIN_SAMPLE:
                continue
            wins = sum(1 for r in regime_history if r["result"] == "WIN")
            wr = wins / len(regime_history)
            if wr >= self.DISABLE_WINRATE:
                scored.append((pattern_name, wr))

        scored.sort(key=lambda t: t[1], reverse=True)
        return [name for name, _ in scored[:top_n]]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _filter_recent(
        self, history: list[dict], lookback_days: int
    ) -> list[dict]:
        """Filter history to only observations within the lookback window.

        Args:
            history: Full observation list for a pattern.
            lookback_days: Number of days to look back from now.

        Returns:
            Filtered list (may be empty).
        """
        if not history:
            return []
        cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        return [r for r in history if r["timestamp"] >= cutoff]

    @staticmethod
    def _calc_streak(history: list[dict]) -> int:
        """Calculate the current consecutive win/loss streak.

        Walks the history list backwards (most recent first).

        Returns:
            Positive integer for a winning streak, negative for a losing streak.
            Zero if history is empty.
        """
        if not history:
            return 0

        last_result = history[-1]["result"]
        streak = 0
        for record in reversed(history):
            if record["result"] == last_result:
                streak += 1
            else:
                break

        return streak if last_result == "WIN" else -streak

    @staticmethod
    def _regime_win_rates(history: list[dict]) -> dict[str, float]:
        """Calculate per-regime win rates from a history list.

        Args:
            history: List of outcome records.

        Returns:
            Dict mapping regime → win_rate.
        """
        regime_wins: dict[str, int] = defaultdict(int)
        regime_totals: dict[str, int] = defaultdict(int)

        for record in history:
            regime = record.get("regime", "UNKNOWN")
            regime_totals[regime] += 1
            if record["result"] == "WIN":
                regime_wins[regime] += 1

        return {
            regime: regime_wins[regime] / total
            for regime, total in regime_totals.items()
            if total > 0
        }
