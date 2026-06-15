"""UserSettings ORM model for user configuration."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Numeric, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class UserSettings(Base):
    """Per-user configuration and risk management settings."""

    __tablename__ = "user_settings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    capital: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    risk_per_trade_pct: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("1.5")
    )
    max_drawdown_pct: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("10.0")
    )
    telegram_chat_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    enabled_assets: Mapped[list[str]] = mapped_column(
        JSONB, default=lambda: ["BTC/USDT", "ETH/USDT"]
    )
    system_status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
