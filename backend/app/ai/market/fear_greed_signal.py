"""Fear & Greed Contrarian Signal — extreme readings are high-probability reversals.

The Fear & Greed Index is a contrarian indicator: extreme fear (< 20) suggests
most participants are already out, creating a buying opportunity. Extreme greed
(> 80) suggests euphoria and a likely top.

Data source: alternative.me Fear & Greed API.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)

_CACHE: dict[str, Any] = {}
_CACHE_TTL = 3600  # 1 hour (index updates daily)

CONTRARIAN_ZONES: dict[str, dict[str, Any]] = {
    "extreme_fear": {"range": (0, 25), "signal": "BUY", "strength": "STRONG"},
    "fear": {"range": (25, 45), "signal": "BUY", "strength": "MODERATE"},
    "neutral": {"range": (45, 55), "signal": "NEUTRAL", "strength": "NONE"},
    "greed": {"range": (55, 75), "signal": "SELL", "strength": "MODERATE"},
    "extreme_greed": {"range": (75, 100), "signal": "SELL", "strength": "STRONG"},
}


def _classify_value(value: int) -> tuple[str, str, str]:
    """Classify an F&G value into zone, signal, and strength.

    Args:
        value: F&G index value 0-100

    Returns:
        Tuple of (zone_name, signal, strength)
    """
    for zone_name, zone_data in CONTRARIAN_ZONES.items():
        low, high = zone_data["range"]
        if low <= value <= high:
            return zone_name, zone_data["signal"], zone_data["strength"]
    return "neutral", "NEUTRAL", "NONE"


async def get_contrarian_signal() -> dict[str, Any]:
    """Fetch F&G index and return contrarian trading signal.

    Returns:
        {current_value, current_label, contrarian_signal, signal_strength,
         7d_trend, recommendation, history}
    """
    now = time.time()
    if _CACHE.get("data") and now - _CACHE.get("ts", 0) < _CACHE_TTL:
        return _CACHE["data"]

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://api.alternative.me/fng/",
                params={"limit": 7, "format": "json"},
            )
            resp.raise_for_status()
            data = resp.json()

        entries = data.get("data", [])
        if not entries:
            return _fallback_result()

        current = entries[0]
        current_value = int(current["value"])
        current_label = current.get("value_classification", "Unknown")

        # 7-day trend
        if len(entries) >= 7:
            week_ago_value = int(entries[-1]["value"])
            if current_value > week_ago_value + 5:
                trend = "IMPROVING"
            elif current_value < week_ago_value - 5:
                trend = "WORSENING"
            else:
                trend = "STABLE"
        else:
            trend = "STABLE"

        zone, signal, strength = _classify_value(current_value)

        if signal == "BUY" and strength == "STRONG":
            recommendation = f"🟢 STRONG BUY opportunity — market in extreme fear ({current_value}). Historical reversals likely."
        elif signal == "BUY":
            recommendation = f"Moderate buy opportunity — fear in market ({current_value}). Scale in cautiously."
        elif signal == "SELL" and strength == "STRONG":
            recommendation = f"🔴 REDUCE EXPOSURE — extreme greed ({current_value}). High probability of correction."
        elif signal == "SELL":
            recommendation = f"Take profits opportunity — greed building ({current_value}). Tighten stops."
        else:
            recommendation = f"Neutral zone ({current_value}). No contrarian edge, follow trend signals."

        history = [
            {"date": e.get("timestamp"), "value": int(e["value"]), "label": e.get("value_classification")}
            for e in entries
        ]

        result: dict[str, Any] = {
            "current_value": current_value,
            "current_label": current_label,
            "zone": zone,
            "contrarian_signal": signal,
            "signal_strength": strength,
            "7d_trend": trend,
            "recommendation": recommendation,
            "history_7d": history,
            "timestamp": int(now * 1000),
        }
        _CACHE["data"] = result
        _CACHE["ts"] = now
        return result

    except Exception as exc:
        logger.warning("Fear & Greed fetch failed: %s", exc)
        return _fallback_result(str(exc))


def _fallback_result(error: str | None = None) -> dict[str, Any]:
    """Return fallback result when API is unavailable.

    Args:
        error: Optional error message

    Returns:
        Neutral fallback result
    """
    result: dict[str, Any] = {
        "current_value": 50,
        "current_label": "Neutral",
        "zone": "neutral",
        "contrarian_signal": "NEUTRAL",
        "signal_strength": "NONE",
        "7d_trend": "STABLE",
        "recommendation": "Unable to fetch Fear & Greed data. Using neutral default.",
        "timestamp": int(time.time() * 1000),
    }
    if error:
        result["error"] = error
    return result
