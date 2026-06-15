"""Webhook Dispatcher — push signals to external services.

Supports multiple webhook targets with customizable payload transforms for:
- TradingView alerts
- 3Commas bot triggers
- Notion database entries
- Custom HTTP endpoints

Each dispatch is logged with response status for debugging.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)

# Payload transform functions per target type
PAYLOAD_TEMPLATES: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "tradingview": lambda s: {
        "action": s.get("direction", "").lower(),
        "ticker": s.get("symbol", ""),
        "price": s.get("entry_price", 0),
        "confidence": s.get("confidence", 0),
        "strategy": s.get("strategy", ""),
    },
    "3commas": lambda s: {
        "message_type": "bot",
        "action": "CLOSE_AT_MARKET_PRICE" if s.get("direction") == "EXIT" else "OPEN_POSITION",
        "base_order_volume": 1.0,
        "delay_seconds": 0,
    },
    "default": lambda s: {
        "symbol": s.get("symbol"),
        "direction": s.get("direction"),
        "confidence": s.get("confidence"),
        "strategy": s.get("strategy"),
        "entry_price": s.get("entry_price"),
        "stop_loss": s.get("stop_loss"),
        "take_profit": s.get("take_profit"),
        "regime": s.get("regime"),
        "timestamp": int(time.time() * 1000),
    },
}


@dataclass
class WebhookTarget:
    """Represents a single webhook dispatch target."""

    name: str
    url: str
    method: str = "POST"
    headers: dict[str, str] = field(default_factory=dict)
    transform: str = "default"
    active: bool = True


class WebhookDispatcher:
    """Dispatches signal notifications to registered webhook targets."""

    def __init__(self) -> None:
        """Initialize with an empty target list."""
        self._targets: list[WebhookTarget] = []

    def add_target(self, target: WebhookTarget) -> None:
        """Register a new webhook target.

        Args:
            target: WebhookTarget to add
        """
        self._targets = [t for t in self._targets if t.name != target.name]
        self._targets.append(target)
        logger.info("WebhookDispatcher | Target added: %s → %s", target.name, target.url)

    def remove_target(self, name: str) -> bool:
        """Remove a webhook target by name.

        Args:
            name: Target name

        Returns:
            True if target was found and removed
        """
        before = len(self._targets)
        self._targets = [t for t in self._targets if t.name != name]
        return len(self._targets) < before

    def get_targets(self) -> list[dict[str, Any]]:
        """Return all targets as serializable dicts.

        Returns:
            List of target dicts (URL masked for security)
        """
        return [
            {
                "name": t.name,
                "url": t.url[:20] + "..." if len(t.url) > 20 else t.url,
                "method": t.method,
                "transform": t.transform,
                "active": t.active,
            }
            for t in self._targets
        ]

    async def dispatch_signal(self, signal: dict[str, Any]) -> list[dict[str, Any]]:
        """Send a signal to all active registered webhook targets.

        Args:
            signal: Signal dict to dispatch

        Returns:
            List of dispatch results: [{target, success, status_code, error}]
        """
        results: list[dict[str, Any]] = []

        for target in self._targets:
            if not target.active:
                continue

            transform_fn = PAYLOAD_TEMPLATES.get(target.transform, PAYLOAD_TEMPLATES["default"])
            payload = transform_fn(signal)

            result = await self._send(target, payload)
            results.append(result)

        return results

    async def test_webhook(self, target: WebhookTarget) -> dict[str, Any]:
        """Send a test payload to verify webhook connectivity.

        Args:
            target: Target to test

        Returns:
            {success, response_time_ms, status_code, error}
        """
        test_signal = {
            "symbol": "BTCUSDT",
            "direction": "LONG",
            "confidence": 0.75,
            "strategy": "test",
            "entry_price": 50000.0,
            "stop_loss": 49000.0,
            "take_profit": 52000.0,
            "regime": "TREND_BULL",
        }
        transform_fn = PAYLOAD_TEMPLATES.get(target.transform, PAYLOAD_TEMPLATES["default"])
        payload = {**transform_fn(test_signal), "_test": True}
        return await self._send(target, payload)

    async def _send(self, target: WebhookTarget, payload: dict[str, Any]) -> dict[str, Any]:
        """Execute a single HTTP webhook request.

        Args:
            target: Webhook target configuration
            payload: Request payload

        Returns:
            Result dict with success status and timing
        """
        start = time.time()
        try:
            headers = {"Content-Type": "application/json", **target.headers}
            async with httpx.AsyncClient(timeout=10.0) as client:
                if target.method.upper() == "POST":
                    resp = await client.post(target.url, json=payload, headers=headers)
                else:
                    resp = await client.get(target.url, params=payload, headers=headers)

            duration_ms = round((time.time() - start) * 1000)
            success = resp.status_code < 400
            if not success:
                logger.warning("Webhook failed: %s status=%d", target.name, resp.status_code)

            return {
                "target": target.name,
                "success": success,
                "status_code": resp.status_code,
                "response_time_ms": duration_ms,
                "error": None,
            }
        except Exception as exc:
            duration_ms = round((time.time() - start) * 1000)
            logger.error("Webhook error for %s: %s", target.name, exc)
            return {
                "target": target.name,
                "success": False,
                "status_code": None,
                "response_time_ms": duration_ms,
                "error": str(exc),
            }


# Module-level singleton
_dispatcher: WebhookDispatcher | None = None


def get_webhook_dispatcher() -> WebhookDispatcher:
    """Return the global WebhookDispatcher singleton.

    Returns:
        Shared WebhookDispatcher instance
    """
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = WebhookDispatcher()
    return _dispatcher
