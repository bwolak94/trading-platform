"""Portfolio Stress Tester — simulate portfolio PnL under adverse scenarios.

Runs predefined market scenarios against current positions to identify
maximum loss exposure before it happens. Essential for risk management
and position sizing decisions.
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

# Scenario definitions: symbol_pattern -> expected_move_pct
SCENARIOS: dict[str, dict[str, float]] = {
    "btc_crash_30pct": {
        "BTC": -0.30,
        "ETH": -0.35,
        "SOL": -0.45,
        "BNB": -0.38,
        "alts_default": -0.50,
    },
    "flash_crash": {
        "BTC": -0.15,
        "ETH": -0.18,
        "SOL": -0.22,
        "BNB": -0.20,
        "alts_default": -0.25,
    },
    "correlation_spike": {
        "all": -0.20,  # everything drops together
    },
    "alt_season": {
        "BTC": 0.05,
        "ETH": 0.20,
        "SOL": 0.35,
        "BNB": 0.25,
        "alts_default": 0.40,
    },
    "btc_rally_20pct": {
        "BTC": 0.20,
        "ETH": 0.18,
        "SOL": 0.22,
        "BNB": 0.15,
        "alts_default": 0.12,
    },
    "risk_off_mild": {
        "BTC": -0.10,
        "ETH": -0.12,
        "SOL": -0.15,
        "alts_default": -0.18,
    },
}

_SYMBOL_MAPPING: dict[str, str] = {
    "BTCUSDT": "BTC",
    "ETHUSDT": "ETH",
    "SOLUSDT": "SOL",
    "BNBUSDT": "BNB",
}


async def run_stress_test(
    positions: list[dict[str, Any]],
    scenarios: list[str] | None = None,
) -> dict[str, Any]:
    """Simulate portfolio PnL under stress scenarios.

    Args:
        positions: List of {symbol, size_usd, direction: LONG|SHORT}
        scenarios: List of scenario names to run (None = all)

    Returns:
        {results, worst_case_scenario, worst_case_loss_usd, portfolio_total_usd}
    """
    scenarios_to_run = scenarios or list(SCENARIOS.keys())
    results: list[dict[str, Any]] = []

    portfolio_total = sum(p.get("size_usd", 0) for p in positions)

    for scenario_name in scenarios_to_run:
        if scenario_name not in SCENARIOS:
            continue

        scenario_moves = SCENARIOS[scenario_name]
        position_results: list[dict[str, Any]] = []
        total_pnl = 0.0

        for position in positions:
            symbol = position.get("symbol", "UNKNOWN")
            size_usd = float(position.get("size_usd", 0))
            direction = position.get("direction", "LONG").upper()

            move = _get_scenario_move(symbol, scenario_moves)
            if direction == "SHORT":
                move = -move  # short profits from price down

            pnl_usd = size_usd * move
            total_pnl += pnl_usd

            position_results.append({
                "symbol": symbol,
                "direction": direction,
                "size_usd": size_usd,
                "price_move_pct": round(move * 100, 2),
                "pnl_usd": round(pnl_usd, 2),
            })

        position_results.sort(key=lambda x: x["pnl_usd"])
        total_pnl_pct = (total_pnl / portfolio_total * 100) if portfolio_total > 0 else 0.0

        results.append({
            "scenario": scenario_name,
            "total_pnl_usd": round(total_pnl, 2),
            "total_pnl_pct": round(total_pnl_pct, 2),
            "worst_position": position_results[0] if position_results else None,
            "best_position": position_results[-1] if position_results else None,
            "position_details": position_results,
        })

    # Find worst case
    results.sort(key=lambda x: x["total_pnl_usd"])
    worst = results[0] if results else None

    return {
        "results": results,
        "worst_case_scenario": worst["scenario"] if worst else None,
        "worst_case_loss_usd": worst["total_pnl_usd"] if worst else 0.0,
        "worst_case_loss_pct": worst["total_pnl_pct"] if worst else 0.0,
        "portfolio_total_usd": round(portfolio_total, 2),
        "positions_analyzed": len(positions),
        "scenarios_run": len(results),
        "available_scenarios": list(SCENARIOS.keys()),
    }


def _get_scenario_move(symbol: str, scenario_moves: dict[str, float]) -> float:
    """Get price move for a symbol in a given scenario.

    Args:
        symbol: Trading pair symbol (e.g. BTCUSDT)
        scenario_moves: Scenario move dict

    Returns:
        Expected price move as decimal (e.g. -0.30 = -30%)
    """
    # Check for "all" key (correlation spike scenario)
    if "all" in scenario_moves:
        return scenario_moves["all"]

    # Try direct match (strip USDT)
    base = _SYMBOL_MAPPING.get(symbol, symbol.replace("USDT", "").replace("PERP", ""))
    if base in scenario_moves:
        return scenario_moves[base]

    # Use alts default
    return scenario_moves.get("alts_default", -0.25)
