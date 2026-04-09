"""Sentiment data fetcher — Twitter + Reddit with FinBERT scoring."""

import asyncio
import logging
import re
from datetime import datetime, timezone

import httpx
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from app.core.config import settings

logger = logging.getLogger(__name__)

ASSET_KEYWORDS: dict[str, list[str]] = {
    "BTC/USDT": ["bitcoin", "btc", "#btc", "#bitcoin"],
    "ETH/USDT": ["ethereum", "eth", "#eth", "#ethereum"],
    "SOL/USDT": ["solana", "sol", "#sol", "#solana"],
    "EUR/USD": ["eurusd", "eur/usd", "#eurusd"],
    "GBP/USD": ["gbpusd", "gbp/usd", "#gbpusd"],
}

REDDIT_SUBREDDITS = ["CryptoCurrency", "Bitcoin", "ethereum"]

MIN_SAMPLE_SIZE = 50
FINBERT_MODEL = "ProsusAI/finbert"
BATCH_SIZE = 32


def _clean_text(text: str) -> str:
    """Lowercase, remove URLs and clean up whitespace."""
    text = text.lower()
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"@\w+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


class FinBERTScorer:
    """Lazy-loaded FinBERT model for sentiment scoring."""

    def __init__(self) -> None:
        self._tokenizer = None
        self._model = None
        self._device: str = "cpu"

    def _load(self) -> None:
        """Load model and tokenizer on first use."""
        if self._model is not None:
            return
        logger.info("Loading FinBERT model: %s", FINBERT_MODEL)
        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        self._tokenizer = AutoTokenizer.from_pretrained(FINBERT_MODEL)
        self._model = AutoModelForSequenceClassification.from_pretrained(FINBERT_MODEL)
        self._model.to(self._device)
        self._model.eval()
        logger.info("FinBERT loaded on %s", self._device)

    def score_texts(self, texts: list[str]) -> list[float]:
        """Score a list of texts. Returns values in [-1.0, +1.0].

        Score = P(positive) - P(negative).
        """
        self._load()
        scores: list[float] = []

        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i : i + BATCH_SIZE]
            inputs = self._tokenizer(
                batch,
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="pt",
            ).to(self._device)

            with torch.no_grad():
                outputs = self._model(**inputs)
                probs = torch.softmax(outputs.logits, dim=1)

            # FinBERT classes: positive(0), negative(1), neutral(2)
            for prob in probs:
                score = float(prob[0] - prob[1])
                scores.append(score)

        return scores


# Singleton scorer
_scorer = FinBERTScorer()


class SentimentFetcher:
    """Fetches social media posts and scores them with FinBERT."""

    async def fetch_twitter(self, asset: str) -> list[str]:
        """Fetch recent tweets for an asset via Twitter API v2."""
        keywords = ASSET_KEYWORDS.get(asset, [])
        if not keywords or not settings.TWITTER_BEARER_TOKEN:
            return []

        query = " OR ".join(keywords) + " -is:retweet lang:en"
        url = "https://api.twitter.com/2/tweets/search/recent"

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    url,
                    params={"query": query, "max_results": 100},
                    headers={
                        "Authorization": f"Bearer {settings.TWITTER_BEARER_TOKEN}"
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                tweets = [t["text"] for t in data.get("data", [])]
                logger.info("Fetched %d tweets for %s", len(tweets), asset)
                return tweets
        except Exception as exc:
            logger.error("Twitter fetch failed for %s: %s", asset, exc)
            return []

    async def fetch_reddit(self, asset: str) -> list[str]:
        """Fetch recent Reddit posts from crypto subreddits."""
        keywords = ASSET_KEYWORDS.get(asset, [])
        if not keywords or not settings.REDDIT_CLIENT_ID:
            return []

        posts: list[str] = []
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                # Get OAuth token
                auth_resp = await client.post(
                    "https://www.reddit.com/api/v1/access_token",
                    data={"grant_type": "client_credentials"},
                    auth=(settings.REDDIT_CLIENT_ID, settings.REDDIT_CLIENT_SECRET),
                    headers={"User-Agent": "TradingAI/0.1"},
                )
                auth_resp.raise_for_status()
                token = auth_resp.json()["access_token"]

                headers = {
                    "Authorization": f"Bearer {token}",
                    "User-Agent": "TradingAI/0.1",
                }

                for subreddit in REDDIT_SUBREDDITS:
                    resp = await client.get(
                        f"https://oauth.reddit.com/r/{subreddit}/new.json",
                        params={"limit": 50},
                        headers=headers,
                    )
                    resp.raise_for_status()
                    children = resp.json().get("data", {}).get("children", [])
                    for child in children:
                        title = child["data"].get("title", "")
                        selftext = child["data"].get("selftext", "")
                        text = f"{title} {selftext}".strip()
                        if any(kw in text.lower() for kw in keywords):
                            posts.append(text)

                logger.info("Fetched %d Reddit posts for %s", len(posts), asset)
        except Exception as exc:
            logger.error("Reddit fetch failed for %s: %s", asset, exc)

        return posts

    async def analyze(self, asset: str) -> dict:
        """Fetch from all sources, score with FinBERT, return aggregated result.

        Returns:
            {
                "asset": str,
                "score": float,       # -1.0 to +1.0 (0 if insufficient data)
                "volume": int,        # number of posts analyzed
                "period_start": datetime,
                "period_end": datetime,
                "sources": {"twitter": float, "reddit": float},
            }
        """
        now = datetime.now(timezone.utc)

        # Fetch from both sources in parallel
        twitter_texts, reddit_texts = await asyncio.gather(
            self.fetch_twitter(asset),
            self.fetch_reddit(asset),
        )

        # Clean texts
        twitter_clean = [_clean_text(t) for t in twitter_texts if t.strip()]
        reddit_clean = [_clean_text(t) for t in reddit_texts if t.strip()]
        all_texts = twitter_clean + reddit_clean

        result = {
            "asset": asset,
            "score": 0.0,
            "volume": len(all_texts),
            "period_start": now,
            "period_end": now,
            "sources": {"twitter": 0.0, "reddit": 0.0},
        }

        if len(all_texts) < MIN_SAMPLE_SIZE:
            logger.warning(
                "Insufficient data for %s: %d texts (min %d)",
                asset, len(all_texts), MIN_SAMPLE_SIZE,
            )
            return result

        # Score all texts with FinBERT (runs in thread to avoid blocking)
        loop = asyncio.get_event_loop()
        scores = await loop.run_in_executor(None, _scorer.score_texts, all_texts)

        # Split scores back to sources
        tw_count = len(twitter_clean)
        tw_scores = scores[:tw_count]
        rd_scores = scores[tw_count:]

        tw_avg = sum(tw_scores) / len(tw_scores) if tw_scores else 0.0
        rd_avg = sum(rd_scores) / len(rd_scores) if rd_scores else 0.0
        total_avg = sum(scores) / len(scores)

        result["score"] = round(total_avg, 4)
        result["sources"]["twitter"] = round(tw_avg, 4)
        result["sources"]["reddit"] = round(rd_avg, 4)

        logger.info(
            "Sentiment for %s: score=%.4f, volume=%d (tw=%.4f, rd=%.4f)",
            asset, total_avg, len(all_texts), tw_avg, rd_avg,
        )
        return result
