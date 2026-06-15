"""Adaptive Kelly Criterion — position sizing that adapts to recent win rate.

Static Kelly from all-time statistics misses regime changes. By recalculating
from a rolling window of the most recent N trades, this module captures
current strategy effectiveness and sizes positions accordingly.

Kelly formula: f* = (bp - q) / b
  where:
    b = avg_win / avg_loss  (win-to-loss ratio)
    p = win probability
    q = 1 - p  (loss probability)

Half Kelly is recommended as primary sizing: it retains ~75% of the theoretical
EV while cutting variance significantly.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class KellyResult:
    """Result of Kelly Criterion calculation."""

    full_kelly_pct: float       # theoretical optimal bet size (%)
    half_kelly_pct: float       # recommended: 50% of full Kelly (safer)
    quarter_kelly_pct: float    # conservative: 25% of full Kelly
    win_rate: float             # recent win rate used
    avg_win_pct: float          # average winning trade (%)
    avg_loss_pct: float         # average losing trade (%) — positive number
    edge: float                 # expected value per unit risked
    trades_count: int           # number of trades used in calculation
    is_statistically_significant: bool  # True if >= 20 trades
    recommendation: str         # "FULL_KELLY", "HALF_KELLY", "QUARTER_KELLY", "DO_NOT_TRADE"


class AdaptiveKelly:
    """Rolling-window Kelly Criterion that recalculates from recent trades.

    Key insight: static Kelly from all-time stats misses regime changes.
    A rolling 20-30 trade window captures current strategy effectiveness.

    Hard caps applied:
    - Maximum Kelly = 25% of capital (never risk more than a quarter on one trade)
    - Minimum trades = 10 for a non-zero Kelly
    - Recommended output = Half Kelly (reduces variance, keeps ~75% of EV)
    """

    MAX_KELLY_PCT: float = 25.0   # hard cap on full Kelly output
    MIN_TRADES: int = 10          # minimum trades for meaningful calculation
    RECOMMENDED_TRADES: int = 20  # ideal rolling window size

    # --------------------------------------------------------------------- public

    def calculate(
        self,
        recent_trades: list[dict],
        window: int = 20,
    ) -> KellyResult:
        """Calculate Kelly fractions from a rolling window of trades.

        Args:
            recent_trades: List of trade dicts. Each must have either:
                - ``result`` ("WIN" | "LOSS") and ``pnl_pct`` (float), OR
                - only ``pnl_pct`` (positive = win, negative = loss).
            window: Number of most recent trades to use.

        Returns:
            :class:`KellyResult` with all Kelly fractions and metadata.
        """
        if not recent_trades:
            return self._zero_kelly(reason="DO_NOT_TRADE", n=0)

        # Slice to rolling window
        trades = recent_trades[-window:]
        n = len(trades)

        if n < self.MIN_TRADES:
            logger.debug(
                "AdaptiveKelly: only %d trades (need %d) — returning zero Kelly",
                n,
                self.MIN_TRADES,
            )
            return self._zero_kelly(reason="DO_NOT_TRADE", n=n)

        # Separate wins and losses
        wins: list[float] = []
        losses: list[float] = []

        for t in trades:
            pnl = float(t.get("pnl_pct", 0.0))
            result = t.get("result", "WIN" if pnl >= 0 else "LOSS")

            if result == "WIN" or pnl > 0:
                wins.append(abs(pnl))
            else:
                losses.append(abs(pnl))

        win_rate = len(wins) / n if n > 0 else 0.0
        avg_win = float(np.mean(wins)) if wins else 0.0
        avg_loss = float(np.mean(losses)) if losses else 1.0  # avoid division by zero

        return self._calculate_from_stats(win_rate, avg_win, avg_loss, n)

    def calculate_for_strategy(
        self,
        strategy_name: str,
        all_trades: list[dict],
        window: int = 20,
    ) -> KellyResult:
        """Calculate Kelly for a specific strategy's recent trades.

        Args:
            strategy_name: Strategy identifier to filter by (case-insensitive).
            all_trades: All trades with a ``strategy`` (or ``strategy_name``) key.
            window: Number of most recent strategy trades to use.

        Returns:
            :class:`KellyResult` for the specified strategy.
        """
        filtered = [
            t for t in all_trades
            if t.get("strategy", t.get("strategy_name", "")).lower()
            == strategy_name.lower()
        ]

        logger.debug(
            "AdaptiveKelly: strategy=%s total_trades=%d filtered=%d",
            strategy_name,
            len(all_trades),
            len(filtered),
        )

        return self.calculate(filtered, window=window)

    def recommend_risk_pct(
        self,
        result: KellyResult,
        base_risk_pct: float = 1.0,
    ) -> float:
        """Recommend actual risk % combining Kelly and a baseline risk parameter.

        The recommended value is the minimum of:
        - Half Kelly percentage
        - Base risk × win-rate multiplier (scales with recent performance)

        Args:
            result: :class:`KellyResult` from :meth:`calculate`.
            base_risk_pct: Default risk per trade percentage (e.g. 1.0).

        Returns:
            Recommended risk percentage, floored at 0.0.
        """
        if result.recommendation == "DO_NOT_TRADE":
            return 0.0

        # Win-rate multiplier: scales from 0.5× (WR=35%) to 1.5× (WR=70%+)
        wr_multiplier = np.clip(
            (result.win_rate - 0.35) / (0.70 - 0.35) + 0.5, 0.5, 1.5
        )
        adjusted_base = base_risk_pct * float(wr_multiplier)

        recommended = min(result.half_kelly_pct, adjusted_base)
        recommended = max(0.0, round(recommended, 4))

        logger.debug(
            "recommend_risk_pct: half_kelly=%.4f adjusted_base=%.4f result=%.4f",
            result.half_kelly_pct,
            adjusted_base,
            recommended,
        )
        return recommended

    # --------------------------------------------------------------------- private

    def _calculate_from_stats(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        n_trades: int,
    ) -> KellyResult:
        """Core Kelly calculation from aggregated statistics.

        Args:
            win_rate: Fraction of winning trades [0, 1].
            avg_win: Average win size as a percentage (positive).
            avg_loss: Average loss size as a percentage (positive).
            n_trades: Total number of trades in the sample.

        Returns:
            Fully populated :class:`KellyResult`.
        """
        loss_rate = 1.0 - win_rate

        if avg_loss <= 0:
            avg_loss = 1.0  # prevent division by zero — conservative fallback

        b = avg_win / avg_loss  # win/loss ratio

        # Kelly formula: f* = (bp - q) / b  =  p - q/b
        full_kelly_raw = (b * win_rate - loss_rate) / b
        full_kelly_raw = max(0.0, full_kelly_raw)  # clamp to non-negative

        # Edge = EV per unit risked
        edge = win_rate * avg_win - loss_rate * avg_loss

        # Convert to percentage and apply hard cap
        full_kelly_pct = min(full_kelly_raw * 100.0, self.MAX_KELLY_PCT)
        half_kelly_pct = full_kelly_pct / 2.0
        quarter_kelly_pct = full_kelly_pct / 4.0

        is_significant = n_trades >= self.RECOMMENDED_TRADES

        # Recommendation logic
        if edge <= 0:
            recommendation = "DO_NOT_TRADE"
        elif not is_significant:
            recommendation = "QUARTER_KELLY"
        elif full_kelly_pct < 3.0:
            recommendation = "QUARTER_KELLY"
        elif full_kelly_pct < 8.0:
            recommendation = "HALF_KELLY"
        else:
            recommendation = "HALF_KELLY"  # never suggest full Kelly in production

        logger.debug(
            "KellyResult: wr=%.3f avg_win=%.3f avg_loss=%.3f "
            "full_kelly=%.2f%% recommendation=%s",
            win_rate,
            avg_win,
            avg_loss,
            full_kelly_pct,
            recommendation,
        )

        return KellyResult(
            full_kelly_pct=round(full_kelly_pct, 4),
            half_kelly_pct=round(half_kelly_pct, 4),
            quarter_kelly_pct=round(quarter_kelly_pct, 4),
            win_rate=round(win_rate, 4),
            avg_win_pct=round(avg_win, 4),
            avg_loss_pct=round(avg_loss, 4),
            edge=round(edge, 4),
            trades_count=n_trades,
            is_statistically_significant=is_significant,
            recommendation=recommendation,
        )

    def _zero_kelly(self, reason: str, n: int) -> KellyResult:
        """Return a zero-Kelly result used when calculation is not possible.

        Args:
            reason: Recommendation string explaining why Kelly is zero.
            n: Number of trades available.

        Returns:
            :class:`KellyResult` with all sizing at 0.
        """
        return KellyResult(
            full_kelly_pct=0.0,
            half_kelly_pct=0.0,
            quarter_kelly_pct=0.0,
            win_rate=0.0,
            avg_win_pct=0.0,
            avg_loss_pct=0.0,
            edge=0.0,
            trades_count=n,
            is_statistically_significant=False,
            recommendation=reason,
        )


# Module-level singleton
_adaptive_kelly: AdaptiveKelly | None = None


def get_adaptive_kelly() -> AdaptiveKelly:
    """Return the global :class:`AdaptiveKelly` singleton.

    Returns:
        Shared AdaptiveKelly instance.
    """
    global _adaptive_kelly
    if _adaptive_kelly is None:
        _adaptive_kelly = AdaptiveKelly()
    return _adaptive_kelly
