"""Celery task monitoring and system observability endpoints."""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.logging import get_logger

router = APIRouter(tags=["monitoring"])
logger = get_logger(__name__)


@router.get("/monitoring/tasks")
async def get_celery_task_status() -> dict[str, Any]:
    """Get status of all Celery scheduled tasks.

    Pulls the live beat-schedule configuration from the Celery app so this
    endpoint never drifts out of sync with tasks.py.

    Returns:
        Dict with ``tasks`` list and ``total`` count.
    """
    from app.tasks import celery_app

    beat_schedule = celery_app.conf.beat_schedule or {}
    tasks: list[dict[str, Any]] = []

    for job_id, job_cfg in beat_schedule.items():
        schedule = job_cfg.get("schedule")
        # Convert numeric seconds to a human-readable string
        if isinstance(schedule, (int, float)):
            secs = int(schedule)
            if secs < 60:
                schedule_str = f"every {secs} seconds"
            elif secs < 3600:
                schedule_str = f"every {secs // 60} minutes"
            else:
                schedule_str = f"every {secs // 3600} hours"
        else:
            schedule_str = str(schedule)

        tasks.append({
            "id": job_id,
            "task": job_cfg.get("task", ""),
            "schedule": schedule_str,
            "expires": job_cfg.get("options", {}).get("expires"),
        })

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


@router.get("/monitoring/health/deep")
async def get_deep_health() -> dict[str, Any]:
    """Deep dependency health check — pings DB, Redis, Binance, and Telegram.

    Each dependency is checked independently; failures are reported without
    raising HTTP errors so monitoring systems receive a full picture.

    Returns:
        Dict with overall ``status`` (``ok`` | ``degraded`` | ``down``) and
        per-dependency ``checks`` map including latency_ms.
    """
    import time
    import httpx

    checks: dict[str, Any] = {}

    # --- Database ---
    t0 = time.monotonic()
    try:
        from app.core.database import async_session
        from sqlalchemy import text

        async with async_session() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = {"status": "ok", "latency_ms": round((time.monotonic() - t0) * 1000)}
    except Exception as exc:
        checks["database"] = {"status": "error", "error": str(exc), "latency_ms": -1}

    # --- Redis ---
    t0 = time.monotonic()
    try:
        import redis as _redis
        from app.core.config import settings as _settings

        r = _redis.from_url(_settings.REDIS_URL, decode_responses=True)
        r.ping()
        checks["redis"] = {"status": "ok", "latency_ms": round((time.monotonic() - t0) * 1000)}
    except Exception as exc:
        checks["redis"] = {"status": "error", "error": str(exc), "latency_ms": -1}

    # --- Binance API ---
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get("https://api.binance.com/api/v3/ping")
            resp.raise_for_status()
        checks["binance"] = {"status": "ok", "latency_ms": round((time.monotonic() - t0) * 1000)}
    except Exception as exc:
        checks["binance"] = {"status": "error", "error": str(exc), "latency_ms": -1}

    # --- Telegram Bot ---
    t0 = time.monotonic()
    try:
        from app.notifications.telegram_bot import get_telegram_bot

        bot = get_telegram_bot()
        is_running = bot is not None and getattr(bot, "_running", False)
        checks["telegram"] = {
            "status": "ok" if is_running else "degraded",
            "bot_running": is_running,
            "latency_ms": round((time.monotonic() - t0) * 1000),
        }
    except Exception as exc:
        checks["telegram"] = {"status": "error", "error": str(exc), "latency_ms": -1}

    # --- Overall status ---
    statuses = {c["status"] for c in checks.values()}
    if all(s == "ok" for s in statuses):
        overall = "ok"
    elif "error" in statuses:
        overall = "degraded"
    else:
        overall = "degraded"

    return {
        "status": overall,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
    }


@router.get("/monitoring/tasks/{task_id}")
async def get_task_status(task_id: str) -> dict[str, Any]:
    """E7: Get status and result of a specific Celery task by ID.

    Returns task state (PENDING, STARTED, SUCCESS, FAILURE, RETRY) along with
    progress percentage and result/error when available.  Useful for polling
    long-running backtest tasks from the frontend.

    Args:
        task_id: Celery task UUID returned by a task dispatch endpoint.

    Returns:
        Dict with ``task_id``, ``status``, ``progress_pct``, and optional
        ``result`` or ``error`` fields.
    """
    try:
        from celery.result import AsyncResult
        from app.tasks import celery_app

        result: AsyncResult = AsyncResult(task_id, app=celery_app)
        state = result.state

        response: dict[str, Any] = {
            "task_id": task_id,
            "status": state,
            "progress_pct": 0,
        }

        if state == "PENDING":
            response["progress_pct"] = 0
        elif state == "STARTED":
            meta = result.info or {}
            response["progress_pct"] = meta.get("progress_pct", 10)
        elif state == "SUCCESS":
            response["progress_pct"] = 100
            response["result"] = result.result
        elif state == "FAILURE":
            response["progress_pct"] = 0
            response["error"] = str(result.result)
        elif state == "RETRY":
            meta = result.info or {}
            response["progress_pct"] = meta.get("progress_pct", 5)

        return response
    except Exception as exc:
        logger.warning("get_task_status failed for %s: %s", task_id, exc)
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")


@router.get("/monitoring/rate-limits")
async def get_rate_limit_status() -> dict[str, Any]:
    """E1: Expose Binance API weight consumption and platform rate-limit state.

    Returns remaining Binance API weight (if obtainable), plus a warning flag
    when consumption exceeds 80 % of the per-minute limit.

    Returns:
        Dict with ``binance_weight_used``, ``binance_weight_limit``,
        ``warning`` flag, and ``timestamp``.
    """
    import httpx

    result: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "binance_weight_used": None,
        "binance_weight_limit": 1200,
        "warning": False,
    }

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get("https://api.binance.com/api/v3/ping")
            used_raw = resp.headers.get("X-MBX-USED-WEIGHT-1M")
            if used_raw is not None:
                used = int(used_raw)
                result["binance_weight_used"] = used
                result["warning"] = used >= 960  # 80 % of 1 200
    except Exception as exc:
        logger.debug("Rate limit status check failed: %s", exc)

    return result


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
