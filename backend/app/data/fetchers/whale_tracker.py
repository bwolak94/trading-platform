"""Whale & Position Tracker — monitors large transfers and market positioning."""

import asyncio
import logging
from collections import deque
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

COINGLASS_HEADERS = {"User-Agent": "TradingAI/1.0"}
POLL_INTERVAL = 60  # seconds


class WhaleTracker:
    def __init__(self):
        self._running = False
        self._task = None
        self._long_short_ratios: dict[str, dict] = {}
        self._whale_alerts: deque[dict] = deque(maxlen=200)
        self._oi_data: dict[str, float] = {}
        self._retail_sentiment: dict[str, float] = {}  # symbol -> % long

    async def start(self):
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("WhaleTracker started")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()

    async def _poll_loop(self):
        while self._running:
            try:
                await asyncio.gather(
                    self._fetch_long_short_ratios(),
                    self._fetch_oi(),
                    self._fetch_retail_sentiment(),
                    return_exceptions=True,
                )
            except Exception as exc:
                logger.error("WhaleTracker poll error: %s", exc)
            await asyncio.sleep(POLL_INTERVAL)

    async def _fetch_long_short_ratios(self):
        """Fetch global long/short account ratio from Binance Futures."""
        symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
        async with httpx.AsyncClient(timeout=10.0) as client:
            for sym in symbols:
                try:
                    resp = await client.get(
                        "https://fapi.binance.com/futures/data/globalLongShortAccountRatio",
                        params={"symbol": sym, "period": "5m", "limit": 1},
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        if data:
                            ratio = float(data[0].get("longShortRatio", 1.0))
                            long_pct = ratio / (1 + ratio) * 100
                            self._long_short_ratios[sym] = {
                                "ratio": round(ratio, 3),
                                "long_pct": round(long_pct, 1),
                                "short_pct": round(100 - long_pct, 1),
                                "bias": "LONG" if ratio > 1.1 else "SHORT" if ratio < 0.9 else "NEUTRAL",
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                            }
                except Exception as exc:
                    logger.debug("L/S ratio fetch failed for %s: %s", sym, exc)

    async def _fetch_oi(self):
        """Fetch open interest from Binance Futures."""
        symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
        async with httpx.AsyncClient(timeout=10.0) as client:
            for sym in symbols:
                try:
                    resp = await client.get(
                        "https://fapi.binance.com/fapi/v1/openInterest",
                        params={"symbol": sym},
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        self._oi_data[sym] = float(data.get("openInterest", 0))
                except Exception:
                    pass

    async def _fetch_retail_sentiment(self):
        """Fetch retail sentiment from Binance top trader positions."""
        symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
        async with httpx.AsyncClient(timeout=10.0) as client:
            for sym in symbols:
                try:
                    resp = await client.get(
                        "https://fapi.binance.com/futures/data/topLongShortPositionRatio",
                        params={"symbol": sym, "period": "5m", "limit": 1},
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        if data:
                            ratio = float(data[0].get("longShortRatio", 1.0))
                            self._retail_sentiment[sym] = round(ratio / (1 + ratio) * 100, 1)
                except Exception:
                    pass

    def get_data(self) -> dict:
        return {
            "long_short_ratios": self._long_short_ratios,
            "open_interest": self._oi_data,
            "retail_sentiment": self._retail_sentiment,
            "whale_alerts": list(self._whale_alerts)[-20:],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def get_status(self) -> dict:
        return {
            "running": self._running,
            "symbols_tracked": len(self._long_short_ratios),
            "whale_alerts_count": len(self._whale_alerts),
        }


_tracker: WhaleTracker | None = None

def get_whale_tracker() -> WhaleTracker:
    global _tracker
    if _tracker is None:
        _tracker = WhaleTracker()
    return _tracker
