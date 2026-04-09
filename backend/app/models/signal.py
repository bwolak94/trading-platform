"""Signal ORM model for trading signals."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, Numeric, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Signal(Base):
    """Trading signal with scoring breakdown and status tracking."""

    __tablename__ = "signals"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    asset: Mapped[str] = mapped_column(String(20), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    regime: Mapped[str] = mapped_column(String(30), nullable=False)
    entry_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    stop_loss: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    take_profit_1: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    take_profit_2: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    risk_reward: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    position_size_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)

    # Scoring breakdown
    technical_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    onchain_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    sentiment_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    macro_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)

    # Factors
    factors: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)

    # Status tracking
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )
