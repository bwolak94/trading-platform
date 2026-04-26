"""FastAPI application entry point."""

import asyncio
import random
import time as _time
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager
from urllib.parse import parse_qs, urlencode

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.api.v1 import agent, analyze, backtest, chat, intelligence, market, notifications, pro_analysis, settings, signals, simulation, strategy_params
from app.api.v1.watchlist import router as watchlist_router
from app.api.v1.webhook_settings import router as webhook_settings_router
from app.api.v1.webhooks import router as webhooks_router
from app.api.v1.signal_quality import router as signal_quality_router
from app.api.v1.risk_advanced import router as risk_advanced_router
from app.api.v1.market_intelligence import router as market_intelligence_router
from app.api.v1.analytics import router as analytics_router
from app.api.v1.automation import router as automation_router
from app.api.v1.monitoring import router as monitoring_router
from app.api.v1.mtf_matrix import router as mtf_matrix_router
from app.api.v1.benchmark import router as benchmark_router
from app.api.v1.earnings import router as earnings_router
from app.ai.signals.regime_transition import router as regime_transition_router
from app.ai.signals.liquidation_cascade import router as liquidation_cascade_router
from app.ai.risk.drawdown_budget import router as drawdown_budget_router
from app.api.v1.features import router as features_router
from app.api.v1.features2 import router as features2_router
from app.api.v1.multi_exchange import router as multi_exchange_router
from app.api.v1.oi_momentum import router as oi_momentum_router
from app.api.v1.dark_pool import router as dark_pool_router
from app.api.v1.ai_commentary import router as ai_commentary_router
from app.api.v1.news_backtester import router as news_backtester_router
from app.api.v1.futures_testnet import router as futures_testnet_router
from app.core.config import settings as app_settings
from app.core.exceptions import (
    DataFetchError,
    InsufficientDataError,
    KillSwitchActiveError,
    RateLimitError,
    TradingPlatformError,
)
from app.core.logging import get_logger, set_request_id
from app.core.websocket import manager

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    logger.info("AI Trading Navigator starting up")

    # Enforce production security — raises RuntimeError on insecure defaults
    app_settings.enforce_production_security()

    # Load all Binance USDT perpetual futures symbols dynamically
    from app.core.symbols import load_dynamic_symbols
    try:
        loaded_symbols = await load_dynamic_symbols()
        logger.info("Loaded %d dynamic futures symbols from Binance", len(loaded_symbols))
    except Exception as exc:
        logger.warning("Failed to load dynamic symbols, falling back to static list: %s", exc)

    # Validate production configuration
    prod_warnings = app_settings.validate_production()
    for w in prod_warnings:
        logger.warning("CONFIG WARNING: %s", w)

    # Start Order Flow engines for default symbols
    from app.data.fetchers.orderflow_engine import get_orderflow_manager

    of_manager = get_orderflow_manager()
    default_symbols = [
        ("BTCUSDT", 1.0, 60),
        ("ETHUSDT", 1.0, 60),
        ("SOLUSDT", 0.1, 60),
    ]
    for symbol, tick_size, window_sec in default_symbols:
        try:
            await of_manager.start_engine(
                symbol=symbol,
                tick_size=tick_size,
                window_seconds=window_sec,
            )
        except Exception as exc:
            logger.warning(
                "Failed to start OrderFlowEngine for %s: %s", symbol, exc,
            )

    logger.info("Order Flow engines started for %s", list(of_manager.list_engines().keys()))

    # Start Liquidation Engine (single engine covers all symbols via !forceOrder@arr)
    from app.data.fetchers.liquidation_engine import get_liquidation_manager

    liq_manager = get_liquidation_manager()
    try:
        await liq_manager.start()
        logger.info("Liquidation engine started")
    except Exception as exc:
        logger.warning("Failed to start LiquidationEngine: %s", exc)

    # Start AI Trading Agent
    from app.ai.agent.trading_agent import get_trading_agent

    trading_agent = get_trading_agent()
    try:
        await trading_agent.start()
        logger.info("AI Trading Agent started")
    except Exception as exc:
        logger.warning("Failed to start TradingAgent: %s", exc)

    # Start Day Trading Engine
    from app.ai.agent.day_trading import get_day_trading_engine

    day_trading_engine = get_day_trading_engine()
    try:
        await day_trading_engine.start()
        logger.info("Day Trading Engine started")
    except Exception as exc:
        logger.warning("Failed to start DayTradingEngine: %s", exc)

    # Start Forex Provider
    from app.data.fetchers.forex_provider import get_forex_provider

    forex_provider = get_forex_provider()
    try:
        await forex_provider.start()
        logger.info("Forex Provider started")
    except Exception as exc:
        logger.warning("Failed to start ForexProvider: %s", exc)

    # Start News Aggregator
    from app.data.fetchers.news_aggregator import get_news_aggregator

    news_aggregator = get_news_aggregator()
    try:
        await news_aggregator.start()
        logger.info("News Aggregator started")
    except Exception as exc:
        logger.warning("Failed to start NewsAggregator: %s", exc)

    # Start Whale Tracker
    from app.data.fetchers.whale_tracker import get_whale_tracker

    whale_tracker = get_whale_tracker()
    try:
        await whale_tracker.start()
        logger.info("Whale Tracker started")
    except Exception as exc:
        logger.warning("Failed to start WhaleTracker: %s", exc)

    # Start Paper Trading Simulation Engine
    from app.ai.simulation.paper_trading_engine import get_paper_trading_engine

    paper_engine = get_paper_trading_engine()
    try:
        await paper_engine.start()
        logger.info("Paper Trading Engine started — session %s", paper_engine.session_id)
    except Exception as exc:
        logger.warning("Failed to start PaperTradingEngine: %s", exc)

    # Start APScheduler for periodic report jobs
    from app.ai.reports.daily_briefing import generate_and_send_daily_briefing
    from app.ai.reports.weekly_report import generate_weekly_report

    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        generate_and_send_daily_briefing,
        "cron",
        hour=0,
        minute=0,
        id="daily_briefing",
        misfire_grace_time=300,
    )
    scheduler.add_job(
        generate_weekly_report,
        "cron",
        day_of_week="mon",
        hour=8,
        minute=0,
        id="weekly_report",
        misfire_grace_time=300,
    )
    try:
        scheduler.start()
        logger.info("APScheduler started — daily_briefing at 00:00 UTC, weekly_report on Mon 08:00 UTC")
    except Exception as exc:
        logger.warning("Failed to start APScheduler: %s", exc)

    yield

    # Shutdown APScheduler
    logger.info("Shutting down APScheduler...")
    try:
        scheduler.shutdown(wait=False)
    except Exception as exc:
        logger.warning("APScheduler shutdown error: %s", exc)

    # Shutdown Paper Trading Engine
    logger.info("Shutting down Paper Trading Engine...")
    await paper_engine.stop()

    # Shutdown Whale Tracker
    logger.info("Shutting down Whale Tracker...")
    await whale_tracker.stop()

    # Shutdown News Aggregator
    logger.info("Shutting down News Aggregator...")
    await news_aggregator.stop()

    # Shutdown Forex Provider
    logger.info("Shutting down Forex Provider...")
    await forex_provider.stop()

    # Shutdown Day Trading Engine
    logger.info("Shutting down Day Trading Engine...")
    await day_trading_engine.stop()

    # Shutdown AI Trading Agent
    logger.info("Shutting down AI Trading Agent...")
    await trading_agent.stop()

    # Shutdown Liquidation Engine
    logger.info("Shutting down Liquidation engine...")
    await liq_manager.stop()

    # Shutdown Order Flow engines
    logger.info("Shutting down Order Flow engines...")
    await of_manager.stop_all()
    logger.info("AI Trading Navigator shutting down")


