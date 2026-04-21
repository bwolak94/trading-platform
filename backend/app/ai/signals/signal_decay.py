"""Signal Decay Manager — TTL-based signal expiry driven by volatility.

High-volatility environments require faster signal expiry since market
conditions change rapidly. Low-volatility environments allow signals
to remain valid for longer periods.

TTL tiers:
- High vol (ATR% > 3%): 15 minutes
- Medium vol (ATR% 1-3%): 1 hour
- Low vol (ATR% < 1%): 4 hours
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)


class SignalDecayManager:
    """Manages signal TTL based on volatility and timeframe context."""

    # TTL in seconds per volatility tier
    _HIGH_VOL_TTL = 900     # 15 minutes
    _MEDIUM_VOL_TTL = 3600  # 1 hour
    _LOW_VOL_TTL = 14400    # 4 hours

    # Interval-based base multipliers
    _INTERVAL_MULTIPLIERS: dict[str, float] = {
        "1m": 0.25,
        "5m": 0.5,
        "15m": 1.0,
        "1h": 2.0,
        "4h": 4.0,
        "1d": 12.0,
    }

    def compute_ttl(self, symbol: str, atr_pct: float, interval: str) -> int:
        """Compute signal TTL in seconds based on volatility and timeframe.

        Args:
            symbol: Trading pair (for logging)
            atr_pct: ATR as percentage of price (ATR/close * 100)
            interval: Kline interval string

        Returns:
            TTL in seconds
        """
        if atr_pct > 3.0:
            base_ttl = self._HIGH_VOL_TTL
            tier = "HIGH"
        elif atr_pct > 1.0:
            base_ttl = self._MEDIUM_VOL_TTL
            tier = "MEDIUM"
        else:
            base_ttl = self._LOW_VOL_TTL
            tier = "LOW"

        multiplier = self._INTERVAL_MULTIPLIERS.get(interval, 1.0)
        ttl = int(base_ttl * multiplier)

        logger.debug(
            "Signal TTL | %s atr_pct=%.2f%% interval=%s tier=%s ttl=%ds",
            symbol, atr_pct, interval, tier, ttl,
        )
        return ttl

    def is_signal_expired(
        self,
        signal_id: str,
        created_at: datetime,
        atr_pct: float,
        interval: str,
    ) -> bool:
        """Check if a signal has expired based on its age vs computed TTL.

        Args:
            signal_id: Signal identifier (for logging)
            created_at: Signal creation timestamp (timezone-aware)
            atr_pct: ATR percentage at time of signal
            interval: Signal timeframe

        Returns:
            True if signal is expired
        """
        ttl = self.compute_ttl(signal_id, atr_pct, interval)
        now = datetime.now(timezone.utc)
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        elapsed = (now - created_at).total_seconds()
        expired = elapsed > ttl
        if expired:
            logger.debug("Signal %s expired (elapsed=%.0fs ttl=%ds)", signal_id, elapsed, ttl)
        return expired

    def get_decay_info(self, created_at: datetime, ttl_seconds: int) -> dict[str, Any]:
        """Compute decay metadata for a signal.

        Args:
            created_at: Signal creation timestamp
            ttl_seconds: Signal TTL in seconds

        Returns:
            {ttl_seconds, elapsed_seconds, remaining_seconds, decay_pct, is_expired}
        """
        now = datetime.now(timezone.utc)
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)

        elapsed = max(0.0, (now - created_at).total_seconds())
        remaining = max(0.0, ttl_seconds - elapsed)
        decay_pct = min(100.0, round(elapsed / ttl_seconds * 100, 1)) if ttl_seconds > 0 else 100.0

        return {
            "ttl_seconds": ttl_seconds,
            "elapsed_seconds": round(elapsed),
            "remaining_seconds": round(remaining),
            "decay_pct": decay_pct,
            "is_expired": elapsed >= ttl_seconds,
        }


# Module-level singleton
_decay_manager: SignalDecayManager | None = None


def get_decay_manager() -> SignalDecayManager:
    """Return the global SignalDecayManager singleton.

    Returns:
        Shared SignalDecayManager instance
    """
    global _decay_manager
    if _decay_manager is None:
        _decay_manager = SignalDecayManager()
    return _decay_manager
