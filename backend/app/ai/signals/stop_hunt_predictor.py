"""Stop Hunt Predictor — predicts WHERE the next stop run will occur."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class StopCluster:
    """Represents a price level with a concentration of estimated stop orders."""

    price: float
    estimated_stops: int      # number of estimated stop orders (touches × weight)
    side: str                 # "LONG_STOPS" (below price) or "SHORT_STOPS" (above price)
    distance_pct: float       # % away from current price
    cluster_strength: float   # 0-100


@dataclass
class StopHuntPrediction:
    """Full stop hunt prediction for a symbol."""

    symbol: str
    likely_hunt_direction: str   # "UP" (hunting short stops) or "DOWN" (hunting long stops)
    confidence: float
    target_price: float          # predicted hunt target
    nearest_cluster: StopCluster
    setup_quality: str           # "A" / "B" / "C"
    expected_timing: str         # "IMMINENT" (<2 candles), "SOON" (2-10), "PENDING"
    description: str


class StopHuntPredictor:
    """Predict stop hunt locations using price structure and volume.

    Logic:
    1. Identify swing highs/lows from the last 50 candles.
    2. Find "equal highs" or "equal lows" (two touches at the same level ± 0.05%).
       These double clusters represent the densest stop concentrations.
    3. Compare upper vs lower cluster sizes to determine hunt direction.
    4. Timing: if price has ranged for >10 candles near a cluster and volume
       is decreasing → imminent hunt.
    5. Funding rate confirmation: positive funding → longs at risk of down hunt.
    """

    SWING_LOOKBACK = 50        # candles to scan for swing highs/lows
    SWING_ORDER = 3            # bars on each side to define a swing
    EQUAL_LEVEL_TOLERANCE = 0.0005  # 0.05% tolerance for "equal" levels
    MIN_CANDLES_RANGING = 10   # candles price must range near cluster for IMMINENT

    def predict(self, symbol: str, df: pd.DataFrame) -> StopHuntPrediction | None:
        """Generate a full stop hunt prediction from OHLCV data.

        Args:
            symbol: Trading pair name (e.g. "BTCUSDT").
            df: OHLCV DataFrame, latest candle last. Requires columns:
                open, high, low, close, volume. Optional: funding_rate.

        Returns:
            StopHuntPrediction or None if insufficient data or no clear setup.
        """
        if df is None or len(df) < self.SWING_LOOKBACK + self.SWING_ORDER * 2:
            logger.debug("stop_hunt_predictor: insufficient data for %s", symbol)
            return None

        current_price = float(df["close"].iloc[-1])
        clusters = self.find_stop_clusters(df, current_price)

        if not clusters:
            return None

        # Split clusters into upper (short stops) and lower (long stops)
        upper_clusters = [c for c in clusters if c.side == "SHORT_STOPS"]
        lower_clusters = [c for c in clusters if c.side == "LONG_STOPS"]

        upper_strength = sum(c.cluster_strength for c in upper_clusters)
        lower_strength = sum(c.cluster_strength for c in lower_clusters)

        # Determine hunt direction — go where the stops are denser
        if upper_strength == 0 and lower_strength == 0:
            return None

        # Funding rate bias: positive funding → over-leveraged longs → hunt DOWN
        funding_rate: float = 0.0
        if "funding_rate" in df.columns:
            funding_rate = float(df["funding_rate"].iloc[-1])

        funding_bias = 0.0
        if abs(funding_rate) > 0.0005:
            # Positive funding → increase bias toward down hunt
            funding_bias = funding_rate * 100  # scale to comparable units

        adjusted_lower = lower_strength + max(0.0, funding_bias * 10)
        adjusted_upper = upper_strength + max(0.0, -funding_bias * 10)

        if adjusted_upper >= adjusted_lower:
            hunt_direction = "UP"
            target_clusters = upper_clusters
        else:
            hunt_direction = "DOWN"
            target_clusters = lower_clusters

        if not target_clusters:
            return None

        # Pick the nearest cluster in the hunt direction
        nearest = min(target_clusters, key=lambda c: c.distance_pct)

        # Confidence calculation
        total_strength = upper_strength + lower_strength
        direction_ratio = (
            adjusted_upper / (adjusted_upper + adjusted_lower)
            if hunt_direction == "UP"
            else adjusted_lower / (adjusted_upper + adjusted_lower)
        )
        base_confidence = 40.0 + direction_ratio * 45.0

        # Boost for equal-level clusters (double tops/bottoms)
        equal_boost = min(15.0, nearest.cluster_strength * 0.15)
        confidence = round(min(base_confidence + equal_boost, 92.0), 1)

        # Timing
        timing = self._hunt_timing(df, nearest.price)

        # Quality grade
        if confidence >= 75 and timing in ("IMMINENT", "SOON"):
            quality = "A"
        elif confidence >= 62:
            quality = "B"
        else:
            quality = "C"

        direction_word = "upward" if hunt_direction == "UP" else "downward"
        description = (
            f"Stop cluster at {nearest.price:.4f} ({nearest.side}, "
            f"strength={nearest.cluster_strength:.0f}). "
            f"Expected {direction_word} sweep. Timing: {timing}."
        )

        logger.info(
            "stop_hunt_predictor: %s hunt_direction=%s target=%.4f confidence=%.1f",
            symbol,
            hunt_direction,
            nearest.price,
            confidence,
        )

        return StopHuntPrediction(
            symbol=symbol,
            likely_hunt_direction=hunt_direction,
            confidence=confidence,
            target_price=round(nearest.price, 8),
            nearest_cluster=nearest,
            setup_quality=quality,
            expected_timing=timing,
            description=description,
        )

    def find_stop_clusters(
        self, df: pd.DataFrame, current_price: float
    ) -> list[StopCluster]:
        """Find price levels with concentrated stops.

        Combines swing highs/lows with equal-level detection to score each
        price zone as a potential stop cluster.

        Args:
            df: OHLCV DataFrame (latest candle last).
            current_price: Current market price.

        Returns:
            List of StopCluster objects, sorted by cluster_strength descending.
        """
        window = df.iloc[-self.SWING_LOOKBACK :].copy()

        swing_highs = self._find_swing_highs(window)
        swing_lows = self._find_swing_lows(window)

        # Equal highs and lows are the strongest stop magnets
        equal_highs = self._find_equal_levels(swing_highs)
        equal_lows = self._find_equal_levels(swing_lows)

        clusters: list[StopCluster] = []

        # Process swing high levels (short stops sitting above price)
        for price in swing_highs:
            if price <= current_price:
                continue  # only consider levels above current price
            distance_pct = abs(price - current_price) / current_price * 100
            if distance_pct > 5.0:  # ignore clusters more than 5% away
                continue
            estimated_stops = self._estimate_stop_count(price, window)
            is_equal = price in equal_highs
            strength = min(100.0, estimated_stops * 15.0 + (30.0 if is_equal else 0.0))
            clusters.append(
                StopCluster(
                    price=round(price, 8),
                    estimated_stops=estimated_stops,
                    side="SHORT_STOPS",
                    distance_pct=round(distance_pct, 4),
                    cluster_strength=round(strength, 2),
                )
            )

        # Process swing low levels (long stops sitting below price)
        for price in swing_lows:
            if price >= current_price:
                continue  # only consider levels below current price
            distance_pct = abs(current_price - price) / current_price * 100
            if distance_pct > 5.0:
                continue
            estimated_stops = self._estimate_stop_count(price, window)
            is_equal = price in equal_lows
            strength = min(100.0, estimated_stops * 15.0 + (30.0 if is_equal else 0.0))
            clusters.append(
                StopCluster(
                    price=round(price, 8),
                    estimated_stops=estimated_stops,
                    side="LONG_STOPS",
                    distance_pct=round(distance_pct, 4),
                    cluster_strength=round(strength, 2),
                )
            )

        clusters.sort(key=lambda c: c.cluster_strength, reverse=True)
        return clusters

    def _find_equal_levels(
        self, levels: list[float], tolerance_pct: float = 0.05
    ) -> list[float]:
        """Find prices that appear 2+ times (double tops/bottoms = stop magnet).

        Args:
            levels: List of price levels (swing highs or swing lows).
            tolerance_pct: Percentage within which two levels are considered equal.

        Returns:
            List of price levels that form equal clusters.
        """
        if not levels:
            return []

        equal: list[float] = []
        tolerance = tolerance_pct / 100.0

        for i, p1 in enumerate(levels):
            for p2 in levels[i + 1 :]:
                if p1 == 0:
                    continue
                diff = abs(p1 - p2) / p1
                if diff <= tolerance:
                    # Use the average of the two as the cluster price
                    cluster_price = (p1 + p2) / 2.0
                    if cluster_price not in equal:
                        equal.append(cluster_price)
                    break

        return equal

    def _estimate_stop_count(self, price: float, df: pd.DataFrame) -> int:
        """Estimate number of stops at a level based on how many times it was touched.

        Each test of a level adds potential stop placement. More touches = more stops.

        Args:
            price: The price level to check.
            df: OHLCV window.

        Returns:
            Estimated number of stop clusters (integer, 1-5 scale).
        """
        if price == 0:
            return 0

        tolerance = price * self.EQUAL_LEVEL_TOLERANCE * 5  # 0.25% band
        touch_count = 0

        for _, row in df.iterrows():
            high = float(row.get("high", 0))
            low = float(row.get("low", 0))
            # Count if candle's high or low came within tolerance of the level
            if abs(high - price) <= tolerance or abs(low - price) <= tolerance:
                touch_count += 1

        # Cap at 5 — beyond that it's already a broken level
        return min(touch_count, 5)

    def _hunt_timing(self, df: pd.DataFrame, cluster_price: float) -> str:
        """Estimate timing based on candles ranging near level + volume trend.

        Args:
            df: Full OHLCV DataFrame.
            cluster_price: Target cluster price.

        Returns:
            "IMMINENT" if price is ranging and volume declining near cluster,
            "SOON" if approaching but not yet tight,
            "PENDING" otherwise.
        """
        if len(df) < self.MIN_CANDLES_RANGING:
            return "PENDING"

        recent = df.iloc[-self.MIN_CANDLES_RANGING :]
        current_price = float(df["close"].iloc[-1])
        tolerance = cluster_price * 0.015  # within 1.5% of cluster

        # Count how many of the recent candles were within the tolerance band
        close_candles = (
            (recent["close"] - cluster_price).abs() <= tolerance
        ).sum()

        # Volume trend: compare first half vs second half of recent window
        half = self.MIN_CANDLES_RANGING // 2
        vol_early = float(recent["volume"].iloc[:half].mean())
        vol_late = float(recent["volume"].iloc[half:].mean())
        volume_declining = vol_early > 0 and (vol_late / vol_early) < 0.85

        distance_pct = abs(current_price - cluster_price) / current_price * 100

        if close_candles >= self.MIN_CANDLES_RANGING * 0.6 and volume_declining:
            return "IMMINENT"
        elif distance_pct < 0.5 or close_candles >= self.MIN_CANDLES_RANGING * 0.3:
            return "SOON"
        else:
            return "PENDING"

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _find_swing_highs(self, df: pd.DataFrame) -> list[float]:
        """Return list of swing high prices using rolling argmax approach."""
        highs: list[float] = []
        order = self.SWING_ORDER
        high_series = df["high"].values

        for i in range(order, len(high_series) - order):
            window = high_series[i - order : i + order + 1]
            if high_series[i] == window.max():
                highs.append(float(high_series[i]))

        # Deduplicate levels within 0.1% of each other
        return _deduplicate_levels(highs, tolerance_pct=0.001)

    def _find_swing_lows(self, df: pd.DataFrame) -> list[float]:
        """Return list of swing low prices."""
        lows: list[float] = []
        order = self.SWING_ORDER
        low_series = df["low"].values

        for i in range(order, len(low_series) - order):
            window = low_series[i - order : i + order + 1]
            if low_series[i] == window.min():
                lows.append(float(low_series[i]))

        return _deduplicate_levels(lows, tolerance_pct=0.001)


def _deduplicate_levels(levels: list[float], tolerance_pct: float = 0.001) -> list[float]:
    """Merge levels that are within tolerance_pct of each other."""
    if not levels:
        return []

    levels_sorted = sorted(levels)
    merged: list[float] = [levels_sorted[0]]

    for price in levels_sorted[1:]:
        if merged[-1] == 0:
            merged.append(price)
            continue
        if abs(price - merged[-1]) / merged[-1] > tolerance_pct:
            merged.append(price)

    return merged