app = FastAPI(
    title="AI Trading Navigator",
    description="AI-powered market analysis and signal generation system",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware — validate origins before adding
_cors_origins = [o.strip() for o in app_settings.CORS_ORIGINS.split(",")]

if app_settings.ENVIRONMENT == "production" and "*" in _cors_origins:
    logger.warning(
        "CORS_ORIGINS contains wildcard '*' in production. "
        "Restricting to localhost origins only for safety."
    )
    _cors_origins = ["http://localhost:5173", "http://localhost:3000"]

app.add_middleware(GZipMiddleware, minimum_size=1000)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Correlation ID middleware
@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    """Attach a per-request correlation ID to every log line and response header.

    Reads X-Request-ID from the incoming request (e.g. set by a proxy/frontend),
    or generates a new UUID4. The ID is stored in a ContextVar so all loggers
    in the same async context automatically include it.
    """
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    set_request_id(request_id)
    response = await call_next(request)
    response.headers["x-request-id"] = request_id
    return response


# Rate limiting middleware
_rate_limits: dict[str, list[float]] = defaultdict(list)
EXPENSIVE_PATHS = {"/api/v1/analyze/run", "/api/v1/chat", "/api/v1/backtest/run"}


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Enforce per-IP rate limits: 10 req/min for expensive endpoints, 60 req/min otherwise."""
    client_ip = request.client.host if request.client else "unknown"
    path = request.url.path
    now = _time.time()
    key = f"{client_ip}:{path}"

    # Clean old entries
    _rate_limits[key] = [t for t in _rate_limits[key] if now - t < 60]

    limit = 10 if path in EXPENSIVE_PATHS else 60
    if len(_rate_limits[key]) >= limit:
        return JSONResponse(
            status_code=429,
            content={"error": "rate_limited", "detail": f"Max {limit} requests/minute"},
        )

    _rate_limits[key].append(now)
    return await call_next(request)


# --- Sensitive value masking for request logging ---

_SENSITIVE_HEADERS: frozenset[str] = frozenset({
    "authorization", "api_key", "token", "secret", "x-api-key",
})

_SENSITIVE_QUERY_PARAMS: frozenset[str] = frozenset({
    "api_key", "token", "secret",
})

_SENSITIVE_BODY_FIELDS: frozenset[str] = frozenset({
    "api_key", "token", "secret", "password", "authorization",
})

_MASKED = "***MASKED***"


def _mask_value(value: str) -> str:
    """Mask a sensitive value, keeping the first 4 chars if longer than 8."""
    if len(value) > 8:
        return value[:4] + _MASKED
    return _MASKED


def _mask_headers(headers: dict[str, str]) -> dict[str, str]:
    """Return a copy of headers with sensitive values masked."""
    return {
        k: _mask_value(v) if k.lower() in _SENSITIVE_HEADERS else v
        for k, v in headers.items()
    }


def _mask_query_string(query_string: str) -> str:
    """Return query string with sensitive parameter values masked."""
    if not query_string:
        return query_string
    parsed = parse_qs(query_string, keep_blank_values=True)
    masked: dict[str, list[str]] = {}
    for key, values in parsed.items():
        if key.lower() in _SENSITIVE_QUERY_PARAMS:
            masked[key] = [_mask_value(v) for v in values]
        else:
            masked[key] = values
    return urlencode(masked, doseq=True)


def _mask_body(body: dict[str, object]) -> dict[str, object]:
    """Return a copy of request body dict with sensitive fields masked."""
    return {
        k: _mask_value(str(v)) if k.lower() in _SENSITIVE_BODY_FIELDS else v
        for k, v in body.items()
    }


_API_VERSION = "0.1.0"

# Paths that get a hard 30 s server-side timeout — prevents ML endpoints from hanging
_TIMEOUT_PATHS = {"/api/v1/analyze/run", "/api/v1/chat", "/api/v1/backtest/run"}

# Paths sampled at 1 % to keep logs quiet
_SAMPLED_PATHS = {"/api/v1/health", "/api/v1/status"}


# Request logging + version header + timeout middleware
@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    """Log requests, attach X-API-Version header, enforce timeouts on expensive paths."""
    start = _time.time()
    path = request.url.path

    # Per-endpoint timeout for expensive ML routes
    if path in _TIMEOUT_PATHS:
        try:
            response = await asyncio.wait_for(call_next(request), timeout=30.0)
        except asyncio.TimeoutError:
            return JSONResponse(
                status_code=504,
                content={"error": "gateway_timeout", "detail": "Request exceeded 30 s timeout"},
            )
    else:
        response = await call_next(request)

    duration = round((_time.time() - start) * 1000, 1)

    # Attach version header to every response
    response.headers["x-api-version"] = _API_VERSION

    # Log at 1 % for sampled paths, always for the rest (skip health entirely at 99 %)
    if path not in _SAMPLED_PATHS or random.random() < 0.01:
        masked_qs = _mask_query_string(request.url.query or "")
        safe_path = f"{path}?{masked_qs}" if masked_qs else path
        logger.info(
            '{"method":"%s","path":"%s","status":%d,"duration_ms":%.1f}',
            request.method, safe_path, response.status_code, duration,
        )
    return response


# Error handling middleware
@app.middleware("http")
async def error_handling_middleware(request: Request, call_next):
    """Catch unhandled exceptions and return structured JSON errors."""
    try:
        return await call_next(request)
    except Exception as exc:
        logger.exception("Unhandled error: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"error": "internal_server_error", "detail": str(exc)},
        )


# Custom exception handlers for TradingPlatformError hierarchy
_ERROR_STATUS_MAP: dict[type, int] = {
    DataFetchError: 502,
    InsufficientDataError: 422,
    KillSwitchActiveError: 503,
    RateLimitError: 429,
}


@app.exception_handler(TradingPlatformError)
async def trading_platform_error_handler(request: Request, exc: TradingPlatformError) -> JSONResponse:
    """Return structured JSON responses for all TradingPlatformError subclasses."""
    status_code = _ERROR_STATUS_MAP.get(type(exc), 500)

    body: dict[str, object] = {
        "error": exc.error_code,
        "detail": exc.message,
    }

    # Include retry_after header and field for rate-limit errors
    headers: dict[str, str] = {}
    if isinstance(exc, RateLimitError):
        body["retry_after"] = exc.retry_after
        headers["Retry-After"] = str(int(exc.retry_after))

    if isinstance(exc, DataFetchError):
        body["source"] = exc.source

    if isinstance(exc, InsufficientDataError):
        body["required"] = exc.required
        body["available"] = exc.available

    logger.warning(
        "TradingPlatformError handled",
        extra={"error_code": exc.error_code, "status": status_code, "path": request.url.path},
    )

    return JSONResponse(status_code=status_code, content=body, headers=headers)


# API routers
app.include_router(agent.router, prefix="/api/v1")
app.include_router(signals.router, prefix="/api/v1")
app.include_router(market.router, prefix="/api/v1")
app.include_router(backtest.router, prefix="/api/v1")
app.include_router(settings.router, prefix="/api/v1")
app.include_router(analyze.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")
app.include_router(intelligence.router, prefix="/api/v1")
app.include_router(pro_analysis.router, prefix="/api/v1")
app.include_router(strategy_params.router, prefix="/api/v1")
app.include_router(simulation.router, prefix="/api/v1")
app.include_router(notifications.router, prefix="/api/v1")
app.include_router(watchlist_router, prefix="/api/v1")
app.include_router(webhook_settings_router, prefix="/api/v1")
app.include_router(signal_quality_router, prefix="/api/v1")
app.include_router(risk_advanced_router, prefix="/api/v1")
app.include_router(market_intelligence_router, prefix="/api/v1")
app.include_router(analytics_router, prefix="/api/v1")
app.include_router(automation_router, prefix="/api/v1")
app.include_router(monitoring_router, prefix="/api/v1")
app.include_router(mtf_matrix_router, prefix="/api/v1")
app.include_router(benchmark_router, prefix="/api/v1")
app.include_router(earnings_router, prefix="/api/v1")
app.include_router(regime_transition_router, prefix="/api/v1")
app.include_router(liquidation_cascade_router, prefix="/api/v1")
app.include_router(drawdown_budget_router, prefix="/api/v1")
app.include_router(features_router, prefix="/api/v1")
app.include_router(features2_router, prefix="/api/v1")
app.include_router(futures_testnet_router, prefix="/api/v1")
app.include_router(multi_exchange_router, prefix="/api/v1")
app.include_router(oi_momentum_router, prefix="/api/v1")
app.include_router(dark_pool_router, prefix="/api/v1")
app.include_router(ai_commentary_router, prefix="/api/v1")
app.include_router(news_backtester_router, prefix="/api/v1")


# Health & status
@app.get("/api/v1/health")
async def health_check() -> dict:
    """Health check endpoint."""
    return {"status": "ok", "version": "0.1.0"}


@app.get("/api/v1/status")
async def system_status() -> dict:
    """System status including drawdown and active connections."""
    return {
        "status": "ok",
        "websocket_clients": manager.active_count,
        "system_status": "ACTIVE",
        "drawdown_pct": 0.0,
    }


# --- Auth token endpoint ---

class _TokenRequest(BaseModel):
    """Request body for the token endpoint."""
    username: str
    password: str


class _TokenResponse(BaseModel):
    """Response body for the token endpoint."""
    access_token: str
    token_type: str = "bearer"


@app.post("/api/v1/auth/token", response_model=_TokenResponse)
async def login_for_access_token(body: _TokenRequest) -> _TokenResponse:
    """Issue a JWT access token after validating credentials.

    Credentials are checked against ADMIN_USERNAME / ADMIN_PASSWORD env vars.
    This is a simple, single-user auth suitable for MVP / dev usage.
    """
    if (
        body.username != app_settings.ADMIN_USERNAME
        or body.password != app_settings.ADMIN_PASSWORD
    ):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    from app.core.auth import create_access_token

    token = create_access_token(data={"sub": body.username, "role": "admin"})
    return _TokenResponse(access_token=token)


# WebSocket
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time signal/regime/sentiment updates."""
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action")
            channels = data.get("channels", [])

            if action == "subscribe":
                manager.subscribe(websocket, channels)
                await manager.send_personal(
                    websocket, {"type": "SUBSCRIBED", "channels": channels}
                )
            elif action == "unsubscribe":
                manager.unsubscribe(websocket, channels)
                await manager.send_personal(
                    websocket, {"type": "UNSUBSCRIBED", "channels": channels}
                )
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)
