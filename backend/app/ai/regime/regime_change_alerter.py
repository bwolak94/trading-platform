"""Regime Change Alerter — fires alerts when market regime transitions.

Monitors regime classifications and detects when regime changes.
Sends Telegram notification + WebSocket broadcast on regime change.

Usage:
    alerter = RegimeChangeAlerter()
    await alerter.check_and_alert(symbol="BTCUSDT", new_regime="TRENDING_BULL", confidence=0.85)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)


class RegimeChangeAlerter:
    """Tracks regime per symbol and fires alerts on transitions."""

    def __init__(self) -> None:
        self._last_regimes: dict[str, str] = {}
        self._change_history: list[dict[str, Any]] = []

    async def check_and_alert(
        self,
        symbol: str,
        new_regime: str,
        confidence: float = 0.0,
    ) -> bool:
        """Check if regime changed for a symbol and fire alerts.

        Args:
            symbol: Asset symbol (e.g. "BTCUSDT")
            new_regime: The new regime classification
            confidence: Classifier confidence (0-1)

        Returns:
            True if regime changed, False otherwise
        """
        prev_regime = self._last_regimes.get(symbol)

        if prev_regime is None:
            # First observation — just record it
            self._last_regimes[symbol] = new_regime
            return False

        if prev_regime == new_regime:
            return False

        # Regime changed!
        self._last_regimes[symbol] = new_regime
        change_event = {
            "symbol": symbol,
            "from_regime": prev_regime,
            "to_regime": new_regime,
            "confidence": round(confidence, 3),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._change_history.append(change_event)
        # Keep last 100 changes
        if len(self._change_history) > 100:
            self._change_history = self._change_history[-100:]

        logger.info(
            "REGIME CHANGE | %s: %s → %s (conf=%.0f%%)",
            symbol, prev_regime, new_regime, confidence * 100,
        )

        await self._send_telegram_alert(change_event)
        await self._broadcast_websocket(change_event)
        return True

    async def _send_telegram_alert(self, event: dict[str, Any]) -> None:
        """Send a Telegram notification about the regime change."""
        try:
            from app.notifications.telegram_bot import get_telegram_bot
            bot = get_telegram_bot()
            msg = (
                f"🔄 *Regime Change Alert*\n"
                f"Symbol: `{event['symbol']}`\n"
                f"{event['from_regime']} → *{event['to_regime']}*\n"
                f"Confidence: {event['confidence'] * 100:.0f}%"
            )
            await bot.send_message(msg)
        except Exception as exc:
            logger.debug("Regime change Telegram alert failed: %s", exc)

    async def _broadcast_websocket(self, event: dict[str, Any]) -> None:
        """Broadcast regime change event to WebSocket subscribers."""
        try:
            from app.core.websocket import manager
            await manager.broadcast(
                {"type": "REGIME_CHANGE", "event": event},
                channel="regime",
            )
        except Exception as exc:
            logger.debug("Regime change WebSocket broadcast failed: %s", exc)

    def get_recent_changes(self, limit: int = 10) -> list[dict[str, Any]]:
        """Return the most recent regime change events."""
        return list(reversed(self._change_history[-limit:]))

    def get_current_regimes(self) -> dict[str, str]:
        """Return current regime for all tracked symbols."""
        return dict(self._last_regimes)


# Module-level singleton
_alerter: RegimeChangeAlerter | None = None


def get_regime_change_alerter() -> RegimeChangeAlerter:
    """Return the global RegimeChangeAlerter singleton."""
    global _alerter
    if _alerter is None:
        _alerter = RegimeChangeAlerter()
    return _alerter
