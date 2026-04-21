"""SQLAlchemy model for paper-trading simulated positions."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SimulatedPosition(Base):
    """A paper-trading position opened by the simulation engine."""

    __tablename__ = "simulated_positions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )

    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)  # LONG | SHORT
    strategy: Mapped[str] = mapped_column(String(50), nullable=False)
    regime: Mapped[str] = mapped_column(String(30), nullable=False)
    confidence: Mapped[int] = mapped_column(nullable=False, default=0)

    entry_price: Mapped[float] = mapped_column(Numeric(precision=20, scale=8), nullable=False)
    stop_loss: Mapped[float] = mapped_column(Numeric(precision=20, scale=8), nullable=False)
    take_profit_1: Mapped[float] = mapped_column(Numeric(precision=20, scale=8), nullable=False)
    take_profit_2: Mapped[float | None] = mapped_column(Numeric(precision=20, scale=8), nullable=True)
    take_profit_3: Mapped[float | None] = mapped_column(Numeric(precision=20, scale=8), nullable=True)

    current_price: Mapped[float | None] = mapped_column(Numeric(precision=20, scale=8), nullable=True)
    exit_price: Mapped[float | None] = mapped_column(Numeric(precision=20, scale=8), nullable=True)
    pnl_pct: Mapped[float] = mapped_column(Numeric(precision=10, scale=4), nullable=False, default=0.0)

    # OPEN | CLOSED | STOPPED_OUT | TP1_HIT | TP2_HIT | TP3_HIT
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="OPEN", index=True)
    exit_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Extra signal metadata stored as JSON
    factors: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # MAE/MFE — added by migration 006_mae_mfe_tags
    mae_pct: Mapped[float | None] = mapped_column("max_adverse_excursion", Numeric(precision=10, scale=6), nullable=True)
    mfe_pct: Mapped[float | None] = mapped_column("max_favorable_excursion", Numeric(precision=10, scale=6), nullable=True)

    # Trade journal — added by migration 006_mae_mfe_tags
    tags: Mapped[list[str] | None] = mapped_column(ARRAY(String(50)), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_simpos_symbol_status", "symbol", "status"),
        Index("ix_simpos_opened_at", "opened_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<SimulatedPosition {self.symbol} {self.direction} "
            f"entry={self.entry_price} status={self.status}>"
        )
