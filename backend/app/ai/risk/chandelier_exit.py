"""Chandelier Exit — trailing stop that moves only in favor of the trade."""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ChandelierStop:
    """Current state of a chandelier trailing stop."""

    direction: str            # "LONG" or "SHORT"
    stop_price: float         # current trailing stop level
    highest_high: float       # for long: highest close since entry
    lowest_low: float         # for short: lowest close since entry
    atr: float
    atr_multiplier: float
    is_triggered: bool        # True if current price crossed the stop
    trail_distance_pct: float  # how far stop is from current price in %


class ChandelierExitCalculator:
    """Chandelier Exit trailing stop — invented by Charles Le Beau.

    LONG:  stop = highest_close_since_entry - (ATR × multiplier)
           stop moves UP as trade profits, never DOWN.
    SHORT: stop = lowest_close_since_entry + (ATR × multiplier)
           stop moves DOWN as trade profits, never UP.

    Default multiplier: 3.0 (standard).
    ATR period: 22 candles (standard).

    This captures full trend moves rather than exiting at a fixed TP.
    """

    DEFAULT_ATR_PERIOD = 22
    DEFAULT_ATR_MULTIPLIER = 3.0

    def calculate(
        self,
        df: pd.DataFrame,
        direction: str,
        entry_idx: int = 0,
        atr_multiplier: float = 3.0,
    ) -> ChandelierStop:
        """Calculate current chandelier stop level from entry candle onwards.

        For LONG:
            atr          = ATR(22) over full df
            highest_close = max(close[entry_idx:])
            stop          = highest_close - (atr * multiplier)

        For SHORT:
            lowest_close  = min(close[entry_idx:])
            stop          = lowest_close + (atr * multiplier)

        is_triggered = True when the current price crosses the stop level.

        Args:
            df: OHLCV DataFrame from trade entry onwards (at least 22 rows
                before entry_idx recommended for a meaningful ATR).
            direction: ``"LONG"`` or ``"SHORT"`` (case-insensitive).
            entry_idx: Integer iloc index of the entry candle in df.
            atr_multiplier: ATR multiplier (default 3.0).

        Returns:
            ChandelierStop dataclass with the current stop state.
        """
        if df is None or df.empty:
            logger.warning("ChandelierExitCalculator.calculate: empty DataFrame")
            return ChandelierStop(
                direction=direction.upper(),
                stop_price=0.0,
                highest_high=0.0,
                lowest_low=0.0,
                atr=0.0,
                atr_multiplier=atr_multiplier,
                is_triggered=False,
                trail_distance_pct=0.0,
            )

        direction = direction.upper()
        atr = self._calculate_atr(df, period=self.DEFAULT_ATR_PERIOD)

        close = df["close"].astype(float)
        since_entry = close.iloc[entry_idx:]
        current_price = float(close.iloc[-1])

        if direction == "LONG":
            highest_high = float(since_entry.max())
            lowest_low = float(since_entry.min())  # tracked but not used for stop
            stop_price = highest_high - (atr * atr_multiplier)
            is_triggered = current_price < stop_price
            trail_distance_pct = (
                ((current_price - stop_price) / current_price * 100)
                if current_price > 0
                else 0.0
            )
        else:  # SHORT
            lowest_low = float(since_entry.min())
            highest_high = float(since_entry.max())  # tracked but not used for stop
            stop_price = lowest_low + (atr * atr_multiplier)
            is_triggered = current_price > stop_price
            trail_distance_pct = (
                ((stop_price - current_price) / current_price * 100)
                if current_price > 0
                else 0.0
            )

        stop = ChandelierStop(
            direction=direction,
            stop_price=round(stop_price, 8),
            highest_high=round(highest_high, 8),
            lowest_low=round(lowest_low, 8),
            atr=round(atr, 8),
            atr_multiplier=atr_multiplier,
            is_triggered=is_triggered,
            trail_distance_pct=round(trail_distance_pct, 4),
        )

        logger.debug(
            "ChandelierStop calculated: direction=%s stop=%.6f triggered=%s dist_pct=%.2f%%",
            direction,
            stop_price,
            is_triggered,
            trail_distance_pct,
        )
        return stop

    def update_stop(
        self,
        current_stop: ChandelierStop,
        new_candle: pd.Series,
        current_atr: float,
    ) -> ChandelierStop:
        """Update an existing chandelier stop with one new candle.

        The stop level can only move in the profitable direction — it never
        moves against the trade (ratchet behaviour).

        Args:
            current_stop: The previous ChandelierStop state.
            new_candle: A pandas Series with at least a ``close`` key.
            current_atr: The latest ATR value to use for this update.

        Returns:
            Updated ChandelierStop dataclass.
        """
        new_close = float(new_candle["close"])
        direction = current_stop.direction
        multiplier = current_stop.atr_multiplier

        if direction == "LONG":
            new_highest = max(current_stop.highest_high, new_close)
            new_stop = new_highest - (current_atr * multiplier)
            # Ratchet: stop can only move up
            new_stop = max(new_stop, current_stop.stop_price)
            is_triggered = new_close < new_stop
            trail_distance_pct = (
                ((new_close - new_stop) / new_close * 100) if new_close > 0 else 0.0
            )
            new_lowest = current_stop.lowest_low  # unchanged
        else:  # SHORT
            new_lowest = min(current_stop.lowest_low, new_close)
            new_stop = new_lowest + (current_atr * multiplier)
            # Ratchet: stop can only move down
            new_stop = min(new_stop, current_stop.stop_price)
            is_triggered = new_close > new_stop
            trail_distance_pct = (
                ((new_stop - new_close) / new_close * 100) if new_close > 0 else 0.0
            )
            new_highest = current_stop.highest_high  # unchanged

        updated = ChandelierStop(
            direction=direction,
            stop_price=round(new_stop, 8),
            highest_high=round(new_highest, 8),
            lowest_low=round(new_lowest, 8),
            atr=round(current_atr, 8),
            atr_multiplier=multiplier,
            is_triggered=is_triggered,
            trail_distance_pct=round(trail_distance_pct, 4),
        )

        logger.debug(
            "ChandelierStop updated: direction=%s stop=%.6f→%.6f triggered=%s",
            direction,
            current_stop.stop_price,
            new_stop,
            is_triggered,
        )
        return updated

    def _calculate_atr(self, df: pd.DataFrame, period: int = 22) -> float:
        """Calculate ATR using Wilder's smoothed (RMA) method.

        True Range = max(high-low, |high-prev_close|, |low-prev_close|)
        ATR = Wilder's smoothed average of TR over ``period`` bars.

        Args:
            df: OHLCV DataFrame with ``high``, ``low``, ``close`` columns.
            period: ATR period (default 22).

        Returns:
            Latest ATR value as float. Returns 0.0 if insufficient data.
        """
        if len(df) < 2:
            return 0.0

        high = df["high"].astype(float)
        low = df["low"].astype(float)
        close = df["close"].astype(float)
        prev_close = close.shift(1)

        tr = pd.concat(
            [
                high - low,
                (high - prev_close).abs(),
                (low - prev_close).abs(),
            ],
            axis=1,
        ).max(axis=1)

        # Wilder's smoothing (equivalent to EWM with alpha = 1/period)
        atr_series = tr.ewm(alpha=1.0 / period, adjust=False).mean()
        result = float(atr_series.iloc[-1])
        return result if not np.isnan(result) else 0.0

    def compare_vs_fixed(
        self,
        chandelier_stop: ChandelierStop,
        fixed_tp: float,
        current_price: float,
    ) -> dict:
        """Compare chandelier exit versus a fixed take-profit level.

        Estimates which exit strategy would yield a better outcome based on
        current price and the trailing stop distance.

        Args:
            chandelier_stop: The current ChandelierStop state.
            fixed_tp: Fixed take-profit price level.
            current_price: Current market price.

        Returns:
            Dict with keys:
              - ``preferred``: ``"chandelier"`` or ``"fixed_tp"``
              - ``chandelier_gain_pct``: estimated gain if chandelier exit
              - ``fixed_tp_gain_pct``: gain at fixed TP
              - ``gain_difference_pct``: chandelier - fixed_tp
              - ``rationale``: short explanation string
        """
        direction = chandelier_stop.direction

        if direction == "LONG":
            chandelier_gain_pct = (
                (chandelier_stop.stop_price / current_price - 1) * 100
                if current_price > 0
                else 0.0
            )
            fixed_tp_gain_pct = (
                (fixed_tp / current_price - 1) * 100 if current_price > 0 else 0.0
            )
        else:  # SHORT
            chandelier_gain_pct = (
                (current_price / chandelier_stop.stop_price - 1) * 100
                if chandelier_stop.stop_price > 0
                else 0.0
            )
            fixed_tp_gain_pct = (
                (current_price / fixed_tp - 1) * 100 if fixed_tp > 0 else 0.0
            )

        gain_difference = chandelier_gain_pct - fixed_tp_gain_pct

        if gain_difference > 0:
            preferred = "chandelier"
            rationale = (
                f"Chandelier stop at {chandelier_stop.stop_price:.6f} captures "
                f"{gain_difference:.2f}% more than fixed TP — trend still running."
            )
        else:
            preferred = "fixed_tp"
            rationale = (
                f"Fixed TP at {fixed_tp:.6f} delivers {abs(gain_difference):.2f}% "
                f"more than current chandelier stop — take profit now."
            )

        return {
            "preferred": preferred,
            "chandelier_gain_pct": round(chandelier_gain_pct, 4),
            "fixed_tp_gain_pct": round(fixed_tp_gain_pct, 4),
            "gain_difference_pct": round(gain_difference, 4),
            "rationale": rationale,
        }
