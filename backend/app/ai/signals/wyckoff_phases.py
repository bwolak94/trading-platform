"""Wyckoff Phase Detector — identifies accumulation and distribution phases.

Implements the Wyckoff Method's key events:

Accumulation:
  PS  – Preliminary Support: first significant buying after a downtrend
  SC  – Selling Climax: volume/price climax on the downside
  AR  – Automatic Rally: bounce from SC (accumulation) or drop from BC (distribution)
  ST  – Secondary Test: retest of SC/BC area on lower volume
  Spring – false break below support to trap shorts
  LPS – Last Point of Support: higher low before mark-up
  SOS – Sign of Strength: strong up-bar with volume confirming accumulation

Distribution:
  PSY  – Preliminary Supply: first significant selling after an uptrend
  BC   – Buying Climax: volume/price climax on the upside
  UT   – Upthrust: false break above resistance to trap longs
  LPSY – Last Point of Supply: lower high before mark-down
  SOW  – Sign of Weakness: strong down-bar with volume confirming distribution
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import pandas as pd

from app.core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_VOLUME_CLIMAX_MULTIPLIER: Final[float] = 3.0   # volume > 3× rolling mean
_VOLUME_ROLLING_WINDOW: Final[int] = 20
_SUPPORT_RESISTANCE_WINDOW: Final[int] = 20
_SPRING_UPTHRUST_TOLERANCE_PCT: Final[float] = 0.5  # 0.5% break beyond range
_MIN_CANDLES: Final[int] = 100


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class WyckoffResult:
    """Detected Wyckoff phase with metadata."""

    phase: str        # e.g. "ACCUMULATION_SPRING", "DISTRIBUTION_BC", "NEUTRAL"
    subphase: str     # specific event label
    confidence: float  # 0–100
    description: str
    is_bullish: bool
    key_level: float  # price level associated with the detected pattern

    def __repr__(self) -> str:
        bias = "BULLISH" if self.is_bullish else "BEARISH"
        return (
            f"WyckoffResult(phase={self.phase!r}, subphase={self.subphase!r}, "
            f"confidence={self.confidence:.1f}, bias={bias}, key_level={self.key_level:.4f})"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_down_bar(row: pd.Series) -> bool:
    """Return True if the candle closed below its open (bearish bar)."""
    return float(row["close"]) < float(row["open"])


def _is_up_bar(row: pd.Series) -> bool:
    """Return True if the candle closed above its open (bullish bar)."""
    return float(row["close"]) > float(row["open"])


def _bar_range(row: pd.Series) -> float:
    """High minus low of a single candle."""
    return float(row["high"]) - float(row["low"])


def _rolling_support(df: pd.DataFrame, window: int) -> pd.Series:
    """Rolling minimum of lows — acts as dynamic support level."""
    return df["low"].rolling(window).min()


def _rolling_resistance(df: pd.DataFrame, window: int) -> pd.Series:
    """Rolling maximum of highs — acts as dynamic resistance level."""
    return df["high"].rolling(window).max()


def _volume_climax_mask(df: pd.DataFrame, window: int, multiplier: float) -> pd.Series:
    """Boolean mask: True where volume is a climax spike (> multiplier × rolling mean)."""
    vol_mean = df["volume"].rolling(window).mean()
    return df["volume"] > (vol_mean * multiplier)


def _large_range_mask(df: pd.DataFrame, window: int) -> pd.Series:
    """Boolean mask: True where the candle range is above the rolling average range."""
    candle_range = df["high"] - df["low"]
    avg_range = candle_range.rolling(window).mean()
    return candle_range > avg_range


def _confidence_from_factors(
    volume_ratio: float,
    range_ratio: float,
    zone_proximity_pct: float,
) -> float:
    """Compute confidence (0–100) from three quality factors.

    Args:
        volume_ratio:       current_volume / rolling_mean_volume
        range_ratio:        current_range / rolling_mean_range
        zone_proximity_pct: how close the price is to a key zone (0 = perfect, higher = worse)

    Returns:
        Confidence score 0–100.
    """
    # Volume contribution: max 40 points
    vol_score = min(40.0, (volume_ratio / _VOLUME_CLIMAX_MULTIPLIER) * 40.0)

    # Range contribution: max 35 points
    range_score = min(35.0, range_ratio * 17.5)

    # Proximity contribution: max 25 points (inverse of distance)
    proximity_score = max(0.0, 25.0 - zone_proximity_pct * 5.0)

    return round(min(100.0, vol_score + range_score + proximity_score), 1)


# ---------------------------------------------------------------------------
# Main detector class
# ---------------------------------------------------------------------------


class WyckoffPhaseDetector:
    """Detects Wyckoff accumulation/distribution phases from OHLCV data.

    Detection priority (first match wins):
      1. Selling Climax   (ACCUMULATION_SC)
      2. Buying Climax    (DISTRIBUTION_BC)
      3. Spring           (ACCUMULATION_SPRING)
      4. Upthrust         (DISTRIBUTION_UT)
      5. Sign of Strength (ACCUMULATION_SOS)
      6. Sign of Weakness (DISTRIBUTION_SOW)
      7. Secondary Test   (NEUTRAL_ST)
      8. NEUTRAL
    """

    def detect(self, df: pd.DataFrame) -> WyckoffResult:
        """Detect the most recent Wyckoff event in the OHLCV data.

        Args:
            df: OHLCV DataFrame with columns open, high, low, close, volume.
                Minimum 100 candles required for reliable detection.

        Returns:
            WyckoffResult describing the detected phase, confidence, and key level.
        """
        if df is None or len(df) < _MIN_CANDLES:
            logger.warning(
                "WyckoffPhaseDetector: insufficient data (%d candles, need %d)",
                len(df) if df is not None else 0,
                _MIN_CANDLES,
            )
            return WyckoffResult(
                phase="NEUTRAL",
                subphase="INSUFFICIENT_DATA",
                confidence=0.0,
                description=f"Need at least {_MIN_CANDLES} candles.",
                is_bullish=False,
                key_level=float(df["close"].iloc[-1]) if df is not None and len(df) else 0.0,
            )

        df = df.copy().reset_index(drop=True)

        # Pre-compute rolling series once
        vol_mean = df["volume"].rolling(_VOLUME_ROLLING_WINDOW).mean()
        candle_range = df["high"] - df["low"]
        range_mean = candle_range.rolling(_VOLUME_ROLLING_WINDOW).mean()
        support = _rolling_support(df, _SUPPORT_RESISTANCE_WINDOW)
        resistance = _rolling_resistance(df, _SUPPORT_RESISTANCE_WINDOW)
        climax_mask = _volume_climax_mask(df, _VOLUME_ROLLING_WINDOW, _VOLUME_CLIMAX_MULTIPLIER)
        large_range_m = _large_range_mask(df, _VOLUME_ROLLING_WINDOW)

        # Focus on recent candles (last 20) for event detection
        recent_start = max(_VOLUME_ROLLING_WINDOW, len(df) - 20)
        recent_idx = range(recent_start, len(df))

        current_price = float(df["close"].iloc[-1])

        # --- 1. Selling Climax (SC) → ACCUMULATION -----------------------
        # Volume climax + down bar + price near/at rolling support
        for i in reversed(recent_idx):
            if not (climax_mask.iloc[i] and large_range_m.iloc[i] and _is_down_bar(df.iloc[i])):
                continue
            sup = support.iloc[i]
            if sup <= 0:
                continue
            proximity_pct = abs(float(df["low"].iloc[i]) - sup) / sup * 100
            if proximity_pct > 2.0:
                continue
            vol_ratio = float(df["volume"].iloc[i]) / max(float(vol_mean.iloc[i]), 1e-9)
            range_ratio = float(candle_range.iloc[i]) / max(float(range_mean.iloc[i]), 1e-9)
            confidence = _confidence_from_factors(vol_ratio, range_ratio, proximity_pct)
            logger.info("Wyckoff SC detected", extra={"confidence": confidence, "key_level": sup})
            return WyckoffResult(
                phase="ACCUMULATION_SC",
                subphase="SELLING_CLIMAX",
                confidence=confidence,
                description=(
                    f"Selling Climax detected: volume {vol_ratio:.1f}× average on large "
                    f"down-bar near support {sup:.4f}. Classic accumulation entry signal."
                ),
                is_bullish=True,
                key_level=round(sup, 6),
            )

        # --- 2. Buying Climax (BC) → DISTRIBUTION ------------------------
        for i in reversed(recent_idx):
            if not (climax_mask.iloc[i] and large_range_m.iloc[i] and _is_up_bar(df.iloc[i])):
                continue
            res = resistance.iloc[i]
            if res <= 0:
                continue
            proximity_pct = abs(float(df["high"].iloc[i]) - res) / res * 100
            if proximity_pct > 2.0:
                continue
            vol_ratio = float(df["volume"].iloc[i]) / max(float(vol_mean.iloc[i]), 1e-9)
            range_ratio = float(candle_range.iloc[i]) / max(float(range_mean.iloc[i]), 1e-9)
            confidence = _confidence_from_factors(vol_ratio, range_ratio, proximity_pct)
            logger.info("Wyckoff BC detected", extra={"confidence": confidence, "key_level": res})
            return WyckoffResult(
                phase="DISTRIBUTION_BC",
                subphase="BUYING_CLIMAX",
                confidence=confidence,
                description=(
                    f"Buying Climax detected: volume {vol_ratio:.1f}× average on large "
                    f"up-bar near resistance {res:.4f}. Classic distribution signal."
                ),
                is_bullish=False,
                key_level=round(res, 6),
            )

        # --- 3. Spring (price breaks below support, closes back above) ---
        last_support = float(support.iloc[-1]) if support.iloc[-1] > 0 else None
        if last_support:
            for i in reversed(recent_idx):
                low_i = float(df["low"].iloc[i])
                close_i = float(df["close"].iloc[i])
                broke_below = low_i < last_support * (1 - _SPRING_UPTHRUST_TOLERANCE_PCT / 100)
                closed_above = close_i > last_support
                if broke_below and closed_above:
                    vol_ratio = float(df["volume"].iloc[i]) / max(float(vol_mean.iloc[i]), 1e-9)
                    proximity_pct = abs(close_i - last_support) / last_support * 100
                    range_ratio = float(candle_range.iloc[i]) / max(float(range_mean.iloc[i]), 1e-9)
                    confidence = _confidence_from_factors(vol_ratio, range_ratio, proximity_pct)
                    logger.info("Wyckoff Spring detected", extra={"key_level": last_support})
                    return WyckoffResult(
                        phase="ACCUMULATION_SPRING",
                        subphase="SPRING",
                        confidence=confidence,
                        description=(
                            f"Spring detected: price briefly broke below support "
                            f"{last_support:.4f} then closed back above — shorts trapped. "
                            "High-probability long setup."
                        ),
                        is_bullish=True,
                        key_level=round(last_support, 6),
                    )

        # --- 4. Upthrust (price breaks above resistance, closes back below) ---
        last_resistance = float(resistance.iloc[-1]) if resistance.iloc[-1] > 0 else None
        if last_resistance:
            for i in reversed(recent_idx):
                high_i = float(df["high"].iloc[i])
                close_i = float(df["close"].iloc[i])
                broke_above = high_i > last_resistance * (1 + _SPRING_UPTHRUST_TOLERANCE_PCT / 100)
                closed_below = close_i < last_resistance
                if broke_above and closed_below:
                    vol_ratio = float(df["volume"].iloc[i]) / max(float(vol_mean.iloc[i]), 1e-9)
                    proximity_pct = abs(close_i - last_resistance) / last_resistance * 100
                    range_ratio = float(candle_range.iloc[i]) / max(float(range_mean.iloc[i]), 1e-9)
                    confidence = _confidence_from_factors(vol_ratio, range_ratio, proximity_pct)
                    logger.info("Wyckoff UT detected", extra={"key_level": last_resistance})
                    return WyckoffResult(
                        phase="DISTRIBUTION_UT",
                        subphase="UPTHRUST",
                        confidence=confidence,
                        description=(
                            f"Upthrust detected: price briefly broke above resistance "
                            f"{last_resistance:.4f} then closed back below — longs trapped. "
                            "High-probability short setup."
                        ),
                        is_bullish=False,
                        key_level=round(last_resistance, 6),
                    )

        # --- 5. Sign of Strength (SOS) — strong up-bar after potential accumulation ---
        for i in reversed(recent_idx):
            if not (_is_up_bar(df.iloc[i]) and large_range_m.iloc[i]):
                continue
            vol_ratio = float(df["volume"].iloc[i]) / max(float(vol_mean.iloc[i]), 1e-9)
            if vol_ratio < 1.5:
                continue
            close_i = float(df["close"].iloc[i])
            if last_resistance and close_i > last_resistance * 0.98:
                confidence = _confidence_from_factors(vol_ratio, float(candle_range.iloc[i]) / max(float(range_mean.iloc[i]), 1e-9), 0.5)
                logger.info("Wyckoff SOS detected", extra={"confidence": confidence})
                return WyckoffResult(
                    phase="ACCUMULATION_SOS",
                    subphase="SIGN_OF_STRENGTH",
                    confidence=confidence,
                    description=(
                        f"Sign of Strength: strong up-bar ({vol_ratio:.1f}× average volume) "
                        "approaching resistance — accumulation phase may be completing."
                    ),
                    is_bullish=True,
                    key_level=round(close_i, 6),
                )

        # --- 6. Sign of Weakness (SOW) — strong down-bar after potential distribution ---
        for i in reversed(recent_idx):
            if not (_is_down_bar(df.iloc[i]) and large_range_m.iloc[i]):
                continue
            vol_ratio = float(df["volume"].iloc[i]) / max(float(vol_mean.iloc[i]), 1e-9)
            if vol_ratio < 1.5:
                continue
            close_i = float(df["close"].iloc[i])
            if last_support and close_i < last_support * 1.02:
                confidence = _confidence_from_factors(vol_ratio, float(candle_range.iloc[i]) / max(float(range_mean.iloc[i]), 1e-9), 0.5)
                logger.info("Wyckoff SOW detected", extra={"confidence": confidence})
                return WyckoffResult(
                    phase="DISTRIBUTION_SOW",
                    subphase="SIGN_OF_WEAKNESS",
                    confidence=confidence,
                    description=(
                        f"Sign of Weakness: strong down-bar ({vol_ratio:.1f}× average volume) "
                        "approaching support — distribution phase may be completing."
                    ),
                    is_bullish=False,
                    key_level=round(close_i, 6),
                )

        # --- 7. Secondary Test (ST) — low-volume retest of SC/BC area ---
        # Detect as price returning near a recent extreme on low volume
        recent_vol_ratio = float(df["volume"].iloc[-1]) / max(float(vol_mean.iloc[-1]), 1e-9)
        if recent_vol_ratio < 0.7:  # volume contraction on retest
            if last_support and abs(current_price - last_support) / last_support * 100 < 1.5:
                return WyckoffResult(
                    phase="ACCUMULATION_ST",
                    subphase="SECONDARY_TEST",
                    confidence=45.0,
                    description=(
                        f"Secondary Test near support {last_support:.4f} on reduced volume "
                        f"({recent_vol_ratio:.2f}× avg). Watch for successful test to confirm accumulation."
                    ),
                    is_bullish=True,
                    key_level=round(last_support, 6),
                )
            if last_resistance and abs(current_price - last_resistance) / last_resistance * 100 < 1.5:
                return WyckoffResult(
                    phase="DISTRIBUTION_ST",
                    subphase="SECONDARY_TEST",
                    confidence=45.0,
                    description=(
                        f"Secondary Test near resistance {last_resistance:.4f} on reduced volume "
                        f"({recent_vol_ratio:.2f}× avg). Watch for rejection to confirm distribution."
                    ),
                    is_bullish=False,
                    key_level=round(last_resistance, 6),
                )

        logger.debug("Wyckoff: no strong phase detected, returning NEUTRAL")
        return WyckoffResult(
            phase="NEUTRAL",
            subphase="NO_EVENT",
            confidence=0.0,
            description="No clear Wyckoff phase event detected in the recent candles.",
            is_bullish=False,
            key_level=round(current_price, 6),
        )
