"""Overnight Gap Scanner — assesses risk of holding through session closes."""

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class GapRiskAssessment:
    """Full risk assessment for holding a position through an upcoming gap period."""

    symbol: str
    direction: str               # trade direction: "LONG" or "SHORT"
    stop_loss_distance_pct: float
    avg_gap_pct: float           # historical average gap for this period type
    max_gap_pct: float           # historical worst-case gap
    gap_exceeds_stop: bool       # True if avg_gap > stop_loss_distance — dangerous
    risk_level: str              # "LOW", "MEDIUM", "HIGH", "EXTREME"
    recommendation: str          # "HOLD", "REDUCE_SIZE", "TIGHTEN_STOP", "CLOSE_BEFORE_GAP"
    next_gap_event: str          # "WEEKEND", "DAILY_CLOSE", "NONE"
    hours_until_gap: float
    description: str


class OvernightGapScanner:
    """Assesses the risk of holding positions through gap periods.

    Covered gap events
    ------------------
    - Weekends : Friday 21:00 UTC → Monday 00:00 UTC
    - Daily session closes : 21:00 UTC each day (crypto perpetuals stay open, but
      traditional instruments and many algos reset at this time causing gaps)

    Usage
    -----
    Pass a daily OHLCV DataFrame (``df``) with enough history (≥ 30 bars) for
    reliable gap statistics.  The scanner calculates historical gap sizes,
    compares them against the current stop-loss distance, and emits a
    recommendation.
    """

    WEEKEND_START_HOUR: int = 21   # Friday 21:00 UTC = weekend open risk
    WEEKEND_START_WEEKDAY: int = 4  # Friday (Python: Monday=0 … Sunday=6)
    DAILY_CLOSE_HOUR: int = 21     # 21:00 UTC daily

    MIN_HISTORY: int = 10          # minimum gap observations for statistics

    def assess(
        self,
        symbol: str,
        df: pd.DataFrame,
        direction: str,
        stop_loss_price: float,
        entry_price: float,
    ) -> GapRiskAssessment:
        """Produce a gap risk assessment for a potential or open position.

        Steps
        -----
        1. Calculate historical gaps from daily OHLCV.
        2. Separate weekend gaps from regular daily gaps.
        3. Determine average and worst-case gap statistics for the relevant period.
        4. Determine the next gap event and hours until it occurs.
        5. Compare gap risk against the stop-loss distance.
        6. Generate a recommendation.

        Args:
            symbol: Instrument symbol (for logging/display).
            df: Daily OHLCV DataFrame.  Must have ``open`` and ``close`` columns.
            direction: Trade direction — ``"LONG"`` or ``"SHORT"``.
            stop_loss_price: Current stop-loss price.
            entry_price: Trade entry price (used to calculate SL distance %).

        Returns:
            GapRiskAssessment dataclass.
        """
        direction = direction.upper()

        # Compute stop-loss distance as % of entry
        if entry_price > 0:
            sl_distance_pct = abs(entry_price - stop_loss_price) / entry_price * 100
        else:
            sl_distance_pct = 0.0

        # Determine next gap event
        next_event, hours_until = self.get_next_gap_event()

        # Select appropriate gap history based on the upcoming event type
        weekend_only = next_event == "WEEKEND"
        gaps = self._calculate_gaps(df, weekend_only=weekend_only)

        if len(gaps) < self.MIN_HISTORY:
            # Fall back to all gaps if insufficient weekend-only history
            gaps = self._calculate_gaps(df, weekend_only=False)

        if not gaps:
            logger.warning(
                "OvernightGapScanner: no gap history for %s — returning LOW risk",
                symbol,
            )
            return GapRiskAssessment(
                symbol=symbol,
                direction=direction,
                stop_loss_distance_pct=round(sl_distance_pct, 4),
                avg_gap_pct=0.0,
                max_gap_pct=0.0,
                gap_exceeds_stop=False,
                risk_level="LOW",
                recommendation="HOLD",
                next_gap_event=next_event,
                hours_until_gap=round(hours_until, 2),
                description="Insufficient gap history to assess risk.",
            )

        avg_gap = float(np.mean(gaps))
        max_gap = float(np.max(gaps))
        gap_exceeds_stop = avg_gap > sl_distance_pct

        risk_level = self._risk_level(avg_gap, max_gap, sl_distance_pct)
        recommendation = self._recommendation(
            risk_level, hours_until, gap_exceeds_stop
        )

        description = (
            f"Next gap event: {next_event} in {hours_until:.1f}h. "
            f"Avg historical gap: {avg_gap:.2f}%, worst-case: {max_gap:.2f}%. "
            f"SL distance: {sl_distance_pct:.2f}%. "
            f"Risk: {risk_level}. Action: {recommendation}."
        )

        logger.info(
            "GapRisk %s %s: level=%s rec=%s (avg_gap=%.2f%% sl=%.2f%%)",
            symbol,
            direction,
            risk_level,
            recommendation,
            avg_gap,
            sl_distance_pct,
        )

        return GapRiskAssessment(
            symbol=symbol,
            direction=direction,
            stop_loss_distance_pct=round(sl_distance_pct, 4),
            avg_gap_pct=round(avg_gap, 4),
            max_gap_pct=round(max_gap, 4),
            gap_exceeds_stop=gap_exceeds_stop,
            risk_level=risk_level,
            recommendation=recommendation,
            next_gap_event=next_event,
            hours_until_gap=round(hours_until, 2),
            description=description,
        )

    def get_next_gap_event(self) -> tuple[str, float]:
        """Return the type and timing of the next gap event relative to now (UTC).

        Logic
        -----
        - If today is Friday and current hour ≥ 21:00, or Saturday/Sunday
          → next event is WEEKEND (could be ongoing; report hours to Monday 00:00)
        - If current hour < 21:00 and today is not Friday/Saturday/Sunday
          → next event is DAILY_CLOSE (today at 21:00)
        - If current hour ≥ 21:00 and tomorrow is a weekday (not Friday)
          → next event is DAILY_CLOSE (tomorrow at 21:00)

        Returns:
            Tuple of (event_type: str, hours_until: float).
        """
        now = datetime.now(timezone.utc)
        weekday = now.weekday()  # Monday=0 … Sunday=6
        hour = now.hour + now.minute / 60.0 + now.second / 3600.0

        # Determine next Monday 00:00 UTC (start of week)
        (7 - weekday) % 7  # 0 if today is Monday

        if weekday == 4 and hour >= self.WEEKEND_START_HOUR:
            # Friday after 21:00 — weekend has started
            monday_00 = (now + timedelta(days=(7 - weekday))).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            hours_until = (monday_00 - now).total_seconds() / 3600
            return ("WEEKEND", max(0.0, hours_until))

        if weekday in (5, 6):
            # Saturday or Sunday — weekend ongoing
            monday_00 = (now + timedelta(days=(7 - weekday))).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            hours_until = (monday_00 - now).total_seconds() / 3600
            return ("WEEKEND", max(0.0, hours_until))

        # Weekday — check proximity to Friday 21:00 or next daily close (21:00)
        if weekday == 4:
            # Friday, before 21:00
            friday_21 = now.replace(
                hour=self.WEEKEND_START_HOUR, minute=0, second=0, microsecond=0
            )
            hours_until = (friday_21 - now).total_seconds() / 3600
            return ("WEEKEND", max(0.0, hours_until))

        # Monday–Thursday
        if hour < self.DAILY_CLOSE_HOUR:
            today_21 = now.replace(
                hour=self.DAILY_CLOSE_HOUR, minute=0, second=0, microsecond=0
            )
            hours_until = (today_21 - now).total_seconds() / 3600
            return ("DAILY_CLOSE", max(0.0, hours_until))

        # After 21:00 on a Mon-Thu — next event is tomorrow's close (or Friday weekend)
        tomorrow = now + timedelta(days=1)
        if tomorrow.weekday() == 4:
            # Tomorrow is Friday → next event is WEEKEND
            friday_21 = tomorrow.replace(
                hour=self.WEEKEND_START_HOUR, minute=0, second=0, microsecond=0
            )
            hours_until = (friday_21 - now).total_seconds() / 3600
            return ("WEEKEND", max(0.0, hours_until))

        tomorrow_21 = tomorrow.replace(
            hour=self.DAILY_CLOSE_HOUR, minute=0, second=0, microsecond=0
        )
        hours_until = (tomorrow_21 - now).total_seconds() / 3600
        return ("DAILY_CLOSE", max(0.0, hours_until))

    def _calculate_gaps(
        self, df: pd.DataFrame, weekend_only: bool = False
    ) -> list[float]:
        """Extract historical gap sizes from a daily OHLCV DataFrame.

        A gap is defined as: ``|open[t] - close[t-1]| / close[t-1] * 100`` (percent).

        Args:
            df: Daily OHLCV DataFrame with ``open`` and ``close`` columns and a
                DatetimeIndex (or any index — weekend detection uses ``.index`` if
                it is a DatetimeIndex, otherwise uses all rows).
            weekend_only: If ``True``, only include gaps where the previous row is
                a Friday (proxy for weekend gaps in daily data).

        Returns:
            List of gap sizes in percent (positive floats).
        """
        if df is None or len(df) < 2:
            return []

        try:
            close = df["close"].astype(float)
            open_ = df["open"].astype(float)
            prev_close = close.shift(1)
            gap_series = (open_ - prev_close).abs() / prev_close.abs() * 100
            gap_series = gap_series.dropna()

            if not weekend_only:
                return [float(g) for g in gap_series if not np.isnan(g) and g >= 0]

            # Weekend-only: check if index is DatetimeIndex
            if isinstance(df.index, pd.DatetimeIndex):
                # Friday close → Monday open = weekend gap (weekday 4 = Friday)
                gaps: list[float] = []
                for idx_label in gap_series.index:
                    pos = df.index.get_loc(idx_label)
                    if pos == 0:
                        continue
                    prev_label = df.index[pos - 1]
                    if hasattr(prev_label, "weekday") and prev_label.weekday() == 4:
                        g = float(gap_series.loc[idx_label])
                        if not np.isnan(g) and g >= 0:
                            gaps.append(g)
                return gaps
            else:
                # No DatetimeIndex — cannot distinguish weekend gaps
                return [float(g) for g in gap_series if not np.isnan(g) and g >= 0]
        except Exception as exc:
            logger.error("OvernightGapScanner._calculate_gaps error: %s", exc)
            return []

    def _risk_level(
        self, avg_gap: float, max_gap: float, sl_distance: float
    ) -> str:
        """Classify gap risk into LOW / MEDIUM / HIGH / EXTREME.

        Rules
        -----
        - EXTREME : sl_distance < max_gap * 0.5  (stop is inside worst-case gap)
        - HIGH    : sl_distance < avg_gap         (stop smaller than average gap)
        - MEDIUM  : sl_distance < avg_gap * 1.5   (stop less than 1.5× avg gap)
        - LOW     : sl_distance ≥ avg_gap * 2.0

        Args:
            avg_gap: Average historical gap in percent.
            max_gap: Worst-case historical gap in percent.
            sl_distance: Current stop-loss distance from entry in percent.

        Returns:
            Risk level string.
        """
        if sl_distance <= 0:
            return "HIGH"  # can't assess without SL distance
        if sl_distance < max_gap * 0.5:
            return "EXTREME"
        if sl_distance < avg_gap:
            return "HIGH"
        if sl_distance < avg_gap * 1.5:
            return "MEDIUM"
        return "LOW"

    def _recommendation(
        self, risk_level: str, hours_until: float, gap_exceeds_stop: bool
    ) -> str:
        """Generate an actionable recommendation based on risk level and timing.

        Args:
            risk_level: One of ``"LOW"``, ``"MEDIUM"``, ``"HIGH"``, ``"EXTREME"``.
            hours_until: Hours until the next gap event.
            gap_exceeds_stop: Whether the average gap exceeds the SL distance.

        Returns:
            Recommendation string.
        """
        if risk_level == "EXTREME":
            return "CLOSE_BEFORE_GAP"
        if risk_level == "HIGH":
            if hours_until <= 2.0:
                return "CLOSE_BEFORE_GAP"
            return "TIGHTEN_STOP"
        if risk_level == "MEDIUM":
            if hours_until <= 1.0:
                return "TIGHTEN_STOP"
            return "REDUCE_SIZE"
        # LOW
        return "HOLD"
