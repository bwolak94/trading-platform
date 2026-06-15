"""News & RSS Aggregator — scrapes financial news from multiple free sources."""

import asyncio
import logging
import xml.etree.ElementTree as ET
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

# RSS Feed sources (all free, no API key needed)
RSS_FEEDS = {
    "reuters_business": "https://feeds.reuters.com/reuters/businessNews",
    "reuters_markets": "https://feeds.reuters.com/reuters/USVideoBreakingviews",
    "coindesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "cointelegraph": "https://cointelegraph.com/rss",
    "forexlive": "https://www.forexlive.com/feed/news",
    "investing": "https://www.investing.com/rss/news.rss",
}

# Emergency keywords that trigger high-priority alerts
EMERGENCY_KEYWORDS = {
    "war", "attack", "nuclear", "crash", "black swan", "explosion",
    "rate hike", "rate cut", "fed rate", "emergency meeting",
    "default", "collapse", "bankruptcy", "liquidated", "hack",
    "sanctions", "invasion", "missile", "terrorist",
}

# Market-moving keywords for scoring
BULLISH_KEYWORDS = {"rally", "surge", "bull", "breakout", "accumulation", "buy", "upgrade", "bullish", "ath", "moon"}
BEARISH_KEYWORDS = {"crash", "dump", "bear", "breakdown", "sell-off", "downgrade", "bearish", "plunge", "fear"}

MAX_NEWS_ITEMS = 500
FETCH_INTERVAL = 30  # seconds


@dataclass
class NewsItem:
    title: str
    source: str
    url: str
    published: str
    sentiment: float  # -1 to +1
    is_emergency: bool
    keywords_found: list[str]
    timestamp: datetime


