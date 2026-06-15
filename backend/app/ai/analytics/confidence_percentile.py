"""Confidence Percentile Tracker — ranks signals vs historical distribution.

This module answers the question: "Is this 72% confidence signal actually good,
or does the system routinely produce 75%+ signals, making it mediocre?"

By maintaining rolling histories per symbol/strategy combination and computing
percentile ranks, traders can calibrate how much weight to give each signal
relative to past signal quality — not just the absolute confidence number.

Separate histories are maintained for:
- Global ("ALL") — all signals ever seen
- Per symbol ("BTC/USDT", "ETH/USDT", …)
- Per strategy ("trend_following", "smc", …)
- Combined per-symbol+strategy ("BTC/USDT|trend_following")
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import numpy as np

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ConfidencePercentileResult:
    """Result of ranking a signal against historical confidence distribution."""

    signal_confidence: float
    percentile: float           # 0–100: proportion of historical signals BELOW this
    percentile_label: str       # "TOP_5%", "TOP_15%", "AVERAGE", "BELOW_AVERAGE"
    historical_count: int       # number of signals in the reference history
    historical_mean: float
    historical_p75: float       # 75th percentile threshold
    historical_p90: float       # 90th percentile threshold
    is_exceptional: bool        # True if confidence is in top 15% historically
    recommendation: str         # "STRONG_SIGNAL", "AVERAGE_SIGNAL", "WEAK_SIGNAL"


class ConfidencePercentileTracker:
    """Maintains rolling signal confidence histories and computes percentile ranks.

    The tracker stores up to MAX_HISTORY signals per key. When the deque is full,
    the oldest entries are dropped automatically.

    Usage::

        tracker = ConfidencePercentileTracker()

        # Record signals over time
        tracker.add_signal(72.5, symbol="BTC/USDT", strategy="trend_following")
        tracker.add_signal(68.0, symbol="BTC/USDT", strategy="trend_following")

        # Rank a new signal
        result = tracker.rank_signal(75.0, symbol="BTC/USDT", strategy="trend_following")
        print(result.percentile_label)  # e.g. "TOP_15%"
    """

    MAX_HISTORY: int = 1000        # rolling window per key
    TOP_EXCEPTIONAL_PCT: float = 85.0  # above this percentile = exceptional
    MIN_HISTORY_FOR_SPECIFIC: int = 50  # fall back to global if fewer

    def __init__(self) -> None:
        """Initialise tracker with empty history stores."""
        self._histories: dict[str, deque] = {}

    # --------------------------------------------------------------------- public

    def add_signal(
        self,
        confidence: float,
        symbol: str,
        strategy: str,
        timestamp: Optional[datetime] = None,
    ) -> None:
        """Record a signal confidence value to all relevant history buckets.

        Adds the confidence to:
        - The global "ALL" history
        - The per-symbol history
        - The per-strategy history
        - The combined symbol+strategy history

        Args:
            confidence: Signal confidence value (0–100 typical range).
            symbol: Trading pair symbol, e.g. "BTC/USDT".
            strategy: Strategy name, e.g. "trend_following".
            timestamp: Optional signal timestamp; stored for future TTL use.
        """
        value = float(confidence)

        keys = [
            "ALL",
            self._get_history_key(symbol, None),
            self._get_history_key(None, strategy),
            self._get_history_key(symbol, strategy),
        ]

        for key in keys:
            self._ensure_history(key)
            self._histories[key].append(value)

        logger.debug(
            "ConfidenceTracker: added confidence=%.2f symbol=%s strategy=%s",
            value,
            symbol,
            strategy,
        )

    def rank_signal(
        self,
        confidence: float,
        symbol: Optional[str] = None,
        strategy: Optional[str] = None,
        use_global: bool = True,
    ) -> ConfidencePercentileResult:
        """Rank a confidence value against stored historical distribution.

        Selection priority:
        1. Combined symbol+strategy history (if >= MIN_HISTORY_FOR_SPECIFIC entries)
        2. Per-symbol or per-strategy history (if >= MIN_HISTORY_FOR_SPECIFIC entries)
        3. Global "ALL" history (when use_global=True)
        4. Empty result with sensible defaults

        Percentile = % of historical signals STRICTLY below this confidence.

        Args:
            confidence: Confidence value to rank (0–100).
            symbol: Optional symbol filter.
            strategy: Optional strategy filter.
            use_global: When True, fall back to global history when specific
                history is too small.

        Returns:
            :class:`ConfidencePercentileResult` with percentile and labels.
        """
        value = float(confidence)

        # Determine the best available history
        history_arr = self._resolve_history(symbol, strategy, use_global)

        if history_arr is None or len(history_arr) == 0:
            logger.debug(
                "ConfidenceTracker: no history for symbol=%s strategy=%s — "
                "returning default result",
                symbol,
                strategy,
            )
            return self._default_result(value)

        arr = np.array(history_arr, dtype=float)
        n = len(arr)

        percentile = float(np.mean(arr < value) * 100.0)
        mean = float(np.mean(arr))
        p75 = float(np.percentile(arr, 75))
        p90 = float(np.percentile(arr, 90))

        is_exceptional = percentile >= self.TOP_EXCEPTIONAL_PCT
        percentile_label = self._percentile_label(percentile)
        recommendation = self._build_recommendation(percentile)

        logger.debug(
            "ConfidenceTracker: confidence=%.2f percentile=%.1f "
            "label=%s n=%d",
            value,
            percentile,
            percentile_label,
            n,
        )

        return ConfidencePercentileResult(
            signal_confidence=round(value, 4),
            percentile=round(percentile, 2),
            percentile_label=percentile_label,
            historical_count=n,
            historical_mean=round(mean, 4),
            historical_p75=round(p75, 4),
            historical_p90=round(p90, 4),
            is_exceptional=is_exceptional,
            recommendation=recommendation,
        )

    def get_stats(self, symbol: str = "ALL") -> dict:
        """Return distribution statistics for a given symbol (or global).

        Args:
            symbol: Symbol key or "ALL" for global stats.

        Returns:
            Dict with count, mean, std, p25, p50, p75, p90, p95.
        """
        key = symbol if symbol == "ALL" else self._get_history_key(symbol, None)
        self._ensure_history(key)
        arr = np.array(list(self._histories[key]), dtype=float)

        if len(arr) == 0:
            return {"count": 0, "mean": 0.0, "std": 0.0,
                    "p25": 0.0, "p50": 0.0, "p75": 0.0, "p90": 0.0, "p95": 0.0}

        return {
            "count": len(arr),
            "mean": round(float(np.mean(arr)), 4),
            "std": round(float(np.std(arr)), 4),
            "p25": round(float(np.percentile(arr, 25)), 4),
            "p50": round(float(np.percentile(arr, 50)), 4),
            "p75": round(float(np.percentile(arr, 75)), 4),
            "p90": round(float(np.percentile(arr, 90)), 4),
            "p95": round(float(np.percentile(arr, 95)), 4),
        }

    # --------------------------------------------------------------------- private

    def _get_history_key(
        self,
        symbol: Optional[str],
        strategy: Optional[str],
    ) -> str:
        """Generate a string key for the history dictionary.

        Args:
            symbol: Optional symbol; None is represented as "ALL".
            strategy: Optional strategy; None is represented as "ALL".

        Returns:
            A colon-separated key string.
        """
        sym_part = symbol if symbol else "ALL"
        strat_part = strategy if strategy else "ALL"
        return f"{sym_part}|{strat_part}"

    def _ensure_history(self, key: str) -> None:
        """Create a deque for ``key`` if it does not already exist.

        Args:
            key: History dictionary key.
        """
        if key not in self._histories:
            self._histories[key] = deque(maxlen=self.MAX_HISTORY)

    def _resolve_history(
        self,
        symbol: Optional[str],
        strategy: Optional[str],
        use_global: bool,
    ) -> Optional[list[float]]:
        """Find the most specific history that meets the minimum size threshold.

        Args:
            symbol: Optional symbol filter.
            strategy: Optional strategy filter.
            use_global: Whether to fall back to global history.

        Returns:
            List of confidence values, or None if nothing is available.
        """
        candidates: list[str] = []

        if symbol and strategy:
            candidates.append(self._get_history_key(symbol, strategy))
        if symbol:
            candidates.append(self._get_history_key(symbol, None))
        if strategy:
            candidates.append(self._get_history_key(None, strategy))
        if use_global:
            candidates.append("ALL")

        for key in candidates:
            if key in self._histories and len(self._histories[key]) >= self.MIN_HISTORY_FOR_SPECIFIC:
                return list(self._histories[key])

        # Fallback: return whatever we have from global even if small
        if use_global and "ALL" in self._histories and len(self._histories["ALL"]) > 0:
            return list(self._histories["ALL"])

        return None

    def _percentile_label(self, pct: float) -> str:
        """Convert a percentile number to a human-readable label.

        Args:
            pct: Percentile rank [0, 100].

        Returns:
            Label string describing relative strength.
        """
        if pct >= 95:
            return "TOP_5%"
        if pct >= 85:
            return "TOP_15%"
        if pct >= 60:
            return "ABOVE_AVERAGE"
        if pct >= 40:
            return "AVERAGE"
        return "BELOW_AVERAGE"

    def _build_recommendation(self, percentile: float) -> str:
        """Build a recommendation string based on percentile rank.

        Args:
            percentile: Percentile rank [0, 100].

        Returns:
            One of "STRONG_SIGNAL", "AVERAGE_SIGNAL", "WEAK_SIGNAL".
        """
        if percentile >= self.TOP_EXCEPTIONAL_PCT:
            return "STRONG_SIGNAL"
        if percentile >= 40:
            return "AVERAGE_SIGNAL"
        return "WEAK_SIGNAL"

    def _default_result(self, confidence: float) -> ConfidencePercentileResult:
        """Return a neutral result when no history is available.

        Args:
            confidence: Signal confidence value.

        Returns:
            :class:`ConfidencePercentileResult` with neutral defaults.
        """
        return ConfidencePercentileResult(
            signal_confidence=round(confidence, 4),
            percentile=50.0,
            percentile_label="AVERAGE",
            historical_count=0,
            historical_mean=confidence,
            historical_p75=confidence,
            historical_p90=confidence,
            is_exceptional=False,
            recommendation="AVERAGE_SIGNAL",
        )


# Module-level singleton
_tracker: ConfidencePercentileTracker | None = None


def get_confidence_tracker() -> ConfidencePercentileTracker:
    """Return the global :class:`ConfidencePercentileTracker` singleton.

    Returns:
        Shared ConfidencePercentileTracker instance.
    """
    global _tracker
    if _tracker is None:
        _tracker = ConfidencePercentileTracker()
    return _tracker
