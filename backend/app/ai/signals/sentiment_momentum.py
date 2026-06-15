"""D4: FinBERT sentiment momentum filter.

Tracks rolling 6-hour sentiment scores.  Emits a boost signal when sentiment
has been positive (> 0) for 3 or more consecutive readings.  A negative streak
produces a bearish bias instead.

This is used as a pre-filter in the signal aggregator to amplify or dampen the
``sentiment_score`` component based on momentum, not just the latest reading.
"""

from collections import deque
from datetime import datetime, timezone
from dataclasses import dataclass

from app.core.logging import get_logger

logger = get_logger(__name__)

# How many consecutive same-direction readings trigger a momentum boost
MOMENTUM_STREAK_THRESHOLD = 3
BOOST_MULTIPLIER = 1.25
DAMPEN_MULTIPLIER = 0.75


@dataclass
class SentimentReading:
    """A single sentiment score with timestamp."""

    score: float
    timestamp: datetime


@dataclass
class SentimentMomentumResult:
    """Result of momentum calculation."""

    raw_score: float
    adjusted_score: float
    streak: int
    direction: str  # "bullish" | "bearish" | "neutral"
    multiplier: float


class SentimentMomentumFilter:
    """Rolling sentiment momentum tracker.

    Maintains the last ``window`` sentiment readings and detects streaks
    of consecutive positive or negative scores.

    Args:
        window:             Maximum number of readings to retain (default 12 = 6 h at 30 min intervals).
        streak_threshold:   Consecutive same-direction readings needed for a boost.
        boost_multiplier:   Multiplier applied to score on positive streak.
        dampen_multiplier:  Multiplier applied to score on negative streak.
    """

    def __init__(
        self,
        window: int = 12,
        streak_threshold: int = MOMENTUM_STREAK_THRESHOLD,
        boost_multiplier: float = BOOST_MULTIPLIER,
        dampen_multiplier: float = DAMPEN_MULTIPLIER,
    ) -> None:
        self._readings: deque[SentimentReading] = deque(maxlen=window)
        self.streak_threshold = streak_threshold
        self.boost_multiplier = boost_multiplier
        self.dampen_multiplier = dampen_multiplier

    def add(self, score: float) -> None:
        """Record a new sentiment score."""
        self._readings.append(SentimentReading(score=score, timestamp=datetime.now(timezone.utc)))

    def compute(self, raw_score: float) -> SentimentMomentumResult:
        """Calculate momentum-adjusted sentiment score.

        Args:
            raw_score: Latest raw sentiment score in [-1, 1].

        Returns:
            :class:`SentimentMomentumResult` with the adjusted score and metadata.
        """
        self.add(raw_score)

        if len(self._readings) < self.streak_threshold:
            return SentimentMomentumResult(
                raw_score=raw_score,
                adjusted_score=raw_score,
                streak=len(self._readings),
                direction="neutral",
                multiplier=1.0,
            )

        recent = list(self._readings)[-self.streak_threshold:]
        all_positive = all(r.score > 0 for r in recent)
        all_negative = all(r.score < 0 for r in recent)

        # Measure full streak length (not just the threshold window)
        streak = 0
        if all_positive or all_negative:
            target_positive = all_positive
            for r in reversed(list(self._readings)):
                if target_positive and r.score > 0:
                    streak += 1
                elif not target_positive and r.score < 0:
                    streak += 1
                else:
                    break

        if all_positive and streak >= self.streak_threshold:
            multiplier = self.boost_multiplier
            direction = "bullish"
        elif all_negative and streak >= self.streak_threshold:
            multiplier = self.dampen_multiplier
            direction = "bearish"
        else:
            multiplier = 1.0
            direction = "neutral"

        adjusted = max(-1.0, min(1.0, raw_score * multiplier))

        logger.debug(
            "SentimentMomentum: raw=%.3f streak=%d dir=%s → adjusted=%.3f",
            raw_score, streak, direction, adjusted,
        )

        return SentimentMomentumResult(
            raw_score=raw_score,
            adjusted_score=round(adjusted, 4),
            streak=streak,
            direction=direction,
            multiplier=multiplier,
        )


# Per-asset singleton tracker instances
_trackers: dict[str, SentimentMomentumFilter] = {}


def get_tracker(asset: str) -> SentimentMomentumFilter:
    """Return a per-asset :class:`SentimentMomentumFilter` singleton."""
    if asset not in _trackers:
        _trackers[asset] = SentimentMomentumFilter()
    return _trackers[asset]
