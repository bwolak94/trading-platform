"""Volatility-Normalized Position Sizing — keeps dollar risk constant across vol regimes.

When volatility is high, the market can move further against a position for the
same percentage loss. This module inversely scales position sizes by volatility
so that the expected dollar loss on a 1 ATR adverse move is constant regardless
of the current vol regime.

Formula:
    position_multiplier = sqrt(baseline_hv / current_hv)

Using square-root scaling (rather than linear) avoids over-correcting: when vol
doubles, position is multiplied by 1/sqrt(2) ≈ 0.71x rather than 0.5x.

Caps and floors applied:
    - Minimum multiplier: 0.25x (never smaller than 25% of normal)
    - Maximum multiplier: 1.0x  (never increase beyond base size)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class VolSizingResult:
    """Result of volatility-adjusted position sizing."""

    base_risk_pct: float         # input risk percentage
    vol_ratio: float             # current_vol / baseline_vol
    adjusted_risk_pct: float     # vol-adjusted risk percentage
    position_multiplier: float   # how much to scale position (0.25 – 1.0)
    current_hv20: float          # current 20-day historical volatility
    baseline_hv20: float         # reference volatility (60-day mean)
    vol_regime: str              # "LOW_VOL", "NORMAL", "HIGH_VOL"
    reasoning: str


class VolatilityNormalizedSizer:
    """Adjusts position sizes inversely to volatility to maintain constant dollar risk.

    Usage::

        sizer = VolatilityNormalizedSizer()
        result = sizer.calculate(df_ohlcv, base_risk_pct=1.0)
        adjusted_position = result.adjusted_risk_pct
    """

    BASELINE_WINDOW: int = 60   # candles for baseline HV
    CURRENT_WINDOW: int = 20    # candles for current HV
    MIN_MULTIPLIER: float = 0.25
    MAX_MULTIPLIER: float = 1.0

    # ----------------------------------------------------------------------- public

    def calculate(
        self,
        df: pd.DataFrame,
        base_risk_pct: float,
    ) -> VolSizingResult:
        """Calculate volatility-adjusted position size.

        Steps:
        1. Calculate current HV (CURRENT_WINDOW days) from ``df``
        2. Calculate baseline HV (BASELINE_WINDOW days) from ``df``
        3. vol_ratio = current_hv / baseline_hv
        4. multiplier = sqrt(1 / vol_ratio), capped at [MIN, MAX]
        5. adjusted_risk = base_risk * multiplier

        Args:
            df: OHLCV DataFrame; must contain a ``close`` column. At least
                ``BASELINE_WINDOW`` rows are needed for a meaningful baseline.
            base_risk_pct: Unadjusted risk-per-trade as a percentage of capital.

        Returns:
            :class:`VolSizingResult` with all sizing data.
        """
        try:
            if "close" not in df.columns:
                raise ValueError("DataFrame must contain a 'close' column")

            close = df["close"].dropna()

            if len(close) < self.CURRENT_WINDOW + 1:
                logger.warning(
                    "VolSizer: not enough data (%d rows) for HV calculation "
                    "— returning base risk",
                    len(close),
                )
                return self._fallback_result(base_risk_pct, reason="Insufficient data")

            current_hv = self._calc_hv(close, self.CURRENT_WINDOW)

            # If we have enough history for baseline; otherwise reuse current_hv
            if len(close) >= self.BASELINE_WINDOW + 1:
                baseline_hv = self._calc_hv(close, self.BASELINE_WINDOW)
            else:
                baseline_hv = current_hv
                logger.debug(
                    "VolSizer: not enough data for %d-period baseline, "
                    "using current HV as baseline",
                    self.BASELINE_WINDOW,
                )

            if baseline_hv <= 0:
                return self._fallback_result(base_risk_pct, reason="Zero baseline HV")

            multiplier, vol_ratio, vol_regime = self._compute_multiplier(
                current_hv, baseline_hv
            )
            adjusted_risk_pct = round(base_risk_pct * multiplier, 4)

            reasoning = (
                f"Vol ratio {vol_ratio:.2f}x (HV20={current_hv:.1%} vs "
                f"baseline={baseline_hv:.1%}). "
                f"Scaling position by {multiplier:.2f}x → {adjusted_risk_pct:.4f}%."
            )

            logger.info(
                "VolSizer: vol_regime=%s ratio=%.2f multiplier=%.2f "
                "base_risk=%.4f adjusted=%.4f",
                vol_regime,
                vol_ratio,
                multiplier,
                base_risk_pct,
                adjusted_risk_pct,
            )

            return VolSizingResult(
                base_risk_pct=base_risk_pct,
                vol_ratio=round(vol_ratio, 4),
                adjusted_risk_pct=adjusted_risk_pct,
                position_multiplier=round(multiplier, 4),
                current_hv20=round(current_hv, 6),
                baseline_hv20=round(baseline_hv, 6),
                vol_regime=vol_regime,
                reasoning=reasoning,
            )

        except Exception as exc:
            logger.exception("VolSizer: unexpected error: %s", exc)
            return self._fallback_result(base_risk_pct, reason=f"Error: {exc}")

    def get_multiplier_from_atr(
        self,
        current_atr: float,
        baseline_atr: float,
    ) -> float:
        """ATR-based position multiplier: simpler alternative to HV.

        Args:
            current_atr: Current ATR value.
            baseline_atr: Reference ATR value (e.g. 60-period mean ATR).

        Returns:
            Position multiplier in the range [MIN_MULTIPLIER, MAX_MULTIPLIER].
        """
        if baseline_atr <= 0 or current_atr <= 0:
            logger.warning("VolSizer ATR: invalid ATR values — returning 1.0")
            return 1.0

        vol_ratio = current_atr / baseline_atr
        multiplier, _, _ = self._compute_multiplier_from_ratio(vol_ratio)
        return multiplier

    # ----------------------------------------------------------------------- private

    def _calc_hv(self, close: pd.Series, window: int) -> float:
        """Calculate annualized historical volatility over a rolling window.

        Uses log-return standard deviation scaled by sqrt(252) for annualisation.

        Args:
            close: Closing price series (at least ``window + 1`` elements).
            window: Look-back period in candles/days.

        Returns:
            Annualized HV as a float (e.g. 0.80 = 80% annualized vol).
        """
        log_returns = np.log(close / close.shift(1)).dropna()

        if len(log_returns) < window:
            # Use available data with min_periods=1
            rolling_std = log_returns.std()
        else:
            rolling_std = log_returns.iloc[-window:].std()

        annualized_hv = float(rolling_std) * np.sqrt(252)
        return max(annualized_hv, 1e-8)  # prevent exact zero

    def _compute_multiplier(
        self,
        current_hv: float,
        baseline_hv: float,
    ) -> tuple[float, float, str]:
        """Compute position multiplier from HV values.

        Args:
            current_hv: Current historical volatility.
            baseline_hv: Baseline (reference) historical volatility.

        Returns:
            Tuple of (multiplier, vol_ratio, vol_regime_label).
        """
        vol_ratio = current_hv / baseline_hv
        return self._compute_multiplier_from_ratio(vol_ratio)

    def _compute_multiplier_from_ratio(
        self, vol_ratio: float
    ) -> tuple[float, float, str]:
        """Compute multiplier, classify regime from a pre-computed vol ratio.

        Args:
            vol_ratio: current_vol / baseline_vol.

        Returns:
            Tuple of (multiplier, vol_ratio, vol_regime_label).
        """
        # sqrt scaling: multiplier = sqrt(1 / vol_ratio)
        raw_multiplier = np.sqrt(1.0 / max(vol_ratio, 1e-8))
        multiplier = float(
            np.clip(raw_multiplier, self.MIN_MULTIPLIER, self.MAX_MULTIPLIER)
        )

        if vol_ratio < 0.8:
            vol_regime = "LOW_VOL"
        elif vol_ratio > 1.4:
            vol_regime = "HIGH_VOL"
        else:
            vol_regime = "NORMAL"

        return round(multiplier, 4), round(vol_ratio, 4), vol_regime

    def _fallback_result(
        self, base_risk_pct: float, reason: str = ""
    ) -> VolSizingResult:
        """Return a neutral (no-adjustment) result when calculation fails.

        Args:
            base_risk_pct: Original risk percentage to pass through.
            reason: Human-readable reason for the fallback.

        Returns:
            :class:`VolSizingResult` with multiplier = 1.0.
        """
        return VolSizingResult(
            base_risk_pct=base_risk_pct,
            vol_ratio=1.0,
            adjusted_risk_pct=base_risk_pct,
            position_multiplier=1.0,
            current_hv20=0.0,
            baseline_hv20=0.0,
            vol_regime="NORMAL",
            reasoning=reason or "Using base risk — no vol adjustment applied.",
        )


# Module-level singleton
_vol_sizer: VolatilityNormalizedSizer | None = None


def get_vol_sizer() -> VolatilityNormalizedSizer:
    """Return the global :class:`VolatilityNormalizedSizer` singleton.

    Returns:
        Shared VolatilityNormalizedSizer instance.
    """
    global _vol_sizer
    if _vol_sizer is None:
        _vol_sizer = VolatilityNormalizedSizer()
    return _vol_sizer
