"""Momentum Scorer — ranks all Binance futures by multi-timeframe momentum.

Scoring components per timeframe:
  - Price vs 20 EMA: above = +1, below = -1 (normalized 0-1)
  - ROC-5 (5-bar rate of change): normalized vs all symbols
  - ROC-20: normalized vs all symbols
  - RSI: (RSI - 50) / 50, capped ±1

Weighted average: 1h × 30% + 4h × 40% + 1d × 30%

Cached for 15 minutes to avoid excessive API calls.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from app.core.logging import get_logger
from app.core.symbols import get_active_crypto_symbols

logger = get_logger(__name__)

_CACHE_TTL = 900  # 15 minutes
_cache: list[dict[str, Any]] | None = None
_cache_ts: datetime | None = None

_TF_WEIGHTS = {"1h": 0.30, "4h": 0.40, "1d": 0.30}


async def get_momentum_rankings(top_n: int = 20) -> list[dict[str, Any]]:
    """Return top N symbols ranked by momentum score.

    Args:
        top_n: Number of top symbols to return (sorted by |score| descending)

    Returns:
        List of {symbol, score, direction, tf_scores} sorted by |score| descending
    """
    global _cache, _cache_ts

    now = datetime.now(timezone.utc)
    if _cache and _cache_ts and (now - _cache_ts).total_seconds() < _CACHE_TTL:
        return _cache[:top_n]

    symbols = list(get_active_crypto_symbols())[:30]  # limit for speed
    results = await asyncio.gather(
        *[_score_symbol(sym) for sym in symbols],
        return_exceptions=True,
    )

    rankings: list[dict[str, Any]] = []
    for sym, result in zip(symbols, results):
        if isinstance(result, Exception) or result is None:
            continue
        rankings.append(result)

    # Sort by absolute score (strong signals in either direction first)
    rankings.sort(key=lambda x: abs(x.get("score", 0)), reverse=True)
    _cache = rankings
    _cache_ts = now
    return rankings[:top_n]


async def _score_symbol(symbol: str) -> dict[str, Any] | None:
    """Compute momentum score for a single symbol across timeframes.

    Args:
        symbol: Binance trading pair symbol (e.g. BTCUSDT)

    Returns:
        Dict with symbol, score, direction, and per-timeframe scores, or None on failure
    """
    tf_scores: dict[str, float] = {}
    total = 0.0

    for tf, weight in _TF_WEIGHTS.items():
        try:
            score = await _tf_momentum_score(symbol, tf)
            if score is not None:
                tf_scores[tf] = round(score, 3)
                total += score * weight
        except Exception as exc:
            logger.debug("Momentum score failed %s %s: %s", symbol, tf, exc)

    if not tf_scores:
        return None

    return {
        "symbol": symbol,
        "score": round(total, 3),
        "direction": "LONG" if total > 0.1 else ("SHORT" if total < -0.1 else "NEUTRAL"),
        "tf_scores": tf_scores,
    }


async def _tf_momentum_score(symbol: str, interval: str) -> float | None:
    """Compute single-timeframe momentum score (range -1 to +1).

    Args:
        symbol: Trading pair symbol
        interval: Kline interval string (e.g. '1h', '4h', '1d')

    Returns:
        Momentum score in range [-1.0, 1.0], or None if insufficient data
    """
    from app.data.fetchers.binance_fetcher import BinanceFetcher

    fetcher = BinanceFetcher(symbol=symbol, interval=interval)
    candles = await fetcher.fetch_historical_ohlcv(limit=50)
    if not candles or len(candles) < 25:
        return None

    closes = [float(c["close"]) for c in candles]
    current = closes[-1]

    # EMA20
    k = 2 / 21
    ema20 = sum(closes[:20]) / 20
    for v in closes[20:]:
        ema20 = v * k + ema20 * (1 - k)
    ema_signal = 1.0 if current > ema20 else -1.0

    # ROC-5
    roc5 = (closes[-1] - closes[-6]) / closes[-6] if closes[-6] != 0 else 0.0
    roc5_norm = max(-1.0, min(1.0, roc5 * 20))  # scale ±5% → ±1

    # ROC-20
    roc20 = (closes[-1] - closes[-21]) / closes[-21] if closes[-21] != 0 else 0.0
    roc20_norm = max(-1.0, min(1.0, roc20 * 10))  # scale ±10% → ±1

    # RSI
    rsi = _rsi(closes[-16:], 14)
    rsi_norm = (rsi - 50) / 50 if rsi else 0.0
    rsi_norm = max(-1.0, min(1.0, rsi_norm))

    # Weighted composite
    score = ema_signal * 0.3 + roc5_norm * 0.3 + roc20_norm * 0.2 + rsi_norm * 0.2
    return score


def _rsi(closes: list[float], period: int = 14) -> float:
    """Compute single RSI value from the last `period` deltas.

    Args:
        closes: List of close prices (needs at least period + 1 values)
        period: RSI period

    Returns:
        RSI value in range [0, 100], defaults to 50.0 on insufficient data
    """
    if len(closes) <= period:
        return 50.0
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = sum(max(d, 0) for d in deltas[-period:]) / period
    losses = sum(-min(d, 0) for d in deltas[-period:]) / period
    rs = gains / losses if losses > 0 else 100
    return 100 - 100 / (1 + rs)