class NewsAggregator:
    def __init__(self):
        self._news: deque[NewsItem] = deque(maxlen=MAX_NEWS_ITEMS)
        self._running = False
        self._task = None
        self._emergency_active = False
        self._emergency_reason = ""
        self._global_sentiment = 0.0
        self._priority_alerts: deque[str] = deque(maxlen=20)
        self._seen_urls: set[str] = set()

    async def start(self):
        self._running = True
        self._task = asyncio.create_task(self._fetch_loop())
        logger.info("NewsAggregator started")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
        logger.info("NewsAggregator stopped")

    async def _fetch_loop(self):
        while self._running:
            try:
                await self._fetch_all_feeds()
                self._update_global_sentiment()
            except Exception as exc:
                logger.error("News fetch error: %s", exc)
            await asyncio.sleep(FETCH_INTERVAL)

    async def _fetch_single_feed(self, client: httpx.AsyncClient, source_name: str, url: str) -> None:
        """Fetch and process a single RSS feed."""
        try:
            resp = await client.get(url, headers={"User-Agent": "TradingAI/1.0"})
            if resp.status_code == 200:
                items = self._parse_rss(resp.text, source_name)
                for item in items:
                    if item.url not in self._seen_urls:
                        self._seen_urls.add(item.url)
                        self._news.appendleft(item)
                        if item.is_emergency:
                            self._emergency_active = True
                            self._emergency_reason = f"EMERGENCY: {item.title}"
                            self._priority_alerts.appendleft(item.title)
                            logger.warning("EMERGENCY NEWS: %s", item.title)
        except Exception as exc:
            logger.debug("Feed %s failed: %s", source_name, exc)

    async def _fetch_all_feeds(self):
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            tasks = [
                self._fetch_single_feed(client, name, url)
                for name, url in RSS_FEEDS.items()
            ]
            await asyncio.gather(*tasks, return_exceptions=True)

    def _parse_rss(self, xml_text: str, source: str) -> list[NewsItem]:
        items = []
        try:
            root = ET.fromstring(xml_text)
            # Handle both RSS 2.0 and Atom formats
            ns = {"atom": "http://www.w3.org/2005/Atom"}

            # RSS 2.0
            for item in root.findall(".//item")[:20]:
                title = item.findtext("title", "").strip()
                link = item.findtext("link", "").strip()
                pub_date = item.findtext("pubDate", "")
                if title and link:
                    sentiment = self._score_headline(title)
                    emergency, keywords = self._check_emergency(title)
                    items.append(NewsItem(
                        title=title, source=source, url=link,
                        published=pub_date, sentiment=sentiment,
                        is_emergency=emergency, keywords_found=keywords,
                        timestamp=datetime.now(timezone.utc),
                    ))

            # Atom format
            for entry in root.findall("atom:entry", ns)[:20]:
                title = entry.findtext("atom:title", "", ns).strip()
                link_el = entry.find("atom:link", ns)
                link = link_el.get("href", "") if link_el is not None else ""
                pub_date = entry.findtext("atom:published", "", ns)
                if title and link:
                    sentiment = self._score_headline(title)
                    emergency, keywords = self._check_emergency(title)
                    items.append(NewsItem(
                        title=title, source=source, url=link,
                        published=pub_date, sentiment=sentiment,
                        is_emergency=emergency, keywords_found=keywords,
                        timestamp=datetime.now(timezone.utc),
                    ))
        except ET.ParseError as exc:
            logger.debug("RSS parse error for %s: %s", source, exc)
        return items

    def _score_headline(self, title: str) -> float:
        lower = title.lower()
        bull = sum(1 for kw in BULLISH_KEYWORDS if kw in lower)
        bear = sum(1 for kw in BEARISH_KEYWORDS if kw in lower)
        total = bull + bear
        if total == 0:
            return 0.0
        return round((bull - bear) / total, 2)

    def _check_emergency(self, title: str) -> tuple[bool, list[str]]:
        lower = title.lower()
        found = [kw for kw in EMERGENCY_KEYWORDS if kw in lower]
        return (len(found) > 0, found)

    def _update_global_sentiment(self):
        recent = list(self._news)[:50]
        if not recent:
            return
        avg = sum(n.sentiment for n in recent) / len(recent)
        self._global_sentiment = round(avg, 3)

    def clear_emergency(self):
        self._emergency_active = False
        self._emergency_reason = ""

    def get_news(self, limit: int = 50) -> list[dict]:
        return [
            {
                "title": n.title, "source": n.source, "url": n.url,
                "published": n.published, "sentiment": n.sentiment,
                "is_emergency": n.is_emergency,
                "keywords": n.keywords_found,
                "timestamp": n.timestamp.isoformat(),
            }
            for n in list(self._news)[:limit]
        ]

    def get_sentiment_snapshot(self) -> dict:
        recent = list(self._news)[:20]
        [n.title for n in recent if n.is_emergency]
        impact_zones = []

        # Determine impact zones from recent keywords
        crypto_sentiment = sum(n.sentiment for n in recent if any(kw in n.source for kw in ["coindesk", "cointelegraph"])) / max(1, sum(1 for n in recent if any(kw in n.source for kw in ["coindesk", "cointelegraph"])))
        forex_sentiment = sum(n.sentiment for n in recent if any(kw in n.source for kw in ["reuters", "forexlive", "investing"])) / max(1, sum(1 for n in recent if any(kw in n.source for kw in ["reuters", "forexlive", "investing"])))

        if crypto_sentiment > 0.2: impact_zones.append("Crypto: Bullish sentiment")
        elif crypto_sentiment < -0.2: impact_zones.append("Crypto: Bearish sentiment")
        if forex_sentiment > 0.2: impact_zones.append("Forex: Risk-On")
        elif forex_sentiment < -0.2: impact_zones.append("Forex: Risk-Off")

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "global_sentiment": self._global_sentiment,
            "crypto_sentiment": round(crypto_sentiment, 3),
            "forex_sentiment": round(forex_sentiment, 3),
            "emergency_active": self._emergency_active,
            "emergency_reason": self._emergency_reason,
            "priority_alerts": list(self._priority_alerts)[:5],
            "impact_zones": impact_zones,
            "news_count": len(self._news),
        }

    def get_status(self) -> dict:
        return {
            "running": self._running,
            "news_count": len(self._news),
            "global_sentiment": self._global_sentiment,
            "emergency_active": self._emergency_active,
            "sources_configured": len(RSS_FEEDS),
        }


_aggregator: NewsAggregator | None = None

def get_news_aggregator() -> NewsAggregator:
    global _aggregator
    if _aggregator is None:
        _aggregator = NewsAggregator()
    return _aggregator
