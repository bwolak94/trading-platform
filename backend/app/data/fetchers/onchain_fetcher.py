"""On-chain data fetcher — Whale Alert API with scoring and decay."""

import asyncio
import logging
import math
from datetime import datetime, timezone
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

WHALE_ALERT_URL = "https://api.whale-alert.io/v1/transactions"
POLL_INTERVAL = 60  # seconds

# Minimum thresholds for relevance
MIN_THRESHOLDS: dict[str, float] = {
    "BTC": 100.0,
    "ETH": 1000.0,
    "SOL": 10000.0,
}

# Known exchange addresses label patterns
EXCHANGE_LABELS = {"binance", "coinbase", "kraken", "bitfinex", "huobi", "okex", "kucoin"}

# Scoring rules from 04_AI_ENGINE.md
SCORING_RULES: dict[str, float] = {
    "EXCHANGE_INFLOW": -0.7,
    "EXCHANGE_OUTFLOW": 0.7,
    "WHALE_BUY": 0.8,
    "MINER_SELL": -0.5,
    "RESERVE_DECLINE": 0.6,
}

DECAY_HALF_LIFE_HOURS = 6.0


def decayed_score(event_score: float, hours_ago: float) -> float:
    """Apply exponential decay to an event score based on age."""
    return event_score * (0.5 ** (hours_ago / DECAY_HALF_LIFE_HOURS))


def _classify_event(tx: dict[str, Any]) -> tuple[str, str]:
    """Classify a Whale Alert transaction into event_type and direction.

    Returns (event_type, direction) where direction is BULLISH/BEARISH/NEUTRAL.
    """
    from_owner = (tx.get("from", {}).get("owner", "") or "").lower()
    to_owner = (tx.get("to", {}).get("owner", "") or "").lower()

    from_is_exchange = any(ex in from_owner for ex in EXCHANGE_LABELS)
    to_is_exchange = any(ex in to_owner for ex in EXCHANGE_LABELS)

    if to_is_exchange and not from_is_exchange:
        return "EXCHANGE_INFLOW", "BEARISH"
    elif from_is_exchange and not to_is_exchange:
        return "EXCHANGE_OUTFLOW", "BULLISH"
    elif from_is_exchange and to_is_exchange:
        return "EXCHANGE_TRANSFER", "NEUTRAL"
    else:
        # Wallet-to-wallet — likely OTC / accumulation
        return "WHALE_TRANSFER", "NEUTRAL"


def _map_symbol_to_asset(symbol: str) -> str | None:
    """Map Whale Alert symbol to our asset format."""
    mapping = {"btc": "BTC/USDT", "eth": "ETH/USDT", "sol": "SOL/USDT"}
    return mapping.get(symbol.lower())


class OnChainFetcher:
    """Fetches on-chain whale activity from Whale Alert API."""

    def __init__(self) -> None:
        self._running = False
        self._last_cursor: str | None = None

    async def fetch_recent(self, lookback_seconds: int = 3600) -> list[dict[str, Any]]:
        """Fetch recent whale transactions.

        Returns list of parsed event dicts ready for DB storage.
        """
        if not settings.WHALE_ALERT_API_KEY:
            logger.warning("WHALE_ALERT_API_KEY not configured, skipping fetch")
            return []

        now = datetime.now(timezone.utc)
        start = int(now.timestamp()) - lookback_seconds

        events: list[dict[str, Any]] = []

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                params: dict[str, Any] = {
                    "api_key": settings.WHALE_ALERT_API_KEY,
                    "start": start,
                    "min_value": 500000,  # $500k minimum
                }
                if self._last_cursor:
                    params["cursor"] = self._last_cursor

                resp = await client.get(WHALE_ALERT_URL, params=params)
                resp.raise_for_status()
                data = resp.json()

                self._last_cursor = data.get("cursor")
                transactions = data.get("transactions", [])

                for tx in transactions:
                    event = self._parse_transaction(tx, now)
                    if event:
                        events.append(event)

                logger.info("Fetched %d on-chain events", len(events))
        except Exception as exc:
            logger.error("Whale Alert fetch failed: %s", exc)

        return events

    def _parse_transaction(
        self, tx: dict[str, Any], now: datetime
    ) -> dict[str, Any] | None:
        """Parse a single Whale Alert transaction into our event format."""
        symbol = tx.get("symbol", "")
        asset = _map_symbol_to_asset(symbol)
        if not asset:
            return None

        amount = float(tx.get("amount", 0))
        min_threshold = MIN_THRESHOLDS.get(symbol.upper(), 0)
        if amount < min_threshold:
            return None

        event_type, direction = _classify_event(tx)
        base_score = SCORING_RULES.get(event_type, 0.0)

        tx_time = datetime.fromtimestamp(tx.get("timestamp", 0), tz=timezone.utc)
        hours_ago = max((now - tx_time).total_seconds() / 3600, 0)
        score = decayed_score(base_score, hours_ago)

        return {
            "asset": asset,
            "event_type": event_type,
            "amount": amount,
            "amount_usd": float(tx.get("amount_usd", 0)),
            "from_address": tx.get("from", {}).get("address"),
            "to_address": tx.get("to", {}).get("address"),
            "direction": direction,
            "source": "whale_alert",
            "raw_data": tx,
            "timestamp": tx_time,
            "score": round(score, 4),
        }

    def compute_aggregate_score(self, events: list[dict[str, Any]]) -> float:
        """Compute a single aggregate on-chain score from a list of events.

        Returns value in [-1.0, +1.0].
        """
        if not events:
            return 0.0

        now = datetime.now(timezone.utc)
        total = 0.0

        for event in events:
            ts = event.get("timestamp", now)
            hours_ago = max((now - ts).total_seconds() / 3600, 0)
            base = SCORING_RULES.get(event["event_type"], 0.0)
            total += decayed_score(base, hours_ago)

        # Clamp to [-1, 1]
        return max(-1.0, min(1.0, total / max(len(events), 1)))

    async def start_polling(
        self, callback=None, interval: int = POLL_INTERVAL
    ) -> None:
        """Poll Whale Alert API at a regular interval."""
        self._running = True
        logger.info("On-chain polling started (every %ds)", interval)

        while self._running:
            events = await self.fetch_recent(lookback_seconds=interval + 30)
            if events and callback:
                await callback(events)
            await asyncio.sleep(interval)

    def stop_polling(self) -> None:
        """Stop the polling loop."""
        self._running = False
        logger.info("On-chain polling stopped")
