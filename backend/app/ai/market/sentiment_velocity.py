"""Sentiment Velocity Tracker — detects sudden sentiment spikes as exit triggers.

Rate of change of sentiment is often more predictive than the absolute level.
A rapid deterioration in sentiment (e.g., -0.3 per hour) often precedes
price drops and should trigger position review or exit alerts.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)


class SentimentVelocityTracker:
    """Tracks sentiment history and computes rate of change per symbol."""

    def __init__(self, window_size: int = 20) -> None:
        """Initialize the tracker.

        Args:
            window_size: Maximum sentiment readings to keep per symbol
        """
        self._history: dict[str, deque[dict[str, Any]]] = {}
        self._window_size = window_size

    def record_sentiment(self, symbol: str, score: float) -> None:
        """Record a new sentiment reading for a symbol.

        Args:
            symbol: Asset symbol (e.g. BTC, BTCUSDT)
            score: Sentiment score in range [-1.0, 1.0]
        """
        if symbol not in self._history:
            self._history[symbol] = deque(maxlen=self._window_size)

        self._history[symbol].append({
            "score": max(-1.0, min(1.0, score)),
            "timestamp": datetime.now(timezone.utc),
        })

    def compute_velocity(self, symbol: str, periods: int = 5) -> dict[str, Any]:
        """Compute sentiment velocity (change per hour) for a symbol.

        Args:
            symbol: Asset symbol
            periods: Number of recent readings to compute velocity from

        Returns:
            {symbol, current_score, velocity, velocity_direction,
             is_spike, spike_severity, alert}
        """
        history = self._history.get(symbol)
        if not history or len(history) < 2:
            return {
                "symbol": symbol,
                "current_score": 0.0,
                "velocity": 0.0,
                "velocity_direction": "STABLE",
                "is_spike": False,
                "spike_severity": "NONE",
                "alert": None,
            }

        readings = list(history)[-min(periods + 1, len(history)):]
        current_score = readings[-1]["score"]

        # Compute velocity as change per hour
        oldest = readings[0]
        newest = readings[-1]
        time_delta_hours = max(
            0.01,
            (newest["timestamp"] - oldest["timestamp"]).total_seconds() / 3600,
        )
        velocity = round((newest["score"] - oldest["score"]) / time_delta_hours, 4)

        if velocity > 0.05:
            direction = "IMPROVING"
        elif velocity < -0.05:
            direction = "WORSENING"
        else:
            direction = "STABLE"

        # Spike detection
        is_spike = abs(velocity) > 0.20
        if abs(velocity) > 0.40:
            severity = "SEVERE"
        elif abs(velocity) > 0.20:
            severity = "MODERATE"
        else:
            severity = "NONE"

        alert: str | None = None
        if severity == "SEVERE" and velocity < 0:
            alert = f"🚨 SEVERE sentiment deterioration for {symbol}: velocity={velocity:.3f}/h — consider exiting positions"
        elif severity == "MODERATE" and velocity < 0:
            alert = f"⚠️ Moderate negative sentiment spike for {symbol}: velocity={velocity:.3f}/h"
        elif severity != "NONE" and velocity > 0:
            alert = f"✅ Positive sentiment spike for {symbol}: velocity={velocity:.3f}/h — bullish signal"

        return {
            "symbol": symbol,
            "current_score": round(current_score, 4),
            "velocity_per_hour": velocity,
            "velocity_direction": direction,
            "is_spike": is_spike,
            "spike_severity": severity,
            "readings_used": len(readings),
            "time_window_hours": round(time_delta_hours, 2),
            "alert": alert,
        }

    def get_all_velocities(self) -> list[dict[str, Any]]:
        """Return velocity data for all tracked symbols.

        Returns:
            List of velocity dicts for each symbol
        """
        return [self.compute_velocity(sym) for sym in self._history]


# Module-level singleton
_tracker: SentimentVelocityTracker | None = None


def get_sentiment_tracker() -> SentimentVelocityTracker:
    """Return the global SentimentVelocityTracker singleton.

    Returns:
        Shared tracker instance
    """
    global _tracker
    if _tracker is None:
        _tracker = SentimentVelocityTracker()
    return _tracker
