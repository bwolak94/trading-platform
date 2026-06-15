"""Rich Telegram Signal Cards — formatted signal notifications with inline keyboards.

Generates visually rich Telegram messages using Unicode block characters
for confidence bars and emoji for directional indicators.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)

_DIRECTION_EMOJI = {"LONG": "🟢", "SHORT": "🔴", "NEUTRAL": "⚪"}
_CONFIDENCE_CHARS = "▱▱▱▱▱▱▱▱▱▱"
_FILLED_CHAR = "▰"


def _confidence_bar(confidence: float, length: int = 10) -> str:
    """Build a Unicode confidence bar.

    Args:
        confidence: Confidence value [0, 1]
        length: Bar length in characters

    Returns:
        Unicode progress bar string
    """
    filled = round(confidence * length)
    return _FILLED_CHAR * filled + "▱" * (length - filled)


def format_rich_signal_message(
    signal: dict[str, Any],
    playbook: dict[str, Any] | None = None,
) -> str:
    """Format a rich Telegram signal message.

    Args:
        signal: Signal dict with symbol, direction, confidence, strategy, etc.
        playbook: Optional playbook dict with entry/SL/TP details

    Returns:
        Formatted Telegram message string (MarkdownV2 compatible)
    """
    direction = signal.get("direction", "NEUTRAL").upper()
    symbol = signal.get("symbol", "UNKNOWN")
    strategy = signal.get("strategy", "unknown").replace("_", " ").title()
    confidence = float(signal.get("confidence", 0.5))
    regime = signal.get("regime", "UNKNOWN")
    confidence_pct = round(confidence * 100)
    bar = _confidence_bar(confidence)
    emoji = _DIRECTION_EMOJI.get(direction, "⚪")

    lines = [
        f"{emoji} *{direction} Signal* — `{symbol}`",
        f"📊 Confidence: `{bar}` {confidence_pct}%",
        f"📈 Strategy: {strategy}",
        f"⚡ Regime: `{regime}`",
    ]

    if playbook:
        entry = playbook.get("entry", {})
        sl = playbook.get("stop_loss", {})
        tps = playbook.get("take_profits", [])

        lines.append("")
        lines.append(f"📍 Entry: `{entry.get('price', '—')}`")
        lines.append(f"🛑 Stop: `{sl.get('price', '—')}` \\(\\-{sl.get('pct_from_entry', 0):.2f}%\\)")

        for tp in tps[:3]:
            lines.append(
                f"🎯 {tp['level']}: `{tp['price']}` \\(\\+{tp['pct_gain']:.2f}% · {tp['r_multiple']}R\\)"
            )

    elif signal.get("entry_price"):
        lines.append(f"📍 Entry: `{signal['entry_price']}`")
        if signal.get("stop_loss"):
            lines.append(f"🛑 Stop: `{signal['stop_loss']}`")
        if signal.get("take_profit"):
            lines.append(f"🎯 Target: `{signal['take_profit']}`")

    if signal.get("reasoning"):
        reasoning = str(signal["reasoning"])[:200]
        lines.append("")
        lines.append(f"💭 _{reasoning}_")

    return "\n".join(lines)


def get_signal_inline_keyboard() -> list[list[dict[str, str]]]:
    """Build Telegram inline keyboard markup for signal cards.

    Returns:
        List of button rows in Telegram InlineKeyboardMarkup format
    """
    return [
        [
            {"text": "✅ Trade", "callback_data": "signal:trade"},
            {"text": "⏭ Skip", "callback_data": "signal:skip"},
            {"text": "🔔 Alert", "callback_data": "signal:alert"},
        ],
        [
            {"text": "📊 Details", "callback_data": "signal:details"},
            {"text": "🤖 Explain", "callback_data": "signal:explain"},
        ],
    ]


async def send_rich_signal_notification(
    signal: dict[str, Any],
    bot_token: str,
    chat_id: str,
    playbook: dict[str, Any] | None = None,
) -> bool:
    """Send a rich signal notification via Telegram Bot API.

    Args:
        signal: Signal dict
        bot_token: Telegram bot API token
        chat_id: Target chat or channel ID
        playbook: Optional playbook dict

    Returns:
        True if message was sent successfully
    """
    if not bot_token or not chat_id:
        logger.warning("Rich signal notification skipped — missing bot_token or chat_id")
        return False

    text = format_rich_signal_message(signal, playbook)
    keyboard = get_signal_inline_keyboard()

    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "MarkdownV2",
        "reply_markup": {
            "inline_keyboard": keyboard,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json=payload,
            )
            resp.raise_for_status()
            logger.info("Rich signal notification sent for %s %s", signal.get("direction"), signal.get("symbol"))
            return True
    except Exception as exc:
        logger.error("Failed to send rich signal notification: %s", exc)
        return False
