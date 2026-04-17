"""Chart pattern detection — Double Top/Bottom, Head & Shoulders, Triangles."""

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def _find_pivots(
    df: pd.DataFrame,
    order: int = 5,
) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
    """Detect local peaks (swing highs) and troughs (swing lows).

    Args:
        df: DataFrame with 'high' and 'low' columns.
        order: Number of bars on each side to confirm a pivot.

    Returns:
        Tuple of (peaks, troughs) where each is a list of (index_position, price).
    """
    highs = df["high"].values
    lows = df["low"].values
    n = len(df)

    peaks: list[tuple[int, float]] = []
    troughs: list[tuple[int, float]] = []

    for i in range(order, n - order):
        # Check swing high
        is_peak = True
        for j in range(1, order + 1):
            if highs[i] < highs[i - j] or highs[i] < highs[i + j]:
                is_peak = False
                break
        if is_peak:
            peaks.append((i, float(highs[i])))

        # Check swing low
        is_trough = True
        for j in range(1, order + 1):
            if lows[i] > lows[i - j] or lows[i] > lows[i + j]:
                is_trough = False
                break
        if is_trough:
            troughs.append((i, float(lows[i])))

    return peaks, troughs


def _get_atr_at(df: pd.DataFrame, idx: int) -> float:
    """Get ATR value at a given index, falling back to a simple calculation.

    Args:
        df: DataFrame, potentially with 'atr_14' column.
        idx: Index position to read ATR from.

    Returns:
        ATR value as float.
    """
    if "atr_14" in df.columns:
        val = df["atr_14"].iloc[idx]
        if not np.isnan(val):
            return float(val)

    # Fallback: simple range-based estimate over last 14 bars
    start = max(0, idx - 14)
    subset = df.iloc[start:idx + 1]
    if len(subset) < 2:
        return float(df["high"].iloc[idx] - df["low"].iloc[idx])
    return float((subset["high"] - subset["low"]).mean())


def _detect_double_top_bottom(
    df: pd.DataFrame,
    peaks: list[tuple[int, float]],
    troughs: list[tuple[int, float]],
) -> list[dict]:
    """Detect Double Top and Double Bottom patterns.

    Double Top: two peaks at a similar price level with a trough between them.
    Double Bottom: two troughs at a similar price level with a peak between them.

    Args:
        df: OHLCV DataFrame.
        peaks: List of (index, price) for swing highs.
        troughs: List of (index, price) for swing lows.

    Returns:
        List of detected pattern dicts.
    """
    patterns: list[dict] = []

    # Double Top — scan consecutive peak pairs
    for i in range(len(peaks) - 1):
        idx_a, price_a = peaks[i]
        idx_b, price_b = peaks[i + 1]

        atr = _get_atr_at(df, idx_b)
        if atr <= 0:
            continue

        tolerance = atr * 1.5
        if abs(price_a - price_b) > tolerance:
            continue

        # Must have a meaningful trough between the two peaks
        mid_troughs = [t for t in troughs if idx_a < t[0] < idx_b]
        if not mid_troughs:
            continue

        neckline = min(t[1] for t in mid_troughs)
        avg_peak = (price_a + price_b) / 2
        height = avg_peak - neckline
        if height < atr * 0.5:
            continue

        # Confidence: closer peaks in price = higher confidence
        price_diff_ratio = abs(price_a - price_b) / atr
        confidence = max(0.3, min(1.0, 1.0 - price_diff_ratio * 0.3))

        patterns.append({
            "type": "double_top",
            "direction": "bearish",
            "start_idx": int(idx_a),
            "end_idx": int(idx_b),
            "confidence": round(confidence, 2),
            "key_levels": {
                "peak_1": round(price_a, 8),
                "peak_2": round(price_b, 8),
                "neckline": round(neckline, 8),
                "target": round(neckline - height, 8),
            },
        })

    # Double Bottom — scan consecutive trough pairs
    for i in range(len(troughs) - 1):
        idx_a, price_a = troughs[i]
        idx_b, price_b = troughs[i + 1]

        atr = _get_atr_at(df, idx_b)
        if atr <= 0:
            continue

        tolerance = atr * 1.5
        if abs(price_a - price_b) > tolerance:
            continue

        mid_peaks = [p for p in peaks if idx_a < p[0] < idx_b]
        if not mid_peaks:
            continue

        neckline = max(p[1] for p in mid_peaks)
        avg_trough = (price_a + price_b) / 2
        height = neckline - avg_trough
        if height < atr * 0.5:
            continue

        price_diff_ratio = abs(price_a - price_b) / atr
        confidence = max(0.3, min(1.0, 1.0 - price_diff_ratio * 0.3))

        patterns.append({
            "type": "double_bottom",
            "direction": "bullish",
            "start_idx": int(idx_a),
            "end_idx": int(idx_b),
            "confidence": round(confidence, 2),
            "key_levels": {
                "trough_1": round(price_a, 8),
                "trough_2": round(price_b, 8),
                "neckline": round(neckline, 8),
                "target": round(neckline + height, 8),
            },
        })

    return patterns


