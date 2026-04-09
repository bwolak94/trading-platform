"""Pydantic schemas for signal endpoints."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class SignalFactor(BaseModel):
    """Single factor contributing to a signal."""

    name: str
    weight: float
    score: float
    label: str


class SignalResponse(BaseModel):
    """Signal response schema."""

    id: UUID
    asset: str
    direction: str
    confidence: float
    regime: str
    entry_price: float | None = None
    stop_loss: float | None = None
    take_profit_1: float | None = None
    take_profit_2: float | None = None
    risk_reward: float | None = None
    position_size_pct: float | None = None
    technical_score: float | None = None
    onchain_score: float | None = None
    sentiment_score: float | None = None
    macro_score: float | None = None
    factors: list[dict[str, Any]]
    status: str
    expires_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SignalListResponse(BaseModel):
    """Paginated signal list response."""

    data: list[SignalResponse]
    meta: dict[str, int]


class RegimeResponse(BaseModel):
    """Market regime response schema."""

    asset: str
    regime: str
    confidence: float
    started_at: datetime
    ended_at: datetime | None = None
    metadata: dict[str, Any] | None = None

    model_config = {"from_attributes": True}


class SentimentResponse(BaseModel):
    """Sentiment data response schema."""

    asset: str
    source: str
    score: float
    volume: int | None = None
    period_start: datetime
    period_end: datetime

    model_config = {"from_attributes": True}


class OnChainEventResponse(BaseModel):
    """On-chain event response schema."""

    asset: str
    event_type: str
    amount: float
    amount_usd: float | None = None
    direction: str | None = None
    source: str | None = None
    timestamp: datetime

    model_config = {"from_attributes": True}


class UserSettingsResponse(BaseModel):
    """User settings response schema."""

    user_id: str
    capital: float | None = None
    risk_per_trade_pct: float
    max_drawdown_pct: float
    telegram_chat_id: str | None = None
    enabled_assets: list[str]
    system_status: str
    notifications_enabled: bool

    model_config = {"from_attributes": True}


class BacktestResultResponse(BaseModel):
    """Backtest result response schema."""

    id: UUID
    strategy_name: str
    asset: str
    timeframe: str
    period_start: str
    period_end: str
    win_rate: float | None = None
    profit_factor: float | None = None
    max_drawdown: float | None = None
    sharpe_ratio: float | None = None
    calmar_ratio: float | None = None
    total_trades: int | None = None
    prob_ruin_20pct: float | None = None
    prob_ruin_30pct: float | None = None
    equity_curve: list[dict[str, Any]] | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ErrorResponse(BaseModel):
    """Standard error response."""

    error: str
    detail: str | None = None
