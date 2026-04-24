"""CVD Divergence Alert — sustained CVD/price divergence signal."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class CVDDivergenceSignal:
    """Signal produced when CVD diverges from price over a sustained period."""

    symbol: str
    divergence_type: str     # "BEARISH" (price up, CVD down) or "BULLISH" (price down, CVD up)
    direction: str           # "SHORT" for bearish divergence, "LONG" for bullish
    confidence: float
    candles_diverging: int   # how long the divergence has persisted
    price_slope: float       # linear regression slope of price (normalised)
    cvd_slope: float         # linear regression slope of CVD (normalised)
    divergence_score: float  # magnitude of divergence 0-100
    description: str


class CVDDivergenceDetector:
    """Detect when Cumulative Volume Delta diverges from price over a sustained period.

    BEARISH divergence: price trend UP + CVD trend DOWN
        → Sellers absorbing buy orders (distribution) → SHORT signal.

    BULLISH divergence: price trend DOWN + CVD trend UP
        → Buyers absorbing sell orders (accumulation) → LONG signal.

    Requires a minimum of MIN_CANDLES of consecutive divergence for a signal.
    """

    MIN_CANDLES: int = 5         # minimum consecutive candles of divergence
    MIN_SLOPE_DIFF: float = 0.3  # minimum absolute difference of normalised slopes
    SLOPE_WINDOW: int = 10       # rolling window for slope calculation

    def detect(self, symbol: str, df: pd.DataFrame) -> CVDDivergenceSignal | None:
        """Detect a sustained CVD/price divergence from OHLCV data.

        Steps:
        1. Calculate CVD from OHLCV via heuristic buy/sell split.
        2. Calculate rolling linear regression slope of price (window=10), normalised.
        3. Calculate rolling linear regression slope of CVD (window=10), normalised.
        4. Flag candles where slopes have opposite signs AND |diff| > MIN_SLOPE_DIFF.
        5. Count consecutive divergence candles from the tail.
        6. Emit signal if consecutive count >= MIN_CANDLES.

        Args:
            symbol: Trading pair name.
            df: OHLCV DataFrame (open, high, low, close, volume), latest candle last.

        Returns:
            CVDDivergenceSignal or None.
        """
        required = self.SLOPE_WINDOW + self.MIN_CANDLES + 2
        if df is None or len(df) < required:
            logger.debug("cvd_divergence: insufficient data for %s", symbol)
            return None

        df = df.copy().reset_index(drop=True)

        # Step 1: CVD
        cvd = self._calculate_cvd(df)

        # Step 2 & 3: normalised rolling slopes
        price_slopes = self._linear_slope(df["close"], self.SLOPE_WINDOW)
        cvd_slopes = self._linear_slope(cvd, self.SLOPE_WINDOW)

        # Drop leading NaN rows (from rolling window)
        valid_mask = price_slopes.notna() & cvd_slopes.notna()
        if valid_mask.sum() < self.MIN_CANDLES:
            return None

        price_slopes_clean = price_slopes[valid_mask]
        cvd_slopes_clean = cvd_slopes[valid_mask]

        # Step 5: count consecutive divergence candles
        consecutive = self._count_consecutive_divergence(
            price_slopes_clean, cvd_slopes_clean
        )

        if consecutive < self.MIN_CANDLES:
            return None

        # Characterise the divergence using the final window
        final_price_slope = float(price_slopes_clean.iloc[-1])
        final_cvd_slope = float(cvd_slopes_clean.iloc[-1])

        if final_price_slope > 0 and final_cvd_slope < 0:
            divergence_type = "BEARISH"
            direction = "SHORT"
        elif final_price_slope < 0 and final_cvd_slope > 0:
            divergence_type = "BULLISH"
            direction = "LONG"
        else:
            return None  # slopes no longer diverging at the tail

        # Divergence score: based on magnitude of opposing slopes and duration
        slope_diff = abs(final_price_slope - final_cvd_slope)
        raw_score = min(100.0, slope_diff * 50.0 + consecutive * 5.0)
        divergence_score = round(raw_score, 2)

        # Confidence: base 60% + duration bonus + magnitude bonus
        duration_bonus = min(20.0, (consecutive - self.MIN_CANDLES) * 3.0)
        magnitude_bonus = min(15.0, slope_diff * 20.0)
        confidence = round(min(60.0 + duration_bonus + magnitude_bonus, 92.0), 1)

        description = (
            f"{divergence_type} CVD divergence on {symbol}: "
            f"price_slope={final_price_slope:.3f}, cvd_slope={final_cvd_slope:.3f}, "
            f"diverging for {consecutive} candles."
        )

        logger.info(
            "cvd_divergence: %s %s conf=%.1f candles=%d",
            symbol,
            divergence_type,
            confidence,
            consecutive,
        )

        return CVDDivergenceSignal(
            symbol=symbol,
            divergence_type=divergence_type,
            direction=direction,
            confidence=confidence,
            candles_diverging=consecutive,
            price_slope=round(final_price_slope, 5),
            cvd_slope=round(final_cvd_slope, 5),
            divergence_score=divergence_score,
            description=description,
        )

    def _calculate_cvd(self, df: pd.DataFrame) -> pd.Series:
        """Calculate Cumulative Volume Delta from OHLCV.

        Heuristic:
        - Bullish candle (close > open): all volume is treated as buy volume.
        - Bearish candle (close < open): all volume is treated as sell volume.
        - Doji (close == open): half buy, half sell.

        Returns:
            Pandas Series of CVD values (cumulative sum of buy_vol - sell_vol).
        """
        opens = df["open"].values
        closes = df["close"].values
        volumes = df["volume"].values

        deltas = np.where(
            closes > opens,
            volumes,           # bullish candle: all buy
            np.where(
                closes < opens,
                -volumes,      # bearish candle: all sell
                0.0,           # doji: neutral
            ),
        )

        cvd = pd.Series(np.cumsum(deltas), index=df.index, name="cvd")
        return cvd

    def _linear_slope(self, series: pd.Series, window: int = 10) -> pd.Series:
        """Calculate rolling linear regression slope, normalised to [-1, +1].

        The slope is computed via least squares on the index [0, 1, ..., window-1]
        versus the series values. After computation the result is normalised by
        dividing by the mean absolute value of the raw slopes, so that the
        returned series has values in roughly [-1, +1] and can be compared across
        different scales (price vs CVD).

        Args:
            series: Time series (price or CVD).
            window: Rolling window size.

        Returns:
            Normalised slope series (same index as input, NaN for first window-1 rows).
        """
        x = np.arange(window, dtype=float)
        x_mean = x.mean()
        x_var = ((x - x_mean) ** 2).sum()

        def _slope(y: np.ndarray) -> float:
            """Compute OLS slope for a fixed x-vector."""
            y_mean = y.mean()
            return float(((x - x_mean) * (y - y_mean)).sum() / (x_var + 1e-10))

        raw_slopes = series.rolling(window).apply(_slope, raw=True)

        # Normalise: divide by mean absolute value of valid slopes
        valid = raw_slopes.dropna()
        if len(valid) == 0:
            return raw_slopes

        mean_abs = float(valid.abs().mean())
        if mean_abs < 1e-10:
            return raw_slopes * 0.0

        normalised = raw_slopes / mean_abs
        return normalised

    def _count_consecutive_divergence(
        self, price_slopes: pd.Series, cvd_slopes: pd.Series
    ) -> int:
        """Count how many consecutive recent candles have opposing normalised slopes.

        A candle counts as diverging when:
        - price_slope and cvd_slope have opposite signs, AND
        - |price_slope - cvd_slope| > MIN_SLOPE_DIFF.

        Counting starts from the tail and stops at the first non-diverging candle.

        Args:
            price_slopes: Normalised price slope series (NaN already removed).
            cvd_slopes: Normalised CVD slope series (NaN already removed).

        Returns:
            Number of consecutive diverging candles from the end.
        """
        p_vals = price_slopes.values
        c_vals = cvd_slopes.values
        n = min(len(p_vals), len(c_vals))

        count = 0
        for i in range(n - 1, -1, -1):
            p = p_vals[i]
            c = c_vals[i]

            # Opposite signs: product < 0
            opposite_sign = (p * c) < 0
            large_enough = abs(p - c) >= self.MIN_SLOPE_DIFF

            if opposite_sign and large_enough:
                count += 1
            else:
                break  # stop at first non-diverging candle

        return count
