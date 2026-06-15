"""Strategy parameters ORM model for configurable strategy settings."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# Default parameters for each strategy
DEFAULT_STRATEGY_PARAMS: dict[str, dict[str, Any]] = {
    "trend_following": {
        "ema_fast": 12,
        "ema_slow": 26,
        "atr_period": 14,
        "atr_multiplier_sl": 1.5,
        "atr_multiplier_tp": 2.5,
        "adx_threshold": 25,
        "volume_confirmation": True,
        "min_confidence": 0.6,
    },
    "mean_reversion": {
        "bb_period": 20,
        "bb_std_dev": 2.0,
        "rsi_period": 14,
        "rsi_oversold": 30,
        "rsi_overbought": 70,
        "atr_period": 14,
        "min_confidence": 0.6,
    },
    "breakout": {
        "lookback_period": 20,
        "volume_surge_multiplier": 1.5,
        "atr_period": 14,
        "atr_multiplier_sl": 1.0,
        "atr_multiplier_tp": 3.0,
        "confirmation_candles": 2,
        "min_confidence": 0.65,
    },
    "smc": {
        "swing_lookback": 10,
        "fvg_min_gap_pct": 0.1,
        "order_block_lookback": 50,
        "liquidity_zone_tolerance": 0.002,
        "atr_period": 14,
        "min_confidence": 0.7,
    },
}


class StrategyParams(Base):
    """Configurable strategy parameters stored as JSONB."""

    __tablename__ = "strategy_params"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    strategy_name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
