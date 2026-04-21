"""News velocity tracker using CryptoPanic free RSS/API."""
import re
import time
from collections import defaultdict
from typing import Optional
import logging

import httpx

logger = logging.getLogger(__name__)

_cache: Optional[dict] = None
_cache_time: float = 0
_CACHE_TTL = 300  # 5 minutes

# CryptoPanic public RSS feed (no API key needed for basic RSS)
CRYPTOPANIC_RSS = "https://cryptopanic.com/news/rss/"

# Symbol mapping from headline keywords
SYMBOL_KEYWORDS: dict[str, list[str]] = {
    "BTC": ["bitcoin", "btc"],
    "ETH": ["ethereum", "eth", "ether"],
    "SOL": ["solana", "sol"],
    "BNB": ["binance", "bnb"],
    "XRP": ["ripple", "xrp"],
    "ADA": ["cardano", "ada"],
    "DOGE": ["dogecoin", "doge"],
    "AVAX": ["avalanche", "avax"],
    "LINK": ["chainlink", "link"],
    "MATIC": ["polygon", "matic"],
    "ARB": ["arbitrum", "arb"],
    "OP": ["optimism"],
}


async def get_news_velocity() -> dict:
    """Return article count per symbol per hour (last 6h)."""
    global _cache, _cache_time
    now = time.time()
    if _cache and now - _cache_time < _CACHE_TTL:
        return _cache["data"]

    result = await _fetch_news_velocity()
    _cache = {"data": result}
    _cache_time = now
    return result


async def _fetch_news_velocity() -> dict:
    """Fetch CryptoPanic RSS and compute per-symbol news velocity.

    Returns dict with velocity (sorted list), total_articles count,
    and top 10 recent relevant articles.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(CRYPTOPANIC_RSS, headers={
                "User-Agent": "TradingNavigator/1.0"
            })
            resp.raise_for_status()
            content = resp.text

        items = re.findall(r"<item>(.*?)</item>", content, re.DOTALL)

        velocity: dict[str, int] = defaultdict(int)
        articles: list[dict] = []

        for item in items[:50]:  # Latest 50 articles
            title_match = re.search(r"<title>(.*?)</title>", item)
            date_match = re.search(r"<pubDate>(.*?)</pubDate>", item)
            title = title_match.group(1).lower() if title_match else ""

            matched_symbols: list[str] = []
            for sym, keywords in SYMBOL_KEYWORDS.items():
                if any(kw in title for kw in keywords):
                    matched_symbols.append(sym)
                    velocity[sym] += 1

            if matched_symbols:
                articles.append({
                    "title": title_match.group(1) if title_match else "",
                    "symbols": matched_symbols,
                    "pub_date": date_match.group(1) if date_match else "",
                })

        sorted_velocity = sorted(
            [{"symbol": k, "count": v} for k, v in velocity.items()],
            key=lambda x: x["count"],
            reverse=True,
        )

        return {
            "velocity": sorted_velocity,
            "total_articles": len(items),
            "articles": articles[:10],  # Top 10 recent relevant articles
        }
    except Exception as e:
        logger.warning("News velocity fetch failed: %s", e)
        return {"velocity": [], "total_articles": 0, "articles": []}
