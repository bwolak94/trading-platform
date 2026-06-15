"""Advanced Risk Management API — Kelly, EV filter, drawdown, stress test, RoR, VaR."""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db

router = APIRouter(prefix="/risk", tags=["risk-advanced"])


class KellySizeRequest(BaseModel):
    """Request body for Kelly position sizing."""

    account_equity: float = Field(..., gt=0, description="Account equity in USD")
    win_rate: float = Field(..., ge=0.0, le=1.0)
    avg_win_r: float = Field(..., gt=0)
    avg_loss_r: float = Field(..., gt=0)
    kelly_fraction: float = Field(default=0.25, gt=0, le=1.0)
    max_risk_pct: float = Field(default=2.0, gt=0, le=10.0)


class CorrelationRequest(BaseModel):
    """Request body for portfolio correlation analysis."""

    symbols: list[str] = Field(..., min_length=2)
    interval: str = "1d"
    lookback: int = Field(default=60, ge=20, le=365)


class VolSizeRequest(BaseModel):
    """Request body for volatility-scaled position sizing."""

    symbol: str
    account_equity: float = Field(..., gt=0)
    risk_pct: float = Field(default=1.0, gt=0, le=5.0)
    atr_period: int = Field(default=14, ge=5, le=50)
    interval: str = "1h"


class EVFilterRequest(BaseModel):
    """Request body for EV filter."""

    signal: dict
    min_ev: float = Field(default=0.3)
    strategy_stats: dict | None = None


class FeeImpactRequest(BaseModel):
    """Request body for fee impact calculation."""

    position_size_usd: float = Field(..., gt=0)
    entry_price: float = Field(..., gt=0)
    target_price: float = Field(..., gt=0)
    stop_price: float = Field(..., gt=0)
    exchange: str = "binance"
    order_type: str = "taker"
    estimated_slippage_pct: float = Field(default=0.05, ge=0.0, le=1.0)


class StressTestRequest(BaseModel):
    """Request body for stress test."""

    positions: list[dict]
    scenarios: list[str] | None = None


class RiskOfRuinRequest(BaseModel):
    """Request body for risk of ruin calculation."""

    win_rate: float = Field(..., ge=0.0, le=1.0)
    avg_win_r: float = Field(..., gt=0)
    avg_loss_r: float = Field(..., gt=0)
    risk_per_trade_pct: float = Field(..., gt=0, le=10.0)
    ruin_threshold_pct: float = Field(default=50.0, gt=10.0, le=90.0)
    num_simulations: int = Field(default=5000, ge=1000, le=50000)


@router.get("/kelly-stats")
async def get_kelly_stats() -> dict:
    """Get current Kelly criterion statistics from trade history."""
    from app.ai.risk.kelly_criterion import get_kelly_criterion
    return get_kelly_criterion().get_current_stats()


@router.post("/kelly-size")
async def compute_kelly_size(body: KellySizeRequest) -> dict:
    """Compute optimal position size using fractional Kelly criterion."""
    from app.ai.risk.kelly_criterion import get_kelly_criterion
    kelly = get_kelly_criterion()
    return kelly.compute_position_size(
        account_equity=body.account_equity,
        win_rate=body.win_rate,
        avg_win_r=body.avg_win_r,
        avg_loss_r=body.avg_loss_r,
        kelly_fraction=body.kelly_fraction,
        max_risk_pct=body.max_risk_pct,
    )


@router.get("/drawdown-status")
async def get_drawdown_status() -> dict:
    """Get current drawdown waterfall status and active tier."""
    from app.ai.risk.drawdown_waterfall import get_drawdown_waterfall
    return get_drawdown_waterfall().get_state()


@router.post("/ev-filter")
async def ev_filter(body: EVFilterRequest) -> dict:
    """Filter a signal by Expected Value (EV)."""
    from app.ai.risk.ev_filter import filter_signal_by_ev
    return filter_signal_by_ev(
        signal=body.signal,
        min_ev=body.min_ev,
        strategy_stats=body.strategy_stats,
    )


@router.post("/fee-impact")
async def compute_fee_impact(body: FeeImpactRequest) -> dict:
    """Compute round-trip fees and slippage impact on a trade."""
    from app.ai.risk.fee_impact import compute_fee_impact
    return compute_fee_impact(
        position_size_usd=body.position_size_usd,
        entry_price=body.entry_price,
        target_price=body.target_price,
        stop_price=body.stop_price,
        exchange=body.exchange,
        order_type=body.order_type,
        estimated_slippage_pct=body.estimated_slippage_pct,
    )


