"""CoinGecko fetcher — BTC dominance, global market data, and stablecoin SSR, cached."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)

COINGECKO_GLOBAL_URL = "https://api.coingecko.com/api/v3/global"
COINGECKO_MARKETS_URL = "https://api.coingecko.com/api/v3/coins/markets"
_CACHE_TTL = 300  # 5 minutes
_SSR_CACHE_TTL = 900  # 15 minutes

_global_cache: dict[str, Any] | None = None
_global_cache_ts: datetime | None = None

_ssr_cache: dict[str, Any] | None = None
_ssr_cache_ts: datetime | None = None


async def get_btc_dominance() -> dict[str, Any]:
    """Fetch BTC dominance and global crypto market data from CoinGecko.

    Returns:
        dict with btc_dominance (%), total_market_cap_usd, total_volume_24h_usd,
        market_cap_change_24h_pct, active_cryptocurrencies
    """
    global _global_cache, _global_cache_ts

    now = datetime.now(timezone.utc)
    if _global_cache and _global_cache_ts and (now - _global_cache_ts).total_seconds() < _CACHE_TTL:
        return _global_cache

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(COINGECKO_GLOBAL_URL)
            resp.raise_for_status()
            body = resp.json()
            data = body.get("data", {})

            btc_dom = data.get("market_cap_percentage", {}).get("btc", 0.0)
            total_mcap = data.get("total_market_cap", {}).get("usd", 0)
            total_vol = data.get("total_volume", {}).get("usd", 0)
            mcap_change = data.get("market_cap_change_percentage_24h_usd", 0.0)
            active_coins = data.get("active_cryptocurrencies", 0)

            _global_cache = {
                "btc_dominance": round(btc_dom, 2),
                "total_market_cap_usd": total_mcap,
                "total_volume_24h_usd": total_vol,
                "market_cap_change_24h_pct": round(mcap_change, 2),
                "active_cryptocurrencies": active_coins,
                "cached_at": now.isoformat(),
            }
            _global_cache_ts = now
            return _global_cache

    except Exception as exc:
        logger.warning("CoinGecko fetch failed: %s", exc)
        if _global_cache:
            return _global_cache
        return {
            "btc_dominance": 0.0,
            "total_market_cap_usd": 0,
            "total_volume_24h_usd": 0,
            "market_cap_change_24h_pct": 0.0,
            "active_cryptocurrencies": 0,
            "cached_at": now.isoformat(),
            "error": str(exc),
        }


async def get_stablecoin_supply_ratio() -> dict[str, Any]:
    """Compute the Stablecoin Supply Ratio (SSR) from CoinGecko data.

    SSR = (USDT_mcap + USDC_mcap) / total_market_cap

    A high SSR (> 0.15) indicates large stablecoin dry powder relative to
    the total market — typically bullish. A low SSR (< 0.06) suggests most
    capital is already deployed.

    Results are cached for 15 minutes.
    """
    global _ssr_cache, _ssr_cache_ts

    now = datetime.now(timezone.utc)
    if _ssr_cache and _ssr_cache_ts and (now - _ssr_cache_ts).total_seconds() < _SSR_CACHE_TTL:
        return _ssr_cache

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Fetch stablecoin market caps
            markets_resp = await client.get(
                COINGECKO_MARKETS_URL,
                params={
                    "vs_currency": "usd",
                    "ids": "tether,usd-coin",
                    "order": "market_cap_desc",
                    "per_page": 2,
                    "page": 1,
                },
            )
            markets_resp.raise_for_status()
            markets_data = markets_resp.json()

            usdt_mcap = 0.0
            usdc_mcap = 0.0
            for coin in markets_data:
                cid = coin.get("id", "")
                mcap = coin.get("market_cap") or 0
                if cid == "tether":
                    usdt_mcap = float(mcap)
                elif cid == "usd-coin":
                    usdc_mcap = float(mcap)

            # Re-use global cache or fetch fresh
            global_data = await get_btc_dominance()
            total_mcap = global_data.get("total_market_cap_usd", 0) or 0

        stable_mcap = usdt_mcap + usdc_mcap
        ssr = round(stable_mcap / total_mcap, 4) if total_mcap > 0 else 0.0

        # Interpret SSR signal
        if ssr > 0.15:
            signal = "bullish"
            interpretation = "Large stablecoin dry powder — potential buying pressure incoming"
        elif ssr > 0.10:
            signal = "neutral_bullish"
            interpretation = "Moderate stablecoin reserves — some dry powder available"
        elif ssr > 0.06:
            signal = "neutral"
            interpretation = "Normal stablecoin levels"
        else:
            signal = "bearish"
            interpretation = "Low stablecoin ratio — most capital already deployed"

        _ssr_cache = {
            "ssr": ssr,
            "usdt_market_cap": usdt_mcap,
            "usdc_market_cap": usdc_mcap,
            "stable_total": stable_mcap,
            "total_market_cap": total_mcap,
            "signal": signal,
            "interpretation": interpretation,
            "cached_at": now.isoformat(),
        }
        _ssr_cache_ts = now
        return _ssr_cache

    except Exception as exc:
        logger.warning("Stablecoin SSR fetch failed: %s", exc)
        if _ssr_cache:
            return _ssr_cache
        return {
            "ssr": 0.0,
            "usdt_market_cap": 0.0,
            "usdc_market_cap": 0.0,
            "stable_total": 0.0,
            "total_market_cap": 0,
            "signal": "unknown",
            "interpretation": "Data unavailable",
            "cached_at": now.isoformat(),
            "error": str(exc),
        }
