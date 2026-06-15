"""Signal Playbook Generator — auto-generates complete trade playbook cards.

A playbook provides everything a trader needs before entering a position:
entry zone, stop loss, three take profit levels, pre-trade checklist,
invalidation conditions, and maximum hold time guidelines.
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

# Risk-Reward ratios for TP levels
_TP_RR = [
    {"level": "TP1", "r_multiple": 1.0, "size_pct": 40},
    {"level": "TP2", "r_multiple": 2.0, "size_pct": 35},
    {"level": "TP3", "r_multiple": 3.0, "size_pct": 25},
]

# Max hold time guidelines per timeframe
_HOLD_TIMES: dict[str, str] = {
    "1m": "15-60 minutes (scalp)",
    "5m": "30 min - 4 hours (scalp)",
    "15m": "2-12 hours (intraday)",
    "1h": "4-48 hours (swing)",
    "4h": "1-7 days (swing)",
    "1d": "1-4 weeks (position)",
}


def generate_playbook(
    signal: dict[str, Any],
    current_price: float,
    atr_value: float,
) -> dict[str, Any]:
    """Generate a complete trade playbook from a signal.

    Args:
        signal: {symbol, direction, confidence, strategy, entry_price, stop_loss, take_profit}
        current_price: Current market price
        atr_value: ATR value for the symbol

    Returns:
        Complete playbook dict with entry, SL, TPs, checklist, invalidation
    """
    symbol = signal.get("symbol", "UNKNOWN")
    direction = signal.get("direction", "LONG").upper()
    strategy = signal.get("strategy", "unknown")
    confidence = signal.get("confidence", 0.5)
    interval = signal.get("interval", "1h")

    entry_price = float(signal.get("entry_price") or current_price)
    stop_loss = float(signal.get("stop_loss") or _compute_stop(entry_price, direction, atr_value))
    float(signal.get("take_profit") or _compute_tp(entry_price, stop_loss, direction, 1.0))

    # Risk distance
    risk_distance = abs(entry_price - stop_loss)
    if risk_distance == 0:
        risk_distance = atr_value or entry_price * 0.01

    # Entry zone: ±0.2% around entry
    entry_zone = [
        round(entry_price * 0.998, 6),
        round(entry_price * 1.002, 6),
    ]

    # Take profit levels
    take_profits = []
    for tp_def in _TP_RR:
        if direction == "LONG":
            tp_price = entry_price + risk_distance * tp_def["r_multiple"]
        else:
            tp_price = entry_price - risk_distance * tp_def["r_multiple"]

        tp_pct = abs(tp_price - entry_price) / entry_price * 100

        take_profits.append({
            "level": tp_def["level"],
            "price": round(tp_price, 6),
            "pct_gain": round(tp_pct, 3),
            "r_multiple": tp_def["r_multiple"],
            "size_pct": tp_def["size_pct"],
        })

    # Invalidation: opposite side of stop by 0.5× ATR
    if direction == "LONG":
        invalidation_price = round(stop_loss - atr_value * 0.5, 6)
    else:
        invalidation_price = round(stop_loss + atr_value * 0.5, 6)

    sl_pct = abs(entry_price - stop_loss) / entry_price * 100
    rr_ratio = take_profits[0]["pct_gain"] / sl_pct if sl_pct > 0 else 0.0

    checklist = generate_checklist(signal, signal.get("regime", "UNKNOWN"))
    hold_time = _HOLD_TIMES.get(interval, "varies")

    return {
        "symbol": symbol,
        "direction": direction,
        "strategy": strategy,
        "confidence": confidence,
        "entry": {
            "price": round(entry_price, 6),
            "type": "LIMIT" if confidence >= 0.70 else "MARKET",
            "zone": entry_zone,
        },
        "stop_loss": {
            "price": round(stop_loss, 6),
            "pct_from_entry": round(sl_pct, 3),
            "r_distance": round(risk_distance, 6),
        },
        "take_profits": take_profits,
        "invalidation": {
            "price": invalidation_price,
            "condition": f"Close {'below' if direction == 'LONG' else 'above'} {invalidation_price} — signal invalid",
        },
        "checklist": checklist,
        "risk_reward_ratio": round(rr_ratio, 2),
        "max_hold_time": hold_time,
        "notes": _generate_notes(signal, confidence),
    }


def generate_checklist(signal: dict[str, Any], regime: str) -> list[str]:
    """Generate pre-trade checklist based on signal and regime.

    Args:
        signal: Signal dict
        regime: Current market regime

    Returns:
        List of checklist items to verify before entry
    """
    checklist = [
        "✅ Confirm signal confidence ≥ 70%",
        "✅ Check current market regime matches strategy",
        "✅ Verify position size ≤ 2% account risk",
        "✅ Confirm stop loss is set before entry",
        "✅ Check for upcoming high-impact news events",
        "✅ Verify liquidity is sufficient (spread < 0.05%)",
    ]

    if regime in ("HIGH_VOL_CHOPPY", "CONSOLIDATION"):
        checklist.append("⚠️ Market is choppy — reduce position size by 50%")

    if signal.get("direction") == "LONG" and signal.get("rsi", 100) > 70:
        checklist.append("⚠️ RSI overbought — wait for pullback entry")

    if signal.get("direction") == "SHORT" and signal.get("rsi", 0) < 30:
        checklist.append("⚠️ RSI oversold — wait for bounce to fade")

    if signal.get("confidence", 1.0) < 0.65:
        checklist.append("⚠️ Low confidence signal — use quarter-size position")

    return checklist


def _compute_stop(entry: float, direction: str, atr: float) -> float:
    """Compute a default stop loss at 1.5× ATR from entry.

    Args:
        entry: Entry price
        direction: LONG or SHORT
        atr: ATR value

    Returns:
        Stop loss price
    """
    if direction == "LONG":
        return round(entry - atr * 1.5, 6)
    return round(entry + atr * 1.5, 6)


def _compute_tp(entry: float, stop: float, direction: str, r_multiple: float) -> float:
    """Compute take profit at given R-multiple from entry.

    Args:
        entry: Entry price
        stop: Stop loss price
        direction: LONG or SHORT
        r_multiple: R-multiple for TP

    Returns:
        Take profit price
    """
    risk = abs(entry - stop)
    if direction == "LONG":
        return round(entry + risk * r_multiple, 6)
    return round(entry - risk * r_multiple, 6)


def _generate_notes(signal: dict[str, Any], confidence: float) -> str:
    """Generate trade notes string.

    Args:
        signal: Signal dict
        confidence: Signal confidence

    Returns:
        Notes string
    """
    strategy = signal.get("strategy", "unknown")
    notes = f"{strategy.replace('_', ' ').title()} signal. "
    if confidence >= 0.80:
        notes += "High confidence — consider scaling in if price revisits entry zone."
    elif confidence >= 0.65:
        notes += "Standard confidence — single entry at zone midpoint."
    else:
        notes += "Lower confidence — wait for additional confirmation before entering."
    return notes
