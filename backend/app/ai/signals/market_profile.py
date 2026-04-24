"""Market Profile (TPO) — Value Area, POC, Balance/Imbalance analysis."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class MarketProfileResult:
    """Result of a Market Profile / TPO analysis session."""

    symbol: str
    timeframe: str
    poc: float                      # Point of Control (price level with most TPOs)
    vah: float                      # Value Area High (upper bound of 70% volume zone)
    val: float                      # Value Area Low (lower bound of 70% volume zone)
    value_area_width_pct: float     # (VAH - VAL) / POC * 100 — indicates range breadth
    current_price: float
    price_vs_va: str                # "ABOVE_VA", "IN_VALUE", "BELOW_VA"
    single_prints: list[float]      # price levels with exactly 1 TPO (unfair prices)
    signal: str                     # see analyze() docstring for signal definitions
    confidence: float               # 0-100
    description: str


class MarketProfileAnalyzer:
    """Builds a Market Profile and generates Value Area-based trading signals.

    Market Profile analysis divides trading time into 30-minute (or configurable)
    letter periods called TPOs (Time Price Opportunities).  The Value Area contains
    ~70% of all trading activity and acts as a magnet / fair-value zone.

    Trading logic:
    - Price rejecting the VAL from below → fade back toward POC (LONG).
    - Price rejecting the VAH from above → fade back toward POC (SHORT).
    - Price breaking above VAH with acceptance → balance break, trend LONG.
    - Price breaking below VAL with acceptance → balance break, trend SHORT.
    """

    VALUE_AREA_PCT: float = 0.70       # 70% of TPOs define the Value Area
    TPO_PERIOD_MINUTES: int = 30       # each TPO letter = 30 minutes

    def analyze(
        self,
        df: pd.DataFrame,
        session_candles: int = 48,
        tick_size: float = 0.01,
    ) -> MarketProfileResult | None:
        """Build TPO chart and generate Value Area-based signal.

        Algorithm:
        1. Limit data to the last *session_candles* candles (one trading session).
        2. Divide the high-low range into ``tick_size``-wide price buckets.
        3. Count how many candles (TPOs) touched each bucket.
        4. POC = price bucket with the highest TPO count.
        5. Expand from POC outward until 70% of TPOs are included → VAL / VAH.
        6. Identify single-print levels (exactly 1 TPO — "unfair" prices).
        7. Compare current price vs Value Area to generate signal.

        Args:
            df: OHLCV DataFrame with columns ``open``, ``high``, ``low``, ``close``,
                ``volume`` and a ``DatetimeIndex``.
            session_candles: Number of most recent candles forming one session
                (48 × 30-min = 24 h).
            tick_size: Minimum price increment for bucket resolution.

        Returns:
            :class:`MarketProfileResult` or ``None`` if data is insufficient.
        """
        if df is None or len(df) < 10:
            logger.warning("MarketProfileAnalyzer: insufficient data (need ≥ 10 candles)")
            return None

        required_cols = {"high", "low", "close"}
        if not required_cols.issubset(df.columns):
            logger.error("MarketProfileAnalyzer: missing required columns %s", required_cols)
            return None

        # Use the last *session_candles* rows as the analysis window
        session_df = df.iloc[-min(session_candles, len(df)):]

        current_price = float(session_df["close"].iloc[-1])

        # Infer symbol / timeframe from DataFrame if available
        symbol = getattr(df, "attrs", {}).get("symbol", "UNKNOWN")
        timeframe = getattr(df, "attrs", {}).get("timeframe", "UNKNOWN")

        # Snap tick_size to a safe minimum to avoid zero-division
        if tick_size <= 0:
            tick_size = 0.01

        tpo_profile = self._build_tpo_profile(session_df, tick_size)

        if not tpo_profile:
            logger.warning("MarketProfileAnalyzer: empty TPO profile, skipping")
            return None

        total_tpos = sum(tpo_profile.values())
        poc = max(tpo_profile, key=lambda p: tpo_profile[p])

        val, vah = self._find_value_area(tpo_profile, poc, total_tpos)

        # Single prints — price levels touched by only 1 TPO
        single_prints = [
            round(price, 8) for price, count in tpo_profile.items() if count == 1
        ]
        single_prints.sort()

        # Value Area width as % of POC
        value_area_width_pct = (vah - val) / poc * 100.0 if poc > 0 else 0.0

        # Price position relative to Value Area
        if current_price > vah:
            price_vs_va = "ABOVE_VA"
        elif current_price < val:
            price_vs_va = "BELOW_VA"
        else:
            price_vs_va = "IN_VALUE"

        signal, confidence, description = self._generate_signal(
            current_price=current_price,
            poc=poc,
            val=val,
            vah=vah,
            price_vs_va=price_vs_va,
            tick_size=tick_size,
        )

        logger.info(
            "MarketProfile: POC=%.4f VAL=%.4f VAH=%.4f price=%.4f signal=%s conf=%.1f",
            poc, val, vah, current_price, signal, confidence,
        )

        return MarketProfileResult(
            symbol=symbol,
            timeframe=timeframe,
            poc=round(poc, 8),
            vah=round(vah, 8),
            val=round(val, 8),
            value_area_width_pct=round(value_area_width_pct, 3),
            current_price=round(current_price, 8),
            price_vs_va=price_vs_va,
            single_prints=single_prints,
            signal=signal,
            confidence=round(confidence, 2),
            description=description,
        )

    def _build_tpo_profile(
        self, df: pd.DataFrame, tick_size: float
    ) -> dict[float, int]:
        """Build a price → TPO count mapping for the given OHLCV session.

        Each candle contributes a TPO to every price bucket it touched
        (i.e. any bucket within the candle's [low, high] range).

        Args:
            df: OHLCV DataFrame slice representing one session.
            tick_size: Width of each price bucket.

        Returns:
            Dict mapping rounded price level → number of TPOs.
        """
        profile: dict[float, int] = {}

        for _, row in df.iterrows():
            try:
                low = float(row["low"])
                high = float(row["high"])
            except (TypeError, ValueError):
                continue

            # Enumerate all price buckets this candle covers
            level = _snap_to_tick(low, tick_size)
            while level <= high + tick_size / 2:
                profile[level] = profile.get(level, 0) + 1
                level = round(level + tick_size, 10)

        return profile

    def _find_value_area(
        self,
        tpo_profile: dict[float, int],
        poc: float,
        total_tpos: int,
    ) -> tuple[float, float]:
        """Expand from POC outward until VALUE_AREA_PCT of TPOs are included.

        The standard Market Profile algorithm adds one price level above OR
        below the current boundary on each iteration, choosing whichever adds
        more TPOs (greedy expansion).

        Args:
            tpo_profile: Price → TPO count mapping.
            poc: Point of Control (starting price).
            total_tpos: Total number of TPOs in the session.

        Returns:
            Tuple of ``(val, vah)`` — Value Area Low and High.
        """
        target = int(total_tpos * self.VALUE_AREA_PCT)
        prices = sorted(tpo_profile.keys())

        if poc not in tpo_profile:
            return poc, poc

        poc_idx = prices.index(poc)
        lower_idx = poc_idx
        upper_idx = poc_idx
        accumulated = tpo_profile[poc]

        while accumulated < target:
            can_expand_down = lower_idx > 0
            can_expand_up = upper_idx < len(prices) - 1

            if not can_expand_down and not can_expand_up:
                break

            next_down_count = tpo_profile.get(prices[lower_idx - 1], 0) if can_expand_down else -1
            next_up_count = tpo_profile.get(prices[upper_idx + 1], 0) if can_expand_up else -1

            if next_up_count >= next_down_count and can_expand_up:
                upper_idx += 1
                accumulated += next_up_count
            elif can_expand_down:
                lower_idx -= 1
                accumulated += next_down_count
            else:
                upper_idx += 1
                accumulated += next_up_count

        return prices[lower_idx], prices[upper_idx]

    def _generate_signal(
        self,
        current_price: float,
        poc: float,
        val: float,
        vah: float,
        price_vs_va: str,
        tick_size: float,
    ) -> tuple[str, float, str]:
        """Generate a directional signal based on price position within the Value Area.

        Signals and their rationale:
        - ``BUY_VA_LOW_TEST``: price is at or just below VAL — fade back toward POC.
        - ``SELL_VA_HIGH_TEST``: price is at or just above VAH — fade back toward POC.
        - ``BALANCE_BREAK_LONG``: price is significantly above VAH — breakout trade.
        - ``BALANCE_BREAK_SHORT``: price is significantly below VAL — breakdown trade.
        - ``NEUTRAL``: price is within Value Area with no edge.

        Args:
            current_price: Most recent close price.
            poc: Point of Control price.
            val: Value Area Low.
            vah: Value Area High.
            price_vs_va: Position classification string.
            tick_size: Minimum price increment (used for proximity threshold).

        Returns:
            Tuple of ``(signal_name, confidence, description)``.
        """
        # Proximity threshold: 0.3% of POC or 10 ticks, whichever is larger
        proximity_pct = 0.003
        proximity = max(poc * proximity_pct, tick_size * 10)

        if price_vs_va == "BELOW_VA":
            distance_below = val - current_price
            if distance_below <= proximity:
                return (
                    "BUY_VA_LOW_TEST",
                    72.0,
                    f"Price {current_price:.4f} testing VAL {val:.4f} from below. "
                    f"High-probability fade toward POC {poc:.4f}.",
                )
            # Deeper below VAL → balance break short
            return (
                "BALANCE_BREAK_SHORT",
                65.0,
                f"Price {current_price:.4f} broke below VAL {val:.4f} (distance {distance_below:.4f}). "
                f"Balance breakdown — target lower distribution.",
            )

        if price_vs_va == "ABOVE_VA":
            distance_above = current_price - vah
            if distance_above <= proximity:
                return (
                    "SELL_VA_HIGH_TEST",
                    72.0,
                    f"Price {current_price:.4f} testing VAH {vah:.4f} from above. "
                    f"High-probability fade toward POC {poc:.4f}.",
                )
            # Significantly above VAH → balance break long
            return (
                "BALANCE_BREAK_LONG",
                65.0,
                f"Price {current_price:.4f} broke above VAH {vah:.4f} (distance {distance_above:.4f}). "
                f"Balance breakout — trend extension expected.",
            )

        # Price is inside Value Area
        return (
            "NEUTRAL",
            40.0,
            f"Price {current_price:.4f} is within Value Area [{val:.4f} – {vah:.4f}]. "
            f"No structural edge; await VA boundary test or breakout.",
        )

    def get_nearest_va_level(
        self, result: MarketProfileResult, current_price: float
    ) -> float:
        """Return the nearest Value Area boundary (VAH or VAL) to current price.

        Args:
            result: Completed :class:`MarketProfileResult`.
            current_price: The current market price to compare against.

        Returns:
            The price of the nearest Value Area boundary.
        """
        dist_to_vah = abs(current_price - result.vah)
        dist_to_val = abs(current_price - result.val)
        return result.vah if dist_to_vah <= dist_to_val else result.val


def _snap_to_tick(price: float, tick_size: float) -> float:
    """Round *price* down to the nearest *tick_size* grid point."""
    return round(int(price / tick_size) * tick_size, 10)
