"""Webhook settings API — configure outbound webhook for signal delivery."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/webhook", tags=["webhook"])


class WebhookConfig(BaseModel):
    """Schema for webhook configuration."""
    url: str | None = None
    secret: str | None = None


@router.get("/")
async def get_webhook_config() -> dict:
    """Return current webhook configuration (URL only, not secret)."""
    from app.notifications.webhook_sender import _webhook_url
    return {
        "url": _webhook_url,
        "configured": _webhook_url is not None,
    }


@router.post("/")
async def set_webhook_config(body: WebhookConfig) -> dict:
    """Configure webhook URL and optional secret."""
    from app.notifications.webhook_sender import configure_webhook
    configure_webhook(url=body.url, secret=body.secret)
    return {"status": "configured", "url": body.url, "has_secret": body.secret is not None}


@router.post("/test")
async def test_webhook() -> dict:
    """Send a test payload to the configured webhook URL."""
    from app.notifications.webhook_sender import send_webhook
    test_payload = {
        "type": "TEST",
        "message": "AI Trading Navigator webhook test",
        "timestamp": __import__("datetime").datetime.utcnow().isoformat(),
    }
    success = await send_webhook(test_payload)
    return {"success": success, "payload": test_payload}
