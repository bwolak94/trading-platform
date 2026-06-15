"""Supply and Demand Zone Detector — finds institutional order zones.

Supply zones are consolidation bases that preceded explosive DOWN moves.
Demand zones are consolidation bases that preceded explosive UP moves.

Zone freshness (not yet retested) is the highest-probability setup:
  strength = explosive_move_pct × freshness_multiplier × (1 / (touch_count + 1))
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import pandas as pd

from app.core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MIN_BASE_CANDLES: Final[int] = 2    # minimum base consolidation length
_MAX_BASE_CANDLES: Final[int] = 6    # maximum base consolidation length
_MIN_CANDLES: Final[int] = 30        # minimum DataFrame length required


# ---------------------------------------------------------------------------
# Zone dataclass
# ---------------------------------------------------------------------------


@dataclass
class SDZone:
    """Represents a single supply or demand zone."""

    zone_type: str             # "DEMAND" or "SUPPLY"
    price_high: float
    price_low: float
    price_mid: float
    strength: float            # 0–100 composite strength score
    is_fresh: bool             # True if not retested since creation
    created_at_idx: int        # candle index when zone was created
    touch_count: int           # how many times price returned to zone
    explosive_move_pct: float  # % move that created this zone

    def __repr__(self) -> str:
        freshness = "FRESH" if self.is_fresh else f"TESTED×{self.touch_count}"
        return (
            f"SDZone(type={self.zone_type}, "
            f"high={self.price_high:.4f}, low={self.price_low:.4f}, "
            f"strength={self.strength:.1f}, {freshness})"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _candle_body_pct(row: pd.Series) -> float:
    """Return body size as a fraction of the full candle range (0–1)."""
    candle_range = float(row["high"]) - float(row["low"])
    if candle_range < 1e-12:
        return 0.0
    body = abs(float(row["close"]) - float(row["open"]))
    return body / candle_range


def _is_small_range(row: pd.Series, avg_range: float) -> bool:
    """Return True if the candle range is below 70 % of the rolling average range."""
    candle_range = float(row["high"]) - float(row["low"])
    return candle_range < avg_range * 0.70


def _count_touches(
    df: pd.DataFrame,
    zone_high: float,
    zone_low: float,
    created_idx: int,
) -> int:
    """Count candles after creation whose lows/highs penetrated the zone."""
    touch_count = 0
    for i in range(created_idx + 1, len(df)):
        low_i = float(df["low"].iloc[i])
        high_i = float(df["high"].iloc[i])
        # Touch: price enters the zone from either side
        if low_i <= zone_high and high_i >= zone_low:
            touch_count += 1
    return touch_count


def _zone_strength(
    explosive_move_pct: float,
    is_fresh: bool,
    touch_count: int,
) -> float:
    """Compute zone strength 0–100.

    Fresh zones with large explosive moves score highest.
    Each additional touch reduces strength by roughly (1 / (touch_count + 1)).
    """
    freshness_multiplier = 2.0 if is_fresh else 1.0
    base = min(50.0, explosive_move_pct * 10.0)   # up to 50 pts from move size
    touch_penalty = 1.0 / (touch_count + 1)
    score = base * freshness_multiplier * touch_penalty
    return round(min(100.0, score), 1)


# ---------------------------------------------------------------------------
# Main scanner class
# ---------------------------------------------------------------------------


class SupplyDemandScanner:
    """Detects supply and demand zones from OHLCV data."""

    MIN_EXPLOSIVE_MOVE_PCT: float = 1.5  # minimum % move to qualify
    ZONE_TOLERANCE_PCT: float = 0.3      # zone half-width tolerance as % of price

    def scan(self, df: pd.DataFrame) -> list[SDZone]:
        """Scan the DataFrame for supply and demand zones.

        A demand zone is a base (2–6 small-range candles) immediately before an
        explosive UP move.  A supply zone is a base before an explosive DOWN move.

        Args:
            df: OHLCV DataFrame with columns open, high, low, close, volume.
                Should contain at least 30 candles.

        Returns:
            List of SDZone objects sorted by strength descending.
        """
        if df is None or len(df) < _MIN_CANDLES:
            logger.warning(
                "SupplyDemandScanner: insufficient data (%d candles)",
                len(df) if df is not None else 0,
            )
            return []

        df = df.copy().reset_index(drop=True)
        avg_range = float((df["high"] - df["low"]).rolling(20).mean().iloc[-1])
        zones: list[SDZone] = []

        # Slide a window looking for base + explosive move patterns
        for base_end in range(_MIN_BASE_CANDLES, len(df) - 1):
            for base_len in range(_MIN_BASE_CANDLES, _MAX_BASE_CANDLES + 1):
                base_start = base_end - base_len + 1
                if base_start < 0:
                    continue

                base_slice = df.iloc[base_start : base_end + 1]

                # All candles in base must be small-range
                if not all(_is_small_range(base_slice.iloc[j], avg_range) for j in range(len(base_slice))):
                    continue

                base_high = float(base_slice["high"].max())
                base_low = float(base_slice["low"].min())
                base_mid = (base_high + base_low) / 2.0

                # Look at the candle immediately following the base
                move_idx = base_end + 1
                if move_idx >= len(df):
                    continue

                move_close = float(df["close"].iloc[move_idx])
                float(df["open"].iloc[move_idx])

                # Demand: explosive UP move departing from base
                up_move_pct = (move_close - base_high) / base_high * 100.0
                if up_move_pct >= self.MIN_EXPLOSIVE_MOVE_PCT:
                    touch_count = _count_touches(df, base_high, base_low, move_idx)
                    is_fresh = touch_count == 0
                    strength = _zone_strength(up_move_pct, is_fresh, touch_count)

                    zones.append(
                        SDZone(
                            zone_type="DEMAND",
                            price_high=round(base_high, 6),
                            price_low=round(base_low, 6),
                            price_mid=round(base_mid, 6),
                            strength=strength,
                            is_fresh=is_fresh,
                            created_at_idx=base_end,
                            touch_count=touch_count,
                            explosive_move_pct=round(up_move_pct, 3),
                        )
                    )
                    break  # found a valid base for this end-candle, move on

                # Supply: explosive DOWN move departing from base
                down_move_pct = (base_low - move_close) / base_low * 100.0
                if down_move_pct >= self.MIN_EXPLOSIVE_MOVE_PCT:
                    touch_count = _count_touches(df, base_high, base_low, move_idx)
                    is_fresh = touch_count == 0
                    strength = _zone_strength(down_move_pct, is_fresh, touch_count)

                    zones.append(
                        SDZone(
                            zone_type="SUPPLY",
                            price_high=round(base_high, 6),
                            price_low=round(base_low, 6),
                            price_mid=round(base_mid, 6),
                            strength=strength,
                            is_fresh=is_fresh,
                            created_at_idx=base_end,
                            touch_count=touch_count,
                            explosive_move_pct=round(down_move_pct, 3),
                        )
                    )
                    break

        # De-duplicate overlapping zones: keep the strongest in each cluster
        zones = _deduplicate_zones(zones)

        # Sort by strength descending
        zones.sort(key=lambda z: z.strength, reverse=True)

        logger.info(
            "SupplyDemandScanner: found %d zones (%d demand, %d supply)",
            len(zones),
            sum(1 for z in zones if z.zone_type == "DEMAND"),
            sum(1 for z in zones if z.zone_type == "SUPPLY"),
        )
        return zones

    def get_nearest_zone(
        self,
        df: pd.DataFrame,
        current_price: float,
        zone_type: str,
    ) -> SDZone | None:
        """Find the closest supply or demand zone to the current price.

        Args:
            df:            OHLCV DataFrame.
            current_price: Current market price.
            zone_type:     "DEMAND" or "SUPPLY".

        Returns:
            The nearest SDZone of the requested type, or None if not found.
        """
        all_zones = self.scan(df)
        relevant = [z for z in all_zones if z.zone_type == zone_type.upper()]
        if not relevant:
            return None

        return min(relevant, key=lambda z: abs(z.price_mid - current_price))


# ---------------------------------------------------------------------------
# Zone de-duplication
# ---------------------------------------------------------------------------


def _deduplicate_zones(zones: list[SDZone]) -> list[SDZone]:
    """Remove duplicate zones that overlap significantly.

    Two zones are considered duplicates if their mid-prices are within 0.5% of
    each other AND they are the same type.  Only the stronger zone is kept.
    """
    if not zones:
        return zones

    unique: list[SDZone] = []
    for zone in sorted(zones, key=lambda z: z.strength, reverse=True):
        is_dup = False
        for kept in unique:
            if kept.zone_type != zone.zone_type:
                continue
            overlap_pct = abs(kept.price_mid - zone.price_mid) / max(kept.price_mid, 1e-9) * 100
            if overlap_pct < 0.5:
                is_dup = True
                break
        if not is_dup:
            unique.append(zone)

    return unique
