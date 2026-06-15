"""Trade Post-Mortem Analyzer — AI analysis of completed trades.

Grades each closed trade on execution quality, entry timing, exit discipline,
and regime alignment. Identifies behavioral patterns and provides actionable
lessons to improve future performance.

Grade scale:
  A: Excellent — followed the plan, optimal entry and exit
  B: Good — minor deviations, profitable or small loss
  C: Average — some errors but manageable
  D: Poor — significant execution errors
  F: Failed — broke rules, emotional decisions detected
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

# Pattern detection thresholds
_EARLY_EXIT_THRESHOLD = 0.5    # exited before 50% of TP distance
_LATE_EXIT_THRESHOLD = 0.2     # held 20% past stop
_GOOD_ENTRY_THRESHOLD = 0.005  # within 0.5% of ideal entry
_POOR_ENTRY_THRESHOLD = 0.01   # more than 1% from ideal entry
_OVERHOLD_HOURS_SCALP = 4.0   # scalp held > 4h
_OVERHOLD_HOURS_SWING = 168.0  # swing held > 7 days

POST_MORTEM_PATTERNS: dict[str, str] = {
    "early_exit": "Exited before take profit — potential profits left on table",
    "late_exit": "Held past stop loss level — possible emotional decision",
    "good_entry": "Entry was within 0.5% of ideal level — excellent timing",
    "poor_entry": "Entry was over 1% from ideal — chased price",
    "regime_mismatch": "Traded against current market regime — structural headwind",
    "overtraded_low_confidence": "Entered with below-threshold confidence signal",
    "winner_cut_short": "Winning trade exited too early relative to target",
    "plan_followed": "Trade followed the original plan — disciplined execution",
    "optimal_hold": "Hold time was appropriate for the timeframe",
}


def analyze_trade(
    entry_price: float,
    exit_price: float,
    direction: str,
    stop_loss: float,
    take_profit: float,
    entry_time: str,
    exit_time: str,
    signal_confidence: float,
    regime_at_entry: str,
    strategy_name: str,
) -> dict[str, Any]:
    """Analyze a completed trade and generate a post-mortem report.

    Args:
        entry_price: Actual entry price
        exit_price: Actual exit price
        direction: LONG or SHORT
        stop_loss: Original stop loss price
        take_profit: Original take profit price (TP1)
        entry_time: ISO datetime string of entry
        exit_time: ISO datetime string of exit
        signal_confidence: Signal confidence at entry [0, 1]
        regime_at_entry: Market regime when trade was entered
        strategy_name: Strategy that generated the signal

    Returns:
        {pnl_pct, pnl_r, outcome, patterns_detected, grade, lessons,
         strengths, improvements, summary}
    """
    direction = direction.upper()

    # Compute PnL
    if direction == "LONG":
        pnl_pct = (exit_price - entry_price) / entry_price * 100
    else:
        pnl_pct = (entry_price - exit_price) / entry_price * 100

    # Compute R-multiple
    risk_distance = abs(entry_price - stop_loss)
    pnl_r = pnl_pct / (risk_distance / entry_price * 100) if risk_distance > 0 else 0.0

    outcome = "WIN" if pnl_pct > 0 else ("BREAKEVEN" if abs(pnl_pct) < 0.05 else "LOSS")

    # Hold time
    try:
        entry_dt = datetime.fromisoformat(entry_time.replace("Z", "+00:00"))
        exit_dt = datetime.fromisoformat(exit_time.replace("Z", "+00:00"))
        hold_hours = (exit_dt - entry_dt).total_seconds() / 3600
    except (ValueError, AttributeError):
        hold_hours = 1.0

    # Pattern detection
    patterns: list[str] = []

    # Early exit: exited before 50% toward TP
    if direction == "LONG":
        tp_pct = (take_profit - entry_price) / entry_price
        exit_pct = (exit_price - entry_price) / entry_price
    else:
        tp_pct = (entry_price - take_profit) / entry_price
        exit_pct = (entry_price - exit_price) / entry_price

    if pnl_pct > 0 and tp_pct > 0 and exit_pct < tp_pct * _EARLY_EXIT_THRESHOLD:
        patterns.append("early_exit")
        patterns.append("winner_cut_short")

    # Late exit: held past stop
    if direction == "LONG" and exit_price < stop_loss * (1 - _LATE_EXIT_THRESHOLD):
        patterns.append("late_exit")
    elif direction == "SHORT" and exit_price > stop_loss * (1 + _LATE_EXIT_THRESHOLD):
        patterns.append("late_exit")

    # Entry quality
    # Good entry: price action aligned with direction
    if signal_confidence >= 0.70:
        patterns.append("good_entry")
    elif signal_confidence < 0.50:
        patterns.append("overtraded_low_confidence")
        patterns.append("poor_entry")

    # Regime mismatch
    unfavorable_regimes = {
        "trend_following": ["CONSOLIDATION", "HIGH_VOL_CHOPPY"],
        "mean_reversion": ["TREND_BULL", "TREND_BEAR"],
        "breakout": ["HIGH_VOL_CHOPPY"],
    }
    strategy_key = strategy_name.lower().replace(" ", "_")
    bad_regimes = unfavorable_regimes.get(strategy_key, [])
    if regime_at_entry in bad_regimes:
        patterns.append("regime_mismatch")

    # Plan followed (no major deviations detected)
    if "late_exit" not in patterns and "poor_entry" not in patterns:
        patterns.append("plan_followed")

    # Optimal hold time check
    if hold_hours < _OVERHOLD_HOURS_SCALP or hold_hours > _OVERHOLD_HOURS_SWING:
        pass  # unusual hold but not a pattern to flag
    else:
        patterns.append("optimal_hold")

    # Grade computation
    grade = _compute_grade(pnl_r, patterns, signal_confidence, outcome)

    # Lessons and strengths
    lessons, strengths, improvements = _generate_feedback(patterns, pnl_r, outcome, grade)

    quality_score = compute_trade_quality_score(
        {"patterns": patterns, "grade": grade, "pnl_r": pnl_r}
    )

    return {
        "pnl_pct": round(pnl_pct, 3),
        "pnl_r": round(pnl_r, 3),
        "hold_hours": round(hold_hours, 2),
        "outcome": outcome,
        "patterns_detected": [POST_MORTEM_PATTERNS.get(p, p) for p in patterns],
        "raw_patterns": patterns,
        "grade": grade,
        "quality_score": quality_score,
        "lessons": lessons,
        "strengths": strengths,
        "improvements": improvements,
        "summary": _generate_summary(grade, outcome, strategy_name, regime_at_entry),
    }


def compute_trade_quality_score(analysis: dict[str, Any]) -> float:
    """Compute a trade quality score from 0-100.

    Args:
        analysis: Analysis dict with patterns, grade, pnl_r

    Returns:
        Quality score 0-100
    """
    score = 50.0  # baseline
    patterns = analysis.get("raw_patterns", analysis.get("patterns", []))

    # Grade bonus/penalty
    grade_map = {"A": 40, "B": 20, "C": 0, "D": -20, "F": -40}
    score += grade_map.get(analysis.get("grade", "C"), 0)

    # Pattern adjustments
    if "good_entry" in patterns:
        score += 10
    if "plan_followed" in patterns:
        score += 10
    if "early_exit" in patterns or "winner_cut_short" in patterns:
        score -= 10
    if "late_exit" in patterns:
        score -= 15
    if "regime_mismatch" in patterns:
        score -= 10
    if "overtraded_low_confidence" in patterns:
        score -= 10

    return round(max(0.0, min(100.0, score)), 1)


def _compute_grade(
    pnl_r: float,
    patterns: list[str],
    confidence: float,
    outcome: str,
) -> str:
    """Compute letter grade for a trade.

    Args:
        pnl_r: Trade result in R-multiples
        patterns: Detected behavioral patterns
        confidence: Signal confidence at entry
        outcome: WIN, LOSS, or BREAKEVEN

    Returns:
        Letter grade A-F
    """
    negative_patterns = {"late_exit", "poor_entry", "regime_mismatch", "overtraded_low_confidence"}
    penalty = sum(1 for p in patterns if p in negative_patterns)

    if pnl_r >= 2.0 and penalty == 0:
        return "A"
    if pnl_r >= 1.0 and penalty <= 1:
        return "B"
    if pnl_r >= 0 and penalty <= 2:
        return "C"
    if pnl_r >= -0.5 and penalty <= 3:
        return "D"
    return "F"


def _generate_feedback(
    patterns: list[str],
    pnl_r: float,
    outcome: str,
    grade: str,
) -> tuple[list[str], list[str], list[str]]:
    """Generate lessons, strengths, and improvement areas.

    Args:
        patterns: Detected patterns
        pnl_r: Trade PnL in R
        outcome: Trade outcome
        grade: Letter grade

    Returns:
        Tuple of (lessons, strengths, improvements)
    """
    lessons: list[str] = []
    strengths: list[str] = []
    improvements: list[str] = []

    if "early_exit" in patterns:
        lessons.append("Exiting early erodes edge over time. Let winners breathe to TP1 at minimum.")
        improvements.append("Set a rule: never exit a winning trade before TP1 unless invalidation triggers.")

    if "late_exit" in patterns:
        lessons.append("Holding past stop suggests emotional attachment. Honor stop losses without exception.")
        improvements.append("Use hard stops in the platform — do not manage stops manually.")

    if "good_entry" in patterns:
        strengths.append("Excellent entry timing — you waited for the setup to fully develop.")

    if "plan_followed" in patterns:
        strengths.append("Trade was executed according to the original plan — disciplined approach.")

    if "regime_mismatch" in patterns:
        lessons.append("Trading against the regime creates unnecessary headwinds. Check regime before every entry.")
        improvements.append("Add regime check to pre-trade checklist — skip trades with regime mismatch.")

    if "overtraded_low_confidence" in patterns:
        lessons.append("Low confidence signals have negative EV on average. Minimum 65% confidence before entering.")
        improvements.append("Set a hard filter: no entries below 65% signal confidence.")

    if grade == "A":
        strengths.append(f"Outstanding execution — {pnl_r:.1f}R result with disciplined process.")
    elif grade == "F":
        lessons.append("Multiple rule violations detected. Review and reset before next trade.")

    return lessons, strengths, improvements


def _generate_summary(grade: str, outcome: str, strategy: str, regime: str) -> str:
    """Generate a one-line trade summary.

    Args:
        grade: Letter grade
        outcome: WIN/LOSS/BREAKEVEN
        strategy: Strategy name
        regime: Regime at entry

    Returns:
        Summary string
    """
    return (
        f"Grade {grade} {outcome} — {strategy.replace('_', ' ').title()} trade "
        f"in {regime} regime."
    )
