"""API endpoints for the AI Trading Agent."""

import logging

from fastapi import APIRouter, HTTPException

from app.ai.agent.trading_agent import get_trading_agent

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
async def record_outcome(
    symbol: str,
    exit_price: float,
    hit_level: str,
) -> dict:
    """Record a trade outcome for learning."""
    agent = get_trading_agent()
    outcome = agent.record_outcome(symbol, exit_price, hit_level)
    if outcome is None:
        raise HTTPException(
            status_code=404,
            detail=f"No active signal found for {symbol}",
        )
    return {
        "symbol": symbol,
        "pnl_pct": outcome.pnl_pct,
        "reward": outcome.reward,
        "lessons": outcome.lessons,
    }
