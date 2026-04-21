"""SQLAlchemy model for Telegram notification history."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class NotificationHistory(Base):
    """Records every Telegram notification sent, with optional trade outcome."""

    __tablename__ = "notification_history"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    chat_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # SIGNAL | KILL_SWITCH | STATUS | PERFORMANCE | CUSTOM
    message_type: Mapped[str] = mapped_column(String(30), nullable=False, default="SIGNAL")

    # Signal-specific fields (nullable for non-signal messages)
    asset: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    direction: Mapped[str | None] = mapped_column(String(10), nullable=True)
    confidence: Mapped[int | None] = mapped_column(nullable=True)
    strategy: Mapped[str | None] = mapped_column(String(50), nullable=True)
    entry_price: Mapped[float | None] = mapped_column(Numeric(precision=20, scale=8), nullable=True)
    stop_loss: Mapped[float | None] = mapped_column(Numeric(precision=20, scale=8), nullable=True)
    take_profit_1: Mapped[float | None] = mapped_column(Numeric(precision=20, scale=8), nullable=True)

    message_text: Mapped[str] = mapped_column(Text, nullable=False)

    # Outcome filled in when position closes: WIN | LOSS | PENDING | EXPIRED
    outcome: Mapped[str | None] = mapped_column(String(20), nullable=True, default="PENDING")
    pnl_pct: Mapped[float | None] = mapped_column(Numeric(precision=10, scale=4), nullable=True)

    # Link to simulation position if applicable
    simulated_position_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    __table_args__ = (
        Index("ix_notif_chat_sent", "chat_id", "sent_at"),
        Index("ix_notif_asset_outcome", "asset", "outcome"),
    )

    def __repr__(self) -> str:
        return (
            f"<NotificationHistory {self.message_type} "
            f"chat={self.chat_id} asset={self.asset} outcome={self.outcome}>"
        )
