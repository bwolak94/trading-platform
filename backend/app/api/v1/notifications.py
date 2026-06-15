"""Notifications API — history and performance of sent Telegram notifications."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from sqlalchemy import func, select, desc

from app.core.database import async_session
from app.core.logging import get_logger

router = APIRouter(prefix="/notifications", tags=["notifications"])
logger = get_logger(__name__)


@router.get("/history")
async def get_notification_history(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    chat_id: str | None = Query(default=None),
    message_type: str | None = Query(default=None),
) -> dict[str, Any]:
    """Return paginated notification history with optional filters."""
    from app.models.notification_history import NotificationHistory

    async with async_session() as session:
        query = select(NotificationHistory)
        if chat_id:
            query = query.where(NotificationHistory.chat_id == chat_id)
        if message_type:
            query = query.where(NotificationHistory.message_type == message_type)
        query = query.order_by(desc(NotificationHistory.sent_at)).limit(limit).offset(offset)

        result = await session.execute(query)
        rows = result.scalars().all()

        count_result = await session.execute(
            select(func.count()).select_from(NotificationHistory)
        )
        total = count_result.scalar_one()

    notifications = [
        {
            "id": str(r.id),
            "chat_id": r.chat_id,
            "message_type": r.message_type,
            "asset": r.asset,
            "direction": r.direction,
            "confidence": r.confidence,
            "strategy": r.strategy,
            "entry_price": float(r.entry_price) if r.entry_price else None,
            "stop_loss": float(r.stop_loss) if r.stop_loss else None,
            "take_profit_1": float(r.take_profit_1) if r.take_profit_1 else None,
            "outcome": r.outcome,
            "pnl_pct": float(r.pnl_pct) if r.pnl_pct else None,
            "message_text": r.message_text,
            "sent_at": r.sent_at.isoformat() if r.sent_at else None,
        }
        for r in rows
    ]

    return {"notifications": notifications, "total": total, "limit": limit, "offset": offset}


@router.get("/performance")
async def get_notification_performance() -> dict[str, Any]:
    """Return aggregated performance of signal notifications (win/loss/pending counts)."""
    from app.models.notification_history import NotificationHistory

    async with async_session() as session:
        result = await session.execute(
            select(
                NotificationHistory.outcome,
                func.count(NotificationHistory.id).label("count"),
                func.avg(NotificationHistory.pnl_pct).label("avg_pnl"),
            )
            .where(NotificationHistory.message_type == "SIGNAL")
            .group_by(NotificationHistory.outcome)
        )
        rows = result.all()

    stats: dict[str, Any] = {
        "WIN": {"count": 0, "avg_pnl": 0.0},
        "LOSS": {"count": 0, "avg_pnl": 0.0},
        "PENDING": {"count": 0, "avg_pnl": 0.0},
        "EXPIRED": {"count": 0, "avg_pnl": 0.0},
    }
    total = 0
    for row in rows:
        outcome = row.outcome or "PENDING"
        stats[outcome] = {
            "count": row.count,
            "avg_pnl": round(float(row.avg_pnl or 0), 4),
        }
        total += row.count

    wins = stats["WIN"]["count"]
    win_rate = round(wins / total, 4) if total > 0 else 0.0

    return {
        "total_signals": total,
        "win_rate": win_rate,
        "breakdown": stats,
    }