def _detect_head_and_shoulders(
    df: pd.DataFrame,
    peaks: list[tuple[int, float]],
    troughs: list[tuple[int, float]],
) -> list[dict]:
    """Detect Head & Shoulders and Inverse Head & Shoulders patterns.

    H&S: three peaks where the middle one is the highest (bearish).
    Inverse H&S: three troughs where the middle one is the lowest (bullish).

    Args:
        df: OHLCV DataFrame.
        peaks: List of (index, price) for swing highs.
        troughs: List of (index, price) for swing lows.

    Returns:
        List of detected pattern dicts.
    """
    patterns: list[dict] = []

    # Head & Shoulders (bearish)
    for i in range(len(peaks) - 2):
        idx_l, price_l = peaks[i]       # left shoulder
        idx_h, price_h = peaks[i + 1]   # head
        idx_r, price_r = peaks[i + 2]   # right shoulder

        atr = _get_atr_at(df, idx_r)
        if atr <= 0:
            continue

        # Head must be higher than both shoulders
        if price_h <= price_l or price_h <= price_r:
            continue

        # Shoulders should be at roughly similar levels
        shoulder_diff = abs(price_l - price_r)
        if shoulder_diff > atr * 2.0:
            continue

        # Find neckline from troughs between the peaks
        left_troughs = [t for t in troughs if idx_l < t[0] < idx_h]
        right_troughs = [t for t in troughs if idx_h < t[0] < idx_r]
        if not left_troughs or not right_troughs:
            continue

        neckline_left = min(t[1] for t in left_troughs)
        neckline_right = min(t[1] for t in right_troughs)
        neckline = (neckline_left + neckline_right) / 2
        height = price_h - neckline

        if height < atr:
            continue

        # Confidence based on shoulder symmetry and head prominence
        symmetry = 1.0 - (shoulder_diff / atr) * 0.2
        prominence = min(1.0, (price_h - max(price_l, price_r)) / atr * 0.3)
        confidence = max(0.3, min(1.0, (symmetry + prominence) / 2))

        patterns.append({
            "type": "head_and_shoulders",
            "direction": "bearish",
            "start_idx": int(idx_l),
            "end_idx": int(idx_r),
            "confidence": round(confidence, 2),
            "key_levels": {
                "left_shoulder": round(price_l, 8),
                "head": round(price_h, 8),
                "right_shoulder": round(price_r, 8),
                "neckline": round(neckline, 8),
                "target": round(neckline - height, 8),
            },
        })

    # Inverse Head & Shoulders (bullish)
    for i in range(len(troughs) - 2):
        idx_l, price_l = troughs[i]       # left shoulder
        idx_h, price_h = troughs[i + 1]   # head (lowest)
        idx_r, price_r = troughs[i + 2]   # right shoulder

        atr = _get_atr_at(df, idx_r)
        if atr <= 0:
            continue

        # Head must be lower than both shoulders
        if price_h >= price_l or price_h >= price_r:
            continue

        shoulder_diff = abs(price_l - price_r)
        if shoulder_diff > atr * 2.0:
            continue

        left_peaks = [p for p in peaks if idx_l < p[0] < idx_h]
        right_peaks = [p for p in peaks if idx_h < p[0] < idx_r]
        if not left_peaks or not right_peaks:
            continue

        neckline_left = max(p[1] for p in left_peaks)
        neckline_right = max(p[1] for p in right_peaks)
        neckline = (neckline_left + neckline_right) / 2
        height = neckline - price_h

        if height < atr:
            continue

        symmetry = 1.0 - (shoulder_diff / atr) * 0.2
        prominence = min(1.0, (min(price_l, price_r) - price_h) / atr * 0.3)
        confidence = max(0.3, min(1.0, (symmetry + prominence) / 2))

        patterns.append({
            "type": "inverse_head_and_shoulders",
            "direction": "bullish",
            "start_idx": int(idx_l),
            "end_idx": int(idx_r),
            "confidence": round(confidence, 2),
            "key_levels": {
                "left_shoulder": round(price_l, 8),
                "head": round(price_h, 8),
                "right_shoulder": round(price_r, 8),
                "neckline": round(neckline, 8),
                "target": round(neckline + height, 8),
            },
        })

    return patterns


