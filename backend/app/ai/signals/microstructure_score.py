"""Market microstructure quality score.

Combines: bid-ask spread proxy, order book imbalance, funding rate,
liquidation proximity, and CVD trend into a single 0-100 "market quality" score.
Low score = avoid trading. High score = favorable conditions.
"""

from typing import Any


def _score_orderbook_imbalance(imbalance: float) -> float:
    """Score order book imbalance. Max 25 points.

    imbalance: -1 (all asks) to +1 (all bids).
    Strong directional imbalance (≥ 0.3 or ≤ -0.3) is favourable for momentum trades.
    Values near 0 indicate balanced book — less clear signal.
    """
    abs_imb = abs(imbalance)
    if abs_imb >= 0.6:
        return 25.0
    elif abs_imb >= 0.4:
        return 20.0
    elif abs_imb >= 0.2:
        return 14.0
    elif abs_imb >= 0.1:
        return 8.0
    return 4.0  # near-balanced book


def _score_funding_rate(funding_rate: float) -> float:
    """Score based on funding rate extremity. Max 20 points.

    Extreme funding (>0.05% or < -0.05% per 8h) is a contrarian risk indicator.
    Moderate funding (0.01–0.03%) with trend = healthy.
    Near-zero funding = neutral.
    """
    abs_fr = abs(funding_rate)
    if abs_fr > 0.10:
        # Extreme funding — very risky, market likely over-extended
        return 2.0
    elif abs_fr > 0.05:
        return 6.0
    elif abs_fr > 0.02:
        return 14.0
    elif abs_fr > 0.005:
        return 20.0
    # Near-zero funding is neutral — moderate score
    return 16.0


def _score_liquidation_proximity(proximity_pct: float) -> float:
    """Score based on distance to nearest liquidation cluster. Max 20 points.

    proximity_pct: percentage away from current price to nearest cluster.
    Being too close to a large liquidation cluster increases cascade risk.
    """
    if proximity_pct < 0.5:
        # Very close — high cascade risk
        return 2.0
    elif proximity_pct < 1.0:
        return 8.0
    elif proximity_pct < 2.0:
        return 14.0
    elif proximity_pct < 3.0:
        return 18.0
    # Far from liquidations — clean microstructure
    return 20.0


def _score_cvd_trend(cvd_trend: float) -> float:
    """Score based on cumulative volume delta direction. Max 20 points.

    cvd_trend: -1 (strong selling pressure) to +1 (strong buying pressure).
    Strong positive CVD with long signal = confirmation.
    """
    abs_cvd = abs(cvd_trend)
    if abs_cvd >= 0.7:
        return 20.0
    elif abs_cvd >= 0.4:
        return 15.0
    elif abs_cvd >= 0.2:
        return 10.0
    return 5.0  # weak or mixed CVD


def _score_volume_ratio(volume_ratio: float) -> float:
    """Score based on volume relative to average. Max 15 points."""
    if volume_ratio >= 2.0:
        return 15.0
    elif volume_ratio >= 1.5:
        return 12.0
    elif volume_ratio >= 1.0:
        return 8.0
    elif volume_ratio >= 0.7:
        return 4.0
    return 1.0  # very low volume — thin market


def _grade_microstructure(score: int) -> str:
    """Convert numeric score to descriptive grade."""
    if score >= 80:
        return "EXCELLENT"
    elif score >= 60:
        return "GOOD"
    elif score >= 40:
        return "FAIR"
    return "POOR"


def _build_recommendation(score: int, grade: str, components: dict[str, float]) -> str:
    """Build a textual recommendation based on the score."""
    if grade == "EXCELLENT":
        return "Microstructure is highly favourable. Proceed with standard position sizing."
    elif grade == "GOOD":
        notes: list[str] = []
        if components.get("funding_score", 20) < 10:
            notes.append("funding rate is elevated")
        if components.get("liq_proximity_score", 20) < 10:
            notes.append("liquidation cluster nearby")
        suffix = " Watch: " + ", ".join(notes) + "." if notes else ""
        return f"Microstructure is acceptable.{suffix}"
    elif grade == "FAIR":
        return (
            "Microstructure is mediocre — consider reducing position size by 30-50% "
            "or waiting for better conditions."
        )
    return (
        "Microstructure is POOR — avoid new entries. "
        "High cascade risk or low liquidity detected."
    )


def calculate_microstructure_score(
    orderbook_imbalance: float,
    funding_rate: float,
    liquidation_proximity_pct: float,
    cvd_trend: float,
    volume_ratio: float,
) -> dict[str, Any]:
    """Calculate microstructure score and return components.

    Args:
        orderbook_imbalance: -1 to 1 (bid vs ask pressure, positive = bid-heavy).
        funding_rate: Current perpetual funding rate (e.g. 0.01 = 0.01% per 8h).
        liquidation_proximity_pct: How far the nearest liquidation cluster is (% from price).
        cvd_trend: Cumulative volume delta direction (-1 to 1).
        volume_ratio: Current volume divided by 20-period average.

    Returns:
        {
            "score": int,           # 0-100
            "grade": str,           # "EXCELLENT" / "GOOD" / "FAIR" / "POOR"
            "components": {
                "orderbook_imbalance_score": float,
                "funding_score": float,
                "liq_proximity_score": float,
                "cvd_score": float,
                "volume_score": float,
            },
            "recommendation": str,
            "inputs": {
                "orderbook_imbalance": float,
                "funding_rate": float,
                "liquidation_proximity_pct": float,
                "cvd_trend": float,
                "volume_ratio": float,
            }
        }
    """
    ob_score = _score_orderbook_imbalance(orderbook_imbalance)
    fund_score = _score_funding_rate(funding_rate)
    liq_score = _score_liquidation_proximity(liquidation_proximity_pct)
    cvd_score = _score_cvd_trend(cvd_trend)
    vol_score = _score_volume_ratio(volume_ratio)

    total = ob_score + fund_score + liq_score + cvd_score + vol_score
    score = min(100, int(round(total)))
    grade = _grade_microstructure(score)

    components: dict[str, float] = {
        "orderbook_imbalance_score": round(ob_score, 2),
        "funding_score": round(fund_score, 2),
        "liq_proximity_score": round(liq_score, 2),
        "cvd_score": round(cvd_score, 2),
        "volume_score": round(vol_score, 2),
    }

    recommendation = _build_recommendation(score, grade, components)

    return {
        "score": score,
        "grade": grade,
        "components": components,
        "recommendation": recommendation,
        "inputs": {
            "orderbook_imbalance": orderbook_imbalance,
            "funding_rate": funding_rate,
            "liquidation_proximity_pct": liquidation_proximity_pct,
            "cvd_trend": cvd_trend,
            "volume_ratio": volume_ratio,
        },
    }
