"""Harmonic pattern detector (Gartley, Bat, Crab, Butterfly) using XABCD Fibonacci ratios."""
from dataclasses import dataclass


@dataclass
class HarmonicPattern:
    """Represents a detected XABCD harmonic pattern."""

    pattern_name: str  # "Gartley", "Bat", "Crab", "Butterfly"
    bias: str  # "bullish" or "bearish"
    completion_zone: tuple[float, float]  # (min, max) PRZ price range
    confidence: float  # 0-1 based on ratio quality
    points: dict[str, float]  # X, A, B, C, D_projected prices
    current_leg: str  # "AB", "BC", "CD", "Complete"


# Fibonacci ratio definitions for each pattern
# Each entry: XA_to_AB = (min, max) retracement, XA_to_AD = (min, max) extension
PATTERNS: dict[str, dict] = {
    "Gartley": {
        "XA_to_AB": (0.618, 0.618),  # B at 61.8% of XA
        "AB_to_BC": (0.382, 0.886),  # C between 38.2-88.6% of AB
        "XA_to_AD": (0.786, 0.786),  # D at 78.6% of XA
        "tolerance": 0.07,
    },
    "Bat": {
        "XA_to_AB": (0.382, 0.500),  # B at 38.2-50% of XA
        "AB_to_BC": (0.382, 0.886),
        "XA_to_AD": (0.886, 0.886),  # D at 88.6% of XA
        "tolerance": 0.07,
    },
    "Crab": {
        "XA_to_AB": (0.382, 0.618),
        "AB_to_BC": (0.382, 0.886),
        "XA_to_AD": (1.618, 1.618),  # D at 161.8% extension of XA
        "tolerance": 0.07,
    },
    "Butterfly": {
        "XA_to_AB": (0.786, 0.786),
        "AB_to_BC": (0.382, 0.886),
        "XA_to_AD": (1.270, 1.618),
        "tolerance": 0.07,
    },
}


def detect_harmonic_patterns(pivots: list[dict]) -> list[HarmonicPattern]:
    """Detect XABCD harmonic patterns from ZigZag pivots.

    Scans every group of 5 consecutive pivots for Gartley, Bat, Crab, and
    Butterfly formations.  A pattern is accepted when both the AB/XA and
    BC/AB retracement ratios fall within the defined tolerance band.

    Args:
        pivots: List of pivot dicts produced by find_zigzag_pivots.

    Returns:
        List of HarmonicPattern instances for all patterns found.
    """
    if len(pivots) < 5:
        return []

    results: list[HarmonicPattern] = []

    for i in range(len(pivots) - 4):
        xabcd = pivots[i : i + 5]
        X, A, B, C, D = (p["price"] for p in xabcd)

        # Determine trade direction based on XA leg
        if A > X:
            # Bearish: X=low, A=high → expect D lower than A
            XA = A - X
            AB = A - B
            BC = C - B
        else:
            # Bullish: X=high, A=low → expect D higher than A
            XA = X - A
            AB = B - A
            BC = B - C

        if XA <= 0 or AB <= 0 or BC <= 0:
            continue

        AB_ratio = AB / XA
        BC_ratio = BC / AB
        bias = "bearish" if A > X else "bullish"

        for pat_name, ratios in PATTERNS.items():
            tol: float = ratios["tolerance"]
            ab_min, ab_max = ratios["XA_to_AB"]
            bc_min, bc_max = ratios["AB_to_BC"]
            ad_target_min, ad_target_max = ratios["XA_to_AD"]

            ab_ok = ab_min - tol <= AB_ratio <= ab_max + tol
            bc_ok = bc_min - tol <= BC_ratio <= bc_max + tol

            if not (ab_ok and bc_ok):
                continue

            # Compute Potential Reversal Zone (PRZ) for point D
            if bias == "bearish":
                prz_min = A - XA * ad_target_max
                prz_max = A - XA * ad_target_min
            else:
                prz_min = A + XA * ad_target_min
                prz_max = A + XA * ad_target_max

            # Confidence: average of AB and BC proximity to ideal ratios
            ab_ideal = (ab_min + ab_max) / 2
            bc_ideal = (bc_min + bc_max) / 2
            ab_conf = max(0.0, 1.0 - abs(AB_ratio - ab_ideal) / ab_ideal)
            bc_conf = max(0.0, 1.0 - abs(BC_ratio - bc_ideal) / bc_ideal)
            confidence = round((ab_conf + bc_conf) / 2 * 0.8, 2)

            results.append(
                HarmonicPattern(
                    pattern_name=pat_name,
                    bias=bias,
                    completion_zone=(
                        round(min(prz_min, prz_max), 4),
                        round(max(prz_min, prz_max), 4),
                    ),
                    confidence=confidence,
                    points={
                        "X": X,
                        "A": A,
                        "B": B,
                        "C": C,
                        "D_projected": round((prz_min + prz_max) / 2, 4),
                    },
                    current_leg="CD",
                )
            )

    return results


def get_harmonic_patterns(prices: list[float]) -> list[HarmonicPattern]:
    """High-level entry point: derive ZigZag pivots then detect harmonic patterns.

    Args:
        prices: List of closing prices (most-recent 150 bars are used).

    Returns:
        List of HarmonicPattern instances sorted by confidence descending.
    """
    from app.ai.signals.elliott_wave import find_zigzag_pivots

    window = prices[-150:] if len(prices) > 150 else prices
    pivots = find_zigzag_pivots(window)
    patterns = detect_harmonic_patterns(pivots)
    return sorted(patterns, key=lambda p: p.confidence, reverse=True)
