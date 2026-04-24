"""Fibonacci Confluence Zone Detector.

Finds price zones where two or more Fibonacci levels from different swing
pairs converge within a tight tolerance.  Zones with higher confluence scores
(more levels clustering) represent stronger support/resistance.

Algorithm:
  1. Detect major swing highs and lows (local extremes with 5-candle prominence).
  2. For each swing high–low pair compute retracement levels.
  3. For each pair where price extended beyond the swing: compute extensions.
  4. Cluster all levels within CLUSTER_TOLERANCE_PCT of each other.
  5. Return zones sorted by confluence_score descending.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

import numpy as np
import pandas as pd

from app.core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FIB_RATIOS: Final[list[float]] = [0.236, 0.382, 0.5, 0.618, 0.786, 1.0, 1.272, 1.618, 2.618]
FIB_EXTENSION_RATIOS: Final[list[float]] = [1.272, 1.618, 2.0, 2.618]

_SWING_WINDOW: Final[int] = 5       # look-back/forward candles for swing detection
_MIN_PROMINENCE_PCT: Final[float] = 0.5  # minimum swing prominence as % of price
_MIN_CANDLES: Final[int] = 30


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class FibLevel:
    """A single Fibonacci level derived from a swing pair."""

    price: float
    ratio: float
    swing_high: float
    swing_low: float
    fib_type: str  # "RETRACEMENT" or "EXTENSION"

    def __repr__(self) -> str:
        return f"FibLevel(price={self.price:.4f}, ratio={self.ratio}, type={self.fib_type})"


@dataclass
class FibConfluenceZone:
    """A price zone where multiple Fibonacci levels converge."""

    price_center: float
    price_high: float
    price_low: float
    confluence_score: int        # number of converging fib levels
    levels: list[FibLevel] = field(default_factory=list)
    is_support: bool = True      # True = below current price (support), False = resistance
    strength: str = "WEAK"       # "WEAK" (2), "MODERATE" (3), "STRONG" (4+)

    def __repr__(self) -> str:
        return (
            f"FibConfluenceZone(center={self.price_center:.4f}, "
            f"score={self.confluence_score}, strength={self.strength}, "
            f"{'support' if self.is_support else 'resistance'})"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _detect_swings(df: pd.DataFrame, window: int, min_prominence_pct: float) -> tuple[list[int], list[int]]:
    """Detect swing highs and swing lows.

    A swing high at index i requires:  df['high'][i] > df['high'][i-k] for k in 1..window
                                   AND df['high'][i] > df['high'][i+k] for k in 1..window
                                   AND prominence > min_prominence_pct

    Args:
        df:                  OHLCV DataFrame.
        window:              Candles on each side for local-extreme check.
        min_prominence_pct:  Minimum prominence as % of the candle price.

    Returns:
        Tuple of (swing_high_indices, swing_low_indices).
    """
    highs: list[int] = []
    lows: list[int] = []
    n = len(df)
    prices_high = df["high"].to_numpy(dtype=float)
    prices_low = df["low"].to_numpy(dtype=float)

    for i in range(window, n - window):
        left_h = prices_high[i - window : i]
        right_h = prices_high[i + 1 : i + window + 1]
        if prices_high[i] > left_h.max() and prices_high[i] > right_h.max():
            # Check prominence
            near_low = min(prices_low[i - window : i + window + 1].min(), prices_low[i])
            prominence_pct = (prices_high[i] - near_low) / prices_high[i] * 100
            if prominence_pct >= min_prominence_pct:
                highs.append(i)

        left_l = prices_low[i - window : i]
        right_l = prices_low[i + 1 : i + window + 1]
        if prices_low[i] < left_l.min() and prices_low[i] < right_l.min():
            near_high = max(prices_high[i - window : i + window + 1].max(), prices_high[i])
            prominence_pct = (near_high - prices_low[i]) / near_high * 100
            if prominence_pct >= min_prominence_pct:
                lows.append(i)

    return highs, lows


def _fib_retracements(swing_high: float, swing_low: float) -> list[FibLevel]:
    """Return Fibonacci retracement levels for a given swing.

    Retracement levels are measured from swing_high down to swing_low.
    """
    levels: list[FibLevel] = []
    diff = swing_high - swing_low
    if diff <= 0:
        return levels
    for ratio in FIB_RATIOS:
        price = swing_high - ratio * diff
        levels.append(
            FibLevel(
                price=round(price, 8),
                ratio=ratio,
                swing_high=swing_high,
                swing_low=swing_low,
                fib_type="RETRACEMENT",
            )
        )
    return levels


def _fib_extensions(swing_high: float, swing_low: float, direction: str) -> list[FibLevel]:
    """Return Fibonacci extension levels.

    For an upward impulse (direction='UP'), extensions project above swing_high.
    For a downward impulse (direction='DOWN'), extensions project below swing_low.
    """
    levels: list[FibLevel] = []
    diff = swing_high - swing_low
    if diff <= 0:
        return levels
    for ratio in FIB_EXTENSION_RATIOS:
        if direction == "UP":
            price = swing_low + ratio * diff
        else:
            price = swing_high - ratio * diff
        levels.append(
            FibLevel(
                price=round(price, 8),
                ratio=ratio,
                swing_high=swing_high,
                swing_low=swing_low,
                fib_type="EXTENSION",
            )
        )
    return levels


def _cluster_levels(
    all_levels: list[FibLevel],
    tolerance_pct: float,
    current_price: float,
) -> list[FibConfluenceZone]:
    """Group Fibonacci levels into confluence zones.

    Two levels belong to the same cluster if their prices differ by less than
    tolerance_pct percent.

    Args:
        all_levels:     Flat list of all FibLevel objects.
        tolerance_pct:  Maximum % distance between levels to be considered clustered.
        current_price:  Used to classify zones as support or resistance.

    Returns:
        List of FibConfluenceZone with at least 2 converging levels.
    """
    if not all_levels:
        return []

    # Sort levels by price
    sorted_levels = sorted(all_levels, key=lambda lv: lv.price)
    clusters: list[list[FibLevel]] = []
    current_cluster: list[FibLevel] = [sorted_levels[0]]

    for lv in sorted_levels[1:]:
        ref_price = current_cluster[0].price
        if ref_price == 0:
            current_cluster.append(lv)
            continue
        diff_pct = abs(lv.price - ref_price) / ref_price * 100
        if diff_pct <= tolerance_pct:
            current_cluster.append(lv)
        else:
            clusters.append(current_cluster)
            current_cluster = [lv]
    clusters.append(current_cluster)

    zones: list[FibConfluenceZone] = []
    for cluster in clusters:
        if len(cluster) < 2:
            continue  # need at least 2 levels for confluence
        prices = [lv.price for lv in cluster]
        center = float(np.mean(prices))
        zone_high = float(np.max(prices))
        zone_low = float(np.min(prices))
        score = len(cluster)
        strength = "STRONG" if score >= 4 else ("MODERATE" if score >= 3 else "WEAK")

        zones.append(
            FibConfluenceZone(
                price_center=round(center, 8),
                price_high=round(zone_high, 8),
                price_low=round(zone_low, 8),
                confluence_score=score,
                levels=cluster,
                is_support=center < current_price,
                strength=strength,
            )
        )

    return zones


# ---------------------------------------------------------------------------
# Main detector class
# ---------------------------------------------------------------------------


class FibConfluenceDetector:
    """Detects price zones where multiple Fibonacci levels converge."""

    CLUSTER_TOLERANCE_PCT: float = 0.3  # levels within 0.3% are clustered

    def detect(
        self,
        df: pd.DataFrame,
        lookback_swings: int = 5,
    ) -> list[FibConfluenceZone]:
        """Find Fibonacci confluence zones in the given OHLCV data.

        Args:
            df:              OHLCV DataFrame.  Needs at least 30 candles.
            lookback_swings: Maximum number of recent swing pairs to process.
                             Higher values generate more levels but may be noisier.

        Returns:
            List of FibConfluenceZone sorted by confluence_score descending.
        """
        if df is None or len(df) < _MIN_CANDLES:
            logger.warning(
                "FibConfluenceDetector: insufficient data (%d candles, need %d)",
                len(df) if df is not None else 0,
                _MIN_CANDLES,
            )
            return []

        df = df.copy().reset_index(drop=True)
        current_price = float(df["close"].iloc[-1])

        swing_highs, swing_lows = _detect_swings(df, _SWING_WINDOW, _MIN_PROMINENCE_PCT)

        # Limit to the most recent N swings
        recent_highs = swing_highs[-lookback_swings:]
        recent_lows = swing_lows[-lookback_swings:]

        if not recent_highs or not recent_lows:
            logger.info("FibConfluenceDetector: no swings detected")
            return []

        all_levels: list[FibLevel] = []

        # Generate retracements from every high–low pair
        for hi in recent_highs:
            for lo in recent_lows:
                sh = float(df["high"].iloc[hi])
                sl = float(df["low"].iloc[lo])
                if sh <= sl:
                    continue
                all_levels.extend(_fib_retracements(sh, sl))

                # Extensions: if the recent trend is up (lo < hi in time), project up
                if lo < hi:
                    all_levels.extend(_fib_extensions(sh, sl, direction="UP"))
                else:
                    all_levels.extend(_fib_extensions(sh, sl, direction="DOWN"))

        if not all_levels:
            return []

        zones = _cluster_levels(all_levels, self.CLUSTER_TOLERANCE_PCT, current_price)

        # Sort by confluence score descending
        zones.sort(key=lambda z: z.confluence_score, reverse=True)

        logger.info(
            "FibConfluenceDetector: detected %d confluence zones (strongest score=%d)",
            len(zones),
            zones[0].confluence_score if zones else 0,
        )
        return zones
