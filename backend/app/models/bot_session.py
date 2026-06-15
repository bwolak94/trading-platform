"""SQLAlchemy model for paper-trading bot run sessions."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Numeric, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class BotSession(Base):
    """Tracks a continuous run of the paper-trading simulation engine."""

    __tablename__ = "bot_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)

    total_trades: Mapped[int] = mapped_column(nullable=False, default=0)
    winning_trades: Mapped[int] = mapped_column(nullable=False, default=0)
    total_pnl_pct: Mapped[float] = mapped_column(Numeric(precision=10, scale=4), nullable=False, default=0.0)
    max_drawdown_pct: Mapped[float] = mapped_column(Numeric(precision=10, scale=4), nullable=False, default=0.0)
    sharpe_ratio: Mapped[float | None] = mapped_column(Numeric(precision=10, scale=4), nullable=True)
    win_rate: Mapped[float] = mapped_column(Numeric(precision=6, scale=4), nullable=False, default=0.0)

    def __repr__(self) -> str:
        return f"<BotSession id={self.id} active={self.is_active} trades={self.total_trades}>"
