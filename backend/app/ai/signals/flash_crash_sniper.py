"""Flash Crash Sniper — detects single-exchange anomalous wicks for reversal entry."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class FlashCrashSignal:
    """Signal generated when an anomalous flash crash wick is detected."""

    symbol: str
    direction: str          # "LONG" (wick down) or "SHORT" (wick up)
    confidence: float
    crash_price: float      # extreme wick price
    entry_price: float      # current price (after recovery)
    recovery_pct: float     # how much price already recovered (0-1)
    wick_size_atr: float    # wick size in ATR multiples
    target: float           # expected full recovery target
    stop_loss: float        # just below wick low (LONG) or above wick high (SHORT)
    description: str


class FlashCrashSniper:
    """Detect exchange-specific flash crashes and generate immediate reversal signals.

    Trigger conditions for a LONG signal (all must be true):
    1. Current candle lower wick > MIN_WICK_ATR_MULTIPLE × ATR(14).
    2. Close is back within the top 25% of the candle range (recovery confirmed).
    3. Wick low is below the 20-period rolling low (structure briefly broken).
    4. Recovery happened in same candle (close above midpoint, not a new trend down).
    5. Volume is elevated (aggressive selling absorbed).

    Mirror conditions for SHORT (upper wick > MIN_WICK_ATR_MULTIPLE × ATR).
    """

    ATR_PERIOD = 14
    RANGE_PERIOD = 20
    MIN_WICK_ATR_MULTIPLE: float = 3.0
    MIN_RECOVERY_PCT: float = 0.50   # must recover at least 50% of the wick
    VOLUME_SPIKE_THRESHOLD: float = 1.5  # volume must be > 1.5× average

    def scan(self, symbol: str, df: pd.DataFrame) -> FlashCrashSignal | None:
        """Scan the latest candle for a flash crash pattern.

        Args:
            symbol: Trading pair name.
            df: OHLCV DataFrame, latest candle last. Requires open/high/low/close/volume.
                ATR is computed internally if 'atr_14' column is absent.

        Returns:
            FlashCrashSignal if detected, None otherwise.
        """
        min_len = max(self.ATR_PERIOD, self.RANGE_PERIOD) + 5
        if df is None or len(df) < min_len:
            logger.debug("flash_crash_sniper: insufficient data for %s", symbol)
            return None

        df = df.copy()

        # Compute ATR if not pre-computed
        if "atr_14" not in df.columns:
            df["atr_14"] = _calculate_atr(df, self.ATR_PERIOD)

        atr = float(df["atr_14"].iloc[-1])
        if atr <= 0:
            return None

        candle = df.iloc[-1]

        # Compute rolling 20-period high/low (excluding current candle)
        period_low = float(df["low"].iloc[-self.RANGE_PERIOD - 1 : -1].min())
        period_high = float(df["high"].iloc[-self.RANGE_PERIOD - 1 : -1].max())

        # Average volume (excluding current candle)
        avg_volume = float(df["volume"].iloc[-self.RANGE_PERIOD - 1 : -1].mean())
        curr_volume = float(candle.get("volume", 0))
        volume_ratio = (curr_volume / avg_volume) if avg_volume > 0 else 1.0

        # --- Try LONG (downward flash crash) ---
        lower_wick = self._lower_wick(candle)
        if lower_wick >= self.MIN_WICK_ATR_MULTIPLE * atr:
            recovery = self._recovery_pct(candle, "lower")
            wick_atr_mult = lower_wick / atr
            wick_low = float(candle["low"])

            if (
                recovery >= self.MIN_RECOVERY_PCT
                and wick_low < period_low           # broke 20-period structure
                and volume_ratio >= self.VOLUME_SPIKE_THRESHOLD
            ):
                close = float(candle["close"])
                stop_loss = round(wick_low * 0.998, 8)  # just below the wick
                target = round(period_high, 8)

                confidence = self.calculate_confidence(wick_atr_mult, recovery, volume_ratio)

                description = (
                    f"Flash crash LONG: lower wick={lower_wick:.4f} "
                    f"({wick_atr_mult:.1f}× ATR), recovery={recovery:.0%}, "
                    f"vol_ratio={volume_ratio:.1f}×"
                )
                logger.info("flash_crash_sniper LONG: %s conf=%.1f", symbol, confidence)

                return FlashCrashSignal(
                    symbol=symbol,
                    direction="LONG",
                    confidence=confidence,
                    crash_price=round(wick_low, 8),
                    entry_price=round(close, 8),
                    recovery_pct=round(recovery, 4),
                    wick_size_atr=round(wick_atr_mult, 2),
                    target=target,
                    stop_loss=stop_loss,
                    description=description,
                )

        # --- Try SHORT (upward flash crash) ---
        upper_wick = self._upper_wick(candle)
        if upper_wick >= self.MIN_WICK_ATR_MULTIPLE * atr:
            recovery = self._recovery_pct(candle, "upper")
            wick_atr_mult = upper_wick / atr
            wick_high = float(candle["high"])

            if (
                recovery >= self.MIN_RECOVERY_PCT
                and wick_high > period_high         # broke 20-period structure
                and volume_ratio >= self.VOLUME_SPIKE_THRESHOLD
            ):
                close = float(candle["close"])
                stop_loss = round(wick_high * 1.002, 8)  # just above the wick
                target = round(period_low, 8)

                confidence = self.calculate_confidence(wick_atr_mult, recovery, volume_ratio)

                description = (
                    f"Flash crash SHORT: upper wick={upper_wick:.4f} "
                    f"({wick_atr_mult:.1f}× ATR), recovery={recovery:.0%}, "
                    f"vol_ratio={volume_ratio:.1f}×"
                )
                logger.info("flash_crash_sniper SHORT: %s conf=%.1f", symbol, confidence)

                return FlashCrashSignal(
                    symbol=symbol,
                    direction="SHORT",
                    confidence=confidence,
                    crash_price=round(wick_high, 8),
                    entry_price=round(close, 8),
                    recovery_pct=round(recovery, 4),
                    wick_size_atr=round(wick_atr_mult, 2),
                    target=target,
                    stop_loss=stop_loss,
                    description=description,
                )

        return None

    def _lower_wick(self, candle: pd.Series) -> float:
        """Calculate lower wick size: min(open, close) - low."""
        low = float(candle["low"])
        body_bottom = min(float(candle["open"]), float(candle["close"]))
        return max(0.0, body_bottom - low)

    def _upper_wick(self, candle: pd.Series) -> float:
        """Calculate upper wick size: high - max(open, close)."""
        high = float(candle["high"])
        body_top = max(float(candle["open"]), float(candle["close"]))
        return max(0.0, high - body_top)

    def _recovery_pct(self, candle: pd.Series, wick_type: str) -> float:
        """Calculate what fraction of the wick was recovered within the same candle.

        For a lower wick: recovery = (close - low) / (high - low) measured against
        the wick portion. Specifically how far close recovered from the wick extreme.

        Args:
            candle: A single OHLCV row.
            wick_type: "lower" or "upper".

        Returns:
            Recovery fraction between 0.0 and 1.0.
        """
        high = float(candle["high"])
        low = float(candle["low"])
        close = float(candle["close"])
        candle_range = high - low

        if candle_range <= 0:
            return 0.0

        if wick_type == "lower":
            # How far did close recover from the low toward the high?
            # Recovery = (close - low) / candle_range
            # But we want recovery relative to the wick, not full range.
            body_bottom = min(float(candle["open"]), float(candle["close"]))
            lower_wick_size = max(0.0, body_bottom - low)
            if lower_wick_size <= 0:
                return 0.0
            # Recovery fraction: how much of the wick was recouped
            recovered = close - low
            return min(1.0, recovered / (lower_wick_size + 1e-10))
        else:
            # Upper wick recovery (close dropped back from the high)
            body_top = max(float(candle["open"]), float(candle["close"]))
            upper_wick_size = max(0.0, high - body_top)
            if upper_wick_size <= 0:
                return 0.0
            recovered = high - close
            return min(1.0, recovered / (upper_wick_size + 1e-10))

    def calculate_confidence(
        self,
        wick_atr_multiple: float,
        recovery_pct: float,
        volume_ratio: float,
    ) -> float:
        """Calculate signal confidence from wick size, recovery, and volume.

        Base: 65%
        + up to 10% for larger wick (capped at 6× ATR)
        + up to 10% for better recovery (1.0 = 10%)
        + up to 10% for higher volume
        Total max: 95%
        """
        base = 65.0

        # Wick size bonus: 0–10% linearly from 3× to 6× ATR
        wick_bonus = min(10.0, max(0.0, (wick_atr_multiple - self.MIN_WICK_ATR_MULTIPLE) / 3.0 * 10.0))

        # Recovery bonus: 0–10% linearly from 50% to 100% recovery
        recovery_bonus = min(10.0, max(0.0, (recovery_pct - self.MIN_RECOVERY_PCT) / 0.5 * 10.0))

        # Volume bonus: 0–10% for volume 1.5× to 4×
        volume_bonus = min(10.0, max(0.0, (volume_ratio - self.VOLUME_SPIKE_THRESHOLD) / 2.5 * 10.0))

        return round(min(base + wick_bonus + recovery_bonus + volume_bonus, 95.0), 1)


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calculate ATR using Wilder's smoothing from OHLCV DataFrame."""
    high = df["high"]
    low = df["low"]
    prev_close = df["close"].shift(1)

    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    # Wilder's smoothing (equivalent to EWM with alpha = 1/period)
    atr = tr.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    return atr
