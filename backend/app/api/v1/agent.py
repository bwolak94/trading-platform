"""API endpoints for the AI Trading Agent."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.agent.trading_agent import get_trading_agent
from app.core.database import get_db
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


@router.get("/divergence-check")
async def check_strategy_divergence(db: AsyncSession = Depends(get_db)) -> dict:
    """Compare live paper trading performance vs backtested baseline for each strategy.

    For each strategy that has at least one BacktestResult and an active BotSession:
    - Fetches the latest BacktestResult (win_rate, sharpe_ratio).
    - Fetches metrics from the most recent active BotSession.
    - Calculates percentage divergence between backtest and live values.
    - Flags any metric where divergence exceeds 20%.

    Returns:
        Dict with ``divergences`` list, each entry containing:
        ``strategy``, ``metric``, ``backtest_value``, ``live_value``,
        ``divergence_pct``, ``is_warning``.
    """
    from app.models.backtest_result import BacktestResult
    from app.models.bot_session import BotSession

    # --- Fetch latest backtest results per strategy ---
    bt_result = await db.execute(
        select(BacktestResult).order_by(desc(BacktestResult.created_at))
    )
    all_backtests = bt_result.scalars().all()

    # Keep only the most recent backtest per strategy name
    latest_backtest: dict[str, BacktestResult] = {}
    for bt in all_backtests:
        if bt.strategy_name not in latest_backtest:
            latest_backtest[bt.strategy_name] = bt

    # --- Fetch the most recent active BotSession for live metrics ---
    session_result = await db.execute(
        select(BotSession)
        .where(BotSession.is_active == True)  # noqa: E712
        .order_by(desc(BotSession.started_at))
        .limit(1)
    )
    live_session = session_result.scalar_one_or_none()

    divergences: list[dict] = []

    if not latest_backtest:
        return {"divergences": divergences, "note": "No backtest results found"}

    if live_session is None:
        return {"divergences": divergences, "note": "No active bot session found"}

    live_win_rate = float(live_session.win_rate) if live_session.win_rate is not None else None
    live_sharpe = float(live_session.sharpe_ratio) if live_session.sharpe_ratio is not None else None

    for strategy_name, bt in latest_backtest.items():
        # --- win_rate comparison ---
        bt_win_rate = float(bt.win_rate) if bt.win_rate is not None else None
        if bt_win_rate is not None and live_win_rate is not None and bt_win_rate > 0:
            div_pct = abs(live_win_rate - bt_win_rate) / bt_win_rate * 100
            divergences.append({
                "strategy": strategy_name,
                "metric": "win_rate",
                "backtest_value": round(bt_win_rate, 4),
                "live_value": round(live_win_rate, 4),
                "divergence_pct": round(div_pct, 2),
                "is_warning": div_pct > 20.0,
            })

        # --- sharpe_ratio comparison ---
        bt_sharpe = float(bt.sharpe_ratio) if bt.sharpe_ratio is not None else None
        if bt_sharpe is not None and live_sharpe is not None and abs(bt_sharpe) > 0:
            div_pct = abs(live_sharpe - bt_sharpe) / abs(bt_sharpe) * 100
            divergences.append({
                "strategy": strategy_name,
                "metric": "sharpe_ratio",
                "backtest_value": round(bt_sharpe, 4),
                "live_value": round(live_sharpe, 4),
                "divergence_pct": round(div_pct, 2),
                "is_warning": div_pct > 20.0,
            })

    # Sort warnings to the top, then by divergence percentage descending
    divergences.sort(key=lambda d: (-int(d["is_warning"]), -d["divergence_pct"]))

    return {"divergences": divergences}
