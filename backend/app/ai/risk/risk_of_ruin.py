"""Risk of Ruin Calculator — probability of account drawdown beyond ruin threshold.

Uses Monte Carlo simulation (pure Python, no external dependencies) to estimate
the probability that a trading account will lose beyond a specified threshold
given current win rate, R-ratio, and position sizing.
"""

from __future__ import annotations

import math
import random
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)


def compute_risk_of_ruin(
    win_rate: float,
    avg_win_r: float,
    avg_loss_r: float,
    risk_per_trade_pct: float,
    ruin_threshold_pct: float = 50.0,
    num_trades: int = 1_000,
    num_simulations: int = 5_000,
) -> dict[str, Any]:
    """Monte Carlo simulation of risk of ruin.

    Args:
        win_rate: Win probability per trade [0, 1]
        avg_win_r: Average win in R-multiples
        avg_loss_r: Average loss in R-multiples (positive value)
        risk_per_trade_pct: Percentage of equity risked per trade
        ruin_threshold_pct: Percentage loss considered "ruin" (default 50%)
        num_trades: Number of trades per simulation path
        num_simulations: Number of Monte Carlo paths (higher = more accurate)

    Returns:
        {ruin_probability, median_final_equity_pct, p5_equity_pct, p95_equity_pct,
         expected_trades_to_ruin, recommendation}
    """
    rng = random.Random(42)  # deterministic seed for reproducibility
    ruin_count = 0
    trades_to_ruin_list: list[int] = []
    final_equities: list[float] = []

    ruin_level = 1.0 - (ruin_threshold_pct / 100.0)

    for _ in range(num_simulations):
        equity = 1.0  # normalized starting equity
        ruined = False

        for trade_num in range(1, num_trades + 1):
            if rng.random() < win_rate:
                equity *= 1 + (risk_per_trade_pct / 100.0) * avg_win_r
            else:
                equity *= 1 - (risk_per_trade_pct / 100.0) * avg_loss_r

            if equity <= ruin_level:
                ruin_count += 1
                trades_to_ruin_list.append(trade_num)
                ruined = True
                break

        if not ruined:
            final_equities.append(equity * 100)  # as percentage

    # Paths that didn't ruin — add their final equities
    ruin_probability = ruin_count / num_simulations

    # Final equity distribution
    all_finals = final_equities + [ruin_level * 100] * len(trades_to_ruin_list)
    all_finals_sorted = sorted(all_finals)

    n = len(all_finals_sorted)
    median = all_finals_sorted[n // 2] if n else 100.0
    p5 = all_finals_sorted[max(0, int(n * 0.05))] if n else ruin_threshold_pct
    p95 = all_finals_sorted[min(n - 1, int(n * 0.95))] if n else 200.0

    avg_trades_to_ruin = (
        sum(trades_to_ruin_list) / len(trades_to_ruin_list)
        if trades_to_ruin_list else None
    )

    recommendation = _build_recommendation(ruin_probability, risk_per_trade_pct)

    return {
        "ruin_probability": round(ruin_probability, 4),
        "ruin_probability_pct": round(ruin_probability * 100, 2),
        "median_final_equity_pct": round(median, 2),
        "p5_equity_pct": round(p5, 2),
        "p95_equity_pct": round(p95, 2),
        "expected_trades_to_ruin": round(avg_trades_to_ruin, 0) if avg_trades_to_ruin else None,
        "ruin_threshold_pct": ruin_threshold_pct,
        "num_simulations": num_simulations,
        "num_trades": num_trades,
        "win_rate": win_rate,
        "avg_win_r": avg_win_r,
        "avg_loss_r": avg_loss_r,
        "risk_per_trade_pct": risk_per_trade_pct,
        "recommendation": recommendation,
    }


def compute_ruin_analytical(
    win_rate: float,
    risk_pct: float,
    ruin_threshold_pct: float = 50.0,
) -> dict[str, Any]:
    """Analytical risk-of-ruin approximation using the gambler's ruin formula.

    This is a simplified estimate; use Monte Carlo for more accuracy.

    Args:
        win_rate: Win probability [0, 1]
        risk_pct: Risk per trade as percentage
        ruin_threshold_pct: Loss considered ruin

    Returns:
        {ruin_probability_analytical, method, note}
    """
    if win_rate <= 0 or win_rate >= 1 or risk_pct <= 0:
        return {"ruin_probability_analytical": 1.0, "method": "invalid_params"}

    loss_rate = 1.0 - win_rate

    # Gambler's ruin: p_ruin = (q/p)^N for N favorable trials to ruin
    # Simplified: R = (L/W)^(ruin_threshold/risk_pct)
    try:
        q_over_p = loss_rate / win_rate
        n_trades_to_ruin = ruin_threshold_pct / risk_pct
        p_ruin = q_over_p ** n_trades_to_ruin if q_over_p != 1.0 else 0.5
        p_ruin = min(1.0, max(0.0, p_ruin))
    except (ZeroDivisionError, OverflowError):
        p_ruin = 1.0

    return {
        "ruin_probability_analytical": round(p_ruin, 4),
        "ruin_probability_pct": round(p_ruin * 100, 2),
        "method": "gamblers_ruin_approximation",
        "note": "Simplified estimate — use Monte Carlo for accuracy",
    }


def _build_recommendation(ruin_probability: float, risk_per_trade_pct: float) -> str:
    """Build a human-readable recommendation.

    Args:
        ruin_probability: Probability of ruin [0, 1]
        risk_per_trade_pct: Current risk percentage

    Returns:
        Recommendation string
    """
    if ruin_probability < 0.01:
        return f"SAFE — Ruin probability {ruin_probability:.1%} is very low. Current sizing is appropriate."
    if ruin_probability < 0.05:
        return f"ACCEPTABLE — Ruin probability {ruin_probability:.1%}. Consider reducing risk slightly."
    if ruin_probability < 0.15:
        return (
            f"RISKY — Ruin probability {ruin_probability:.1%}. "
            f"Reduce risk_per_trade from {risk_per_trade_pct}% to ~{risk_per_trade_pct * 0.6:.1f}%."
        )
    return (
        f"DANGEROUS — Ruin probability {ruin_probability:.1%}. "
        f"Immediately reduce position size. Target < 1% risk per trade."
    )
