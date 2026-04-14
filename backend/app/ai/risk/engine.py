"""Risk Engine — drawdown kill switch, position sizing, risk management."""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.signal import Signal
from app.models.user_settings import UserSettings

logger = logging.getLogger(__name__)

CORRELATED_GROUPS = {
    "large_cap": {"BTC/USDT", "ETH/USDT"},
    "alt_l1": {"SOL/USDT", "AVAX/USDT", "DOT/USDT", "ATOM/USDT", "ADA/USDT"},
    "defi": {"UNI/USDT", "LINK/USDT", "AAVE/USDT"},
    "meme": {"DOGE/USDT", "PEPE/USDT"},
    "l2": {"ARB/USDT", "OP/USDT", "MATIC/USDT"},
}


@dataclass
class PositionSize:
    """Result of position size calculation."""

    units: float
    position_value: float
    position_pct: float
    risk_amount: float


class RiskEngine:
    """Manages risk calculations, kill switch, and position sizing."""

    MAX_CONCURRENT_TRADES = 8
    _recovery_mode: bool = False
    _recovery_scale: float = 0.5

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

    def calculate_position_with_time_decay(
        self,
        capital: float,
        risk_pct: float,
        entry: float,
        stop_loss: float,
        estimated_hours: float,
    ) -> PositionSize:
        """Reduce position for longer trades."""
        base = self.calculate_position_size(capital, risk_pct, entry, stop_loss)
        if estimated_hours > 48:
            decay = max(0.5, 1.0 - (estimated_hours - 48) / 200)
            return PositionSize(
                units=round(base.units * decay, 8),
                position_value=round(base.position_value * decay, 2),
                position_pct=round(base.position_pct * decay, 2),
                risk_amount=round(base.risk_amount * decay, 2),
            )
        return base

    def check_sl_overlap(
        self,
        new_sl: float,
        new_tp1: float,
        active_signals: list[dict],
    ) -> float:
        """Returns discount (0.5-1.0) if SL overlaps with existing TPs."""
        for sig in active_signals:
            existing_tp = sig.get("take_profit_1", 0)
            if existing_tp > 0:
                overlap = abs(new_sl - existing_tp) / max(new_sl, 0.001) * 100
                if overlap < 2.0:
                    return 0.5
        return 1.0

    def get_correlation_discount(self, symbol: str, active_positions: dict[str, str]) -> float:
        """Returns a multiplier (0.3-1.0) based on correlated open positions."""
        my_group = None
        for group, symbols in CORRELATED_GROUPS.items():
            if symbol in symbols:
                my_group = group
                break
        if not my_group:
            return 1.0

        same_dir_count = 0
        for pos_symbol, pos_direction in active_positions.items():
            if pos_symbol != symbol and pos_symbol in CORRELATED_GROUPS.get(my_group, set()):
                same_dir_count += 1

        if same_dir_count >= 3:
            return 0.3  # Heavy penalty
        if same_dir_count >= 2:
            return 0.5
        if same_dir_count >= 1:
            return 0.7
        return 1.0

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

    async def check_daily_loss_limit(self, user_id: str, db: AsyncSession, daily_limit_pct: float = 3.0) -> bool:
        """Check if daily P&L has exceeded daily loss limit. Returns True if limit hit."""
        user_settings = await self._get_user_settings(user_id, db)
        if not user_settings or not user_settings.capital:
            return False

        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        result = await db.execute(
            select(Signal).where(
                and_(Signal.created_at >= today_start, Signal.status.in_(["TP1_HIT", "TP2_HIT", "SL_HIT"]))
            )
        )
        closed_today = result.scalars().all()

        daily_pnl = sum(self._calculate_signal_pnl(s, float(user_settings.capital)) for s in closed_today)
        daily_pnl_pct = (daily_pnl / float(user_settings.capital)) * 100

        if daily_pnl_pct <= -daily_limit_pct:
            logger.warning("Daily loss limit hit: %.2f%% (limit: -%.1f%%)", daily_pnl_pct, daily_limit_pct)
            return True
        return False

    async def check_max_concurrent(self, db: AsyncSession) -> bool:
        """Returns True if at max concurrent trades."""
        result = await db.execute(
            select(func.count(Signal.id)).where(Signal.status == "ACTIVE")
        )
        count = result.scalar() or 0
        return count >= self.MAX_CONCURRENT_TRADES

    def is_recovery_mode(self) -> bool:
        """Check if recovery mode is active."""
        return self._recovery_mode

    def set_recovery_mode(self, active: bool):
        """Enable or disable recovery mode."""
        self._recovery_mode = active
        if active:
            logger.info("Recovery mode ACTIVATED: position sizes reduced to %.0f%%", self._recovery_scale * 100)

    def get_position_scale(self) -> float:
        """Get current position scale factor."""
        return self._recovery_scale if self._recovery_mode else 1.0

    async def calculate_portfolio_heat(self, db: AsyncSession, capital: float) -> float:
        """Calculate total portfolio risk as % of capital."""
        result = await db.execute(
            select(Signal).where(Signal.status == "ACTIVE")
        )
        active = result.scalars().all()
        total_risk = 0.0
        for sig in active:
            if sig.entry_price and sig.stop_loss:
                risk_per_unit = abs(float(sig.entry_price) - float(sig.stop_loss))
                pct = float(sig.position_size_pct or 0) / 100
                total_risk += risk_per_unit * pct * capital / max(float(sig.entry_price), 0.001)
        return round(total_risk / max(capital, 1) * 100, 2)

    def adjust_risk_by_winrate(self, base_risk_pct: float, recent_win_rate: float) -> float:
        """Adjust risk percentage based on recent win rate."""
        if recent_win_rate < 0.35:
            return round(base_risk_pct * 0.6, 2)  # Reduce 40%
        if recent_win_rate < 0.45:
            return round(base_risk_pct * 0.8, 2)  # Reduce 20%
        if recent_win_rate > 0.70:
            return round(base_risk_pct * 1.15, 2)  # Boost 15%
        return base_risk_pct

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
