"""Risk Engine — drawdown kill switch, position sizing, risk management."""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.signal import Signal
from app.models.user_settings import UserSettings

logger = logging.getLogger(__name__)


@dataclass
class PositionSize:
    """Result of position size calculation."""

    units: float
    position_value: float
    position_pct: float
    risk_amount: float


class RiskEngine:
    """Manages risk calculations, kill switch, and position sizing."""

    async def check_kill_switch(self, user_id: str, db: AsyncSession) -> bool:
        """Check if the system should be paused due to excessive drawdown.

        Returns True if the system is paused (signals should NOT be emitted).
        """
        user_settings = await self._get_user_settings(user_id, db)
        if not user_settings:
            return False

        # Already paused
        if user_settings.system_status == "PAUSED":
            return True

        drawdown = await self.calculate_drawdown(user_id, db)
        max_dd = float(user_settings.max_drawdown_pct)

        if drawdown >= max_dd:
            user_settings.system_status = "PAUSED"
            await db.commit()
            logger.warning(
                "Kill switch triggered for %s: drawdown %.2f%% >= max %.2f%%",
                user_id, drawdown, max_dd,
            )
            return True

        return False

    async def reset_kill_switch(self, user_id: str, db: AsyncSession) -> bool:
        """Reset the kill switch and resume the system."""
        user_settings = await self._get_user_settings(user_id, db)
        if not user_settings:
            return False

        user_settings.system_status = "ACTIVE"
        await db.commit()
        logger.info("Kill switch reset for user %s", user_id)
        return True

    def calculate_position_size(
        self,
        capital: float,
        risk_pct: float,
        entry: float,
        stop_loss: float,
    ) -> PositionSize:
        """Calculate position size based on risk percentage and stop loss distance.

        Uses simplified Kelly Criterion approach from 04_AI_ENGINE.md.
        """
        if entry == stop_loss or capital <= 0:
            return PositionSize(units=0, position_value=0, position_pct=0, risk_amount=0)

        risk_amount = capital * (risk_pct / 100)
        price_risk = abs(entry - stop_loss)
        units = risk_amount / price_risk
        position_value = units * entry
        position_pct = (position_value / capital) * 100

        return PositionSize(
            units=round(units, 8),
            position_value=round(position_value, 2),
            position_pct=round(position_pct, 2),
            risk_amount=round(risk_amount, 2),
        )

    def calculate_position_size_volatility_adjusted(
        self,
        capital: float,
        risk_pct: float,
        entry: float,
        stop_loss: float,
        atr: float,
        atr_baseline: float,
    ) -> PositionSize:
        """Position sizing adjusted for volatility.

        Higher volatility (ATR > baseline) → smaller position.
        """
        if atr_baseline <= 0 or atr <= 0:
            return self.calculate_position_size(capital, risk_pct, entry, stop_loss)

        vol_ratio = atr_baseline / atr  # < 1 when vol is high
        adjusted_risk = risk_pct * min(vol_ratio, 1.0)  # never increase beyond base risk

        return self.calculate_position_size(capital, adjusted_risk, entry, stop_loss)

    async def calculate_drawdown(self, user_id: str, db: AsyncSession) -> float:
        """Calculate current drawdown percentage from signal history.

        Looks at signals from the last 30 days and computes P&L based on
        closed signals (TP_HIT / SL_HIT).
        """
        user_settings = await self._get_user_settings(user_id, db)
        if not user_settings or not user_settings.capital:
            return 0.0

        capital = float(user_settings.capital)
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)

        result = await db.execute(
            select(Signal).where(
                and_(
                    Signal.created_at >= cutoff,
                    Signal.status.in_(["TP1_HIT", "TP2_HIT", "SL_HIT"]),
                )
            )
        )
        closed_signals = result.scalars().all()

        if not closed_signals:
            return 0.0

        # Calculate cumulative P&L
        equity = capital
        peak = capital

        for signal in sorted(closed_signals, key=lambda s: s.created_at):
            pnl = self._calculate_signal_pnl(signal, capital)
            equity += pnl
            peak = max(peak, equity)

        if peak <= 0:
            return 0.0

        drawdown = ((peak - equity) / peak) * 100
        return round(drawdown, 2)

    def _calculate_signal_pnl(self, signal: Signal, capital: float) -> float:
        """Calculate P&L for a single closed signal."""
        if not signal.entry_price or not signal.position_size_pct:
            return 0.0

        entry = float(signal.entry_price)
        position_pct = float(signal.position_size_pct)
        position_value = capital * (position_pct / 100)

        if signal.status == "SL_HIT" and signal.stop_loss:
            exit_price = float(signal.stop_loss)
        elif signal.status == "TP1_HIT" and signal.take_profit_1:
            exit_price = float(signal.take_profit_1)
        elif signal.status == "TP2_HIT" and signal.take_profit_2:
            exit_price = float(signal.take_profit_2)
        else:
            return 0.0

        if entry == 0:
            return 0.0

        if signal.direction == "LONG":
            return_pct = (exit_price - entry) / entry
        else:
            return_pct = (entry - exit_price) / entry

        return position_value * return_pct

    async def get_risk_summary(self, user_id: str, db: AsyncSession) -> dict[str, Any]:
        """Get a complete risk summary for a user."""
        user_settings = await self._get_user_settings(user_id, db)
        if not user_settings:
            return {
                "system_status": "UNKNOWN",
                "drawdown_pct": 0.0,
                "capital": 0.0,
            }

        drawdown = await self.calculate_drawdown(user_id, db)
        kill_switch_active = user_settings.system_status == "PAUSED"

        # Win/loss streak from recent signals
        streak = await self._calculate_streak(db)

        return {
            "system_status": user_settings.system_status,
            "drawdown_pct": drawdown,
            "max_drawdown_pct": float(user_settings.max_drawdown_pct),
            "capital": float(user_settings.capital) if user_settings.capital else 0.0,
            "risk_per_trade_pct": float(user_settings.risk_per_trade_pct),
            "kill_switch_active": kill_switch_active,
            "streak": streak,
        }

    async def _calculate_streak(self, db: AsyncSession) -> dict[str, int]:
        """Calculate current win/loss streak."""
        result = await db.execute(
            select(Signal)
            .where(Signal.status.in_(["TP1_HIT", "TP2_HIT", "SL_HIT"]))
            .order_by(Signal.updated_at.desc())
            .limit(50)
        )
        signals = result.scalars().all()

        wins = 0
        losses = 0
        current_type = None

        for signal in signals:
            is_win = signal.status in ("TP1_HIT", "TP2_HIT")
            if current_type is None:
                current_type = "win" if is_win else "loss"
            if is_win and current_type == "win":
                wins += 1
            elif not is_win and current_type == "loss":
                losses += 1
            else:
                break

        return {"wins": wins, "losses": losses}

    async def _get_user_settings(
        self, user_id: str, db: AsyncSession
    ) -> UserSettings | None:
        """Fetch user settings from DB."""
        result = await db.execute(
            select(UserSettings).where(UserSettings.user_id == user_id)
        )
        return result.scalar_one_or_none()
