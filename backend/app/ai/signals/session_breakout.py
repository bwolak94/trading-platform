"""Session Breakout Scanner — detects breakout setups before session opens.

Fires alerts when price is near an overnight range extreme within a
configurable window before a major session open (London, New York, Tokyo).

Trading logic:
  - Identify the overnight range (last OVERNIGHT_HOURS of candles).
  - If price is within PROXIMITY_THRESHOLD_PCT of the range HIGH → LONG setup
    (potential breakout above the overnight high on session open).
  - If price is within PROXIMITY_THRESHOLD_PCT of the range LOW  → SHORT setup
    (potential breakout below the overnight low on session open).
  - Confidence boosted by: volume contraction overnight (tight coil), clean
    range boundaries, minimal wicks at extremes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Final

import pandas as pd

from app.core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Session open times (UTC)
# ---------------------------------------------------------------------------

SESSIONS: Final[dict[str, dict[str, int]]] = {
    "LONDON":   {"open_hour": 8,  "open_minute": 0},
    "NEW_YORK": {"open_hour": 13, "open_minute": 30},
    "TOKYO":    {"open_hour": 0,  "open_minute": 0},
}

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ALERT_WINDOW_MINUTES: Final[int] = 45    # alert within 45 min of session open
_PROXIMITY_THRESHOLD_PCT: Final[float] = 0.5  # price within 0.5% of range extreme
_OVERNIGHT_HOURS: Final[int] = 8          # hours of overnight range
_MIN_CANDLES_OVERNIGHT: Final[int] = 4    # minimum candles for a valid overnight range
_VOLUME_CONTRACTION_RATIO: Final[float] = 0.75  # overnight vol < 75% of daily avg = contraction


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class SessionBreakoutSignal:
    """Breakout setup detected before a session open."""

    symbol: str
    session: str               # "LONDON", "NEW_YORK", "TOKYO"
    minutes_until_open: int
    direction: str             # "LONG" or "SHORT"
    confidence: float          # 0–100
    overnight_range_high: float
    overnight_range_low: float
    current_price: float
    distance_to_extreme_pct: float  # how close to relevant range extreme
    breakout_target: float          # estimated breakout target (1× range projection)
    description: str

    def __repr__(self) -> str:
        return (
            f"SessionBreakoutSignal(symbol={self.symbol!r}, session={self.session!r}, "
            f"direction={self.direction}, confidence={self.confidence:.1f}, "
            f"min_until_open={self.minutes_until_open})"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _minutes_until_session(session_config: dict[str, int], now_utc: datetime) -> int:
    """Compute minutes until the next occurrence of a session open.

    Args:
        session_config: Dict with 'open_hour' and 'open_minute'.
        now_utc:        Current UTC datetime.

    Returns:
        Minutes until the next session open (0–1440).
    """
    target = now_utc.replace(
        hour=session_config["open_hour"],
        minute=session_config["open_minute"],
        second=0,
        microsecond=0,
    )
    diff = (target - now_utc).total_seconds() / 60.0
    if diff < 0:
        diff += 1440.0  # add one day if session already passed today
    return int(diff)


def _compute_overnight_range(
    df: pd.DataFrame,
    overnight_hours: int,
) -> tuple[float, float, pd.DataFrame]:
    """Extract the overnight range from the most recent candles.

    Args:
        df:              OHLCV DataFrame (sorted ascending).
        overnight_hours: How many hours to look back.

    Returns:
        Tuple of (range_high, range_low, overnight_df).
    """
    # Use candle count as proxy for hours (works for any timeframe)
    # Assumes the DataFrame represents reasonably uniform candles
    overnight_df = df.iloc[-overnight_hours:] if len(df) >= overnight_hours else df

    range_high = float(overnight_df["high"].max())
    range_low = float(overnight_df["low"].min())
    return range_high, range_low, overnight_df


def _overnight_volume_contraction(overnight_df: pd.DataFrame, full_df: pd.DataFrame) -> bool:
    """Return True if overnight volume is contracted vs the rolling average.

    Low volume overnight followed by a breakout is a higher-probability setup.
    """
    if len(full_df) < 20:
        return False
    avg_vol = float(full_df["volume"].rolling(20).mean().iloc[-1])
    overnight_avg_vol = float(overnight_df["volume"].mean())
    if avg_vol <= 0:
        return False
    return overnight_avg_vol < avg_vol * _VOLUME_CONTRACTION_RATIO


def _clean_range_boundary(overnight_df: pd.DataFrame, side: str) -> bool:
    """Check if the range extreme is formed by clean, single-wick touches.

    A 'clean' extreme: only 1–2 candles touched the extreme (tight false-break zone).

    Args:
        overnight_df: Slice of the overnight candles.
        side:         "HIGH" or "LOW".

    Returns:
        True if the boundary is clean.
    """
    if side == "HIGH":
        extreme = float(overnight_df["high"].max())
        touching = (overnight_df["high"] >= extreme * 0.9995).sum()
    else:
        extreme = float(overnight_df["low"].min())
        touching = (overnight_df["low"] <= extreme * 1.0005).sum()
    return int(touching) <= 2


def _proximity_pct(current_price: float, level: float) -> float:
    """Return % distance from current_price to level (unsigned)."""
    if level <= 0:
        return float("inf")
    return abs(current_price - level) / level * 100.0


def _breakout_target(direction: str, extreme: float, range_size: float) -> float:
    """Project a 1× range breakout target.

    Args:
        direction:  "LONG" or "SHORT".
        extreme:    The range extreme being broken.
        range_size: High - low of the overnight range.

    Returns:
        Projected price target.
    """
    if direction == "LONG":
        return round(extreme + range_size, 6)
    return round(extreme - range_size, 6)


def _confidence_score(
    proximity_pct: float,
    volume_contracted: bool,
    clean_boundary: bool,
    minutes_until_open: int,
) -> float:
    """Compute confidence 0–100 for the breakout setup.

    Factors:
      - Proximity to extreme:    up to 40 pts  (0 = right at extreme)
      - Volume contraction:      +20 pts
      - Clean boundary:          +20 pts
      - Timing (closer = better): up to 20 pts
    """
    # Proximity: 40 pts at 0%, 0 pts at threshold
    prox_score = max(0.0, 40.0 * (1.0 - proximity_pct / _PROXIMITY_THRESHOLD_PCT))

    # Volume
    vol_score = 20.0 if volume_contracted else 0.0

    # Boundary quality
    boundary_score = 20.0 if clean_boundary else 0.0

    # Timing: full 20 pts when ≤ 10 min away, 0 pts at limit
    timing_score = max(0.0, 20.0 * (1.0 - minutes_until_open / _ALERT_WINDOW_MINUTES))

    return round(min(100.0, prox_score + vol_score + boundary_score + timing_score), 1)


# ---------------------------------------------------------------------------
# Main scanner class
# ---------------------------------------------------------------------------


class SessionBreakoutScanner:
    """Identifies breakout setups before major trading session opens."""

    ALERT_WINDOW_MINUTES: int = _ALERT_WINDOW_MINUTES
    PROXIMITY_THRESHOLD_PCT: float = _PROXIMITY_THRESHOLD_PCT
    OVERNIGHT_HOURS: int = _OVERNIGHT_HOURS

    def is_pre_session(self) -> tuple[bool, str, int]:
        """Check if current UTC time is within the alert window of any session open.

        Returns:
            Tuple of (is_pre_session, session_name, minutes_until_open).
            If not pre-session, session_name is "NONE" and minutes is -1.
        """
        now_utc = datetime.now(tz=timezone.utc)
        for session_name, config in SESSIONS.items():
            minutes = _minutes_until_session(config, now_utc)
            if 0 <= minutes <= self.ALERT_WINDOW_MINUTES:
                logger.debug(
                    "Pre-session window detected",
                    extra={"session": session_name, "minutes_until_open": minutes},
                )
                return True, session_name, minutes
        return False, "NONE", -1

    def scan(self, symbol: str, df: pd.DataFrame) -> SessionBreakoutSignal | None:
        """Scan for a session breakout setup.

        Args:
            symbol: Trading symbol, e.g. "BTCUSDT".
            df:     OHLCV DataFrame (sorted ascending), recent candles last.

        Returns:
            SessionBreakoutSignal if setup detected, else None.
        """
        if df is None or len(df) < _MIN_CANDLES_OVERNIGHT:
            logger.debug(
                "SessionBreakoutScanner: insufficient data for %s (%d candles)",
                symbol,
                len(df) if df is not None else 0,
            )
            return None

        is_pre, session_name, minutes_until_open = self.is_pre_session()
        if not is_pre:
            logger.debug(
                "SessionBreakoutScanner: not in pre-session window for any session"
            )
            return None

        df = df.copy().reset_index(drop=True)
        current_price = float(df["close"].iloc[-1])

        # --- Compute overnight range ---
        range_high, range_low, overnight_df = _compute_overnight_range(
            df, self.OVERNIGHT_HOURS
        )
        range_size = range_high - range_low

        if range_size <= 0:
            logger.debug("SessionBreakoutScanner: zero-size range for %s", symbol)
            return None

        # --- Quality factors ---
        vol_contracted = _overnight_volume_contraction(overnight_df, df)

        # --- Check proximity to range extremes ---
        dist_to_high = _proximity_pct(current_price, range_high)
        dist_to_low = _proximity_pct(current_price, range_low)

        direction: str | None = None
        extreme: float = 0.0
        distance_to_extreme: float = 0.0

        if dist_to_high <= self.PROXIMITY_THRESHOLD_PCT and dist_to_high <= dist_to_low:
            # Price near range HIGH → potential upside breakout on session open
            direction = "LONG"
            extreme = range_high
            distance_to_extreme = dist_to_high
        elif dist_to_low <= self.PROXIMITY_THRESHOLD_PCT:
            # Price near range LOW → potential downside breakout on session open
            direction = "SHORT"
            extreme = range_low
            distance_to_extreme = dist_to_low

        if direction is None:
            logger.debug(
                "SessionBreakoutScanner: price not near range extreme for %s "
                "(high_dist=%.2f%%, low_dist=%.2f%%)",
                symbol,
                dist_to_high,
                dist_to_low,
            )
            return None

        clean_boundary = _clean_range_boundary(
            overnight_df, "HIGH" if direction == "LONG" else "LOW"
        )

        confidence = _confidence_score(
            distance_to_extreme, vol_contracted, clean_boundary, minutes_until_open
        )

        target = _breakout_target(direction, extreme, range_size)

        description = self._build_description(
            symbol=symbol,
            session=session_name,
            direction=direction,
            minutes_until_open=minutes_until_open,
            current_price=current_price,
            range_high=range_high,
            range_low=range_low,
            extreme=extreme,
            distance_pct=distance_to_extreme,
            vol_contracted=vol_contracted,
            clean_boundary=clean_boundary,
            confidence=confidence,
            target=target,
        )

        logger.info(
            "SessionBreakoutScanner: signal generated",
            extra={
                "symbol": symbol,
                "session": session_name,
                "direction": direction,
                "confidence": confidence,
                "minutes_until_open": minutes_until_open,
            },
        )

        return SessionBreakoutSignal(
            symbol=symbol.upper(),
            session=session_name,
            minutes_until_open=minutes_until_open,
            direction=direction,
            confidence=confidence,
            overnight_range_high=round(range_high, 6),
            overnight_range_low=round(range_low, 6),
            current_price=round(current_price, 6),
            distance_to_extreme_pct=round(distance_to_extreme, 4),
            breakout_target=round(target, 6),
            description=description,
        )

    @staticmethod
    def _build_description(
        symbol: str,
        session: str,
        direction: str,
        minutes_until_open: int,
        current_price: float,
        range_high: float,
        range_low: float,
        extreme: float,
        distance_pct: float,
        vol_contracted: bool,
        clean_boundary: bool,
        confidence: float,
        target: float,
    ) -> str:
        """Build a human-readable description of the breakout setup."""
        session_label = f"{session} session ({minutes_until_open} min away)"
        dir_label = "LONG (range HIGH breakout)" if direction == "LONG" else "SHORT (range LOW breakout)"
        parts = [
            f"{symbol} {dir_label} before {session_label}.",
            f"Overnight range: {range_low:.4f} – {range_high:.4f}.",
            f"Price {distance_pct:.2f}% from {extreme:.4f} extreme.",
            f"Breakout target: {target:.4f}.",
        ]
        if vol_contracted:
            parts.append("Volume contracted overnight (coiled spring).")
        if clean_boundary:
            parts.append("Clean range boundary — minimal false tests.")
        parts.append(f"Confidence: {confidence:.0f}%.")
        return " ".join(parts)

    def get_all_upcoming_sessions(self) -> list[dict]:
        """Return time-to-open for all sessions, sorted by proximity.

        Useful for displaying a session countdown widget.

        Returns:
            List of dicts: {'session': str, 'minutes_until_open': int, 'is_pre_session': bool}
        """
        now_utc = datetime.now(tz=timezone.utc)
        result = []
        for session_name, config in SESSIONS.items():
            minutes = _minutes_until_session(config, now_utc)
            result.append({
                "session": session_name,
                "minutes_until_open": minutes,
                "is_pre_session": 0 <= minutes <= self.ALERT_WINDOW_MINUTES,
                "open_time_utc": f"{config['open_hour']:02d}:{config['open_minute']:02d} UTC",
            })
        result.sort(key=lambda x: x["minutes_until_open"])
        return result
