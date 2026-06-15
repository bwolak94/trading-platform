"""BTC Dominance Regime Signal — classifies market rotation between BTC and altcoins.

Rising BTC dominance signals risk-off rotation (capital flowing to BTC safety).
Falling BTC dominance signals alt season (capital flowing into higher-risk alts).

Data source: CoinGecko Global API.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)

_CACHE: dict[str, Any] = {}
_CACHE_TTL = 1800  # 30 minutes


async def get_dominance_signal() -> dict[str, Any]:
    """Fetch BTC dominance data and generate altcoin rotation signal.

    Returns:
        {btc_dominance_pct, eth_dominance_pct, alts_dominance_pct,
         dominance_trend, regime, altcoin_signal, interpretation}
    """
    now = time.time()
    if _CACHE.get("data") and now - _CACHE.get("ts", 0) < _CACHE_TTL:
        return _CACHE["data"]

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get("https://api.coingecko.com/api/v3/global")
            resp.raise_for_status()
            data = resp.json().get("data", {})

        market_cap_pct = data.get("market_cap_percentage", {})
        btc_dom = round(market_cap_pct.get("btc", 50.0), 2)
        eth_dom = round(market_cap_pct.get("eth", 17.0), 2)
        alts_dom = round(100.0 - btc_dom - eth_dom, 2)

        # Trend (compare to cached previous value)
        prev_btc = _CACHE.get("prev_btc_dom", btc_dom)
        if btc_dom > prev_btc + 0.5:
            trend = "RISING"
        elif btc_dom < prev_btc - 0.5:
            trend = "FALLING"
        else:
            trend = "STABLE"

        # Regime classification
        if btc_dom > 55:
            regime = "BTC_SEASON"
            altcoin_signal = "BEARISH"
            interpretation = f"BTC dominance at {btc_dom}% — capital concentrated in BTC. Risk-off environment for altcoins."
        elif btc_dom < 42:
            regime = "ALT_SEASON"
            altcoin_signal = "BULLISH"
            interpretation = f"BTC dominance at {btc_dom}% — capital rotating to altcoins. Favorable for ETH and alts."
        elif eth_dom > 20:
            regime = "ETH_SEASON"
            altcoin_signal = "MODERATELY_BULLISH"
            interpretation = f"ETH dominance rising ({eth_dom}%) — quality altcoins likely to follow."
        elif trend == "RISING":
            regime = "RISK_OFF"
            altcoin_signal = "BEARISH"
            interpretation = f"BTC dominance rising ({btc_dom}% and climbing) — reduce altcoin exposure."
        else:
            regime = "MIXED"
            altcoin_signal = "NEUTRAL"
            interpretation = f"BTC dominance at {btc_dom}% — no clear rotation signal."

        result: dict[str, Any] = {
            "btc_dominance_pct": btc_dom,
            "eth_dominance_pct": eth_dom,
            "alts_dominance_pct": alts_dom,
            "dominance_trend": trend,
            "regime": regime,
            "altcoin_signal": altcoin_signal,
            "interpretation": interpretation,
            "timestamp": int(now * 1000),
        }
        _CACHE["data"] = result
        _CACHE["prev_btc_dom"] = btc_dom
        _CACHE["ts"] = now
        return result

    except Exception as exc:
        logger.warning("BTC dominance fetch failed: %s", exc)
        return {
            "btc_dominance_pct": 50.0,
            "eth_dominance_pct": 17.0,
            "alts_dominance_pct": 33.0,
            "dominance_trend": "STABLE",
            "regime": "MIXED",
            "altcoin_signal": "NEUTRAL",
            "interpretation": "Unable to fetch dominance data",
            "error": str(exc),
            "timestamp": int(now * 1000),
        }
