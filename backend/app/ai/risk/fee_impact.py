"""Fee and Slippage Impact Model — compute realistic net PnL after trading costs.

Accurately models round-trip costs including:
- Exchange maker/taker fees
- Estimated market slippage
- Breakeven move requirement

Use this before entering a trade to ensure the expected move exceeds costs.
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

EXCHANGE_FEES: dict[str, dict[str, float]] = {
    "binance": {"maker": 0.0002, "taker": 0.0004},
    "bybit": {"maker": 0.0001, "taker": 0.0006},
    "okx": {"maker": 0.0002, "taker": 0.0005},
    "coinbase": {"maker": 0.0040, "taker": 0.0060},
}


def compute_fee_impact(
    position_size_usd: float,
    entry_price: float,
    target_price: float,
    stop_price: float,
    exchange: str = "binance",
    order_type: str = "taker",
    estimated_slippage_pct: float = 0.05,
) -> dict[str, Any]:
    """Compute round-trip trading costs and their impact on the trade.

    Args:
        position_size_usd: Position size in USD
        entry_price: Planned entry price
        target_price: Take profit price
        stop_price: Stop loss price
        exchange: Exchange name (key in EXCHANGE_FEES)
        order_type: "maker" or "taker"
        estimated_slippage_pct: Estimated slippage as % of price

    Returns:
        {gross_pnl_usd, total_fees_usd, slippage_usd, net_pnl_usd, net_pnl_pct,
         breakeven_move_pct, fee_impact_on_rr}
    """
    fees = EXCHANGE_FEES.get(exchange, EXCHANGE_FEES["binance"])
    fee_rate = fees.get(order_type, fees["taker"])

    # Determine direction
    is_long = target_price > entry_price

    # Gross PnL
    if is_long:
        move_pct = (target_price - entry_price) / entry_price
    else:
        move_pct = (entry_price - target_price) / entry_price

    gross_pnl_usd = position_size_usd * move_pct

    # Stop distance for R computation
    if is_long:
        stop_dist_pct = abs(entry_price - stop_price) / entry_price
    else:
        stop_dist_pct = abs(stop_price - entry_price) / entry_price

    gross_r = move_pct / stop_dist_pct if stop_dist_pct > 0 else 0.0

    # Round-trip fees (entry + exit)
    total_fees_usd = position_size_usd * fee_rate * 2

    # Slippage (entry + exit)
    slippage_usd = position_size_usd * (estimated_slippage_pct / 100) * 2

    # Net PnL
    net_pnl_usd = gross_pnl_usd - total_fees_usd - slippage_usd
    net_pnl_pct = (net_pnl_usd / position_size_usd * 100) if position_size_usd > 0 else 0.0

    # Breakeven: how much price must move just to cover fees + slippage
    breakeven_cost = total_fees_usd + slippage_usd
    breakeven_move_pct = (breakeven_cost / position_size_usd * 100) if position_size_usd > 0 else 0.0

    # Net R-ratio accounting for costs
    net_win_usd = net_pnl_usd
    stop_loss_usd = position_size_usd * stop_dist_pct - total_fees_usd - slippage_usd
    net_rr = net_win_usd / abs(stop_loss_usd) if stop_loss_usd != 0 else 0.0

    fee_impact_note = (
        f"Fees+slippage consume {breakeven_move_pct:.2f}% of move — "
        f"gross R={gross_r:.2f}, net R≈{net_rr:.2f}"
    )

    return {
        "exchange": exchange,
        "order_type": order_type,
        "position_size_usd": position_size_usd,
        "direction": "LONG" if is_long else "SHORT",
        "gross_pnl_usd": round(gross_pnl_usd, 2),
        "total_fees_usd": round(total_fees_usd, 2),
        "slippage_usd": round(slippage_usd, 2),
        "net_pnl_usd": round(net_pnl_usd, 2),
        "net_pnl_pct": round(net_pnl_pct, 3),
        "gross_move_pct": round(move_pct * 100, 3),
        "breakeven_move_pct": round(breakeven_move_pct, 3),
        "gross_r_ratio": round(gross_r, 3),
        "net_r_ratio": round(net_rr, 3),
        "fee_rate_pct": round(fee_rate * 100, 4),
        "fee_impact_on_rr": fee_impact_note,
    }
