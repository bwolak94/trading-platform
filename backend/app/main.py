"""FastAPI application entry point."""

import uuid
from collections import defaultdict
from contextlib import asynccontextmanager
from urllib.parse import parse_qs, urlencode
import time as _time

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
from app.api.v1.extended_features import router as extended_features_router
from app.api.v1.multi_exchange import router as multi_exchange_router
from app.api.v1.oi_momentum import router as oi_momentum_router
from app.api.v1.dark_pool import router as dark_pool_router
from app.api.v1.ai_commentary import router as ai_commentary_router
from app.api.v1.news_backtester import router as news_backtester_router
from app.api.v1.futures_testnet import router as futures_testnet_router
from app.api.v1.stop_loss_optimizer import router as stop_loss_optimizer_router
from app.api.v1.trade_screener import router as trade_screener_router
from app.api.v1.ab_backtester import router as ab_backtester_router
from app.core.config import settings as app_settings
from app.core.exceptions import (
    DataFetchError,
    InsufficientDataError,
    KillSwitchActiveError,
    RateLimitError,
    TradingPlatformError,
)
from app.core.logging import get_logger, set_request_id
from app.core.startup import start_service, stop_service
from app.core.websocket import manager

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    logger.info("AI Trading Navigator starting up")

    # Wire OpenTelemetry tracing before any I/O
    from app.core.telemetry import setup_tracing
    setup_tracing(app)

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
    for w in app_settings.validate_production():
        logger.warning("CONFIG WARNING: %s", w)

    # Start Order Flow engines for default symbols
    from app.data.fetchers.orderflow_engine import get_orderflow_manager
    of_manager = get_orderflow_manager()
    for symbol, tick_size, window_sec in [
        ("BTCUSDT", 1.0, 60),
        ("ETHUSDT", 1.0, 60),
        ("SOLUSDT", 0.1, 60),
    ]:
        await start_service(
            f"OrderFlowEngine[{symbol}]",
            of_manager.start_engine(symbol=symbol, tick_size=tick_size, window_seconds=window_sec),
        )
    logger.info("Order Flow engines started for %s", list(of_manager.list_engines().keys()))

    # Start remaining background services
    from app.data.fetchers.liquidation_engine import get_liquidation_manager
    from app.ai.agent.trading_agent import get_trading_agent
    from app.ai.agent.day_trading import get_day_trading_engine
    from app.data.fetchers.forex_provider import get_forex_provider
    from app.data.fetchers.news_aggregator import get_news_aggregator
    from app.data.fetchers.whale_tracker import get_whale_tracker
    from app.ai.simulation.paper_trading_engine import get_paper_trading_engine

    liq_manager = get_liquidation_manager()
    trading_agent = get_trading_agent()
    day_trading_engine = get_day_trading_engine()
    forex_provider = get_forex_provider()
    news_aggregator = get_news_aggregator()
    whale_tracker = get_whale_tracker()
    paper_engine = get_paper_trading_engine()

    await start_service("LiquidationEngine", liq_manager.start())
    await start_service("TradingAgent", trading_agent.start())
    await start_service("DayTradingEngine", day_trading_engine.start())
    await start_service("ForexProvider", forex_provider.start())
    await start_service("NewsAggregator", news_aggregator.start())
    await start_service("WhaleTracker", whale_tracker.start())
    await start_service("PaperTradingEngine", paper_engine.start())

    logger.info("Paper Trading Engine session: %s", paper_engine.session_id)

    yield

    # Shutdown in reverse order
    await stop_service("PaperTradingEngine", paper_engine.stop())
    await stop_service("WhaleTracker", whale_tracker.stop())
    await stop_service("NewsAggregator", news_aggregator.stop())
    await stop_service("ForexProvider", forex_provider.stop())
    await stop_service("DayTradingEngine", day_trading_engine.stop())
    await stop_service("TradingAgent", trading_agent.stop())
    await stop_service("LiquidationEngine", liq_manager.stop())
    await stop_service("OrderFlowEngines", of_manager.stop_all())

    logger.info("AI Trading Navigator shut down")


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
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Request-ID", "X-API-Key"],
)


# Correlation ID middleware
@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    """Attach a per-request correlation ID to every log line and response header."""
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    set_request_id(request_id)
    response = await call_next(request)
    response.headers["x-request-id"] = request_id
    return response


# --- Sensitive value masking for request logging ---

