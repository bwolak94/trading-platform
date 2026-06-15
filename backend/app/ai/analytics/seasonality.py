"""Seasonality Engine — historical performance patterns by time periods."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from app.core.logging import get_logger

logger = get_logger(__name__)

# Day-of-week labels (Python weekday: 0 = Monday, 6 = Sunday)
DAY_LABELS: dict[int, str] = {
    0: "Monday",
    1: "Tuesday",
    2: "Wednesday",
    3: "Thursday",
    4: "Friday",
    5: "Saturday",
    6: "Sunday",
}

# Number of trades below which we penalise the confidence multiplier
MIN_TRADE_COUNT_FULL_CONFIDENCE: int = 10


@dataclass
class SeasonalityStats:
    """Performance statistics for a specific time period bucket."""

    period_label: str             # e.g. "Monday", "14:00 UTC", "Week 3"
    win_rate: float               # fraction of winning periods (0-1)
    avg_return_pct: float         # average return (%) for this bucket
    trade_count: int              # number of observations
    confidence_multiplier: float  # 0.5 – 1.5 to scale signal confidence


@dataclass
class SeasonalityReport:
    """Full seasonality report for a symbol / dataset."""

    symbol: str
    best_hours: list[SeasonalityStats]     # top 5 UTC hours by win rate
    worst_hours: list[SeasonalityStats]    # bottom 5 UTC hours
    best_days: list[SeasonalityStats]      # best days of week by win rate
    worst_days: list[SeasonalityStats]     # worst days of week
    current_period_multiplier: float       # multiplier to apply right now
    current_hour_stats: SeasonalityStats
    current_day_stats: SeasonalityStats
    recommendation: str   # "PRIME_TIME", "ABOVE_AVERAGE", "BELOW_AVERAGE", "AVOID"


class SeasonalityEngine:
    """Analyses historical performance patterns by time of day and day of week.

    Two analysis modes are supported:
    - ``analyze_from_trades``: uses a list of completed trade records.
    - ``analyze_from_ohlcv``: derives returns from raw OHLCV candle data.

    The engine emits a ``current_period_multiplier`` (0.5 – 1.5) that can be
    multiplied against a live signal's confidence to account for seasonal edge.
    """

    def analyze_from_trades(
        self,
        trades: list[dict],
        symbol: str = "ALL",
    ) -> SeasonalityReport:
        """Analyse historical trades grouped by hour and day.

        Expected trade dict keys:
        - ``entry_time``: ``datetime`` (timezone-aware recommended)
        - ``pnl_pct``: float (P&L as a percentage of entry price)
        - ``result``: ``"WIN"`` or ``"LOSS"`` (optional — derived from pnl_pct if absent)

        Args:
            trades: List of trade record dicts.
            symbol: Label used in the report (e.g. ``"BTC/USDT"`` or ``"ALL"``).

        Returns:
            :class:`SeasonalityReport` with per-hour and per-day performance stats.
        """
        if not trades:
            logger.warning("SeasonalityEngine.analyze_from_trades: no trades provided")
            return self._empty_report(symbol)

        records: list[dict] = []
        for trade in trades:
            entry_time = trade.get("entry_time")
            pnl_pct = trade.get("pnl_pct", 0.0)
            if entry_time is None:
                continue
            if not isinstance(entry_time, datetime):
                try:
                    entry_time = pd.Timestamp(entry_time).to_pydatetime()
                except Exception:
                    continue

            # Ensure UTC
            if entry_time.tzinfo is None:
                entry_time = entry_time.replace(tzinfo=timezone.utc)

            result = trade.get("result")
            if result is None:
                result = "WIN" if pnl_pct > 0 else "LOSS"

            records.append({
                "hour": entry_time.hour,
                "day": entry_time.weekday(),
                "pnl_pct": float(pnl_pct),
                "is_win": result.upper() == "WIN",
            })

        if not records:
            return self._empty_report(symbol)

        df = pd.DataFrame(records)
        return self._build_report(df, symbol)

    def analyze_from_ohlcv(
        self,
        df: pd.DataFrame,
        symbol: str = "BTC/USDT",
    ) -> SeasonalityReport:
        """Derive seasonality from raw OHLCV candle data.

        Each candle's return is calculated as ``(close - open) / open * 100``.
        Candles are grouped by their UTC hour and weekday to identify historically
        profitable vs unprofitable time windows.

        Args:
            df: OHLCV DataFrame with a ``DatetimeIndex`` (UTC recommended) and
                columns including at least ``open`` and ``close``.
            symbol: Label for the report.

        Returns:
            :class:`SeasonalityReport`.
        """
        required = {"open", "close"}
        if not required.issubset(df.columns):
            logger.error(
                "SeasonalityEngine: missing columns %s in OHLCV data for %s",
                required - set(df.columns), symbol,
            )
            return self._empty_report(symbol)

        if df.empty or len(df) < 20:
            logger.warning(
                "SeasonalityEngine: insufficient OHLCV rows for %s (%d)", symbol, len(df)
            )
            return self._empty_report(symbol)

        # Ensure DatetimeIndex with UTC
        idx = df.index
        if not isinstance(idx, pd.DatetimeIndex):
            try:
                idx = pd.to_datetime(idx, utc=True)
            except Exception as exc:
                logger.error("SeasonalityEngine: failed to parse index as datetime: %s", exc)
                return self._empty_report(symbol)

        if idx.tz is None:
            idx = idx.tz_localize("UTC")
        else:
            idx = idx.tz_convert("UTC")

        opens = df["open"].astype(float).values
        closes = df["close"].astype(float).values

        records = []
        for i, (o, c) in enumerate(zip(opens, closes)):
            if o == 0:
                continue
            pnl_pct = (c - o) / o * 100.0
            records.append({
                "hour": idx[i].hour,
                "day": idx[i].weekday(),
                "pnl_pct": pnl_pct,
                "is_win": pnl_pct > 0,
            })

        if not records:
            return self._empty_report(symbol)

        data_df = pd.DataFrame(records)
        return self._build_report(data_df, symbol)

    def get_current_multiplier(self, report: SeasonalityReport) -> float:
        """Return the confidence multiplier to apply for the current moment.

        The combined multiplier is the average of the current hour's and the
        current day's individual multipliers, clamped to [0.5, 1.5].

        Args:
            report: A previously computed :class:`SeasonalityReport`.

        Returns:
            Combined multiplier in [0.5, 1.5].
        """
        combined = (
            report.current_hour_stats.confidence_multiplier
            + report.current_day_stats.confidence_multiplier
        ) / 2.0
        return round(max(0.5, min(1.5, combined)), 3)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_report(self, df: pd.DataFrame, symbol: str) -> SeasonalityReport:
        """Build the full ``SeasonalityReport`` from a normalised records DataFrame.

        Args:
            df: DataFrame with columns ``hour``, ``day``, ``pnl_pct``, ``is_win``.
            symbol: Symbol label for the report.

        Returns:
            Populated :class:`SeasonalityReport`.
        """
        # Per-hour stats
        hour_stats: list[SeasonalityStats] = []
        for hour in range(24):
            subset = df[df["hour"] == hour]["pnl_pct"].tolist()
            stats = self._calculate_stats(subset, f"{hour:02d}:00 UTC")
            hour_stats.append(stats)

        # Per-day stats
        day_stats: list[SeasonalityStats] = []
        for day_idx in range(7):
            subset = df[df["day"] == day_idx]["pnl_pct"].tolist()
            stats = self._calculate_stats(subset, DAY_LABELS[day_idx])
            day_stats.append(stats)

        # Sort by win rate descending
        sorted_hours = sorted(hour_stats, key=lambda s: s.win_rate, reverse=True)
        sorted_days = sorted(day_stats, key=lambda s: s.win_rate, reverse=True)

        # Current moment stats
        now = datetime.now(timezone.utc)
        current_hour_stats = hour_stats[now.hour]
        current_day_stats = day_stats[now.weekday()]
        current_period_multiplier = (
            current_hour_stats.confidence_multiplier
            + current_day_stats.confidence_multiplier
        ) / 2.0
        current_period_multiplier = round(max(0.5, min(1.5, current_period_multiplier)), 3)

        recommendation = self._recommendation(current_period_multiplier)

        logger.info(
            "SeasonalityEngine: %s current_multiplier=%.3f recommendation=%s",
            symbol, current_period_multiplier, recommendation,
        )

        return SeasonalityReport(
            symbol=symbol,
            best_hours=sorted_hours[:5],
            worst_hours=sorted_hours[-5:],
            best_days=sorted_days[:3],
            worst_days=sorted_days[-3:],
            current_period_multiplier=current_period_multiplier,
            current_hour_stats=current_hour_stats,
            current_day_stats=current_day_stats,
            recommendation=recommendation,
        )

    def _calculate_stats(
        self, returns: list[float], label: str
    ) -> SeasonalityStats:
        """Calculate win rate and average return for a list of period returns.

        Args:
            returns: List of percentage returns for this bucket.
            label: Human-readable label for this time bucket.

        Returns:
            :class:`SeasonalityStats` for the bucket.
        """
        if not returns:
            return SeasonalityStats(
                period_label=label,
                win_rate=0.5,
                avg_return_pct=0.0,
                trade_count=0,
                confidence_multiplier=1.0,
            )

        wins = sum(1 for r in returns if r > 0)
        win_rate = wins / len(returns)
        avg_return = float(np.mean(returns))
        multiplier = self._multiplier_from_winrate(win_rate, float(len(returns)))

        return SeasonalityStats(
            period_label=label,
            win_rate=round(win_rate, 4),
            avg_return_pct=round(avg_return, 4),
            trade_count=len(returns),
            confidence_multiplier=round(multiplier, 3),
        )

    def _multiplier_from_winrate(
        self, win_rate: float, avg_trades: float
    ) -> float:
        """Convert win rate and sample size to a confidence multiplier.

        Tiered mapping:
        - Win rate > 65%: 1.3×
        - Win rate > 60%: 1.2×
        - Win rate 50-60% (average): 1.0×
        - Win rate 40-50% (below avg): 0.85×
        - Win rate < 40%: 0.7×

        Small sample size penalty: if fewer than 10 observations, the multiplier
        is pulled toward 1.0 (neutral) proportionally.

        Args:
            win_rate: Fraction of winning periods (0–1).
            avg_trades: Number of observations in the bucket.

        Returns:
            Multiplier in [0.5, 1.5].
        """
        if win_rate > 0.65:
            multiplier = 1.3
        elif win_rate > 0.60:
            multiplier = 1.2
        elif win_rate >= 0.50:
            multiplier = 1.0
        elif win_rate >= 0.40:
            multiplier = 0.85
        else:
            multiplier = 0.7

        # Insufficient data: blend toward neutral 1.0
        if avg_trades < MIN_TRADE_COUNT_FULL_CONFIDENCE:
            # Linear blend: at 0 observations → 1.0; at 10 → full multiplier
            blend_factor = avg_trades / MIN_TRADE_COUNT_FULL_CONFIDENCE
            multiplier = 1.0 + (multiplier - 1.0) * blend_factor

        return max(0.5, min(1.5, multiplier))

    @staticmethod
    def _recommendation(multiplier: float) -> str:
        """Convert a combined multiplier to a human-readable recommendation.

        Args:
            multiplier: Current combined period multiplier.

        Returns:
            One of ``"PRIME_TIME"``, ``"ABOVE_AVERAGE"``, ``"BELOW_AVERAGE"``, ``"AVOID"``.
        """
        if multiplier >= 1.2:
            return "PRIME_TIME"
        if multiplier >= 1.05:
            return "ABOVE_AVERAGE"
        if multiplier >= 0.85:
            return "BELOW_AVERAGE"
        return "AVOID"

    @staticmethod
    def _empty_report(symbol: str) -> SeasonalityReport:
        """Return a neutral placeholder report when data is unavailable.

        Args:
            symbol: Symbol label.

        Returns:
            :class:`SeasonalityReport` with all neutral values.
        """
        neutral_hour = SeasonalityStats(
            period_label="UNKNOWN", win_rate=0.5, avg_return_pct=0.0,
            trade_count=0, confidence_multiplier=1.0,
        )
        neutral_day = SeasonalityStats(
            period_label="UNKNOWN", win_rate=0.5, avg_return_pct=0.0,
            trade_count=0, confidence_multiplier=1.0,
        )
        return SeasonalityReport(
            symbol=symbol,
            best_hours=[],
            worst_hours=[],
            best_days=[],
            worst_days=[],
            current_period_multiplier=1.0,
            current_hour_stats=neutral_hour,
            current_day_stats=neutral_day,
            recommendation="BELOW_AVERAGE",
        )
