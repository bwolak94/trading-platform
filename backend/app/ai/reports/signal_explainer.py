"""Signal Explainer — uses Claude API to generate human-readable signal explanations.

Triggered when signal confidence > 70%. Produces a concise, professional
trading narrative that a human trader can understand and act on.
"""

from __future__ import annotations

import os
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

_ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
_MIN_CONFIDENCE_FOR_EXPLANATION = 70
_MODEL = "claude-haiku-4-5-20251001"  # Fast and cheap for signal explanations


async def generate_signal_explanation(signal: dict[str, Any]) -> str | None:
    """Generate a human-readable explanation for a high-confidence signal.

    Only runs when signal confidence >= 70% and ANTHROPIC_API_KEY is set.

    Args:
        signal: Signal dict with keys: symbol, action, confidence, regime,
                strategy_name, entry, stop_loss, tp_levels, conditions

    Returns:
        Natural language explanation string, or None if unavailable
    """
    confidence = signal.get("confidence", 0)
    if confidence < _MIN_CONFIDENCE_FOR_EXPLANATION:
        return None

    if not _ANTHROPIC_API_KEY:
        logger.debug("ANTHROPIC_API_KEY not set — skipping signal explanation")
        return None

    symbol = signal.get("symbol", signal.get("asset", "Unknown"))
    action = signal.get("action", signal.get("direction", "UNKNOWN"))
    regime = signal.get("regime", "UNKNOWN")
    strategy = signal.get("strategy_name", "unknown")
    entry = signal.get("entry", signal.get("entry_price", 0))
    sl = signal.get("stop_loss", 0)
    tp_levels = signal.get("tp_levels", [])
    conditions = signal.get("conditions", [])

    # Build conditions summary
    conditions_text = ""
    if conditions:
        cond_names = [c.get("name", "") for c in conditions[:5] if isinstance(c, dict)]
        conditions_text = f"\nKey factors: {', '.join(cond_names)}" if cond_names else ""

    prompt = f"""You are a professional crypto trading analyst. Generate a concise (2-3 sentences) \
explanation for this trading signal. Be direct, professional, and highlight the key reasons.

Signal: {action} {symbol}
Confidence: {confidence}%
Market Regime: {regime}
Strategy: {strategy}
Entry: ${entry:.4f} | Stop Loss: ${sl:.4f}
Take Profits: {', '.join(f'${tp:.4f}' for tp in tp_levels[:2]) if tp_levels else 'None'}{conditions_text}

Write a brief analysis explaining why this signal looks compelling. Mention the regime, \
key technical reasons, and what to watch for. Keep it under 60 words."""

    try:
        import httpx

        headers = {
            "x-api-key": _ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": _MODEL,
            "max_tokens": 150,
            "messages": [{"role": "user", "content": prompt}],
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            explanation = data["content"][0]["text"].strip()
            logger.info(
                "Signal explanation generated for %s %s (conf=%d%%)",
                symbol,
                action,
                confidence,
            )
            return explanation
    except Exception as exc:
        logger.warning("Signal explainer failed: %s", exc)
        return None
