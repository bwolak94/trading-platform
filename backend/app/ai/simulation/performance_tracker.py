"""Performance tracker — calculates PnL, win rate, Sharpe ratio for simulation."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.ai.simulation.position_manager import SimPosition
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class PerformanceSnapshot:
    """Point-in-time snapshot of simulation performance."""

    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    total_pnl_pct: float = 0.0
    avg_win_pct: float = 0.0
    avg_loss_pct: float = 0.0
    profit_factor: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    best_trade: float = 0.0
    worst_trade: float = 0.0
    open_positions: int = 0
    running_pnl: float = 0.0  # unrealized PnL from open positions


class PerformanceTracker:
    """Tracks closed-trade statistics and computes risk-adjusted metrics."""

    def __init__(self) -> None:
        self._closed: list[SimPosition] = []
        self._pnl_series: list[float] = []
        self._peak_equity: float = 100.0
        self._max_drawdown: float = 0.0
        self._session_start: datetime = datetime.now(timezone.utc)
        self._equity_curve: list[dict] = []

    def record_close(self, pos: SimPosition) -> None:
        """Record a newly closed position for metric calculation."""
        self._closed.append(pos)
        self._pnl_series.append(pos.pnl_pct)
        equity = 100.0 + sum(self._pnl_series)
        if equity > self._peak_equity:
            self._peak_equity = equity
        drawdown = (self._peak_equity - equity) / self._peak_equity * 100
        if drawdown > self._max_drawdown:
            self._max_drawdown = drawdown
        self._equity_curve.append({
            "time": datetime.now(timezone.utc).isoformat(),
            "equity": round(equity, 4),
            "pnl_pct": round(pos.pnl_pct, 4),
            "trade_count": len(self._closed),
        })

    def snapshot(self, open_positions: list[SimPosition]) -> PerformanceSnapshot:
        """Build a PerformanceSnapshot from all closed + current open positions."""
        snap = PerformanceSnapshot()
        snap.total_trades = len(self._closed)
        snap.open_positions = len(open_positions)
        snap.max_drawdown_pct = round(self._max_drawdown, 4)

        if not self._closed:
            snap.running_pnl = sum(p.pnl_pct for p in open_positions)
            return snap

        wins = [p.pnl_pct for p in self._closed if p.pnl_pct > 0]
        losses = [p.pnl_pct for p in self._closed if p.pnl_pct <= 0]

        snap.winning_trades = len(wins)
        snap.losing_trades = len(losses)
        snap.win_rate = round(len(wins) / snap.total_trades, 4) if snap.total_trades else 0.0
        snap.total_pnl_pct = round(sum(self._pnl_series), 4)
        snap.avg_win_pct = round(sum(wins) / len(wins), 4) if wins else 0.0
        snap.avg_loss_pct = round(sum(losses) / len(losses), 4) if losses else 0.0
        snap.best_trade = round(max(self._pnl_series), 4)
        snap.worst_trade = round(min(self._pnl_series), 4)

        total_gains = sum(wins)
        total_losses = abs(sum(losses))
        snap.profit_factor = round(total_gains / total_losses, 4) if total_losses > 0 else 0.0

        snap.sharpe_ratio = self._calculate_sharpe()
        snap.sortino_ratio = self._calculate_sortino()
        snap.running_pnl = round(sum(p.pnl_pct for p in open_positions), 4)

        return snap

    @property
    def equity_curve(self) -> list[dict]:
        """Return a copy of the equity curve (one entry per closed trade)."""
        return list(self._equity_curve)

    def _calculate_sortino(self, risk_free_rate: float = 0.02) -> float:
        """Calculate Sortino ratio using only downside deviation."""
        if len(self._pnl_series) < 3:
            return 0.0
        n = len(self._pnl_series)
        mean_pnl = sum(self._pnl_series) / n
        # Only penalize returns below zero (downside deviation)
        downside_sq = [min(x, 0) ** 2 for x in self._pnl_series]
        downside_std = (sum(downside_sq) / (n - 1)) ** 0.5 if n > 1 else 0.0
        if downside_std == 0:
            return 0.0
        annualised_return = mean_pnl * 365
        annualised_downside = downside_std * (365 ** 0.5)
        return round((annualised_return - risk_free_rate) / annualised_downside, 4)

    def _calculate_sharpe(self, risk_free_rate: float = 0.02) -> float:
        """Calculate annualised Sharpe ratio from closed-trade PnL series."""
        if len(self._pnl_series) < 3:
            return 0.0
        n = len(self._pnl_series)
        mean_pnl = sum(self._pnl_series) / n
        variance = sum((x - mean_pnl) ** 2 for x in self._pnl_series) / (n - 1)
        std_dev = math.sqrt(variance) if variance > 0 else 0.0
        if std_dev == 0:
            return 0.0
        # Approximate: assume ~365 trades/year for crypto
        annualised_return = mean_pnl * 365
        annualised_std = std_dev * math.sqrt(365)
        sharpe = (annualised_return - risk_free_rate) / annualised_std
        return round(sharpe, 4)
