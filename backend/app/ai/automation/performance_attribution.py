"""Performance Attribution — breaks down PnL by strategy, regime, time-of-day, and more.

Identifies which conditions, strategies, and time windows generate alpha,
allowing traders to focus on high-edge setups and avoid low-edge ones.
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

_SESSIONS: dict[str, tuple[int, int]] = {
    "asian": (0, 8),      # UTC 00-08
    "london": (8, 16),    # UTC 08-16
    "ny": (13, 21),       # UTC 13-21
    "overlap": (13, 16),  # UTC 13-16 (London-NY overlap)
}


def attribute_performance(trades: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute multi-dimensional performance attribution.

    Args:
        trades: List of trade dicts with fields:
            {strategy, regime, pnl_r, entry_time (ISO str), holding_hours, symbol, direction}

    Returns:
        Comprehensive attribution report
    """
    if not trades:
        return {"error": "No trades provided", "total_trades": 0}

    by_strategy: dict[str, list[float]] = {}
    by_regime: dict[str, list[float]] = {}
    by_session: dict[str, list[float]] = {}
    by_hold: dict[str, list[float]] = {}
    by_direction: dict[str, list[float]] = {}

    for trade in trades:
        pnl = float(trade.get("pnl_r", 0))
        strategy = trade.get("strategy", "unknown")
        regime = trade.get("regime", "UNKNOWN")
        direction = trade.get("direction", "LONG").upper()
        holding_hours = float(trade.get("holding_hours", 1))

        # By strategy
        by_strategy.setdefault(strategy, []).append(pnl)

        # By regime
        by_regime.setdefault(regime, []).append(pnl)

        # By session
        entry_time = trade.get("entry_time", "")
        session = _classify_session(entry_time)
        by_session.setdefault(session, []).append(pnl)

        # By holding period
        hold_label = _classify_holding(holding_hours)
        by_hold.setdefault(hold_label, []).append(pnl)

        # By direction
        by_direction.setdefault(direction, []).append(pnl)

    total_r = sum(t.get("pnl_r", 0) for t in trades)
    all_pnls = [t.get("pnl_r", 0) for t in trades]
    wins = [p for p in all_pnls if p > 0]
    overall_wr = len(wins) / len(all_pnls) if all_pnls else 0.0

    def _summarize(groups: dict[str, list[float]]) -> dict[str, Any]:
        result = {}
        for key, pnls in groups.items():
            wins_g = [p for p in pnls if p > 0]
            result[key] = {
                "trades": len(pnls),
                "win_rate": round(len(wins_g) / len(pnls), 3),
                "avg_r": round(sum(pnls) / len(pnls), 4),
                "total_r": round(sum(pnls), 4),
                "contribution_pct": round(sum(pnls) / abs(total_r) * 100, 2) if total_r != 0 else 0.0,
            }
        return result

    strategy_attr = _summarize(by_strategy)
    regime_attr = _summarize(by_regime)
    session_attr = _summarize(by_session)
    hold_attr = _summarize(by_hold)
    direction_attr = _summarize(by_direction)

    best_strategy = max(strategy_attr, key=lambda k: strategy_attr[k]["avg_r"], default=None)
    best_regime = max(regime_attr, key=lambda k: regime_attr[k]["avg_r"], default=None)
    best_session = max(session_attr, key=lambda k: session_attr[k]["avg_r"], default=None)

    return {
        "by_strategy": strategy_attr,
        "by_regime": regime_attr,
        "by_time_of_day": session_attr,
        "by_holding_period": hold_attr,
        "by_direction": direction_attr,
        "best_performing_strategy": best_strategy,
        "best_performing_regime": best_regime,
        "best_time_of_day": best_session,
        "total_r": round(total_r, 4),
        "total_trades": len(trades),
        "overall_win_rate": round(overall_wr, 3),
    }


def _classify_session(entry_time_iso: str) -> str:
    """Classify trade entry into a trading session.

    Args:
        entry_time_iso: ISO 8601 datetime string

    Returns:
        Session label string
    """
    try:
        hour = int(entry_time_iso[11:13]) if len(entry_time_iso) > 13 else 12
    except (ValueError, IndexError):
        return "unknown"

    # Overlap first (most specific)
    if 13 <= hour < 16:
        return "overlap"
    if 0 <= hour < 8:
        return "asian"
    if 8 <= hour < 16:
        return "london"
    if 13 <= hour < 21:
        return "ny"
    return "other"


def _classify_holding(hours: float) -> str:
    """Classify trade holding period.

    Args:
        hours: Trade duration in hours

    Returns:
        Duration category label
    """
    if hours < 4:
        return "scalp"
    if hours < 24:
        return "intraday"
    return "swing"
