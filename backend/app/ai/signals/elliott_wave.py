"""Simplified Elliott Wave counter using ZigZag pivots."""
from dataclasses import dataclass
from typing import Optional


@dataclass
class WaveContext:
    """Holds the result of an Elliott Wave analysis."""

    current_wave: int  # 1-5 for impulse, A/B/C for corrective (as int 6=A,7=B,8=C)
    wave_type: str  # "impulse" or "corrective"
    wave_label: str  # "1", "2", "3", "4", "5", "A", "B", "C"
    projected_target: Optional[float]  # next wave target price
    confidence: float  # 0-1
    pivots: list[dict]  # list of {price, index, type: "high"|"low"}


def find_zigzag_pivots(prices: list[float], deviation: float = 0.03) -> list[dict]:
    """Find significant swing highs and lows using ZigZag algorithm.

    Args:
        prices: List of closing prices.
        deviation: Minimum percentage move to qualify as a new pivot (default 3%).

    Returns:
        List of pivot dicts with keys: price, index, type ("high" | "low").
    """
    if len(prices) < 10:
        return []

    pivots: list[dict] = []
    trend: Optional[str] = None  # "up" or "down"
    last_high_idx = 0
    last_low_idx = 0
    last_high = prices[0]
    last_low = prices[0]

    for i, price in enumerate(prices):
        if trend is None:
            if price > last_high * (1 + deviation):
                trend = "up"
                last_high = price
                last_high_idx = i
            elif price < last_low * (1 - deviation):
                trend = "down"
                last_low = price
                last_low_idx = i
        elif trend == "up":
            if price > last_high:
                last_high = price
                last_high_idx = i
            elif price < last_high * (1 - deviation):
                pivots.append({"price": last_high, "index": last_high_idx, "type": "high"})
                trend = "down"
                last_low = price
                last_low_idx = i
        elif trend == "down":
            if price < last_low:
                last_low = price
                last_low_idx = i
            elif price > last_low * (1 + deviation):
                pivots.append({"price": last_low, "index": last_low_idx, "type": "low"})
                trend = "up"
                last_high = price
                last_high_idx = i

    # Append the last unconfirmed pivot
    if trend == "up" and (not pivots or pivots[-1]["index"] != last_high_idx):
        pivots.append({"price": last_high, "index": last_high_idx, "type": "high"})
    elif trend == "down" and (not pivots or pivots[-1]["index"] != last_low_idx):
        pivots.append({"price": last_low, "index": last_low_idx, "type": "low"})

    return pivots


def count_elliott_waves(prices: list[float], current_price: float) -> Optional[WaveContext]:
    """Simplified Elliott Wave counter.

    Looks for a 5-wave impulse pattern in recent price action and projects
    the next wave target via Fibonacci extensions.

    Args:
        prices: Historical closing prices.
        current_price: The most recent closing price.

    Returns:
        WaveContext if a valid pattern is identified, otherwise None.
    """
    if len(prices) < 20:
        return None

    pivots = find_zigzag_pivots(prices[-100:] if len(prices) > 100 else prices)

    if len(pivots) < 4:
        return None

    # Use up to the last 6 pivots to identify the current wave position
    recent_pivots = pivots[-6:]

    if len(recent_pivots) < 4:
        return None

    first_type = recent_pivots[0]["type"]

    # Count consecutively alternating pivots
    wave_count = 0
    valid = True
    for i, pivot in enumerate(recent_pivots[1:], 1):
        if first_type == "low":
            expected_type = "high" if i % 2 == 1 else "low"
        else:
            expected_type = "low" if i % 2 == 1 else "high"

        if pivot["type"] == expected_type:
            wave_count += 1
        else:
            valid = False
            break

    if not valid or wave_count < 3:
        return None

    # Determine current wave position (cap at wave 5)
    current_wave_num = min(wave_count + 1, 5)
    is_impulse = wave_count >= 4
    wave_type = "impulse" if is_impulse else "corrective"
    wave_label = str(current_wave_num)

    # Project the next target using Fibonacci extensions
    projected_target: Optional[float] = None
    if len(recent_pivots) >= 3:
        wave1_low = recent_pivots[0]["price"] if first_type == "low" else recent_pivots[1]["price"]
        wave1_high = recent_pivots[1]["price"] if first_type == "low" else recent_pivots[0]["price"]
        wave1_range = abs(wave1_high - wave1_low)

        if current_wave_num == 3 and first_type == "low":
            # Wave 3 target: wave2 low + 1.618 * wave1 range
            wave2_low = recent_pivots[2]["price"]
            projected_target = wave2_low + 1.618 * wave1_range
        elif current_wave_num == 5 and first_type == "low" and len(recent_pivots) >= 4:
            # Wave 5 target: wave3 high + 0.618 * wave1 range
            wave3_high = recent_pivots[3]["price"]
            projected_target = wave3_high + 0.618 * wave1_range

    confidence = min(0.9, 0.4 + wave_count * 0.1)

    return WaveContext(
        current_wave=current_wave_num,
        wave_type=wave_type,
        wave_label=wave_label,
        projected_target=round(projected_target, 4) if projected_target is not None else None,
        confidence=round(confidence, 2),
        pivots=recent_pivots[-5:],
    )
