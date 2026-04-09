"""BacktestResult ORM model for backtest results."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Date, DateTime, Integer, Numeric, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class BacktestResult(Base):
    """Walk-forward backtest and Monte Carlo simulation results."""

    __tablename__ = "backtest_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    strategy_name: Mapped[str] = mapped_column(String(50), nullable=False)
    asset: Mapped[str] = mapped_column(String(20), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(5), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)

    # Performance metrics
    win_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    profit_factor: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    max_drawdown: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    sharpe_ratio: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    calmar_ratio: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    total_trades: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Monte Carlo
    prob_ruin_20pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    prob_ruin_30pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    equity_curve: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
