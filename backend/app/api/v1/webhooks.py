"""TradingView inbound webhook endpoint."""

import hashlib
import hmac
import json
import logging
import os
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
logger = logging.getLogger(__name__)

TV_WEBHOOK_SECRET = os.environ.get("TV_WEBHOOK_SECRET", "")


@router.post("/tradingview")
async def tradingview_webhook(
    request: Request,
    x_tv_signature: Optional[str] = Header(None),
) -> dict:
    """Receive TradingView alert webhooks.

    Expected JSON body:
    {
        "symbol": "BTCUSDT",
        "action": "BUY" | "SELL",
        "price": 50000.0,
        "message": "RSI oversold signal",
        "strategy_name": "TV_RSI_Strategy",
        "confidence": 75  (optional, 0-100 scale)
    }

    Validates HMAC-SHA256 signature when TV_WEBHOOK_SECRET env var is set,
    broadcasts the signal over WebSocket, and sends a Telegram notification.
    """
    body = await request.body()

    # Validate signature if secret is configured
    if TV_WEBHOOK_SECRET:
        if not x_tv_signature:
            raise HTTPException(status_code=401, detail="Missing signature")
        expected = hmac.new(TV_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(x_tv_signature, expected):
            raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        data = json.loads(body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    symbol: str = data.get("symbol", "").upper()
    action: str = data.get("action", "").upper()
    price: float = float(data.get("price", 0))
    message: str = data.get("message", "TradingView alert")
    strategy_name: str = data.get("strategy_name", "TradingView")
    confidence: float = float(data.get("confidence", 70)) / 100

    if not symbol or action not in ("BUY", "SELL"):
        raise HTTPException(status_code=400, detail="Missing symbol or invalid action")

    signal = {
        "type": "SIGNAL",
        "symbol": symbol,
        "direction": "LONG" if action == "BUY" else "SHORT",
        "confidence": confidence,
        "strategy": strategy_name,
        "price": price,
        "factors": [f"TradingView: {message}"],
        "source": "tradingview_webhook",
    }

    logger.info("TradingView webhook received: %s %s @ %s", symbol, action, price)

    # Broadcast via WebSocket to the "signals" channel
    try:
        from app.core.websocket import manager
        await manager.broadcast("signals", signal)
    except Exception as exc:
        logger.warning("WebSocket broadcast failed: %s", exc)

    # Send Telegram notification
    try:
        from app.notifications.telegram_bot import get_telegram_bot
        bot = get_telegram_bot()
        if bot:
            direction_emoji = "\U0001f7e2" if action == "BUY" else "\U0001f534"
            msg = (
                f"{direction_emoji} *TradingView Alert*\n"
                f"{symbol} {action} @ ${price:,.2f}\n"
                f"_{message}_"
            )
            await bot.send_message(msg)
    except Exception as exc:
        logger.warning("Telegram notification failed: %s", exc)

    return {"status": "received", "symbol": symbol, "action": action}