_SENSITIVE_HEADERS: frozenset[str] = frozenset({
    "authorization", "api_key", "token", "secret", "x-api-key",
})

_SENSITIVE_QUERY_PARAMS: frozenset[str] = frozenset({
    "api_key", "token", "secret",
})

_MASKED = "***MASKED***"


def _mask_value(value: str) -> str:
    """Mask a sensitive value, keeping the first 4 chars if longer than 8."""
    if len(value) > 8:
        return value[:4] + _MASKED
    return _MASKED


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


_API_VERSION = "0.1.0"

# Request body size limit — 1 MB cap to prevent oversized payloads
_MAX_BODY_BYTES = 1 * 1024 * 1024  # 1 MB


@app.middleware("http")
async def body_size_limit_middleware(request: Request, call_next):
    """Reject requests with Content-Length exceeding 1 MB."""
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > _MAX_BODY_BYTES:
        return JSONResponse(
            status_code=413,
            content={"error": "payload_too_large", "detail": "Request body must be ≤ 1 MB"},
        )
    return await call_next(request)


# Rate limiting middleware
# NOTE: This is a single-process in-memory implementation.
# In multi-worker deployments use the Redis-backed rate limiter instead.
_rate_limits: dict[str, list[float]] = defaultdict(list)

# Auth endpoint uses a stricter limit to prevent brute-force attacks
EXPENSIVE_PATHS = {
    "/api/v1/analyze/run",
    "/api/v1/chat",
    "/api/v1/backtest/run",
    "/api/v1/auth/token",  # brute-force protection
}


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Enforce per-IP rate limits: 10 req/min for expensive/auth endpoints, 60 req/min otherwise."""
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


# Paths that get a hard 30 s server-side timeout
_TIMEOUT_PATHS = {"/api/v1/analyze/run", "/api/v1/chat", "/api/v1/backtest/run"}

# Paths sampled at 1% to keep logs quiet
_SAMPLED_PATHS = {"/api/v1/health", "/api/v1/status"}

import asyncio
import random


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    """Log requests, attach X-API-Version header, enforce timeouts on expensive paths."""
    start = _time.time()
    path = request.url.path

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
    response.headers["x-api-version"] = _API_VERSION

    if path not in _SAMPLED_PATHS or random.random() < 0.01:
        masked_qs = _mask_query_string(request.url.query or "")
        safe_path = f"{path}?{masked_qs}" if masked_qs else path
        logger.info(
            '{"method":"%s","path":"%s","status":%d,"duration_ms":%.1f}',
            request.method, safe_path, response.status_code, duration,
        )
    return response


@app.middleware("http")
async def error_handling_middleware(request: Request, call_next):
    """Catch unhandled exceptions and return structured JSON errors."""
    try:
        return await call_next(request)
    except Exception as exc:
        logger.exception("Unhandled error: %s", exc)
        # Never leak internal details (stack traces, file paths) in production
        detail = str(exc) if app_settings.ENVIRONMENT != "production" else "An internal error occurred"
        return JSONResponse(
            status_code=500,
            content={"error": "internal_server_error", "detail": detail},
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
app.include_router(extended_features_router, prefix="/api/v1")
app.include_router(futures_testnet_router, prefix="/api/v1")
app.include_router(multi_exchange_router, prefix="/api/v1")
app.include_router(oi_momentum_router, prefix="/api/v1")
app.include_router(dark_pool_router, prefix="/api/v1")
app.include_router(ai_commentary_router, prefix="/api/v1")
app.include_router(news_backtester_router, prefix="/api/v1")
app.include_router(stop_loss_optimizer_router, prefix="/api/v1")
app.include_router(trade_screener_router, prefix="/api/v1")
app.include_router(ab_backtester_router, prefix="/api/v1")
app.include_router(webhooks_router, prefix="/api/v1")


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
    """WebSocket endpoint for real-time signal/regime/sentiment updates.

    Accepts an optional ``token`` query parameter for authentication.
    In development mode, no token is required.
    """
    # Optional token validation — reject unauthenticated connections in production
    if app_settings.ENVIRONMENT == "production":
        token = websocket.query_params.get("token")
        if not token:
            await websocket.close(code=4001, reason="Authentication required")
            return
        try:
            from app.core.auth import _decode_token
            _decode_token(token)
        except Exception:
            await websocket.close(code=4001, reason="Invalid or expired token")
            return

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