@router.post("/stress-test")
async def run_stress_test(body: StressTestRequest) -> dict:
    """Run portfolio stress test across multiple adverse scenarios."""
    from app.ai.risk.stress_tester import run_stress_test
    return await run_stress_test(
        positions=body.positions,
        scenarios=body.scenarios,
    )


@router.get("/stress")
async def get_stress_test(
    scenarios: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get stress test results for current paper trading positions (GET alias)."""
    from datetime import datetime, timezone

    from sqlalchemy import select

    from app.ai.risk.stress_tester import run_stress_test
    from app.models.simulated_position import SimulatedPosition

    result = await db.execute(
        select(SimulatedPosition).where(SimulatedPosition.status == "OPEN").limit(20)
    )
    open_positions = result.scalars().all()
    positions = [
        {
            "symbol": p.symbol,
            "direction": p.direction,
            "entry_price": float(p.entry_price or 0),
            "current_price": float(p.entry_price or 0),
            "size_usd": float(getattr(p, "position_size_usdt", 100)),
        }
        for p in open_positions
    ]
    scenario_list = scenarios.split(",") if scenarios else None
    try:
        return await run_stress_test(positions=positions, scenarios=scenario_list)
    except Exception:
        return {
            "scenarios": [],
            "portfolio_value": 0.0,
            "last_run": datetime.now(timezone.utc).isoformat(),
        }


@router.post("/stress")
async def run_stress_test_alias(body: StressTestRequest) -> dict:
    """Alias for /stress-test (POST)."""
    from app.ai.risk.stress_tester import run_stress_test
    return await run_stress_test(
        positions=body.positions,
        scenarios=body.scenarios,
    )


@router.post("/risk-of-ruin")
async def compute_risk_of_ruin(body: RiskOfRuinRequest) -> dict:
    """Compute risk of ruin probability via Monte Carlo simulation."""
    from app.ai.risk.risk_of_ruin import compute_risk_of_ruin
    return compute_risk_of_ruin(
        win_rate=body.win_rate,
        avg_win_r=body.avg_win_r,
        avg_loss_r=body.avg_loss_r,
        risk_per_trade_pct=body.risk_per_trade_pct,
        ruin_threshold_pct=body.ruin_threshold_pct,
        num_simulations=body.num_simulations,
    )

@router.get("/drawdown-tiers")
async def get_drawdown_tiers() -> dict:
    """Get the drawdown waterfall tier definitions."""
    from app.ai.risk.drawdown_waterfall import DRAWDOWN_TIERS
    return {"tiers": DRAWDOWN_TIERS}


@router.get("/var")
async def get_value_at_risk(
    confidence: float = Query(default=0.95, ge=0.5, le=0.999, description="Confidence level for VaR"),
    lookback_days: int = Query(default=30, ge=1, le=365, description="Number of days to look back"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get VaR and CVaR for the current paper trading portfolio.

    Fetches recent closed simulated positions from the database, derives per-trade
    percentage returns and feeds them to the RiskEngine's portfolio VaR calculation.

    Returns:
        Dict with ``var_95``, ``cvar_95``, ``var_99``, ``cvar_99`` and ``confidence``.
    """
    from datetime import datetime, timedelta, timezone

    from app.ai.risk.engine import RiskEngine
    from app.models.simulated_position import SimulatedPosition

    risk_engine = RiskEngine()
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)

    result = await db.execute(
        select(SimulatedPosition)
        .where(
            SimulatedPosition.status != "OPEN",
            SimulatedPosition.pnl_pct.isnot(None),
            SimulatedPosition.closed_at >= cutoff,
        )
        .order_by(desc(SimulatedPosition.closed_at))
    )
    closed_positions = result.scalars().all()

    if not closed_positions:
        return {
            "var_95": 0.0,
            "cvar_95": 0.0,
            "var_99": 0.0,
            "cvar_99": 0.0,
            "confidence": confidence,
            "sample_size": 0,
            "lookback_days": lookback_days,
        }

    # Build position dicts expected by calculate_portfolio_var
    position_dicts = [
        {"returns": [float(pos.pnl_pct)]}
        for pos in closed_positions
    ]

    var_result = risk_engine.calculate_portfolio_var(position_dicts, confidence=confidence)

    return {
        **var_result,
        "confidence": confidence,
        "sample_size": len(closed_positions),
        "lookback_days": lookback_days,
    }
