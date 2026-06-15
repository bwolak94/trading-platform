"""TradingView inbound webhook endpoint."""

import hashlib
import hmac
import json
import logging
import os
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db

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

    # Send Telegram notification asynchronously via Celery
    try:
        from app.tasks import send_telegram_message
        direction_emoji = "\U0001f7e2" if action == "BUY" else "\U0001f534"
        msg = (
            f"{direction_emoji} *TradingView Alert*\n"
            f"{symbol} {action} @ ${price:,.2f}\n"
            f"_{message}_"
        )
        send_telegram_message.delay(msg)
    except Exception as exc:
        logger.warning("Telegram task dispatch failed: %s", exc)

    return {"status": "received", "symbol": symbol, "action": action}


@router.post("/tradingview/pine")
async def receive_tradingview_pine_alert(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Parse TradingView Pine Script alert and persist as a Signal.

    Expected JSON payload from a Pine Script alertcondition():
    {
        "ticker":     "BTCUSDT",
        "action":     "buy" | "sell" | "close",
        "price":      45000.0,
        "strategy":   "custom_strategy_name",
        "message":    "Optional message",
        "timeframe":  "1h",
        "confidence": 75    (optional, default 70)
    }

    - "buy"   → LONG signal created in DB
    - "sell"  → SHORT signal created in DB
    - "close" → skipped (no DB write, returns status: skipped)

    Returns:
        {"signal_id": str, "status": "created"}  on success
        {"status": "skipped", "reason": str}      when action is "close" or unrecognised
    """

    from app.models.signal import Signal

    try:
        body: dict[str, Any] = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    ticker: str = str(body.get("ticker", "BTCUSDT")).upper()
    action: str = str(body.get("action", "")).lower()

    if action not in ("buy", "sell"):
        return {
            "status": "skipped",
            "reason": f"action '{action}' is not buy/sell — no signal created",
        }

    direction = "LONG" if action == "buy" else "SHORT"
    price = float(body.get("price", 0))
    confidence = min(100, max(0, int(body.get("confidence", 70))))
    strategy = str(body.get("strategy", "tradingview_pine"))
    timeframe = str(body.get("timeframe", "1h"))
    message = str(body.get("message", ""))

    # Basic SL/TP: 2% SL, 4%/8% TP for LONG; reversed for SHORT
    sl_pct = 0.02
    tp_pct = 0.04

    if direction == "LONG":
        stop_loss = price * (1 - sl_pct) if price > 0 else 0.0
        tp1 = price * (1 + tp_pct) if price > 0 else 0.0
        tp2 = price * (1 + tp_pct * 2) if price > 0 else 0.0
    else:
        stop_loss = price * (1 + sl_pct) if price > 0 else 0.0
        tp1 = price * (1 - tp_pct) if price > 0 else 0.0
        tp2 = price * (1 - tp_pct * 2) if price > 0 else 0.0

    # Risk/reward = tp_pct / sl_pct
    risk_reward = tp_pct / sl_pct  # = 2.0

    factors: list[dict[str, Any]] = [
        {
            "name": "TradingView Pine Alert",
            "weight": 1.0,
            "label": "BULLISH" if direction == "LONG" else "BEARISH",
            "timeframe": timeframe,
        }
    ]
    if message:
        factors.append({"name": message, "weight": 0.5, "label": "INFO"})

    sig = Signal(
        asset=ticker,
        direction=direction,
        confidence=confidence,
        regime="UNKNOWN",
        entry_price=price if price > 0 else None,
        stop_loss=stop_loss if stop_loss > 0 else None,
        take_profit_1=tp1 if tp1 > 0 else None,
        take_profit_2=tp2 if tp2 > 0 else None,
        risk_reward=risk_reward,
        factors=factors,
        status="ACTIVE",
    )

    db.add(sig)
    await db.flush()  # assigns the UUID
    signal_id = str(sig.id)
    await db.commit()

    logger.info(
        "TradingView Pine alert → Signal %s created: %s %s @ %.4f (tf=%s)",
        signal_id,
        direction,
        ticker,
        price,
        timeframe,
    )

    # Broadcast via WebSocket
    try:
        from app.core.websocket import manager

        await manager.broadcast(
            "signals",
            {
                "type": "SIGNAL",
                "signal_id": signal_id,
                "asset": ticker,
                "direction": direction,
                "confidence": confidence,
                "strategy": strategy,
                "price": price,
                "source": "tradingview_pine",
            },
        )
    except Exception as ws_exc:
        logger.warning("WebSocket broadcast failed: %s", ws_exc)

    # Send Telegram notification asynchronously via Celery
    try:
        from app.tasks import send_telegram_message
        icon = "\U0001f7e2" if direction == "LONG" else "\U0001f534"
        text = (
            f"{icon} <b>TV Pine Signal: {ticker} {direction}</b>\n"
            f"Confidence: {confidence}% | Strategy: {strategy}\n"
            f"Entry: ${price:,.4f} | SL: ${stop_loss:,.4f} | TP1: ${tp1:,.4f}"
        )
        send_telegram_message.delay(text)
    except Exception as tg_exc:
        logger.warning("Telegram task dispatch failed: %s", tg_exc)

    return {"signal_id": signal_id, "status": "created"}
