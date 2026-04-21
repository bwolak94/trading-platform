"""Discord Bot — sends trading signals and alerts to a Discord channel.

Uses Discord webhook POST (no bot token required). Configure via environment:
  DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...

Mirrors all Telegram signals to Discord automatically.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")

# Color constants (Discord embed colors)
_COLOR_LONG = 0x4ADE80    # green
_COLOR_SHORT = 0xF87171   # red
_COLOR_NEUTRAL = 0x94A3B8 # gray
_COLOR_ALERT = 0xFBBF24   # yellow


def _direction_color(direction: str) -> int:
    """Map trade direction to Discord embed color."""
    direction = direction.upper()
    if direction in ("LONG", "BUY"):
        return _COLOR_LONG
    if direction in ("SHORT", "SELL"):
        return _COLOR_SHORT
    return _COLOR_NEUTRAL


async def send_signal_to_discord(signal: dict[str, Any]) -> bool:
    """Send a trading signal as a Discord embed.

    Args:
        signal: Dict with symbol, action/direction, confidence, entry_price,
                stop_loss, tp_levels, strategy_name, regime

    Returns:
        True on success, False on failure
    """
    if not DISCORD_WEBHOOK_URL:
        return False

    symbol = signal.get("symbol", signal.get("asset", "Unknown"))
    direction = signal.get("action", signal.get("direction", "UNKNOWN"))
    confidence = signal.get("confidence", 0)
    entry = signal.get("entry", signal.get("entry_price", 0))
    sl = signal.get("stop_loss", 0)
    tp_levels = signal.get("tp_levels", [])
    strategy = signal.get("strategy_name", "unknown")
    regime = signal.get("regime", "UNKNOWN")

    tp_text = " / ".join(f"${tp:.4f}" for tp in tp_levels[:3]) if tp_levels else "—"
    direction_emoji = "🟢" if direction == "LONG" else "🔴"

    embed = {
        "title": f"{direction_emoji} {direction} Signal — {symbol}",
        "color": _direction_color(direction),
        "fields": [
            {"name": "Confidence", "value": f"{confidence}%", "inline": True},
            {"name": "Strategy", "value": strategy, "inline": True},
            {"name": "Regime", "value": regime, "inline": True},
            {"name": "Entry", "value": f"${entry:.4f}", "inline": True},
            {"name": "Stop Loss", "value": f"${sl:.4f}", "inline": True},
            {"name": "Take Profits", "value": tp_text, "inline": True},
        ],
        "footer": {"text": "AI Trading Navigator"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    return await _post_embed(embed)


async def send_alert_to_discord(title: str, message: str, level: str = "info") -> bool:
    """Send a general alert/notification to Discord.

    Args:
        title: Alert title
        message: Alert message
        level: "info", "warning", "error"

    Returns:
        True on success
    """
    if not DISCORD_WEBHOOK_URL:
        return False

    color = _COLOR_ALERT if level == "warning" else (0xEF4444 if level == "error" else _COLOR_NEUTRAL)
    embed = {
        "title": title,
        "description": message,
        "color": color,
        "footer": {"text": "AI Trading Navigator"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return await _post_embed(embed)


async def _post_embed(embed: dict[str, Any]) -> bool:
    """POST an embed payload to the Discord webhook."""
    if not DISCORD_WEBHOOK_URL:
        return False
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                DISCORD_WEBHOOK_URL,
                json={"embeds": [embed]},
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            logger.info("Discord notification sent: %s", embed.get("title", ""))
            return True
    except Exception as exc:
        logger.warning("Discord notification failed: %s", exc)
        return False
