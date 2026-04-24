"""Trade setup quality scoring module.

Grades each signal A/B/C/D based on:
- Risk/Reward ratio (higher is better)
- Regime alignment (strategy matches current regime)
- Volume confirmation (above-average volume is bullish)
- MTF confluence (signal appears on multiple timeframes)
- Time-of-day suitability (avoid low-volume hours 00:00-06:00 UTC)
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class QualityGrade(str, Enum):
    """Signal quality grade from best (A) to weakest (D)."""

    A = "A"
    B = "B"
    C = "C"
    D = "D"


@dataclass
class QualityScore:
    """Full quality assessment for a trade setup."""

    grade: QualityGrade
    score: float  # 0-100
    breakdown: dict[str, float] = field(default_factory=dict)  # component scores
    reasoning: str = ""  # human-readable explanation


# Regimes where LONG signals align well vs SHORT signals align well
_LONG_FRIENDLY_REGIMES = {"TREND_BULL", "BREAKOUT", "ACCUMULATION"}
_SHORT_FRIENDLY_REGIMES = {"TREND_BEAR", "BREAKDOWN", "DISTRIBUTION"}
_NEUTRAL_REGIMES = {"CONSOLIDATION", "HIGH_VOL_CHOPPY", "RANGING"}

# UTC hours considered low-volume (crypto is 24/7 but majors are thin here)
_LOW_VOLUME_HOURS = set(range(0, 6))  # 00:00 – 05:59 UTC


def _score_risk_reward(signal: dict[str, Any]) -> float:
    """Score based on R/R ratio. Max 25 points."""
    rr = float(signal.get("risk_reward") or 0)
    if rr <= 0:
        # Try to compute from entry / sl / tp1
        entry = float(signal.get("entry_price") or 0)
        sl = float(signal.get("stop_loss") or 0)
        tp1 = float(signal.get("take_profit_1") or 0)
        direction = signal.get("direction", "LONG")
        if entry and sl and tp1:
            if direction == "LONG":
                risk = entry - sl
                reward = tp1 - entry
            else:
                risk = sl - entry
                reward = entry - tp1
            rr = reward / risk if risk > 0 else 0

    if rr >= 3.0:
        return 25.0
    elif rr >= 2.0:
        return 20.0
    elif rr >= 1.5:
        return 15.0
    elif rr >= 1.0:
        return 10.0
    else:
        return max(0.0, rr * 8)  # partial credit for sub-1 R/R


def _score_regime_alignment(signal: dict[str, Any], regime: str) -> float:
    """Score regime alignment with signal direction. Max 20 points."""
    direction = signal.get("direction", "NEUTRAL")
    regime_upper = regime.upper()

    if direction == "LONG" and regime_upper in _LONG_FRIENDLY_REGIMES:
        return 20.0
    elif direction == "SHORT" and regime_upper in _SHORT_FRIENDLY_REGIMES:
        return 20.0
    elif regime_upper in _NEUTRAL_REGIMES:
        # Neutral regime — partial credit
        return 8.0
    elif direction == "LONG" and regime_upper in _SHORT_FRIENDLY_REGIMES:
        # Counter-trend long in bear regime — penalise
        return 0.0
    elif direction == "SHORT" and regime_upper in _LONG_FRIENDLY_REGIMES:
        # Counter-trend short in bull regime — penalise
        return 0.0
    # Unknown regime — give partial
    return 10.0


def _score_volume(market_data: dict[str, Any]) -> float:
    """Score volume confirmation. Max 20 points."""
    volume_ratio = float(market_data.get("volume_ratio", 1.0))  # current / 20-period avg
    if volume_ratio >= 2.0:
        return 20.0
    elif volume_ratio >= 1.5:
        return 16.0
    elif volume_ratio >= 1.2:
        return 12.0
    elif volume_ratio >= 1.0:
        return 8.0
    else:
        # Below average volume = weak confirmation
        return max(0.0, volume_ratio * 6)


def _score_mtf_confluence(signal: dict[str, Any]) -> float:
    """Score multi-timeframe confluence. Max 20 points."""
    mtf_score = float(signal.get("mtf_confluence_score", 0))
    if mtf_score > 0:
        return min(20.0, mtf_score * 20)

    # Alternatively, check factors for MTF mentions
    factors = signal.get("factors", [])
    mtf_count = 0
    for f in factors:
        name = (f.get("name", "") if isinstance(f, dict) else str(f)).lower()
        if any(tf in name for tf in ["4h", "1d", "15m", "multi", "mtf", "confluence"]):
            mtf_count += 1

    if mtf_count >= 3:
        return 20.0
    elif mtf_count == 2:
        return 14.0
    elif mtf_count == 1:
        return 8.0
    return 4.0  # Default minimal score if no data


def _score_timing(signal: dict[str, Any]) -> float:
    """Score time-of-day suitability. Max 15 points."""
    # Determine the signal hour
    created_at = signal.get("created_at")
    if isinstance(created_at, str):
        try:
            created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except ValueError:
            created_at = None

    if created_at is None:
        created_at = datetime.now(timezone.utc)

    hour = created_at.hour if hasattr(created_at, "hour") else datetime.now(timezone.utc).hour

    if hour in _LOW_VOLUME_HOURS:
        # Low volume Asian session — partial score
        return 5.0
    elif 8 <= hour <= 16:
        # London / NY session overlap — best liquidity
        return 15.0
    elif 6 <= hour <= 20:
        # Reasonable trading hours
        return 12.0
    else:
        # Off-hours but not worst
        return 8.0


def _grade_from_score(score: float) -> QualityGrade:
    """Convert numeric score to letter grade."""
    if score >= 85:
        return QualityGrade.A
    elif score >= 70:
        return QualityGrade.B
    elif score >= 50:
        return QualityGrade.C
    return QualityGrade.D


def _build_reasoning(
    breakdown: dict[str, float],
    grade: QualityGrade,
    score: float,
    regime: str,
    signal: dict[str, Any],
) -> str:
    """Build a human-readable explanation for the quality score."""
    parts: list[str] = [f"Overall grade {grade.value} ({score:.1f}/100)."]

    rr_val = breakdown.get("rr_score", 0)
    if rr_val >= 20:
        parts.append("Excellent R/R ratio.")
    elif rr_val >= 10:
        parts.append("Acceptable R/R ratio.")
    else:
        parts.append("Poor R/R — consider adjusting stops/targets.")

    reg_val = breakdown.get("regime_alignment", 0)
    if reg_val >= 18:
        parts.append(f"Signal aligns with {regime} regime.")
    elif reg_val >= 8:
        parts.append(f"Neutral regime ({regime}) — moderate alignment.")
    else:
        parts.append(f"Counter-trend vs {regime} — elevated risk.")

    vol_val = breakdown.get("volume_score", 0)
    if vol_val >= 16:
        parts.append("Strong volume confirmation.")
    elif vol_val < 8:
        parts.append("Below-average volume — weak confirmation.")

    mtf_val = breakdown.get("mtf_score", 0)
    if mtf_val >= 16:
        parts.append("Good multi-timeframe confluence.")
    elif mtf_val < 8:
        parts.append("Limited MTF confluence.")

    return " ".join(parts)


def score_trade_setup(
    signal: dict[str, Any],
    market_data: dict[str, Any],
    regime: str,
) -> QualityScore:
    """Score a trade setup and return grade + breakdown.

    Args:
        signal: Signal dictionary with keys like direction, entry_price, stop_loss,
                take_profit_1, risk_reward, factors, mtf_confluence_score, created_at.
        market_data: Market data dictionary with volume_ratio (current / 20-period average).
        regime: Current market regime string (e.g. "TREND_BULL", "CONSOLIDATION").

    Returns:
        QualityScore with grade (A/B/C/D), numeric score (0-100), component breakdown,
        and human-readable reasoning.
    """
    rr_score = _score_risk_reward(signal)
    regime_score = _score_regime_alignment(signal, regime)
    vol_score = _score_volume(market_data)
    mtf_score = _score_mtf_confluence(signal)
    timing_score = _score_timing(signal)

    total = rr_score + regime_score + vol_score + mtf_score + timing_score

    breakdown: dict[str, float] = {
        "rr_score": round(rr_score, 2),
        "regime_alignment": round(regime_score, 2),
        "volume_score": round(vol_score, 2),
        "mtf_score": round(mtf_score, 2),
        "timing_score": round(timing_score, 2),
    }

    grade = _grade_from_score(total)
    reasoning = _build_reasoning(breakdown, grade, total, regime, signal)

    return QualityScore(
        grade=grade,
        score=round(total, 2),
        breakdown=breakdown,
        reasoning=reasoning,
    )
