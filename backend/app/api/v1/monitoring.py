"""Celery task monitoring and system observability endpoints."""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.logging import get_logger

router = APIRouter(tags=["monitoring"])
logger = get_logger(__name__)


@router.get("/monitoring/tasks")
async def get_celery_task_status() -> dict[str, Any]:
    """Get status of all Celery scheduled tasks.

    Returns the static beat-schedule configuration — task name, human-readable
    schedule description and a brief description of what each task does.
    Live last-run timestamps are not available without a Celery result backend
    query; this endpoint provides the canonical schedule for observability dashboards.

    Returns:
        Dict with ``tasks`` list and ``total`` count.
    """
    tasks: list[dict[str, str]] = [
        {
            "name": "generate_signals",
            "schedule": "every 30 seconds",
            "description": "AI signal generation",
        },
        {
            "name": "update_market_regime",
            "schedule": "every 5 minutes",
            "description": "Market regime update",
        },
        {
            "name": "send_signal_notifications",
            "schedule": "every 1 minute",
            "description": "Telegram/Discord alerts",
        },
        {
            "name": "update_paper_trading",
            "schedule": "every 1 minute",
            "description": "Paper trading P&L update",
        },
        {
            "name": "cleanup_expired_signals",
            "schedule": "daily at 03:00 UTC",
            "description": "Signal cleanup — archives terminal signals older than 30 days",
        },
    ]
    return {"tasks": tasks, "total": len(tasks)}


@router.get("/monitoring/health/detailed")
async def get_detailed_health() -> dict[str, Any]:
    """Detailed health check including all subsystems.

    Inspects the trading agent running state and the number of active
    orderflow engines.  Returns ``"ok"`` status when reachable; individual
    subsystem errors are caught and reported without raising HTTP errors so
    that monitoring systems receive a partial health picture rather than a 500.

    Returns:
        Dict with ``status`` and nested ``subsystems`` dict.
    """
    subsystems: dict[str, Any] = {}

    # --- Trading Agent ---
    try:
        from app.ai.agent.trading_agent import get_trading_agent

        agent = get_trading_agent()
        subsystems["trading_agent"] = {
            "running": getattr(agent, "_running", False),
        }
    except Exception as exc:
        logger.warning("Could not inspect trading agent: %s", exc)
        subsystems["trading_agent"] = {"running": False, "error": str(exc)}

    # --- Orderflow Engines ---
    try:
        from app.data.fetchers.orderflow_engine import get_orderflow_manager

        of_manager = get_orderflow_manager()
        subsystems["orderflow_engines"] = {
            "count": len(of_manager.list_engines()),
        }
    except Exception as exc:
        logger.warning("Could not inspect orderflow manager: %s", exc)
        subsystems["orderflow_engines"] = {"count": 0, "error": str(exc)}

    return {
        "status": "ok",
        "subsystems": subsystems,
    }


class FrontendError(BaseModel):
    """Single frontend error event."""

    message: str
    stack: str | None = None
    url: str = ""
    component: str | None = None
    extra: dict[str, Any] | None = None


class FrontendErrorBatch(BaseModel):
    """Batch of frontend errors from the browser."""

    errors: list[FrontendError]


@router.post("/monitoring/frontend-errors")
async def record_frontend_errors(body: FrontendErrorBatch) -> dict[str, int]:
    """Receive and log browser-side JavaScript errors.

    The frontend installs window.onerror and unhandledrejection handlers that
    batch errors and POST them here, making JS errors visible in the unified
    server log stream.

    Returns:
        Dict with ``logged`` count.
    """
    now = datetime.now(timezone.utc).isoformat()
    for err in body.errors:
        logger.error(
            "[FRONTEND] %s | url=%s component=%s | %s | ts=%s",
            err.message,
            err.url,
            err.component or "unknown",
            (err.stack or "").split("\n")[0],
            now,
        )
    return {"logged": len(body.errors)}