def _detect_triangles(
    df: pd.DataFrame,
    peaks: list[tuple[int, float]],
    troughs: list[tuple[int, float]],
    min_points: int = 4,
) -> list[dict]:
    """Detect Ascending and Descending Triangle patterns.

    Ascending Triangle: flat resistance with rising support (bullish).
    Descending Triangle: flat support with falling resistance (bearish).

    Args:
        df: OHLCV DataFrame.
        peaks: List of (index, price) for swing highs.
        troughs: List of (index, price) for swing lows.
        min_points: Minimum number of pivots required to form a triangle.

    Returns:
        List of detected pattern dicts.
    """
    patterns: list[dict] = []

    if len(peaks) < 2 or len(troughs) < 2:
        return patterns

    # Use a sliding window over recent pivots
    window_sizes = [4, 6, 8]

    for ws in window_sizes:
        if len(peaks) < ws // 2 or len(troughs) < ws // 2:
            continue

        recent_peaks = peaks[-(ws // 2):]
        recent_troughs = troughs[-(ws // 2):]

        if len(recent_peaks) < 2 or len(recent_troughs) < 2:
            continue

        start_idx = min(recent_peaks[0][0], recent_troughs[0][0])
        end_idx = max(recent_peaks[-1][0], recent_troughs[-1][0])

        atr = _get_atr_at(df, end_idx)
        if atr <= 0:
            continue

        # Compute slopes via simple linear regression
        peak_indices = np.array([p[0] for p in recent_peaks], dtype=float)
        peak_prices = np.array([p[1] for p in recent_peaks])
        trough_indices = np.array([t[0] for t in recent_troughs], dtype=float)
        trough_prices = np.array([t[1] for t in recent_troughs])

        # Slopes (price change per bar)
        if len(peak_indices) >= 2:
            peak_slope = float(np.polyfit(peak_indices, peak_prices, 1)[0])
        else:
            continue
        if len(trough_indices) >= 2:
            trough_slope = float(np.polyfit(trough_indices, trough_prices, 1)[0])
        else:
            continue

        # Normalize slopes by ATR for comparisons
        peak_slope_norm = peak_slope / atr
        trough_slope_norm = trough_slope / atr

        flat_threshold = 0.02   # slope per bar relative to ATR
        rising_threshold = 0.01
        falling_threshold = -0.01

        # Ascending Triangle: flat highs + rising lows
        if abs(peak_slope_norm) < flat_threshold and trough_slope_norm > rising_threshold:
            resistance = float(np.mean(peak_prices))
            # Confidence from how flat the resistance is and how consistent the rise
            flatness = 1.0 - min(1.0, abs(peak_slope_norm) / flat_threshold)
            rise_consistency = min(1.0, trough_slope_norm / 0.05)
            confidence = max(0.3, min(0.95, (flatness + rise_consistency) / 2))

            patterns.append({
                "type": "ascending_triangle",
                "direction": "bullish",
                "start_idx": int(start_idx),
                "end_idx": int(end_idx),
                "confidence": round(confidence, 2),
                "key_levels": {
                    "resistance": round(resistance, 8),
                    "support_start": round(float(trough_prices[0]), 8),
                    "support_end": round(float(trough_prices[-1]), 8),
                    "target": round(resistance + (resistance - float(trough_prices[0])), 8),
                },
            })

        # Descending Triangle: flat lows + falling highs
        if abs(trough_slope_norm) < flat_threshold and peak_slope_norm < falling_threshold:
            support = float(np.mean(trough_prices))
            flatness = 1.0 - min(1.0, abs(trough_slope_norm) / flat_threshold)
            fall_consistency = min(1.0, abs(peak_slope_norm) / 0.05)
            confidence = max(0.3, min(0.95, (flatness + fall_consistency) / 2))

            patterns.append({
                "type": "descending_triangle",
                "direction": "bearish",
                "start_idx": int(start_idx),
                "end_idx": int(end_idx),
                "confidence": round(confidence, 2),
                "key_levels": {
                    "resistance_start": round(float(peak_prices[0]), 8),
                    "resistance_end": round(float(peak_prices[-1]), 8),
                    "support": round(support, 8),
                    "target": round(support - (float(peak_prices[0]) - support), 8),
                },
            })

    return patterns


def detect_patterns(df: pd.DataFrame) -> list[dict]:
    """Detect chart patterns in OHLCV data.

    Scans the DataFrame for:
    - Double Top / Double Bottom
    - Head & Shoulders / Inverse Head & Shoulders
    - Ascending / Descending Triangles

    Each detected pattern includes:
    - type: pattern name (e.g. 'double_top', 'head_and_shoulders')
    - direction: 'bullish' or 'bearish'
    - start_idx: DataFrame row index where the pattern begins
    - end_idx: DataFrame row index where the pattern ends
    - confidence: float 0-1 indicating detection quality
    - key_levels: dict of important price levels (neckline, target, etc.)

    Args:
        df: DataFrame with at least 'high' and 'low' columns.
            If 'atr_14' is present it will be used for tolerance calculations.

    Returns:
        List of pattern dicts sorted by end_idx (most recent last).
    """
    if len(df) < 20:
        return []

    # Use a smaller pivot order for shorter datasets
    order = 5 if len(df) >= 50 else 3

    peaks, troughs = _find_pivots(df, order=order)

    if not peaks and not troughs:
        return []

    patterns: list[dict] = []

    patterns.extend(_detect_double_top_bottom(df, peaks, troughs))
    patterns.extend(_detect_head_and_shoulders(df, peaks, troughs))
    patterns.extend(_detect_triangles(df, peaks, troughs))

    # Sort by end_idx so most recent patterns come last
    patterns.sort(key=lambda p: p["end_idx"])

    logger.info("Detected %d chart patterns", len(patterns))
    return patterns
