"""Equity Curve Scaler — dynamically adjusts position sizes based on system performance.

Implements the Turtle Trader approach: reduce position sizes when the equity
curve is underperforming relative to its own moving averages. This prevents
compounding losses during strategy drawdowns by automatically de-risking when
the system is struggling and ramping back up when it recovers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional

import numpy as np
import pandas as pd

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class EquityCurveState:
    """Current state of the equity curve and scaling decision."""

    current_equity: float
    peak_equity: float
    drawdown_pct: float
    equity_vs_ma20: float       # % above/below 20-period MA
    equity_vs_ma50: float       # % above/below 50-period MA
    ma20: float
    ma50: float
    scale_factor: float         # 0.25, 0.50, 0.75, or 1.0
    scale_reason: str
    is_below_ma20: bool
    is_below_ma50: bool
    regime: str                 # "FULL_SIZE", "REDUCED_75", "REDUCED_50", "REDUCED_25"


class EquityCurveScaler:
    """Reduces position sizes when the system's equity curve is underperforming.

    Rules (Turtle Trader inspired):
    - Equity above both MA20 and MA50: FULL SIZE (1.0x)
    - Equity below MA20, above MA50:   REDUCED_75 (0.75x)
    - Equity below MA50, above MA20:   REDUCED_50 (0.50x)
    - Equity below BOTH MA20 and MA50: REDUCED_25 (0.25x)

    MA periods are measured in TRADES (not time), so slow/fast trading
    cadence does not affect the system behaviour.
    """

    MA_SHORT: int = 20  # trades
    MA_LONG: int = 50   # trades

    # ------------------------------------------------------------------ public

    def calculate_state(
        self,
        closed_trades: list[dict],
        starting_equity: float = 10_000.0,
    ) -> EquityCurveState:
        """Build equity curve from trade history, calculate MAs, determine scale.

        Args:
            closed_trades: List of closed trade results, each must contain at
                minimum ``pnl_pct`` (float). Optional key ``timestamp``
                (datetime) is used for ordering when present.
            starting_equity: Starting capital in account currency.

        Returns:
            :class:`EquityCurveState` with the ``scale_factor`` to apply to
            *all* position sizes.
        """
        if not closed_trades:
            logger.debug("No closed trades — returning full-size state")
            return self._default_full_size_state(starting_equity)

        equity_curve = self._build_equity_curve(closed_trades, starting_equity)
        current_equity = float(equity_curve.iloc[-1])
        peak_equity = float(equity_curve.max())
        drawdown_pct = (
            ((peak_equity - current_equity) / peak_equity) * 100
            if peak_equity > 0
            else 0.0
        )

        ma20, ma50 = self._calculate_mas(equity_curve)

        # Percentage distance from each MA (positive = above, negative = below)
        equity_vs_ma20 = (
            ((current_equity - ma20) / ma20) * 100 if ma20 > 0 else 0.0
        )
        equity_vs_ma50 = (
            ((current_equity - ma50) / ma50) * 100 if ma50 > 0 else 0.0
        )

        is_below_ma20 = current_equity < ma20
        is_below_ma50 = current_equity < ma50

        # Determine regime and scale factor
        if not is_below_ma20 and not is_below_ma50:
            regime = "FULL_SIZE"
            scale_factor = 1.0
            scale_reason = (
                "Equity above both MA20 and MA50 — system performing well."
            )
        elif is_below_ma20 and not is_below_ma50:
            regime = "REDUCED_75"
            scale_factor = 0.75
            scale_reason = (
                f"Equity below MA20 ({ma20:.2f}) but above MA50 ({ma50:.2f}) "
                f"— minor underperformance, reducing to 75%."
            )
        elif not is_below_ma20 and is_below_ma50:
            regime = "REDUCED_50"
            scale_factor = 0.50
            scale_reason = (
                f"Equity below MA50 ({ma50:.2f}) but above MA20 ({ma20:.2f}) "
                f"— moderate underperformance, reducing to 50%."
            )
        else:
            regime = "REDUCED_25"
            scale_factor = 0.25
            scale_reason = (
                f"Equity below BOTH MA20 ({ma20:.2f}) and MA50 ({ma50:.2f}) "
                f"— significant underperformance, reducing to 25%."
            )

        logger.info(
            "Equity curve state: regime=%s scale=%.2f dd=%.2f%% "
            "equity=%.2f ma20=%.2f ma50=%.2f",
            regime,
            scale_factor,
            drawdown_pct,
            current_equity,
            ma20,
            ma50,
        )

        return EquityCurveState(
            current_equity=round(current_equity, 2),
            peak_equity=round(peak_equity, 2),
            drawdown_pct=round(drawdown_pct, 2),
            equity_vs_ma20=round(equity_vs_ma20, 2),
            equity_vs_ma50=round(equity_vs_ma50, 2),
            ma20=round(ma20, 2),
            ma50=round(ma50, 2),
            scale_factor=scale_factor,
            scale_reason=scale_reason,
            is_below_ma20=is_below_ma20,
            is_below_ma50=is_below_ma50,
            regime=regime,
        )

    def apply_scaling(
        self, base_position_pct: float, state: EquityCurveState
    ) -> float:
        """Apply equity curve scale factor to a base position size percentage.

        Args:
            base_position_pct: Base position size as a percentage of capital.
            state: Current equity curve state from :meth:`calculate_state`.

        Returns:
            Scaled position size percentage, rounded to 4 decimal places.
        """
        scaled = base_position_pct * state.scale_factor
        logger.debug(
            "Position scaling: %.4f%% × %.2f = %.4f%%",
            base_position_pct,
            state.scale_factor,
            scaled,
        )
        return round(scaled, 4)

    def get_scale_factor(
        self,
        closed_trades: list[dict],
        starting_equity: float = 10_000.0,
    ) -> float:
        """Convenience method: return only the scale factor (0.25–1.0).

        Args:
            closed_trades: List of closed trade dicts (needs ``pnl_pct``).
            starting_equity: Starting capital.

        Returns:
            Scale factor in the range [0.25, 1.0].
        """
        state = self.calculate_state(closed_trades, starting_equity)
        return state.scale_factor

    def format_explanation(self, state: EquityCurveState) -> str:
        """Human-readable explanation of current scaling decision.

        Args:
            state: Equity curve state.

        Returns:
            Multi-line descriptive explanation string.
        """
        direction_20 = "above" if not state.is_below_ma20 else "below"
        direction_50 = "above" if not state.is_below_ma50 else "below"

        lines = [
            f"Equity Curve Regime: {state.regime}",
            f"Scale Factor: {state.scale_factor:.0%}",
            "",
            f"Current Equity : ${state.current_equity:,.2f}",
            f"Peak Equity    : ${state.peak_equity:,.2f}",
            f"Drawdown       : {state.drawdown_pct:.2f}%",
            "",
            f"MA20  : ${state.ma20:,.2f}  — equity is {direction_20} by "
            f"{abs(state.equity_vs_ma20):.1f}%",
            f"MA50  : ${state.ma50:,.2f}  — equity is {direction_50} by "
            f"{abs(state.equity_vs_ma50):.1f}%",
            "",
            f"Reason: {state.scale_reason}",
        ]
        return "\n".join(lines)

    # ----------------------------------------------------------------- private

    def _build_equity_curve(
        self,
        trades: list[dict],
        starting_equity: float,
    ) -> pd.Series:
        """Convert trade P&L history to a cumulative equity curve series.

        Trades are sorted by ``timestamp`` when available; otherwise the
        original list order is preserved (assumed to be chronological).

        Args:
            trades: List of trade dicts with ``pnl_pct`` key.
            starting_equity: Starting capital value.

        Returns:
            pandas Series of equity values, starting at ``starting_equity``.
        """
        # Sort by timestamp if present
        sorted_trades = sorted(
            trades,
            key=lambda t: t.get("timestamp", datetime.min),
        )

        equity = starting_equity
        equity_values: list[float] = [equity]

        for trade in sorted_trades:
            pnl_pct = float(trade.get("pnl_pct", 0.0))
            equity = equity * (1.0 + pnl_pct / 100.0)
            equity_values.append(equity)

        return pd.Series(equity_values, dtype=float)

    def _calculate_mas(
        self, equity_curve: pd.Series
    ) -> tuple[float, float]:
        """Calculate MA20 and MA50 of the equity curve.

        When the curve is shorter than the window, uses the available data
        (pandas default ``min_periods=1`` via rolling).

        Args:
            equity_curve: Cumulative equity series.

        Returns:
            Tuple of (ma20, ma50) as floats. Returns current equity for
            windows that cannot be computed.
        """
        current = float(equity_curve.iloc[-1])

        if len(equity_curve) < 2:
            return current, current

        ma20_series = equity_curve.rolling(
            window=self.MA_SHORT, min_periods=1
        ).mean()
        ma50_series = equity_curve.rolling(
            window=self.MA_LONG, min_periods=1
        ).mean()

        ma20 = float(ma20_series.iloc[-1])
        ma50 = float(ma50_series.iloc[-1])

        return ma20, ma50

    def _default_full_size_state(self, starting_equity: float) -> EquityCurveState:
        """Return a default FULL_SIZE state when no trade history exists.

        Args:
            starting_equity: Starting capital.

        Returns:
            Full-size :class:`EquityCurveState`.
        """
        return EquityCurveState(
            current_equity=starting_equity,
            peak_equity=starting_equity,
            drawdown_pct=0.0,
            equity_vs_ma20=0.0,
            equity_vs_ma50=0.0,
            ma20=starting_equity,
            ma50=starting_equity,
            scale_factor=1.0,
            scale_reason="No trade history — defaulting to full size.",
            is_below_ma20=False,
            is_below_ma50=False,
            regime="FULL_SIZE",
        )


# Module-level singleton
_scaler: EquityCurveScaler | None = None


def get_equity_curve_scaler() -> EquityCurveScaler:
    """Return the global :class:`EquityCurveScaler` singleton.

    Returns:
        Shared EquityCurveScaler instance.
    """
    global _scaler
    if _scaler is None:
        _scaler = EquityCurveScaler()
    return _scaler
