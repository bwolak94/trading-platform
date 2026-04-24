"""Simulation API — paper trading engine control and data endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.simulation.paper_trading_engine import get_paper_trading_engine
from app.core.database import async_session, get_db
from app.core.logging import get_logger

router = APIRouter(prefix="/simulation", tags=["simulation"])
logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Hardcoded pairwise correlation matrix for common crypto pairs.
# Keys are always in canonical order (alphabetically first symbol first).
# ---------------------------------------------------------------------------
CRYPTO_CORRELATIONS: dict[tuple[str, str], float] = {
    ("BTCUSDT", "ETHUSDT"): 0.94,
    ("BTCUSDT", "SOLUSDT"): 0.88,
    ("BTCUSDT", "BNBUSDT"): 0.82,
    ("BTCUSDT", "AVAXUSDT"): 0.85,
    ("ETHUSDT", "SOLUSDT"): 0.87,
    ("ETHUSDT", "BNBUSDT"): 0.80,
    ("ETHUSDT", "AVAXUSDT"): 0.83,
    ("ETHUSDT", "UNIUSDT"): 0.86,
    ("BTCUSDT", "XRPUSDT"): 0.72,
    ("BTCUSDT", "DOGEUSDT"): 0.75,
}


def _lookup_correlation(symbol_a: str, symbol_b: str) -> float | None:
    """Return the known correlation between two symbols, or None if unknown.

    The lookup is symmetric — order does not matter.
    """
    pair = tuple(sorted([symbol_a.upper(), symbol_b.upper()]))
    return CRYPTO_CORRELATIONS.get(pair)  # type: ignore[arg-type]


@router.get("/positions")
async def get_open_positions() -> dict[str, Any]:
    """Return all currently open paper trading positions with live PnL."""
    engine = get_paper_trading_engine()
    return {
        "positions": engine.get_open_positions(),
        "count": engine.position_manager.open_count,
        "session_id": engine.session_id,
        "is_running": engine.is_running,
    }


@router.get("/positions/closed")
async def get_closed_positions(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """Return paginated closed positions from the database."""
    from app.models.simulated_position import SimulatedPosition

    async with async_session() as session:
        total_q = await session.execute(
            select(SimulatedPosition).where(SimulatedPosition.status != "OPEN")
        )
        total = len(total_q.scalars().all())

        result = await session.execute(
            select(SimulatedPosition)
            .where(SimulatedPosition.status != "OPEN")
            .order_by(desc(SimulatedPosition.closed_at))
            .limit(limit)
            .offset(offset)
        )
        rows = result.scalars().all()

    positions = [
        {
            "id": str(r.id),
            "symbol": r.symbol,
            "direction": r.direction,
            "strategy": r.strategy,
            "regime": r.regime,
            "confidence": r.confidence,
            "entry_price": float(r.entry_price),
            "stop_loss": float(r.stop_loss),
            "take_profit_1": float(r.take_profit_1),
            "take_profit_2": float(r.take_profit_2) if r.take_profit_2 else None,
            "take_profit_3": float(r.take_profit_3) if r.take_profit_3 else None,
            "current_price": float(r.current_price) if r.current_price else None,
            "exit_price": float(r.exit_price) if r.exit_price else None,
            "pnl_pct": float(r.pnl_pct),
            "status": r.status,
            "exit_reason": r.exit_reason,
            "opened_at": r.opened_at.isoformat() if r.opened_at else None,
            "closed_at": r.closed_at.isoformat() if r.closed_at else None,
            "mae_pct": float(r.mae_pct) if r.mae_pct is not None else None,
            "mfe_pct": float(r.mfe_pct) if r.mfe_pct is not None else None,
            "tags": r.tags or [],
            "notes": r.notes or "",
        }
        for r in rows
    ]

    return {"positions": positions, "total": total, "limit": limit, "offset": offset}


@router.get("/performance")
async def get_performance() -> dict[str, Any]:
    """Return live performance metrics for the current simulation session."""
    engine = get_paper_trading_engine()
    return engine.get_performance()


@router.get("/performance/history")
async def get_session_history(limit: int = Query(default=10, ge=1, le=50)) -> dict[str, Any]:
    """Return past bot session performance summaries."""
    from app.models.bot_session import BotSession

    async with async_session() as session:
        result = await session.execute(
            select(BotSession)
            .order_by(desc(BotSession.started_at))
            .limit(limit)
        )
        rows = result.scalars().all()

    sessions = [
        {
            "id": str(r.id),
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "ended_at": r.ended_at.isoformat() if r.ended_at else None,
            "is_active": r.is_active,
            "total_trades": r.total_trades,
            "winning_trades": r.winning_trades,
            "total_pnl_pct": float(r.total_pnl_pct),
            "max_drawdown_pct": float(r.max_drawdown_pct),
            "sharpe_ratio": float(r.sharpe_ratio) if r.sharpe_ratio else None,
            "win_rate": float(r.win_rate),
        }
        for r in rows
    ]

    return {"sessions": sessions}


@router.post("/start")
async def start_simulation() -> dict[str, str]:
    """Start the paper trading simulation engine."""
    engine = get_paper_trading_engine()
    if engine.is_running:
        raise HTTPException(status_code=400, detail="Simulation engine is already running")
    await engine.start()
    return {"status": "started", "session_id": engine.session_id}


@router.post("/stop")
async def stop_simulation() -> dict[str, str]:
    """Stop the paper trading simulation engine."""
    engine = get_paper_trading_engine()
    if not engine.is_running:
        raise HTTPException(status_code=400, detail="Simulation engine is not running")
    await engine.stop()
    return {"status": "stopped"}


# ------------------------------------------------------------------ #
# Enhanced paper trading — manual positions + leverage + funding       #
# ------------------------------------------------------------------ #

class ManualPositionRequest(BaseModel):
    symbol: str
    direction: str
    entry_price: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float | None = None
    take_profit_3: float | None = None
    strategy: str = "manual"
    leverage: float = 1.0
    position_size_usdt: float = 100.0


@router.post("/position/manual")
async def open_manual_position(req: ManualPositionRequest) -> dict[str, Any]:
    """Open a manual paper trading position with leverage and fee simulation.

    This is the entry point for Option B enhanced paper trading — you control
    the exact entry, SL, TP, leverage, and position size.
    """
    engine = get_paper_trading_engine()
    try:
        pos = await engine.open_manual_position(
            symbol=req.symbol,
            direction=req.direction,
            entry_price=req.entry_price,
            stop_loss=req.stop_loss,
            take_profit_1=req.take_profit_1,
            take_profit_2=req.take_profit_2,
            take_profit_3=req.take_profit_3,
            strategy=req.strategy,
            leverage=req.leverage,
            position_size_usdt=req.position_size_usdt,
        )
        return {"status": "opened", "position": pos}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


class DefaultsRequest(BaseModel):
    leverage: float
    position_size_usdt: float


@router.post("/defaults")
async def set_paper_defaults(req: DefaultsRequest) -> dict[str, Any]:
    """Update default leverage and position size for auto-scanned positions."""
    engine = get_paper_trading_engine()
    engine.set_defaults(req.leverage, req.position_size_usdt)
    return {
        "status": "updated",
        "leverage": req.leverage,
        "position_size_usdt": req.position_size_usdt,
    }


@router.get("/funding-history")
async def get_funding_history(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, Any]:
    """Return recent funding rate charges applied to leveraged paper positions."""
    engine = get_paper_trading_engine()
    return {"history": engine.get_funding_history(limit)}


@router.post("/position/{position_id}/close")
async def close_paper_position(position_id: str) -> dict[str, Any]:
    """Manually close an open paper trading position at the current price."""
    import uuid as _uuid
    engine = get_paper_trading_engine()
    try:
        pos_uuid = _uuid.UUID(position_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid position ID")

    pos = engine.position_manager._open_positions.get(pos_uuid)
    if not pos:
        raise HTTPException(status_code=404, detail="Position not found or already closed")

    current_price = pos.current_price or pos.entry_price
    closed = engine.position_manager.close_position(pos_uuid, current_price, "MANUAL_CLOSE")
    if closed:
        engine.performance_tracker.record_close(closed)
        engine.risk_engine.record_trade(closed.pnl_pct)
        await engine._persist_position_close(closed)
        await engine._broadcast_position_update(closed, "closed")
        return {"status": "closed", "position": engine._pos_to_dict(closed)}
    raise HTTPException(status_code=500, detail="Failed to close position")


@router.get("/status")
async def get_simulation_status() -> dict[str, Any]:
    """Return engine status, open position count, and live performance."""
    engine = get_paper_trading_engine()
    return {
        "is_running": engine.is_running,
        "session_id": engine.session_id,
        "open_positions": engine.position_manager.open_count,
        "max_positions": engine.position_manager.max_positions,
        "performance": engine.get_performance(),
    }


@router.get("/equity-curve")
async def get_equity_curve() -> dict[str, Any]:
    """Return the equity curve for the current session (one point per closed trade)."""
    engine = get_paper_trading_engine()
    return {
        "equity_curve": engine.performance_tracker.equity_curve,
        "session_id": engine.session_id,
        "is_running": engine.is_running,
    }


@router.get("/strategy-heatmap")
async def get_strategy_heatmap() -> dict[str, Any]:
    """2D heatmap: strategies × regimes → win rate.

    Returns a matrix where rows=strategies, cols=regimes, values=win_rate (0-1).
    """
    from app.models.simulated_position import SimulatedPosition

    async with async_session() as session:
        result = await session.execute(
            select(SimulatedPosition).where(SimulatedPosition.status != "OPEN")
        )
        rows = result.scalars().all()

    # Build strategy × regime win rate matrix
    from collections import defaultdict
    stats: dict[str, dict[str, dict]] = defaultdict(lambda: defaultdict(lambda: {"wins": 0, "total": 0}))

    for r in rows:
        regime = r.regime or "UNKNOWN"
        strategy = r.strategy or "unknown"
        cell = stats[strategy][regime]
        cell["total"] += 1
        if r.pnl_pct and float(r.pnl_pct) > 0:
            cell["wins"] += 1

    # Convert to serializable format
    heatmap: list[dict] = []
    for strategy, regimes in stats.items():
        for regime, data in regimes.items():
            win_rate = data["wins"] / data["total"] if data["total"] > 0 else 0.0
            heatmap.append({
                "strategy": strategy,
                "regime": regime,
                "win_rate": round(win_rate, 3),
                "total_trades": data["total"],
                "wins": data["wins"],
            })

    # Collect unique strategies and regimes for axes
    strategies = sorted({h["strategy"] for h in heatmap})
    regimes = sorted({h["regime"] for h in heatmap})

    return {
        "heatmap": heatmap,
        "strategies": strategies,
        "regimes": regimes,
        "total_positions": len(rows),
    }


@router.get("/attribution")
async def get_attribution() -> dict[str, Any]:
    """PnL attribution analysis — breakdown by strategy, regime, and symbol.

    Returns grouped sums of PnL and trade counts for each dimension.
    """
    from app.models.simulated_position import SimulatedPosition
    from collections import defaultdict

    async with async_session() as session:
        result = await session.execute(
            select(SimulatedPosition).where(SimulatedPosition.status != "OPEN")
        )
        rows = result.scalars().all()

    def make_entry() -> dict:
        return {"total_pnl": 0.0, "trades": 0, "wins": 0}

    by_strategy: dict[str, dict] = defaultdict(make_entry)
    by_regime: dict[str, dict] = defaultdict(make_entry)
    by_symbol: dict[str, dict] = defaultdict(make_entry)

    for r in rows:
        pnl = float(r.pnl_pct) if r.pnl_pct else 0.0
        strategy = r.strategy or "unknown"
        regime = r.regime or "UNKNOWN"
        symbol = r.symbol or "UNKNOWN"
        is_win = pnl > 0

        for bucket, key in [(by_strategy, strategy), (by_regime, regime), (by_symbol, symbol)]:
            bucket[key]["total_pnl"] = round(bucket[key]["total_pnl"] + pnl, 4)
            bucket[key]["trades"] += 1
            bucket[key]["wins"] += int(is_win)

    def format_bucket(d: dict) -> list[dict]:
        return sorted(
            [
                {
                    "key": k,
                    "total_pnl": round(v["total_pnl"], 4),
                    "trades": v["trades"],
                    "win_rate": round(v["wins"] / v["trades"], 3) if v["trades"] else 0.0,
                }
                for k, v in d.items()
            ],
            key=lambda x: x["total_pnl"],
            reverse=True,
        )

    return {
        "by_strategy": format_bucket(by_strategy),
        "by_regime": format_bucket(by_regime),
        "by_symbol": format_bucket(by_symbol)[:20],  # top 20 symbols
        "total_closed_trades": len(rows),
    }


@router.get("/r-multiple")
async def get_r_multiple_distribution() -> dict[str, Any]:
    """R-Multiple distribution for all closed trades.

    R-multiple = (exit - entry) / (entry - stop_loss) for LONG positions.
    Shows how many times risk was won or lost.
    """
    from app.models.simulated_position import SimulatedPosition

    async with async_session() as session:
        result = await session.execute(
            select(SimulatedPosition).where(SimulatedPosition.status != "OPEN")
        )
        rows = result.scalars().all()

    r_multiples: list[float] = []
    for r in rows:
        if not r.exit_price or not r.entry_price or not r.stop_loss:
            continue
        entry = float(r.entry_price)
        exit_p = float(r.exit_price)
        sl = float(r.stop_loss)
        risk = abs(entry - sl)
        if risk < 1e-10:
            continue
        if r.direction == "LONG":
            r_mult = (exit_p - entry) / risk
        else:
            r_mult = (entry - exit_p) / risk
        r_multiples.append(round(r_mult, 2))

    if not r_multiples:
        return {"distribution": [], "avg_r": 0.0, "expectancy": 0.0, "total_trades": 0}

    # Build histogram buckets: -3R to +5R in 0.5 steps
    from collections import Counter
    def bucket_r(r: float) -> float:
        return round(round(r / 0.5) * 0.5, 1)  # round to nearest 0.5

    counts = Counter(bucket_r(r) for r in r_multiples)
    distribution = sorted(
        [{"r": k, "count": v} for k, v in counts.items()],
        key=lambda x: x["r"],
    )

    avg_r = sum(r_multiples) / len(r_multiples)
    wins = [r for r in r_multiples if r > 0]
    losses = [r for r in r_multiples if r <= 0]
    win_rate = len(wins) / len(r_multiples) if r_multiples else 0
    avg_win_r = sum(wins) / len(wins) if wins else 0
    avg_loss_r = abs(sum(losses) / len(losses)) if losses else 1
    expectancy = (win_rate * avg_win_r) - ((1 - win_rate) * avg_loss_r)

    return {
        "distribution": distribution,
        "avg_r": round(avg_r, 3),
        "expectancy": round(expectancy, 3),
        "win_rate": round(win_rate, 3),
        "avg_win_r": round(avg_win_r, 3),
        "avg_loss_r": round(avg_loss_r, 3),
        "total_trades": len(r_multiples),
    }


@router.get("/risk-state")
async def get_risk_state() -> dict[str, Any]:
    """Return the current risk engine state (circuit breakers, streaks, PnL limits)."""
    from app.ai.risk.risk_engine import get_risk_engine
    return get_risk_engine().get_state()


@router.get("/filters")
async def get_filter_state() -> dict[str, Any]:
    """Return current symbol filters (blacklist, whitelist, cooldowns)."""
    engine = get_paper_trading_engine()
    return engine.get_filter_state()


@router.post("/blacklist/{symbol}")
async def blacklist_symbol(symbol: str) -> dict[str, str]:
    """Manually blacklist a symbol from being traded."""
    engine = get_paper_trading_engine()
    engine.blacklist_symbol(symbol.upper())
    return {"status": "blacklisted", "symbol": symbol.upper()}


@router.delete("/blacklist/{symbol}")
async def remove_from_blacklist(symbol: str) -> dict[str, str]:
    """Remove a symbol from the manual blacklist."""
    engine = get_paper_trading_engine()
    engine._symbol_blacklist.discard(symbol.upper())
    return {"status": "removed", "symbol": symbol.upper()}


@router.post("/trigger-daily-briefing")
async def trigger_daily_briefing() -> dict[str, Any]:
    """Manually trigger the daily briefing report (normally runs at 00:00 UTC)."""
    from app.ai.reports.daily_briefing import generate_and_send_daily_briefing
    return await generate_and_send_daily_briefing()


@router.get("/trade-duration")
async def get_trade_duration_distribution() -> dict[str, Any]:
    """Trade duration distribution histogram by strategy."""
    from app.models.simulated_position import SimulatedPosition

    async with async_session() as db:
        result = await db.execute(
            select(SimulatedPosition).where(
                SimulatedPosition.status == "closed",
                SimulatedPosition.closed_at.isnot(None),
                SimulatedPosition.opened_at.isnot(None),
            )
        )
        positions = result.scalars().all()

    # Build duration buckets: <1h, 1-4h, 4-12h, 12-24h, 1-3d, >3d
    buckets = ["<1h", "1-4h", "4-12h", "12-24h", "1-3d", ">3d"]
    by_strategy: dict[str, dict[str, int]] = {}

    for pos in positions:
        duration_h = (pos.closed_at - pos.opened_at).total_seconds() / 3600
        strategy = pos.strategy or "unknown"
        if strategy not in by_strategy:
            by_strategy[strategy] = {b: 0 for b in buckets}

        if duration_h < 1:
            bucket = "<1h"
        elif duration_h < 4:
            bucket = "1-4h"
        elif duration_h < 12:
            bucket = "4-12h"
        elif duration_h < 24:
            bucket = "12-24h"
        elif duration_h < 72:
            bucket = "1-3d"
        else:
            bucket = ">3d"
        by_strategy[strategy][bucket] += 1

    return {
        "buckets": buckets,
        "by_strategy": by_strategy,
    }


@router.get("/monte-carlo-var")
async def get_monte_carlo_var(
    simulations: int = 1000,
    horizon: int = 20,
) -> dict[str, Any]:
    """Monte Carlo VaR from closed trade returns.

    Runs bootstrap Monte Carlo simulation over closed paper trading returns
    to estimate Value at Risk at 95% and 99% confidence for a forward horizon.
    """
    from app.models.simulated_position import SimulatedPosition
    from app.ai.backtesting.walk_forward import monte_carlo_var

    async with async_session() as db:
        result = await db.execute(
            select(SimulatedPosition.pnl_pct).where(
                SimulatedPosition.status == "closed",
                SimulatedPosition.pnl_pct.isnot(None),
            )
        )
        returns = [float(r) for r in result.scalars().all()]

    if not returns:
        return {"error": "No closed trades yet"}

    return monte_carlo_var(returns, simulations=simulations, horizon=horizon)


@router.get("/entry-timing-heatmap")
async def get_entry_timing_heatmap() -> dict[str, Any]:
    """Win rate by hour-of-day and day-of-week matrix."""
    from app.models.simulated_position import SimulatedPosition

    async with async_session() as db:
        result = await db.execute(
            select(SimulatedPosition).where(
                SimulatedPosition.status == "closed",
                SimulatedPosition.opened_at.isnot(None),
            )
        )
        positions = result.scalars().all()

    # Matrix: 24 hours × 7 days
    wins = [[0] * 7 for _ in range(24)]
    totals = [[0] * 7 for _ in range(24)]

    for pos in positions:
        h = pos.opened_at.hour
        d = pos.opened_at.weekday()  # 0=Mon, 6=Sun
        totals[h][d] += 1
        if (pos.pnl_pct or 0) > 0:
            wins[h][d] += 1

    matrix = []
    for h in range(24):
        for d in range(7):
            t = totals[h][d]
            w = wins[h][d]
            matrix.append({
                "hour": h,
                "day": d,
                "win_rate": round(w / t, 3) if t > 0 else None,
                "total_trades": t,
            })

    return {
        "matrix": matrix,
        "days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    }


@router.get("/ab-tests")
async def get_ab_tests() -> dict[str, Any]:
    """Return results for all registered A/B tests."""
    from app.ai.backtesting.ab_testing import get_all_ab_tests

    return {"tests": get_all_ab_tests()}


@router.post("/ab-tests")
async def create_ab_test_endpoint(body: dict[str, Any]) -> dict[str, str]:
    """Create a new A/B test for strategy parameter comparison."""
    import uuid

    from app.ai.backtesting.ab_testing import create_ab_test

    if "strategy_name" not in body:
        raise HTTPException(status_code=400, detail="strategy_name is required")

    test = create_ab_test(
        test_id=body.get("test_id", str(uuid.uuid4())),
        strategy_name=body["strategy_name"],
        description=body.get("description", ""),
        control_params=body.get("control_params", {}),
        treatment_params=body.get("treatment_params", {}),
        min_trades=body.get("min_trades", 50),
    )
    return {"status": "ok", "test_id": test.test_id}


@router.get("/ab-tests/{test_id}")
async def get_ab_test(test_id: str) -> dict[str, Any]:
    """Return results for a specific A/B test."""
    from app.ai.backtesting.ab_testing import get_ab_test_results

    result = get_ab_test_results(test_id)
    if not result:
        raise HTTPException(status_code=404, detail="Test not found")
    return result


@router.patch("/positions/{position_id}/notes")
async def update_position_notes(
    position_id: int,
    body: dict[str, Any],
) -> dict[str, str]:
    """Update tags and notes for a closed position (trade journal)."""
    from app.models.simulated_position import SimulatedPosition

    async with async_session() as db:
        result = await db.execute(
            select(SimulatedPosition).where(SimulatedPosition.id == position_id)
        )
        pos = result.scalar_one_or_none()
        if not pos:
            raise HTTPException(status_code=404, detail="Position not found")

        if "tags" in body:
            pos.tags = body["tags"]
        if "notes" in body:
            pos.notes = body["notes"]

        await db.commit()

    return {"status": "ok"}


@router.get("/correlation-warning/{symbol}")
async def check_correlation_warning(
    symbol: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Check if a new signal in ``symbol`` would create high correlation with open positions.

    Queries all currently open simulated positions and cross-references each against
    the hardcoded ``CRYPTO_CORRELATIONS`` matrix.  Any open position whose pairwise
    correlation with the requested ``symbol`` exceeds 0.7 is included in the warnings list.

    Args:
        symbol: The normalised symbol for the prospective new signal (e.g. ``BTCUSDT``).
        db: Injected async database session.

    Returns:
        Dict with:
        - ``warnings``: list of dicts containing ``symbol``, ``correlation`` and ``direction``
          for each correlated open position.
        - ``max_correlation``: highest correlation found (0.0 if no open positions).
        - ``symbol``: the queried symbol (normalised to upper-case).
    """
    from app.models.simulated_position import SimulatedPosition

    normalised_symbol = symbol.upper()

    result = await db.execute(
        select(SimulatedPosition).where(SimulatedPosition.status == "OPEN")
    )
    open_positions = result.scalars().all()

    warnings: list[dict[str, Any]] = []
    for pos in open_positions:
        pos_symbol = (pos.symbol or "").upper()
        if pos_symbol == normalised_symbol:
            # Same symbol — skip self-correlation
            continue

        correlation = _lookup_correlation(normalised_symbol, pos_symbol)
        if correlation is not None and correlation > 0.7:
            warnings.append({
                "symbol": pos_symbol,
                "correlation": correlation,
                "direction": pos.direction or "UNKNOWN",
            })

    # Sort descending by correlation so the most correlated pair appears first
    warnings.sort(key=lambda w: w["correlation"], reverse=True)
    max_correlation = warnings[0]["correlation"] if warnings else 0.0

    return {
        "symbol": normalised_symbol,
        "warnings": warnings,
        "max_correlation": max_correlation,
    }
