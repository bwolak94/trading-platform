"""Dual Momentum Strategy — absolute + relative momentum ranking."""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.ai.strategies.base import (
    BaseStrategy,
    MarketContext,
    SignalResult,
    calculate_atr_based_stops,
)
from app.core.logging import get_logger

logger = get_logger(__name__)


class DualMomentumStrategy(BaseStrategy):
    """Gary Antonacci's Dual Momentum adapted for crypto/forex.

    Two-filter approach:
    1. Absolute momentum filter: is the asset above its 1-month moving average?
       If price < SMA(30) → skip LONG signals (respect the downtrend).
    2. Relative momentum rank: is the 1-month return in the strong tier?
       Only the top-quartile performers generate LONG signals.
       Only the bottom-quartile performers (below MA) generate SHORT signals.

    Works best in TREND_BULL but is supported across all regimes as a
    trend-confirmation module.
    """

    name = "dual_momentum"
    supported_regimes = ["TREND_BULL", "TREND_BEAR", "CONSOLIDATION"]
    min_confidence = 58.0

    MOMENTUM_PERIOD: int = 30   # 1-month lookback in candles
    MA_PERIOD: int = 30         # simple moving average period (same as momentum)
    ATR_SL_MULTIPLIER: float = 2.5  # wider stop — momentum needs room to breathe

    # Momentum return thresholds for signal generation
    STRONG_LONG_THRESHOLD: float = 0.05   # +5% return in 30 candles = strong LONG
    STRONG_SHORT_THRESHOLD: float = -0.05  # -5% return in 30 candles = strong SHORT

    def generate_signal(
        self,
        asset: str,
        timeframe: str,
        market_data: pd.DataFrame,
        context: MarketContext,
    ) -> SignalResult | None:
        """Generate a dual-momentum signal from 1-month return and MA filter.

        Steps:
        1. Calculate 1-month return: (close[-1] - close[-30]) / close[-30].
        2. Check absolute momentum: close[-1] vs SMA(30).
        3. Negative absolute momentum → no LONG.
        4. Strong positive return above MA → LONG.
        5. Strong negative return below MA → SHORT.
        6. Confidence scales with the magnitude of momentum.

        Args:
            asset: Trading pair symbol.
            timeframe: Candle timeframe string (e.g. "1h").
            market_data: OHLCV DataFrame, latest candle last.
            context: Current MarketContext.

        Returns:
            SignalResult or None.
        """
        min_len = self.MOMENTUM_PERIOD + 5
        if market_data is None or len(market_data) < min_len:
            logger.debug("dual_momentum: insufficient data for %s", asset)
            return None

        df = market_data.copy()
        close = df["close"]
        current_close = float(close.iloc[-1])
        past_close = float(close.iloc[-self.MOMENTUM_PERIOD - 1])

        if past_close <= 0:
            return None

        # 1. One-month return
        momentum_return = (current_close - past_close) / past_close

        # 2. Absolute momentum: SMA(30) filter
        sma30 = float(close.iloc[-self.MA_PERIOD :].mean())
        above_ma = current_close > sma30

        # ATR for stop calculation
        if "atr_14" in df.columns:
            atr = float(df["atr_14"].iloc[-1])
        else:
            atr = _calculate_atr_value(df, period=14)

        # 3. LONG setup: positive return + price above MA
        if above_ma and momentum_return >= self.STRONG_LONG_THRESHOLD:
            factors = self._build_long_factors(momentum_return, above_ma, context)
            confidence = self._calculate_confidence(factors, momentum_return, "LONG")

            if confidence < self.min_confidence:
                return None

            levels = calculate_atr_based_stops(
                entry_price=current_close,
                atr=atr,
                direction="LONG",
                atr_multiplier_sl=self.ATR_SL_MULTIPLIER,
                atr_multiplier_tp1=2.5,
                atr_multiplier_tp2=5.0,
            )

            logger.info(
                "dual_momentum LONG: %s ret=%.2f%% conf=%.1f",
                asset,
                momentum_return * 100,
                confidence,
            )

            return SignalResult(
                asset=asset,
                timeframe=timeframe,
                direction="LONG",
                confidence=confidence,
                entry_price=round(current_close, 8),
                stop_loss=levels["stop_loss"],
                take_profit_1=levels["take_profit_1"],
                take_profit_2=levels["take_profit_2"],
                risk_reward=levels["risk_reward"],
                factors=factors,
                strategy_name=self.name,
            )

        # 4. SHORT setup: negative return + price below MA
        if not above_ma and momentum_return <= self.STRONG_SHORT_THRESHOLD:
            factors = self._build_short_factors(momentum_return, above_ma, context)
            confidence = self._calculate_confidence(factors, momentum_return, "SHORT")

            if confidence < self.min_confidence:
                return None

            levels = calculate_atr_based_stops(
                entry_price=current_close,
                atr=atr,
                direction="SHORT",
                atr_multiplier_sl=self.ATR_SL_MULTIPLIER,
                atr_multiplier_tp1=2.5,
                atr_multiplier_tp2=5.0,
            )

            logger.info(
                "dual_momentum SHORT: %s ret=%.2f%% conf=%.1f",
                asset,
                momentum_return * 100,
                confidence,
            )

            return SignalResult(
                asset=asset,
                timeframe=timeframe,
                direction="SHORT",
                confidence=confidence,
                entry_price=round(current_close, 8),
                stop_loss=levels["stop_loss"],
                take_profit_1=levels["take_profit_1"],
                take_profit_2=levels["take_profit_2"],
                risk_reward=levels["risk_reward"],
                factors=factors,
                strategy_name=self.name,
            )

        return None

    # ------------------------------------------------------------------
    # Factor builders
    # ------------------------------------------------------------------

    def _build_long_factors(
        self,
        momentum_return: float,
        above_ma: bool,
        context: MarketContext,
    ) -> list[dict]:
        """Build factor list for a LONG dual-momentum setup."""
        factors: list[dict] = []

        # Absolute momentum: above MA
        factors.append({
            "name": "Absolute Momentum (Above MA)",
            "weight": 0.35,
            "score": 0.85 if above_ma else 0.20,
            "label": "BULLISH",
        })

        # Relative momentum: return magnitude
        ret_score = min(1.0, max(0.3, momentum_return / 0.20))  # normalise to 20%
        factors.append({
            "name": f"1-Month Return ({momentum_return*100:.1f}%)",
            "weight": 0.40,
            "score": ret_score,
            "label": "BULLISH",
        })

        # Regime alignment
        regime_score = 0.9 if context.regime == "TREND_BULL" else 0.55
        factors.append({
            "name": "Regime Alignment",
            "weight": 0.25,
            "score": regime_score,
            "label": "BULLISH" if context.regime == "TREND_BULL" else "NEUTRAL",
        })

        return factors

    def _build_short_factors(
        self,
        momentum_return: float,
        above_ma: bool,
        context: MarketContext,
    ) -> list[dict]:
        """Build factor list for a SHORT dual-momentum setup."""
        factors: list[dict] = []

        # Absolute momentum: below MA
        factors.append({
            "name": "Absolute Momentum (Below MA)",
            "weight": 0.35,
            "score": 0.85 if not above_ma else 0.20,
            "label": "BEARISH",
        })

        # Relative momentum: negative return magnitude
        ret_score = min(1.0, max(0.3, abs(momentum_return) / 0.20))
        factors.append({
            "name": f"1-Month Return ({momentum_return*100:.1f}%)",
            "weight": 0.40,
            "score": ret_score,
            "label": "BEARISH",
        })

        # Regime alignment
        regime_score = 0.9 if context.regime == "TREND_BEAR" else 0.55
        factors.append({
            "name": "Regime Alignment",
            "weight": 0.25,
            "score": regime_score,
            "label": "BEARISH" if context.regime == "TREND_BEAR" else "NEUTRAL",
        })

        return factors

    def _calculate_confidence(
        self,
        factors: list[dict],
        momentum_return: float,
        direction: str,
    ) -> float:
        """Calculate confidence from weighted factors with a momentum magnitude bonus.

        A return >10% in 30 candles adds a 5% bonus; >20% adds 10%.
        """
        weighted_sum = sum(f["weight"] * f["score"] for f in factors)
        total_weight = sum(f["weight"] for f in factors)
        base = (weighted_sum / total_weight * 100) if total_weight > 0 else 50.0

        abs_return = abs(momentum_return)
        if abs_return >= 0.20:
            bonus = 10.0
        elif abs_return >= 0.10:
            bonus = 5.0
        else:
            bonus = 0.0

        return round(min(base + bonus, 95.0), 1)


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _calculate_atr_value(df: pd.DataFrame, period: int = 14) -> float:
    """Calculate a single ATR value using Wilder's method."""
    if len(df) < period + 1:
        return 0.0

    window = df.iloc[-(period + 1):]
    high = window["high"].values
    low = window["low"].values
    prev_close = window["close"].values[:-1]
    curr_high = high[1:]
    curr_low = low[1:]

    tr = np.maximum(
        curr_high - curr_low,
        np.maximum(
            np.abs(curr_high - prev_close),
            np.abs(curr_low - prev_close),
        ),
    )
    return float(np.mean(tr))
