"""Advanced Risk Management API — Kelly, EV filter, drawdown, stress test, RoR."""

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

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
