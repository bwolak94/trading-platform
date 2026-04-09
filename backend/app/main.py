"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import backtest, market, settings, signals
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
    yield
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
app.include_router(signals.router, prefix="/api/v1")
app.include_router(market.router, prefix="/api/v1")
app.include_router(backtest.router, prefix="/api/v1")
app.include_router(settings.router, prefix="/api/v1")


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
