"""Expected Value Filter — only allow signals with positive EV.

EV = (win_rate × avg_win_R) - (loss_rate × avg_loss_R)

A signal with EV > 0.3R per trade is considered good. Below 0.0R is
a negative expectancy and should be rejected regardless of confidence score.
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

# Default strategy statistics when no specific data is available
_DEFAULT_STATS = {
    "win_rate": 0.50,
    "avg_win_r": 2.0,
    "avg_loss_r": 1.0,
}


def compute_expected_value(
    win_rate: float,
    avg_win_r: float,
    avg_loss_r: float,
) -> dict[str, Any]:
    """Compute Expected Value per trade in R-multiples.

    Args:
        win_rate: Win probability [0, 1]
        avg_win_r: Average winning trade in R-multiples
        avg_loss_r: Average losing trade in R-multiples (positive value)

    Returns:
        {ev, ev_per_dollar_risked, is_positive_ev, quality}
    """
    loss_rate = 1.0 - win_rate
    ev = (win_rate * avg_win_r) - (loss_rate * avg_loss_r)

    if ev >= 0.5:
        quality = "EXCELLENT"
    elif ev >= 0.3:
        quality = "GOOD"
    elif ev >= 0.0:
        quality = "MARGINAL"
    else:
        quality = "POOR"

    return {
        "ev": round(ev, 4),
        "ev_per_dollar_risked": round(ev, 4),
        "is_positive_ev": ev > 0,
        "quality": quality,
        "win_rate": win_rate,
        "avg_win_r": avg_win_r,
        "avg_loss_r": avg_loss_r,
        "loss_rate": round(loss_rate, 4),
    }


def filter_signal_by_ev(
    signal: dict[str, Any],
    min_ev: float = 0.3,
    strategy_stats: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Annotate a signal with EV-based approval.

    Args:
        signal: Signal dict (at minimum with 'strategy' and 'confidence' keys)
        min_ev: Minimum EV threshold for approval
        strategy_stats: Optional {win_rate, avg_win_r, avg_loss_r} for this strategy

    Returns:
        Signal dict augmented with {ev_approved, ev_score, ev_quality, ev_reason}
    """
    stats = strategy_stats or _DEFAULT_STATS
    ev_data = compute_expected_value(
        win_rate=stats.get("win_rate", _DEFAULT_STATS["win_rate"]),
        avg_win_r=stats.get("avg_win_r", _DEFAULT_STATS["avg_win_r"]),
        avg_loss_r=stats.get("avg_loss_r", _DEFAULT_STATS["avg_loss_r"]),
    )

    approved = ev_data["ev"] >= min_ev
    reason = (
        f"EV = {ev_data['ev']:.3f}R (threshold: {min_ev}R) — "
        f"win_rate={stats.get('win_rate', 0.5):.0%}, "
        f"avg_win={stats.get('avg_win_r', 2.0):.1f}R, "
        f"avg_loss={stats.get('avg_loss_r', 1.0):.1f}R"
    )

    if not approved:
        logger.debug(
            "EV filter blocked signal: %s (ev=%.3f < min_ev=%.3f)",
            signal.get("strategy", "unknown"),
            ev_data["ev"],
            min_ev,
        )

    signal_out = dict(signal)
    signal_out["ev_approved"] = approved
    signal_out["ev_score"] = ev_data["ev"]
    signal_out["ev_quality"] = ev_data["quality"]
    signal_out["ev_reason"] = reason
    signal_out["ev_details"] = ev_data
    return signal_out
