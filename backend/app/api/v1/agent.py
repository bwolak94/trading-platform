"""API endpoints for the AI Trading Agent."""

import logging

from fastapi import APIRouter, HTTPException

from app.ai.agent.trading_agent import get_trading_agent
from app.schemas.market import TradeOutcomeRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["agent"])


@router.get("/signals")
async def get_signals() -> dict:
    """Return all active signals from the agent."""
    agent = get_trading_agent()
    return {"signals": agent.get_active_signals()}


@router.get("/status")
async def get_status() -> dict:
    """Return agent status (running, scan count, win rate, rewards, lessons)."""
    agent = get_trading_agent()
    return agent.get_status()


@router.post("/start")
async def start_agent() -> dict:
    """Start the agent scanning loop."""
    agent = get_trading_agent()
    if agent._running:
        return {"status": "already_running"}
    await agent.start()
    return {"status": "started"}


@router.post("/stop")
async def stop_agent() -> dict:
    """Stop the agent scanning loop."""
    agent = get_trading_agent()
    if not agent._running:
        return {"status": "already_stopped"}
    await agent.stop()
    return {"status": "stopped"}


@router.get("/history")
async def get_history() -> dict:
    """Return signal history."""
    agent = get_trading_agent()
    return {"history": agent.get_signal_history()}


@router.post("/outcome")
async def record_outcome(request: TradeOutcomeRequest) -> dict:
    """Record a trade outcome for learning."""
    agent = get_trading_agent()
    outcome = agent.record_outcome(request.symbol, request.exit_price, request.hit_level)
    if outcome is None:
        raise HTTPException(
            status_code=404,
            detail=f"No active signal found for {request.symbol}",
        )
    return {
        "symbol": request.symbol,
        "pnl_pct": outcome.pnl_pct,
        "reward": outcome.reward,
        "lessons": outcome.lessons,
    }


# --- Day Trading Endpoints ---

@router.get("/day-trading/signals")
async def get_day_trading_signals() -> dict:
    from app.ai.agent.day_trading import get_day_trading_engine
    engine = get_day_trading_engine()
    return {"signals": engine.get_active_signals()}

@router.get("/day-trading/status")
async def get_day_trading_status() -> dict:
    from app.ai.agent.day_trading import get_day_trading_engine
    engine = get_day_trading_engine()
    return engine.get_status()


@router.get("/learning")
async def get_learning_summary() -> dict:
    """Get the AI learning engine's full state — performance per strategy, multipliers, blocked combos."""
    from app.ai.agent.learning_engine import get_learning_engine
    return get_learning_engine().get_learning_summary()
