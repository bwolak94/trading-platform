"""Pydantic schemas for market data and request validation."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class OHLCV(BaseModel):
    """Single OHLCV candle."""

    asset: str
    timeframe: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


# ---------------------------------------------------------------------------
# Request schemas for API endpoints
# ---------------------------------------------------------------------------


class AnalyzeRequest(BaseModel):
    """Request body for on-demand market analysis."""

    asset: str = Field(default="BTC/USDT", description="Trading pair, e.g. BTC/USDT")
    timeframe: str = Field(default="4h", description="Candle timeframe, e.g. 1h, 4h, 1D")
    strategy: str | None = Field(
        default=None,
        description="Run a specific strategy by name, or null/omit for all strategies",
    )


class ChatRequest(BaseModel):
    """Chat message from the user."""

    message: str = Field(..., min_length=1, description="User message text")
    asset: str = Field(default="BTC/USDT", description="Trading pair for context")
    timeframe: str = Field(default="4h", description="Timeframe for market data")
    history: list[dict[str, str]] = Field(
        default_factory=list,
        description="Previous conversation messages [{role, content}]",
    )


class BacktestRunRequest(BaseModel):
    """Request body for running a backtest."""

    strategy: str = Field(..., description="Strategy name to backtest")
    asset: str = Field(..., description="Trading pair, e.g. BTC/USDT")
    timeframe: str = Field(..., description="Candle timeframe")
    from_date: str = Field(..., description="Backtest start date in YYYY-MM-DD format")
    to_date: str = Field(..., description="Backtest end date in YYYY-MM-DD format")
    initial_capital: float = Field(default=10000.0, gt=0, description="Starting capital in USD")
    risk_per_trade_pct: float = Field(
        default=1.5, gt=0, le=100, description="Risk per trade as percentage of capital"
    )


class SettingsUpdateRequest(BaseModel):
    """Partial update for user settings."""

    capital: float | None = Field(default=None, gt=0, description="Trading capital in USD")
    risk_per_trade_pct: float | None = Field(
        default=None, gt=0, le=100, description="Risk per trade %"
    )
    max_drawdown_pct: float | None = Field(
        default=None, gt=0, le=100, description="Max drawdown % before kill switch"
    )
    telegram_chat_id: str | None = Field(default=None, description="Telegram chat ID for alerts")
    enabled_assets: list[str] | None = Field(
        default=None, description="List of enabled trading pairs"
    )
    notifications_enabled: bool | None = Field(
        default=None, description="Toggle Telegram notifications"
    )


class ProAnalysisRequest(BaseModel):
    """Request body for professional-grade technical analysis chat."""

    message: str = Field(..., min_length=1, description="User message / analysis request")
    asset: str = Field(default="BTC/USDT", description="Trading pair, e.g. BTC/USDT")
    timeframe: str = Field(default="4h", description="Candle timeframe, e.g. 1h, 4h, 1D")
    image_base64: str | None = Field(
        default=None, description="Optional base64-encoded chart screenshot (PNG)"
    )
    history: list[dict[str, str]] = Field(
        default_factory=list,
        description="Previous conversation messages [{role, content}]",
    )


class TradeOutcomeRequest(BaseModel):
    """Request body for recording a trade outcome."""

    symbol: str = Field(..., description="Trading pair symbol")
    exit_price: float = Field(..., gt=0, description="Price at which the trade was exited")
    hit_level: str = Field(
        ...,
        description="Which level was hit: tp1, tp2, tp3, sl, or manual",
    )
