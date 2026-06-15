"""Anchored VWAP — Volume Weighted Average Price anchored from key events.

Standard VWAP resets every session.  Anchored VWAP starts the cumulative
calculation from a user-chosen candle (e.g. a swing high/low, a major news
event, the start of a trend).  This reveals the *average cost basis* of all
participants who traded since that anchor.

Price above anchored VWAP → market is net profitable from that anchor point
  (bullish structure).
Price below anchored VWAP → market is net unprofitable (bearish structure).

Standard deviation bands (±1σ, ±2σ) act as dynamic support/resistance.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
import pandas as pd

from app.core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SWING_WINDOW: Final[int] = 5          # candles on each side for swing detection
_MIN_PROMINENCE_PCT: Final[float] = 0.3  # minimum swing prominence as %
_AT_VWAP_TOLERANCE_PCT: Final[float] = 0.1  # within 0.1% = "AT_VWAP"
_MIN_CANDLES: Final[int] = 10


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class AnchoredVWAPResult:
    """Result of an anchored VWAP calculation."""

    vwap: float
    upper_band_1: float  # +1 standard deviation
    lower_band_1: float  # -1 standard deviation
    upper_band_2: float  # +2 standard deviations
    lower_band_2: float  # -2 standard deviations
    price_position: str  # "ABOVE_VWAP", "BELOW_VWAP", "AT_VWAP"
    distance_pct: float  # % distance from VWAP (signed: + above, - below)

    def __repr__(self) -> str:
        return (
            f"AnchoredVWAPResult(vwap={self.vwap:.4f}, "
            f"position={self.price_position}, dist={self.distance_pct:+.2f}%, "
            f"bands=[{self.lower_band_2:.4f}, {self.lower_band_1:.4f}, "
            f"{self.upper_band_1:.4f}, {self.upper_band_2:.4f}])"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _compute_vwap_from_slice(df_slice: pd.DataFrame) -> tuple[float, float, float, float, float]:
    """Compute cumulative anchored VWAP and std-dev bands from a DataFrame slice.

    Args:
        df_slice: OHLCV slice from anchor candle to latest candle.

    Returns:
        Tuple of (vwap, upper_1, lower_1, upper_2, lower_2).
    """
    typical_price = (df_slice["high"] + df_slice["low"] + df_slice["close"]) / 3.0
    volume = df_slice["volume"].astype(float)

    cum_tp_vol = (typical_price * volume).cumsum()
    cum_vol = volume.cumsum()

    # Avoid division by zero on zero-volume candles
    cum_vol_safe = cum_vol.replace(0, np.nan)
    vwap_series = cum_tp_vol / cum_vol_safe

    vwap = float(vwap_series.iloc[-1])
    if np.isnan(vwap):
        vwap = float(typical_price.iloc[-1])

    # Standard deviation of price from VWAP over the anchored window
    deviations = typical_price - vwap_series
    squared_dev = (deviations ** 2 * volume).cumsum() / cum_vol_safe
    std_dev = float(np.sqrt(squared_dev.iloc[-1]))
    if np.isnan(std_dev):
        std_dev = 0.0

    return (
        round(vwap, 8),
        round(vwap + std_dev, 8),
        round(vwap - std_dev, 8),
        round(vwap + 2 * std_dev, 8),
        round(vwap - 2 * std_dev, 8),
    )


def _price_position(current_price: float, vwap: float, tolerance_pct: float) -> tuple[str, float]:
    """Determine price position relative to VWAP.

    Returns:
        Tuple of (position_label, distance_pct).
    """
    if vwap == 0:
        return "AT_VWAP", 0.0
    dist_pct = (current_price - vwap) / vwap * 100.0
    if abs(dist_pct) <= tolerance_pct:
        label = "AT_VWAP"
    elif dist_pct > 0:
        label = "ABOVE_VWAP"
    else:
        label = "BELOW_VWAP"
    return label, round(dist_pct, 4)


def _find_swing_high(df: pd.DataFrame, window: int, min_prominence_pct: float) -> int:
    """Find the index of the most recent swing high.

    Returns 0 (start of DataFrame) if no swing is found.
    """
    n = len(df)
    prices_high = df["high"].to_numpy(dtype=float)
    prices_low = df["low"].to_numpy(dtype=float)

    # Scan from most recent backwards
    for i in range(n - window - 1, window - 1, -1):
        left = prices_high[i - window : i]
        right = prices_high[i + 1 : i + window + 1]
        if len(left) < window or len(right) < window:
            continue
        if prices_high[i] > left.max() and prices_high[i] > right.max():
            near_low = prices_low[i - window : i + window + 1].min()
            prominence = (prices_high[i] - near_low) / prices_high[i] * 100
            if prominence >= min_prominence_pct:
                return i
    return 0


def _find_swing_low(df: pd.DataFrame, window: int, min_prominence_pct: float) -> int:
    """Find the index of the most recent swing low.

    Returns 0 (start of DataFrame) if no swing is found.
    """
    n = len(df)
    prices_high = df["high"].to_numpy(dtype=float)
    prices_low = df["low"].to_numpy(dtype=float)

    for i in range(n - window - 1, window - 1, -1):
        left = prices_low[i - window : i]
        right = prices_low[i + 1 : i + window + 1]
        if len(left) < window or len(right) < window:
            continue
        if prices_low[i] < left.min() and prices_low[i] < right.min():
            near_high = prices_high[i - window : i + window + 1].max()
            prominence = (near_high - prices_low[i]) / near_high * 100
            if prominence >= min_prominence_pct:
                return i
    return 0


# ---------------------------------------------------------------------------
# Main calculator class
# ---------------------------------------------------------------------------


class AnchoredVWAPCalculator:
    """Calculates VWAP anchored from a specific candle index or auto-detected swing."""

    def calculate(self, df: pd.DataFrame, anchor_idx: int = 0) -> AnchoredVWAPResult:
        """Calculate anchored VWAP from anchor_idx to the last candle.

        Args:
            df:         OHLCV DataFrame.
            anchor_idx: Index of the anchor candle.  0 = start of df.

        Returns:
            AnchoredVWAPResult with VWAP, bands, and price position.
        """
        if df is None or len(df) < _MIN_CANDLES:
            raise ValueError(
                f"AnchoredVWAPCalculator: need at least {_MIN_CANDLES} candles, "
                f"got {len(df) if df is not None else 0}"
            )

        anchor_idx = max(0, min(anchor_idx, len(df) - 1))
        df_slice = df.iloc[anchor_idx:].copy().reset_index(drop=True)

        vwap, ub1, lb1, ub2, lb2 = _compute_vwap_from_slice(df_slice)
        current_price = float(df["close"].iloc[-1])
        position, dist_pct = _price_position(current_price, vwap, _AT_VWAP_TOLERANCE_PCT)

        logger.debug(
            "Anchored VWAP calculated",
            extra={
                "anchor_idx": anchor_idx,
                "vwap": vwap,
                "position": position,
                "distance_pct": dist_pct,
            },
        )

        return AnchoredVWAPResult(
            vwap=vwap,
            upper_band_1=ub1,
            lower_band_1=lb1,
            upper_band_2=ub2,
            lower_band_2=lb2,
            price_position=position,
            distance_pct=dist_pct,
        )

    def calculate_from_swing_high(self, df: pd.DataFrame) -> AnchoredVWAPResult:
        """Auto-detect the most recent swing high and anchor VWAP from there.

        Args:
            df: OHLCV DataFrame.

        Returns:
            AnchoredVWAPResult anchored from the detected swing high.
        """
        anchor_idx = _find_swing_high(df, _SWING_WINDOW, _MIN_PROMINENCE_PCT)
        logger.info(
            "Anchored VWAP from swing high",
            extra={"anchor_idx": anchor_idx, "anchor_price": float(df["high"].iloc[anchor_idx])},
        )
        return self.calculate(df, anchor_idx)

    def calculate_from_swing_low(self, df: pd.DataFrame) -> AnchoredVWAPResult:
        """Auto-detect the most recent swing low and anchor VWAP from there.

        Args:
            df: OHLCV DataFrame.

        Returns:
            AnchoredVWAPResult anchored from the detected swing low.
        """
        anchor_idx = _find_swing_low(df, _SWING_WINDOW, _MIN_PROMINENCE_PCT)
        logger.info(
            "Anchored VWAP from swing low",
            extra={"anchor_idx": anchor_idx, "anchor_price": float(df["low"].iloc[anchor_idx])},
        )
        return self.calculate(df, anchor_idx)

    def get_signal(self, df: pd.DataFrame) -> dict:
        """Produce a trading signal dict based on anchored VWAP analysis.

        Checks VWAP anchored from both the most recent swing high and low.
        Generates signals for:
        - Crossover above VWAP from below → LONG
        - Crossover below VWAP from above → SHORT
        - Price at ±2σ band → mean reversion opportunity

        Args:
            df: OHLCV DataFrame.  Needs at least 20 candles.

        Returns:
            Dict with keys: signal, bias, vwap_from_high, vwap_from_low,
            mean_reversion_opportunity, description.
        """
        if df is None or len(df) < 2:
            return {"signal": "NEUTRAL", "bias": "NEUTRAL", "description": "Insufficient data"}

        try:
            result_high = self.calculate_from_swing_high(df)
            result_low = self.calculate_from_swing_low(df)
        except ValueError as exc:
            return {"signal": "NEUTRAL", "bias": "NEUTRAL", "description": str(exc)}

        current_price = float(df["close"].iloc[-1])
        prev_price = float(df["close"].iloc[-2])

        signal = "NEUTRAL"
        bias = "NEUTRAL"
        description_parts: list[str] = []

        # --- VWAP crossover signals ---
        vwap = result_low.vwap  # anchor from swing low is typically more informative for bias
        crossed_above = prev_price < vwap and current_price >= vwap
        crossed_below = prev_price > vwap and current_price <= vwap

        if crossed_above:
            signal = "LONG"
            bias = "BULLISH"
            description_parts.append(
                f"Price crossed above anchored VWAP ({vwap:.4f}) — bullish momentum."
            )
        elif crossed_below:
            signal = "SHORT"
            bias = "BEARISH"
            description_parts.append(
                f"Price crossed below anchored VWAP ({vwap:.4f}) — bearish momentum."
            )

        # --- Mean reversion from ±2σ bands ---
        mean_reversion_opportunity = None
        if current_price >= result_low.upper_band_2:
            mean_reversion_opportunity = "SELL_PREMIUM"
            description_parts.append(
                f"Price at +2σ band ({result_low.upper_band_2:.4f}) — "
                "mean reversion SHORT opportunity."
            )
        elif current_price <= result_low.lower_band_2:
            mean_reversion_opportunity = "BUY_DIPS"
            description_parts.append(
                f"Price at -2σ band ({result_low.lower_band_2:.4f}) — "
                "mean reversion LONG opportunity."
            )

        # Bias from position relative to VWAP (when no crossover)
        if signal == "NEUTRAL":
            if result_low.price_position == "ABOVE_VWAP":
                bias = "BULLISH"
            elif result_low.price_position == "BELOW_VWAP":
                bias = "BEARISH"

        if not description_parts:
            description_parts.append(
                f"Price {result_low.price_position.replace('_', ' ')} "
                f"({result_low.distance_pct:+.2f}% from anchored VWAP)."
            )

        return {
            "signal": signal,
            "bias": bias,
            "vwap_from_swing_high": {
                "vwap": result_high.vwap,
                "position": result_high.price_position,
                "distance_pct": result_high.distance_pct,
                "upper_band_2": result_high.upper_band_2,
                "lower_band_2": result_high.lower_band_2,
            },
            "vwap_from_swing_low": {
                "vwap": result_low.vwap,
                "position": result_low.price_position,
                "distance_pct": result_low.distance_pct,
                "upper_band_2": result_low.upper_band_2,
                "lower_band_2": result_low.lower_band_2,
            },
            "mean_reversion_opportunity": mean_reversion_opportunity,
            "description": " ".join(description_parts),
        }
