"""Multi-Timeframe Confluence Detector.

Fetches signals across 1h, 4h, and 1D timeframes for a given symbol.
Returns an mtf_score (0-3) and aligned_timeframes list.
A higher score means more timeframes agree on direction.
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

_TF_WEIGHTS = {
    "1h": 0.3,
    "4h": 0.4,
    "1d": 0.3,
}


async def get_mtf_confluence(symbol: str, primary_direction: str) -> dict[str, Any]:
    """Compute multi-timeframe confluence for a given symbol and direction.

    Args:
        symbol: Asset symbol (e.g. "BTCUSDT")
        primary_direction: "LONG" or "SHORT"

    Returns:
        dict with:
            mtf_score: float 0.0–1.0 (weighted confluence)
            aligned_timeframes: list of TFs agreeing with direction
            confidence_boost: int (+0 to +20) to add to signal confidence
    """
    aligned: list[str] = []
    total_weight = 0.0

    for tf, weight in _TF_WEIGHTS.items():
        try:
            direction = await _get_tf_direction(symbol, tf)
            if direction == primary_direction:
                aligned.append(tf)
                total_weight += weight
        except Exception as exc:
            logger.debug("MTF check failed for %s %s: %s", symbol, tf, exc)

    confidence_boost = int(total_weight * 20)  # up to +20 when all 3 TFs align

    return {
        "mtf_score": round(total_weight, 2),
        "aligned_timeframes": aligned,
        "confidence_boost": confidence_boost,
    }


async def _get_tf_direction(symbol: str, interval: str) -> str | None:
    """Determine trend direction for a symbol on a given timeframe.

    Uses EMA20 vs EMA50 cross and RSI to determine direction.
    Returns 'LONG', 'SHORT', or None if no clear direction.
    """
    from app.data.fetchers.binance_fetcher import BinanceFetcher

    fetcher = BinanceFetcher(symbol=symbol, interval=interval)
    try:
        candles = await fetcher.fetch_historical_ohlcv(limit=60)
        if not candles or len(candles) < 50:
            return None

        closes = [c["close"] for c in candles]

        # EMA calculation
        ema20 = _ema(closes, 20)
        ema50 = _ema(closes, 50)

        if ema20 is None or ema50 is None:
            return None

        # RSI
        rsi = _rsi(closes[-15:], 14)

        if ema20 > ema50 and rsi and rsi > 45:
            return "LONG"
        elif ema20 < ema50 and rsi and rsi < 55:
            return "SHORT"
    except Exception as exc:
        logger.debug("TF direction check failed %s %s: %s", symbol, interval, exc)
    return None


def _ema(values: list[float], period: int) -> float | None:
    """Calculate EMA for the last value in the series."""
    if len(values) < period:
        return None
    k = 2 / (period + 1)
    ema = sum(values[:period]) / period
    for v in values[period:]:
        ema = v * k + ema * (1 - k)
    return ema


def _rsi(closes: list[float], period: int = 14) -> float | None:
    """Calculate RSI from a list of close prices."""
    if len(closes) < period + 1:
        return None
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [d for d in deltas if d > 0]
    losses = [-d for d in deltas if d < 0]
    avg_gain = sum(gains[-period:]) / period if gains else 0
    avg_loss = sum(losses[-period:]) / period if losses else 1e-10
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))
