"""Funding Rate Regime Detector — classifies market leverage conditions.

Persistent positive funding rates indicate overleveraged long positions
which are a contrarian bearish signal. Extreme negative funding suggests
overleveraged shorts and a potential squeeze opportunity.

Data source: Binance perpetual futures funding rate API.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)

_CACHE: dict[str, Any] = {}
_CACHE_TTL = 300  # 5 minutes

FUNDING_THRESHOLDS = {
    "extreme_long": 0.0005,
    "high_long": 0.0003,
    "neutral_upper": 0.0001,
    "neutral_lower": -0.0001,
    "high_short": -0.0003,
    "extreme_short": -0.0005,
}

_DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]


def _classify_funding(rate: float) -> str:
    """Classify a funding rate into a regime label.

    Args:
        rate: Funding rate decimal (e.g. 0.0003 = 0.03%)

    Returns:
        Regime label string
    """
    if rate > FUNDING_THRESHOLDS["extreme_long"]:
        return "EXTREME_LONG"
    if rate > FUNDING_THRESHOLDS["high_long"]:
        return "HIGH_LONG"
    if rate > FUNDING_THRESHOLDS["neutral_upper"]:
        return "MILD_LONG"
    if rate > FUNDING_THRESHOLDS["neutral_lower"]:
        return "NEUTRAL"
    if rate > FUNDING_THRESHOLDS["high_short"]:
        return "MILD_SHORT"
    if rate > FUNDING_THRESHOLDS["extreme_short"]:
        return "HIGH_SHORT"
    return "EXTREME_SHORT"


async def get_funding_regime(symbols: list[str] | None = None) -> dict[str, Any]:
    """Fetch funding rates for symbols and classify leverage regime.

    Args:
        symbols: List of Binance futures symbols (defaults to major pairs)

    Returns:
        {rates, market_bias, contrarian_signal, avg_funding_rate}
    """
    now = time.time()
    if _CACHE.get("data") and now - _CACHE.get("ts", 0) < _CACHE_TTL:
        return _CACHE["data"]

    target_symbols = symbols or _DEFAULT_SYMBOLS
    rates: list[dict[str, Any]] = []

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get("https://fapi.binance.com/fapi/v1/premiumIndex")
            resp.raise_for_status()
            all_rates = resp.json()

        rate_map = {item["symbol"]: float(item.get("lastFundingRate", 0)) for item in all_rates}

        for sym in target_symbols:
            rate = rate_map.get(sym, 0.0)
            rates.append({
                "symbol": sym,
                "funding_rate": rate,
                "funding_rate_pct": round(rate * 100, 4),
                "regime": _classify_funding(rate),
                "annualized_pct": round(rate * 3 * 365 * 100, 2),  # 3x daily * 365
            })

        avg_rate = sum(r["funding_rate"] for r in rates) / len(rates) if rates else 0.0
        market_bias = _classify_funding(avg_rate)

        if market_bias in ("EXTREME_LONG", "HIGH_LONG"):
            contrarian = "FADE_LONGS"
        elif market_bias in ("EXTREME_SHORT", "HIGH_SHORT"):
            contrarian = "FADE_SHORTS"
        else:
            contrarian = "NEUTRAL"

        result: dict[str, Any] = {
            "rates": rates,
            "market_bias": market_bias,
            "contrarian_signal": contrarian,
            "avg_funding_rate": round(avg_rate, 6),
            "avg_funding_rate_pct": round(avg_rate * 100, 4),
            "timestamp": int(now * 1000),
        }
        _CACHE["data"] = result
        _CACHE["ts"] = now
        return result

    except Exception as exc:
        logger.warning("Funding regime fetch failed: %s", exc)
        return {
            "rates": [],
            "market_bias": "NEUTRAL",
            "contrarian_signal": "NEUTRAL",
            "avg_funding_rate": 0.0,
            "error": str(exc),
            "timestamp": int(now * 1000),
        }


async def get_funding_alert(symbol: str) -> dict[str, Any]:
    """Get funding rate alert and trading recommendation for a specific symbol.

    Args:
        symbol: Binance futures symbol (e.g. BTCUSDT)

    Returns:
        {symbol, funding_rate, regime, alert, recommendation}
    """
    regime_data = await get_funding_regime([symbol])
    rates = regime_data.get("rates", [])
    rate_info = next((r for r in rates if r["symbol"] == symbol), None)

    if not rate_info:
        return {"symbol": symbol, "alert": "No data available", "regime": "UNKNOWN"}

    regime = rate_info["regime"]
    alert: str | None = None
    recommendation = "No action required"

    if regime == "EXTREME_LONG":
        alert = f"⚠️ EXTREME LONG FUNDING: {rate_info['funding_rate_pct']:.4f}% — longs paying heavily"
        recommendation = "Consider short bias or avoid new longs. High probability of long squeeze."
    elif regime == "HIGH_LONG":
        alert = f"Elevated long funding: {rate_info['funding_rate_pct']:.4f}% — market overleveraged long"
        recommendation = "Reduce long exposure, tighten stops on longs."
    elif regime == "EXTREME_SHORT":
        alert = f"⚠️ EXTREME SHORT FUNDING: {rate_info['funding_rate_pct']:.4f}% — shorts paying heavily"
        recommendation = "Consider long bias. High probability of short squeeze."

    return {**rate_info, "alert": alert, "recommendation": recommendation}
