"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import agent, analyze, backtest, chat, intelligence, market, settings, signals
from app.core.config import settings as app_settings
from app.core.websocket import manager

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    logging.basicConfig(
        level=logging.INFO,
        format='{"time":"%(asctime)s","level":"%(levelname)s","module":"%(module)s","message":"%(message)s"}',
    )
    logger.info("AI Trading Navigator starting up")

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

    yield

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

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=app_settings.CORS_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


# API routers
app.include_router(agent.router, prefix="/api/v1")
app.include_router(signals.router, prefix="/api/v1")
app.include_router(market.router, prefix="/api/v1")
app.include_router(backtest.router, prefix="/api/v1")
app.include_router(settings.router, prefix="/api/v1")
app.include_router(analyze.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")
app.include_router(intelligence.router, prefix="/api/v1")


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
