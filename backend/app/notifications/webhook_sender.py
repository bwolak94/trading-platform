"""Outbound webhook sender — POST signal JSON to user-configured URLs.

Features:
- Configurable webhook URL with optional secret header
- Retry up to 3 times on failure (exponential backoff)
- Non-blocking — runs as a fire-and-forget background task
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)

# In-memory webhook configuration (loaded from settings at startup)
_webhook_url: str | None = None
_webhook_secret: str | None = None


def configure_webhook(url: str | None, secret: str | None = None) -> None:
    """Configure the webhook URL and optional secret header."""
    global _webhook_url, _webhook_secret
    _webhook_url = url or None
    _webhook_secret = secret or None
    if url:
        logger.info("Webhook configured: %s", url[:50])
    else:
        logger.info("Webhook disabled")


async def send_webhook(payload: dict[str, Any]) -> bool:
    """Send a JSON payload to the configured webhook URL.

    Args:
        payload: JSON-serializable dict to POST

    Returns:
        True if delivery succeeded, False if all retries failed
    """
    if not _webhook_url:
        return False

    headers = {"Content-Type": "application/json"}
    if _webhook_secret:
        headers["X-Webhook-Secret"] = _webhook_secret

    for attempt in range(1, 4):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(_webhook_url, json=payload, headers=headers)
                resp.raise_for_status()
                logger.info("Webhook delivered (attempt %d): status %d", attempt, resp.status_code)
                return True
        except Exception as exc:
            logger.warning("Webhook attempt %d failed: %s", attempt, exc)
            if attempt < 3:
                await asyncio.sleep(2 ** attempt)  # 2s, 4s

    logger.error("Webhook delivery failed after 3 attempts for URL: %s", _webhook_url[:50] if _webhook_url else "N/A")
    return False


def fire_and_forget_webhook(payload: dict[str, Any]) -> None:
    """Schedule webhook delivery as a background task (non-blocking)."""
    if not _webhook_url:
        return
    try:
        loop = asyncio.get_event_loop()
        loop.create_task(send_webhook(payload))
    except RuntimeError:
        pass  # No event loop running
