"""Automation API — scanner, playbook, XAI explainer, and champion/challenger."""

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

router = APIRouter(prefix="/automation", tags=["automation"])


class PlaybookRequest(BaseModel):
    """Request body for playbook generation."""

    signal: dict
    current_price: float = Field(..., gt=0)
    atr_value: float = Field(default=0.0, ge=0.0)


class XAIRequest(BaseModel):
    """Request body for XAI signal explanation."""

    signal: dict


class AttributionRequest(BaseModel):
    """Request body for performance attribution."""

    trades: list[dict]


@router.get("/scanner/top-setups")
async def get_top_setups(
    top_n: int = Query(default=5, ge=1, le=20),
) -> dict:
    """Scan all active assets and surface top long/short setups."""
    from app.ai.automation.asset_scanner import scan_all_assets
    return await scan_all_assets(top_n=top_n)


@router.post("/playbook")
async def generate_playbook(body: PlaybookRequest) -> dict:
    """Generate a complete trade playbook with entry, SL, TPs, and checklist."""
    from app.ai.automation.playbook_generator import generate_playbook
    return generate_playbook(
        signal=body.signal,
        current_price=body.current_price,
        atr_value=body.atr_value,
    )


@router.post("/xai-explain")
async def xai_explain(body: XAIRequest) -> dict:
    """Generate XAI feature importance report for a signal."""
    from app.ai.automation.xai_explainer import get_shap_like_report
    return get_shap_like_report(signal=body.signal)


@router.post("/attribution")
async def performance_attribution(body: AttributionRequest) -> dict:
    """Compute multi-dimensional performance attribution across strategies and regimes."""
    from app.ai.automation.performance_attribution import attribute_performance
    return attribute_performance(trades=body.trades)


# --- Champion/Challenger ---

class ExperimentRequest(BaseModel):
    """Request body for creating a champion/challenger experiment."""

    experiment_id: str
    champion_params: dict
    challenger_params: dict
    strategy_name: str
    duration_days: int = Field(default=30, ge=1, le=180)
    traffic_split: float = Field(default=0.5, ge=0.1, le=0.9)


class ExperimentResultRequest(BaseModel):
    """Request body for recording an experiment result."""

    experiment_id: str
    variant: str  # champion | challenger
    pnl_r: float
    win: bool


@router.post("/experiments")
async def create_experiment(body: ExperimentRequest) -> dict:
    """Create a champion/challenger A/B test for strategy parameters."""
    from app.ai.automation.champion_challenger import get_champion_challenger
    return get_champion_challenger().create_experiment(
        experiment_id=body.experiment_id,
        champion_params=body.champion_params,
        challenger_params=body.challenger_params,
        strategy_name=body.strategy_name,
        duration_days=body.duration_days,
        traffic_split=body.traffic_split,
    )


@router.get("/experiments")
async def list_experiments() -> dict:
    """List all champion/challenger experiments with evaluation results."""
    from app.ai.automation.champion_challenger import get_champion_challenger
    return {"experiments": get_champion_challenger().get_all_experiments()}


@router.get("/experiments/{experiment_id}/evaluate")
async def evaluate_experiment(experiment_id: str) -> dict:
    """Evaluate statistical significance of an experiment."""
    from app.ai.automation.champion_challenger import get_champion_challenger
    return get_champion_challenger().evaluate_experiment(experiment_id)


@router.post("/experiments/{experiment_id}/promote")
async def promote_challenger(experiment_id: str) -> dict:
    """Promote the challenger to champion, ending the experiment."""
    from app.ai.automation.champion_challenger import get_champion_challenger
    return get_champion_challenger().promote_challenger(experiment_id)


# --- Alert Engine ---

class AlertRuleRequest(BaseModel):
    """Request body for creating an alert rule."""

    rule_id: str
    name: str
    condition_type: str
    operator: str
    threshold: float
    symbol: str
    channels: list[str] = Field(default_factory=lambda: ["telegram"])
    description: str = ""


@router.get("/alert-rules")
async def list_alert_rules() -> dict:
    """List all registered alert rules."""
    from app.ai.automation.alert_engine import get_alert_engine
    return {"rules": get_alert_engine().get_rules()}


@router.post("/alert-rules")
async def create_alert_rule(body: AlertRuleRequest) -> dict:
    """Create a new dynamic alert rule."""
    from app.ai.automation.alert_engine import AlertRule, get_alert_engine
    rule = AlertRule(
        rule_id=body.rule_id,
        name=body.name,
        condition_type=body.condition_type,
        operator=body.operator,
        threshold=body.threshold,
        symbol=body.symbol,
        channels=body.channels,
        description=body.description,
    )
    get_alert_engine().add_rule(rule)
    return {"status": "created", "rule_id": body.rule_id}


@router.delete("/alert-rules/{rule_id}")
async def delete_alert_rule(rule_id: str) -> dict:
    """Remove an alert rule by ID."""
    from app.ai.automation.alert_engine import get_alert_engine
    removed = get_alert_engine().remove_rule(rule_id)
    return {"status": "removed" if removed else "not_found", "rule_id": rule_id}


# --- Post-Mortem ---

class PostMortemRequest(BaseModel):
    """Request body for trade post-mortem analysis."""

    entry_price: float = Field(..., gt=0)
    exit_price: float = Field(..., gt=0)
    direction: str
    stop_loss: float = Field(..., gt=0)
    take_profit: float = Field(..., gt=0)
    entry_time: str
    exit_time: str
    signal_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    regime_at_entry: str = "UNKNOWN"
    strategy_name: str = "unknown"


@router.post("/post-mortem")
async def analyze_trade_postmortem(body: PostMortemRequest) -> dict:
    """Generate AI post-mortem analysis for a completed trade."""
    from app.ai.automation.trade_postmortem import analyze_trade
    return analyze_trade(
        entry_price=body.entry_price,
        exit_price=body.exit_price,
        direction=body.direction,
        stop_loss=body.stop_loss,
        take_profit=body.take_profit,
        entry_time=body.entry_time,
        exit_time=body.exit_time,
        signal_confidence=body.signal_confidence,
        regime_at_entry=body.regime_at_entry,
        strategy_name=body.strategy_name,
    )


# --- Roles ---

@router.get("/roles")
async def get_role_summary() -> dict:
    """Get role-based permission summary."""
    from app.auth.roles import get_session_manager
    return get_session_manager().get_role_summary()


@router.get("/sessions")
async def get_active_sessions() -> dict:
    """Get all active user sessions (admin view)."""
    from app.auth.roles import get_session_manager
    return {"sessions": get_session_manager().get_active_sessions()}
