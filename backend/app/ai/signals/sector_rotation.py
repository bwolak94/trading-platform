"""Sector rotation and momentum ranking for crypto asset groups."""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx
import numpy as np

SECTOR_MAP: dict[str, list[str]] = {
    "Layer 1": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "ADAUSDT", "AVAXUSDT", "DOTUSDT", "ATOMUSDT", "NEARUSDT", "ALGOUSDT"],
    "Layer 2": ["MATICUSDT", "ARBUSDT", "OPUSDT", "IMXUSDT", "STRKUSDT"],
    "DeFi": ["UNIUSDT", "AAVEUSDT", "LINKUSDT", "CRVUSDT", "MKRUSDT", "SNXUSDT", "COMPUSDT"],
    "Gaming/NFT": ["AXSUSDT", "SANDUSDT", "MANAUSDT", "ENJUSDT", "GALAUSDT"],
    "Exchange": ["BNBUSDT", "OKBUSDT"],
    "Meme": ["DOGEUSDT", "SHIBUSDT", "PEPEUSDT"],
    "AI/Data": ["FETUSDT", "OCEANUSDT", "AGIXUSDT", "RENDERUSDT"],
    "Infra": ["FILUSDT", "ARUSDT", "THETAUSDT"],
}

BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"


@dataclass
class SectorMetrics:
    """Momentum metrics for a single crypto sector."""

    sector: str
    momentum_score: float  # weighted combo of 1d and 7d average changes
    avg_1d_change: float
    avg_7d_change: float
    top_performers: list[str] = field(default_factory=list)
    symbol_count: int = 0


_cache: Optional[dict] = None
_cache_time: float = 0.0
_CACHE_TTL = 600  # 10 minutes


async def _fetch_klines(client: httpx.AsyncClient, symbol: str, limit: int = 8) -> list[list]:
    """Fetch daily klines for a single symbol from Binance REST API.

    Args:
        client: Shared async HTTP client.
        symbol: Binance trading pair symbol (e.g. BTCUSDT).
        limit: Number of daily candles to fetch.

    Returns:
        Raw kline list from Binance, or empty list on failure.
    """
    try:
        resp = await client.get(
            BINANCE_KLINES_URL,
            params={"symbol": symbol, "interval": "1d", "limit": limit},
            timeout=8.0,
        )
        resp.raise_for_status()
        return resp.json()  # type: ignore[return-value]
    except Exception:
        return []


async def get_sector_momentum() -> list[SectorMetrics]:
    """Calculate momentum scores per crypto sector.

    Fetches 8 daily candles per symbol, computes 1d and 7d returns, then
    aggregates into per-sector averages. Results are cached for 10 minutes.

    Returns:
        List of SectorMetrics sorted by momentum_score descending.
    """
    global _cache, _cache_time

    now = time.time()
    if _cache and now - _cache_time < _CACHE_TTL:
        return _cache["data"]

    results: list[SectorMetrics] = []

    async with httpx.AsyncClient() as client:
        for sector, symbols in SECTOR_MAP.items():
            # Fetch all symbols in this sector concurrently
            klines_results = await asyncio.gather(
                *[_fetch_klines(client, sym) for sym in symbols],
                return_exceptions=True,
            )

            changes_1d: list[float] = []
            changes_7d: list[float] = []
            symbol_scores: list[tuple[str, float]] = []

            for sym, candles in zip(symbols, klines_results):
                if isinstance(candles, Exception) or not candles or len(candles) < 2:
                    continue
                try:
                    close = [float(c[4]) for c in candles]
                    change_1d = (close[-1] - close[-2]) / close[-2] * 100
                    change_7d = (close[-1] - close[0]) / close[0] * 100
                    changes_1d.append(change_1d)
                    changes_7d.append(change_7d)
                    score = change_1d * 0.4 + change_7d * 0.6
                    symbol_scores.append((sym.replace("USDT", ""), score))
                except (IndexError, ZeroDivisionError, ValueError):
                    continue

            if not changes_1d:
                continue

            avg_1d = float(np.mean(changes_1d))
            avg_7d = float(np.mean(changes_7d))
            momentum = avg_1d * 0.4 + avg_7d * 0.6

            symbol_scores.sort(key=lambda x: x[1], reverse=True)
            top = [s[0] for s in symbol_scores[:3]]

            results.append(
                SectorMetrics(
                    sector=sector,
                    momentum_score=round(momentum, 2),
                    avg_1d_change=round(avg_1d, 2),
                    avg_7d_change=round(avg_7d, 2),
                    top_performers=top,
                    symbol_count=len(changes_1d),
                )
            )

    results.sort(key=lambda x: x.momentum_score, reverse=True)
    _cache = {"data": results}
    _cache_time = now
    return results
