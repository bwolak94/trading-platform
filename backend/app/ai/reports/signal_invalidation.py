"""Signal Invalidation Reporter — lists what could go wrong with a signal."""

from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from app.ai.strategies.base import MarketContext, SignalResult
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class InvalidationFactor:
    """A single identified risk that could cause the signal to fail."""

    risk_name: str
    severity: str             # "HIGH", "MEDIUM", "LOW"
    description: str
    probability: float        # estimated % chance this invalidates the signal
    monitor_price: float | None  # price level to watch (if applicable)


@dataclass
class InvalidationReport:
    """Full invalidation analysis for a single signal."""

    signal: SignalResult
    invalidation_factors: list[InvalidationFactor]
    overall_risk_level: str     # "HIGH", "MEDIUM", "LOW"
    top_risk: InvalidationFactor | None
    max_adverse_move_pct: float  # worst-case % move before stop is hit
    summary: str


# ---------------------------------------------------------------------------
# Severity weights used for overall risk aggregation
# ---------------------------------------------------------------------------
_SEVERITY_WEIGHT = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}


class SignalInvalidationReporter:
    """Generates a "what could go wrong" report for any signal.

    Checks for:
    1.  Upcoming macro events (HIGH impact within 4h)
    2.  Key resistance/support near entry (limited R:R)
    3.  Funding rate opposing direction (cost risk)
    4.  High recent volatility (stop distance may be insufficient)
    5.  Over-extended entry (price far from key MA)
    6.  Session ending soon (signal may not resolve before close)
    """

    # Thresholds
    MACRO_WINDOW_HOURS = 4
    RESISTANCE_PROXIMITY_PCT = 1.5   # within 1.5% of entry
    FUNDING_OPPOSE_THRESHOLD = 0.0002  # 0.02% per 8h — notable cost
    HIGH_VOL_QUANTILE = 0.80         # top 20% of historical HV = high
    OVEREXTENSION_ATR_MULT = 2.0
    SESSION_END_BUFFER_HOURS = 1.0   # flag if session ends within 1h

    # Session end times in UTC (inclusive end hour)
    _SESSIONS = {
        "LONDON": (7, 16),
        "NY": (13, 21),
    }

    def generate(
        self,
        signal: SignalResult,
        market_data: pd.DataFrame,
        context: MarketContext,
        macro_events: list[dict] | None = None,
        funding_rate: float = 0.0,
        btc_dominance_trend: str = "NEUTRAL",
    ) -> InvalidationReport:
        """Generate a complete invalidation report.

        Args:
            signal: The candidate signal.
            market_data: OHLCV DataFrame (at least 50 bars recommended).
            context: Current market regime / session context.
            macro_events: Upcoming macro event dicts (keys: impact, timestamp).
            funding_rate: 8h funding rate as decimal (e.g. 0.0003 = 0.03%).
            btc_dominance_trend: "RISING", "FALLING", or "NEUTRAL".

        Returns:
            InvalidationReport with all identified risks ranked by severity.
        """
        if macro_events is None:
            macro_events = []

        factors: list[InvalidationFactor] = []

        # Run all checks — each returns an InvalidationFactor or None
        checks = [
            self._check_macro_risk(macro_events, signal),
            self._check_resistance_proximity(signal, market_data),
            self._check_funding_risk(signal, funding_rate),
            self._check_volatility_risk(signal, market_data),
            self._check_overextension(signal, market_data),
            self._check_session_risk(signal),
        ]

        for factor in checks:
            if factor is not None:
                factors.append(factor)

        # Sort by severity (HIGH first), then by probability descending
        factors.sort(
            key=lambda f: (_SEVERITY_WEIGHT.get(f.severity, 0) * -1, -f.probability)
        )

        overall_risk = self._overall_risk(factors)
        top_risk = factors[0] if factors else None

        # Max adverse move: distance from entry to stop as %
        entry = signal.entry_price
        stop = signal.stop_loss
        max_adverse_move_pct = round(abs(entry - stop) / max(entry, 1e-9) * 100, 2) if entry > 0 else 0.0

        summary = self._build_summary(signal, factors, overall_risk, max_adverse_move_pct)

        logger.debug(
            "InvalidationReport: asset=%s dir=%s overall=%s factors=%d",
            signal.asset, signal.direction, overall_risk, len(factors),
        )

        return InvalidationReport(
            signal=signal,
            invalidation_factors=factors,
            overall_risk_level=overall_risk,
            top_risk=top_risk,
            max_adverse_move_pct=max_adverse_move_pct,
            summary=summary,
        )

    # ------------------------------------------------------------------
    # Individual risk checks
    # ------------------------------------------------------------------

    def _check_macro_risk(
        self, macro_events: list[dict], signal: SignalResult
    ) -> InvalidationFactor | None:
        """HIGH risk if a high-impact macro event is scheduled within 4 hours."""
        if not macro_events:
            return None

        now = datetime.now(timezone.utc)
        window_seconds = self.MACRO_WINDOW_HOURS * 3600

        upcoming_high: list[str] = []
        for event in macro_events:
            impact = str(event.get("impact", "")).upper()
            if impact != "HIGH":
                continue

            ts = event.get("timestamp") or event.get("event_time")
            if ts is None:
                continue

            event_dt = _parse_timestamp(ts)
            if event_dt is None:
                continue

            delta = (event_dt - now).total_seconds()
            if 0 <= delta <= window_seconds:
                name = event.get("name") or event.get("title") or "Unknown Event"
                upcoming_high.append(str(name))

        if not upcoming_high:
            return None

        return InvalidationFactor(
            risk_name="macro_event_risk",
            severity="HIGH",
            description=(
                f"HIGH impact event(s) within {self.MACRO_WINDOW_HOURS}h: "
                + ", ".join(upcoming_high[:3])
            ),
            probability=65.0,
            monitor_price=None,
        )

    def _check_resistance_proximity(
        self, signal: SignalResult, market_data: pd.DataFrame
    ) -> InvalidationFactor | None:
        """Check if a key resistance (LONG) or support (SHORT) is within 1.5% of the entry.

        Uses recent swing highs/lows as resistance/support proxy.
        """
        if market_data is None or len(market_data) < 20:
            return None

        entry = signal.entry_price
        if entry <= 0:
            return None

        proximity_threshold = entry * (self.RESISTANCE_PROXIMITY_PCT / 100)

        highs = market_data["high"].values.astype(float) if "high" in market_data.columns else market_data["close"].values.astype(float)
        lows = market_data["low"].values.astype(float) if "low" in market_data.columns else market_data["close"].values.astype(float)

        # Find swing highs/lows in last 50 bars using a simple local-extrema approach
        lookback = min(50, len(highs))
        swing_highs = _find_swing_highs(highs[-lookback:], window=5)
        swing_lows = _find_swing_lows(lows[-lookback:], window=5)

        if signal.direction == "LONG":
            # Check for resistance (swing high) just above entry
            blocking_levels = [h for h in swing_highs if entry < h <= entry + proximity_threshold]
            if blocking_levels:
                nearest = min(blocking_levels)
                gap_pct = round((nearest - entry) / entry * 100, 2)
                return InvalidationFactor(
                    risk_name="resistance_proximity",
                    severity="MEDIUM",
                    description=f"Swing resistance at {nearest:.4f} only {gap_pct}% above entry — R:R compressed",
                    probability=40.0,
                    monitor_price=nearest,
                )
        else:
            # SHORT: check for support (swing low) just below entry
            blocking_levels = [l for l in swing_lows if entry - proximity_threshold <= l < entry]
            if blocking_levels:
                nearest = max(blocking_levels)
                gap_pct = round((entry - nearest) / entry * 100, 2)
                return InvalidationFactor(
                    risk_name="support_proximity",
                    severity="MEDIUM",
                    description=f"Swing support at {nearest:.4f} only {gap_pct}% below entry — R:R compressed",
                    probability=40.0,
                    monitor_price=nearest,
                )

        return None

    def _check_funding_risk(
        self, signal: SignalResult, funding_rate: float
    ) -> InvalidationFactor | None:
        """Flag significant funding that opposes the signal direction.

        High positive funding on a LONG means longs pay shorts — increased carry cost.
        High negative funding on a SHORT means shorts pay longs — increased carry cost.
        """
        if abs(funding_rate) < self.FUNDING_OPPOSE_THRESHOLD:
            return None  # negligible funding: not a risk

        annual_pct = round(funding_rate * 3 * 365 * 100, 1)  # 3 funding periods/day

        if signal.direction == "LONG" and funding_rate > self.FUNDING_OPPOSE_THRESHOLD:
            return InvalidationFactor(
                risk_name="adverse_funding_long",
                severity="MEDIUM",
                description=(
                    f"Positive funding {funding_rate*100:.4f}% (8h) opposes LONG "
                    f"(~{annual_pct}% annualised carry cost)"
                ),
                probability=30.0,
                monitor_price=None,
            )

        if signal.direction == "SHORT" and funding_rate < -self.FUNDING_OPPOSE_THRESHOLD:
            return InvalidationFactor(
                risk_name="adverse_funding_short",
                severity="MEDIUM",
                description=(
                    f"Negative funding {funding_rate*100:.4f}% (8h) opposes SHORT "
                    f"(~{abs(annual_pct):.1f}% annualised carry cost)"
                ),
                probability=30.0,
                monitor_price=None,
            )

        return None

    def _check_volatility_risk(
        self, signal: SignalResult, market_data: pd.DataFrame
    ) -> InvalidationFactor | None:
        """Flag if recent historical volatility is in the top-20% — stop may be insufficient."""
        if market_data is None or len(market_data) < 30:
            return None

        closes = market_data["close"].values.astype(float)
        log_returns = np.diff(np.log(closes + 1e-12))

        if len(log_returns) < 10:
            return None

        # Rolling 14-period HV (annualised)
        window = 14
        if len(log_returns) < window:
            window = len(log_returns)

        rolling_std = pd.Series(log_returns).rolling(window).std().dropna().values
        if len(rolling_std) < 2:
            return None

        current_hv = float(rolling_std[-1]) * np.sqrt(365 * 24)  # hourly → annual
        historical_threshold = float(np.quantile(rolling_std, self.HIGH_VOL_QUANTILE)) * np.sqrt(365 * 24)

        if current_hv > historical_threshold:
            # Estimate ATR-based stop adequacy
            entry = signal.entry_price
            stop = signal.stop_loss
            stop_dist_pct = abs(entry - stop) / max(entry, 1e-9) * 100 if entry > 0 else 0.0
            daily_vol_pct = current_hv / np.sqrt(365) * 100

            severity = "HIGH" if daily_vol_pct > stop_dist_pct * 1.5 else "MEDIUM"

            return InvalidationFactor(
                risk_name="elevated_volatility",
                severity=severity,
                description=(
                    f"Current HV {current_hv*100:.1f}% annualised is in top-20% of history. "
                    f"Daily 1-sigma move ~{daily_vol_pct:.2f}% vs stop distance {stop_dist_pct:.2f}%"
                ),
                probability=45.0 if severity == "HIGH" else 30.0,
                monitor_price=None,
            )

        return None

    def _check_overextension(
        self, signal: SignalResult, market_data: pd.DataFrame
    ) -> InvalidationFactor | None:
        """Flag if entry is more than 2 ATR from EMA20 — mean reversion risk."""
        if market_data is None or len(market_data) < 22:
            return None

        closes = market_data["close"].values.astype(float)
        highs = market_data["high"].values.astype(float) if "high" in market_data.columns else closes
        lows = market_data["low"].values.astype(float) if "low" in market_data.columns else closes

        ema20 = float(pd.Series(closes).ewm(span=20, adjust=False).mean().iloc[-1])
        atr = _compute_atr(highs, lows, closes, period=14)

        if atr <= 0:
            return None

        entry = signal.entry_price
        distance = abs(entry - ema20)
        distance_atrs = distance / atr

        if distance_atrs > self.OVEREXTENSION_ATR_MULT:
            direction_word = "above" if entry > ema20 else "below"
            return InvalidationFactor(
                risk_name="overextended_entry",
                severity="MEDIUM",
                description=(
                    f"Entry {entry:.4f} is {distance_atrs:.1f}x ATR {direction_word} EMA20 ({ema20:.4f}). "
                    "Mean-reversion risk is elevated."
                ),
                probability=35.0,
                monitor_price=ema20,
            )

        return None

    def _check_session_risk(self, signal: SignalResult) -> InvalidationFactor | None:
        """Flag if the current trading session ends within 1 hour.

        Signals entered near session close often stall due to reduced liquidity.
        """
        now = datetime.now(timezone.utc)
        hour = now.hour
        minute = now.minute

        # Current fractional hour
        current_decimal = hour + minute / 60.0

        for session_name, (start, end) in self._SESSIONS.items():
            in_session = start <= hour < end
            if not in_session:
                continue

            hours_until_close = end - current_decimal
            if 0 < hours_until_close <= self.SESSION_END_BUFFER_HOURS:
                return InvalidationFactor(
                    risk_name="session_ending_soon",
                    severity="LOW",
                    description=(
                        f"{session_name} session ends in ~{hours_until_close*60:.0f} minutes. "
                        "Liquidity may drop; signal may not trigger before close."
                    ),
                    probability=20.0,
                    monitor_price=None,
                )

        return None

    # ------------------------------------------------------------------
    # Aggregation helpers
    # ------------------------------------------------------------------

    def _overall_risk(self, factors: list[InvalidationFactor]) -> str:
        """Determine overall risk from the union of all factors.

        Logic:
        - Any HIGH factor → overall HIGH
        - Two or more MEDIUM factors → overall HIGH
        - One MEDIUM factor → overall MEDIUM
        - Only LOW factors → overall LOW
        - No factors → overall LOW
        """
        if not factors:
            return "LOW"

        severities = [f.severity for f in factors]
        high_count = severities.count("HIGH")
        medium_count = severities.count("MEDIUM")

        if high_count >= 1:
            return "HIGH"
        if medium_count >= 2:
            return "HIGH"
        if medium_count == 1:
            return "MEDIUM"
        return "LOW"

    def _build_summary(
        self,
        signal: SignalResult,
        factors: list[InvalidationFactor],
        overall_risk: str,
        max_adverse_move_pct: float,
    ) -> str:
        """Build a human-readable summary string."""
        lines = [
            f"Invalidation Report | {signal.asset} {signal.direction} | Overall Risk: {overall_risk}",
            f"Max adverse move to stop: {max_adverse_move_pct:.2f}%",
        ]
        if factors:
            lines.append(f"Identified {len(factors)} risk factor(s):")
            for f in factors:
                lines.append(f"  [{f.severity}] {f.risk_name}: {f.description} (prob ~{f.probability:.0f}%)")
        else:
            lines.append("No significant invalidation risks identified.")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_timestamp(ts) -> datetime | None:
    """Parse a timestamp string, int (unix), or datetime into a UTC datetime."""
    if isinstance(ts, datetime):
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    if isinstance(ts, str):
        try:
            if ts.endswith("Z"):
                ts = ts.replace("Z", "+00:00")
            dt = datetime.fromisoformat(ts)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _find_swing_highs(highs: np.ndarray, window: int = 5) -> list[float]:
    """Return list of swing high values using a rolling local-max approach."""
    result: list[float] = []
    for i in range(window, len(highs) - window):
        local_max = np.max(highs[i - window: i + window + 1])
        if highs[i] == local_max:
            result.append(float(highs[i]))
    return result


def _find_swing_lows(lows: np.ndarray, window: int = 5) -> list[float]:
    """Return list of swing low values using a rolling local-min approach."""
    result: list[float] = []
    for i in range(window, len(lows) - window):
        local_min = np.min(lows[i - window: i + window + 1])
        if lows[i] == local_min:
            result.append(float(lows[i]))
    return result


def _compute_atr(
    highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14
) -> float:
    """Compute the most-recent ATR value using Wilder smoothing."""
    n = len(closes)
    if n < 2:
        return 0.0
    tr_list: list[float] = []
    for i in range(1, n):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        tr_list.append(tr)
    atr_series = pd.Series(tr_list).ewm(span=period, adjust=False).mean()
    return float(atr_series.iloc[-1])
