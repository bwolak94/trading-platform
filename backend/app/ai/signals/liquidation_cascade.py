"""Liquidation cascade prediction model.

Models cascading liquidations: if price moves X%, how much OI gets liquidated,
which may trigger further price moves (reflexive cascade).

The model steps through price in 1% increments up to 10% in both directions,
accumulating liquidations at each level. A simple cascade multiplier is applied
when liquidations exceed 1% of open interest (large liquidations cause slippage
and trigger more stop-outs).
"""

from typing import Any

from fastapi import APIRouter

# Cascade multiplier thresholds
_CASCADE_TRIGGER_PCT_OF_OI = 0.01   # 1% of OI liquidated → cascade kicks in
_FULL_CASCADE_PCT_OF_OI = 0.05      # 5% of OI → severe cascade


def _severity_label(pct_of_oi: float) -> str:
    """Return severity label based on percentage of OI liquidated."""
    if pct_of_oi >= 0.10:
        return "EXTREME"
    elif pct_of_oi >= 0.05:
        return "HIGH"
    elif pct_of_oi >= 0.02:
        return "MEDIUM"
    return "LOW"


def _calculate_cascade_multiplier(pct_of_oi: float) -> float:
    """Estimate reflexive cascade multiplier.

    When liquidations are large relative to OI, they create additional selling/buying
    pressure that triggers more liquidations. This is a simple power-law model.

    Returns a multiplier >= 1.0.
    """
    if pct_of_oi < _CASCADE_TRIGGER_PCT_OF_OI:
        return 1.0
    # Multiplier grows as sqrt of the ratio above the threshold
    ratio = pct_of_oi / _CASCADE_TRIGGER_PCT_OF_OI
    multiplier = 1.0 + 0.5 * (ratio ** 0.5 - 1)
    return round(min(3.0, multiplier), 3)


def predict_cascade(
    symbol: str,
    current_price: float,
    liquidation_levels: list[dict[str, Any]],
    open_interest_usd: float,
) -> dict[str, Any]:
    """Model liquidation cascade scenarios.

    For each 1% price move (down and up, up to 10%), calculates:
    - Total liquidations triggered (USD)
    - Cascade multiplier (reflexive amplification)
    - Percentage of OI liquidated
    - Severity label

    Args:
        symbol: Ticker symbol (for context only).
        current_price: Current market price in USD.
        liquidation_levels: List of dicts with keys:
            - price (float): liquidation trigger price
            - amount_usd (float): USD value of positions liquidated at this price
            - side (str): "LONG" or "SHORT"
        open_interest_usd: Total open interest in USD (for relative sizing).

    Returns:
        {
            "symbol": str,
            "current_price": float,
            "open_interest_usd": float,
            "scenarios": [
                {
                    "price_move_pct": float,
                    "target_price": float,
                    "direction": "DOWN" | "UP",
                    "liquidations_usd": float,
                    "cascade_multiplier": float,
                    "effective_liquidations_usd": float,
                    "pct_of_oi": float,
                    "severity": str,
                }
            ],
            "nearest_cascade_level": float | None,
            "cascade_probability_24h": float,
            "downside_risk_pct": float,
            "upside_risk_pct": float,
        }
    """
    if open_interest_usd <= 0:
        open_interest_usd = 1.0  # avoid division by zero

    scenarios: list[dict[str, Any]] = []
    nearest_cascade_level: float | None = None
    nearest_cascade_dist = float("inf")

    for pct in range(1, 11):
        for direction, sign in [("DOWN", -1), ("UP", 1)]:
            price_move = pct * sign
            target_price = current_price * (1 + price_move / 100)

            # Accumulate liquidations hit between current_price and target_price
            liquidations_usd = 0.0
            for level in liquidation_levels:
                liq_price = float(level.get("price", 0))
                amount = float(level.get("amount_usd", 0))
                side = str(level.get("side", "")).upper()

                if direction == "DOWN":
                    # LONGs get liquidated as price falls
                    if side == "LONG" and target_price <= liq_price <= current_price:
                        liquidations_usd += amount
                else:
                    # SHORTs get liquidated as price rises
                    if side == "SHORT" and current_price <= liq_price <= target_price:
                        liquidations_usd += amount

            pct_of_oi = liquidations_usd / open_interest_usd
            multiplier = _calculate_cascade_multiplier(pct_of_oi)
            effective_liq = liquidations_usd * multiplier
            effective_pct = effective_liq / open_interest_usd
            severity = _severity_label(effective_pct)

            # Track nearest cascade trigger point
            if pct_of_oi >= _CASCADE_TRIGGER_PCT_OF_OI:
                dist = abs(target_price - current_price)
                if dist < nearest_cascade_dist:
                    nearest_cascade_dist = dist
                    nearest_cascade_level = target_price

            scenarios.append({
                "price_move_pct": float(price_move),
                "target_price": round(target_price, 6),
                "direction": direction,
                "liquidations_usd": round(liquidations_usd, 2),
                "cascade_multiplier": multiplier,
                "effective_liquidations_usd": round(effective_liq, 2),
                "pct_of_oi": round(effective_pct, 4),
                "severity": severity,
            })

    # Sort by absolute price move
    scenarios.sort(key=lambda x: abs(x["price_move_pct"]))

    # Estimate 24h cascade probability based on how many severe scenarios exist
    severe_count = sum(
        1 for s in scenarios if s["severity"] in ("HIGH", "EXTREME")
    )
    cascade_probability_24h = round(min(0.95, severe_count * 0.07), 4)

    # Summarise directional risks
    down_scenarios = [s for s in scenarios if s["direction"] == "DOWN"]
    up_scenarios = [s for s in scenarios if s["direction"] == "UP"]

    downside_risk_pct = max(
        (s["pct_of_oi"] for s in down_scenarios), default=0.0
    )
    upside_risk_pct = max(
        (s["pct_of_oi"] for s in up_scenarios), default=0.0
    )

    return {
        "symbol": symbol,
        "current_price": current_price,
        "open_interest_usd": open_interest_usd,
        "scenarios": scenarios,
        "nearest_cascade_level": nearest_cascade_level,
        "cascade_probability_24h": cascade_probability_24h,
        "downside_risk_pct": round(downside_risk_pct, 4),
        "upside_risk_pct": round(upside_risk_pct, 4),
        "total_scenarios": len(scenarios),
    }


