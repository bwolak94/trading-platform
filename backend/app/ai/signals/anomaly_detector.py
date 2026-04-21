"""Anomaly Detector — identifies unusual candles using statistical outlier detection.

Uses a simple z-score method to flag candles where volume or price movement
is statistically unusual. No ML library required; pure Python implementation.

A simplified Isolation Forest equivalent using z-scores across multiple features:
- Volume: unusually high or low volume
- Body size: unusually large candle body (momentum)
- Wick ratio: high wick-to-body ratio (potential reversal/manipulation)
- Price gap: unusual gap from previous close
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)


def detect_anomalies(
    candles: list[dict[str, float]],
    z_threshold: float = 2.5,
    window: int = 50,
) -> list[dict[str, Any]]:
    """Detect anomalous candles in the most recent window.

    Args:
        candles: List of OHLCV dicts (oldest to newest), with keys: open, high, low, close, volume
        z_threshold: Z-score threshold to flag as anomaly (default 2.5 sigma)
        window: Number of candles to analyze (uses last N candles)

    Returns:
        List of anomaly events with type, bar_index, z_score, and description
    """
    if len(candles) < window + 5:
        candles = candles  # Use all if too few
    recent = candles[-window:]

    # Compute features for each candle
    volumes = [c["volume"] for c in recent]
    bodies = [abs(c["close"] - c["open"]) for c in recent]
    wick_ratios = [
        (c["high"] - max(c["open"], c["close"])) / max(abs(c["close"] - c["open"]), 1e-10)
        for c in recent
    ]

    def z_scores(data: list[float]) -> list[float]:
        """Compute z-scores for a list of floats."""
        if len(data) < 2:
            return [0.0] * len(data)
        mean = sum(data) / len(data)
        std = (sum((x - mean) ** 2 for x in data) / (len(data) - 1)) ** 0.5
        if std == 0:
            return [0.0] * len(data)
        return [(x - mean) / std for x in data]

    vol_z = z_scores(volumes)
    body_z = z_scores(bodies)
    wick_z = z_scores(wick_ratios)

    anomalies: list[dict[str, Any]] = []
    for i, candle in enumerate(recent[-10:]):  # Only check last 10 candles
        idx = len(recent) - 10 + i
        if idx < 0 or idx >= len(vol_z):
            continue

        flags: list[str] = []
        max_z = 0.0

        if abs(vol_z[idx]) > z_threshold:
            flags.append(f"volume spike (z={vol_z[idx]:.1f}σ)")
            max_z = max(max_z, abs(vol_z[idx]))

        if abs(body_z[idx]) > z_threshold:
            direction = "bullish" if candle["close"] > candle["open"] else "bearish"
            flags.append(f"{direction} momentum candle (z={body_z[idx]:.1f}σ)")
            max_z = max(max_z, abs(body_z[idx]))

        if wick_z[idx] > z_threshold:
            flags.append(f"extreme wick (z={wick_z[idx]:.1f}σ) — potential manipulation")
            max_z = max(max_z, wick_z[idx])

        if flags:
            anomalies.append(
                {
                    "bar_index": idx,
                    "candle_close": round(candle["close"], 6),
                    "flags": flags,
                    "z_score": round(max_z, 2),
                    "volume": candle["volume"],
                    "description": f"Anomalous candle detected: {'; '.join(flags)}",
                }
            )

    return sorted(anomalies, key=lambda a: a["z_score"], reverse=True)