# ---------------------------------------------------------------------------
# FastAPI router
# ---------------------------------------------------------------------------

router = APIRouter(tags=["liquidations"])


@router.get("/market/liquidation-cascade/{symbol}")
async def get_liquidation_cascade_prediction(symbol: str) -> dict[str, Any]:
    """Get liquidation cascade prediction for a symbol.

    Fetches live liquidation level data and OI from the liquidation engine,
    then runs the cascade model.
    """
    from app.data.fetchers.liquidation_engine import get_liquidation_manager

    symbol_upper = symbol.upper()
    liq_manager = get_liquidation_manager()

    # Attempt to get live data from the liquidation engine
    current_price = 0.0
    liquidation_levels: list[dict[str, Any]] = []
    open_interest_usd = 100_000_000.0  # 100M default if unavailable

    try:
        engine_data = liq_manager.get_liquidation_levels(symbol_upper)
        if engine_data:
            current_price = float(engine_data.get("current_price", 0))
            liquidation_levels = engine_data.get("levels", [])
            open_interest_usd = float(engine_data.get("open_interest_usd", open_interest_usd))
    except Exception:
        pass

    # If no price from engine, try to fetch from a market data store
    if current_price <= 0:
        try:
            from app.data.fetchers.binance_client import get_binance_client
            client = get_binance_client()
            ticker = await client.get_ticker_price(symbol_upper)
            current_price = float(ticker.get("price", 0))
        except Exception:
            current_price = 0.0

    if current_price <= 0:
        return {
            "symbol": symbol_upper,
            "error": "Could not determine current price for cascade analysis",
            "scenarios": [],
            "nearest_cascade_level": None,
            "cascade_probability_24h": 0.0,
        }

    return predict_cascade(
        symbol=symbol_upper,
        current_price=current_price,
        liquidation_levels=liquidation_levels,
        open_interest_usd=open_interest_usd,
    )
