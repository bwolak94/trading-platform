"""Trend Following Strategy — EMA alignment + ADX + RSI pullback."""

import logging

import numpy as np
import pandas as pd

from app.ai.strategies.base import BaseStrategy, MarketContext, SignalResult

logger = logging.getLogger(__name__)


class TrendFollowingStrategy(BaseStrategy):
    """Trend following using EMA crossover, ADX filter, and RSI pullback.

    Supported regimes: TREND_BULL, TREND_BEAR.
    Logic from 04_AI_ENGINE.md — Strategy 1.
    """

    name = "trend_following"
    supported_regimes = ["TREND_BULL", "TREND_BEAR"]
    min_confidence = 50.0

    # Tunable parameters
    ADX_THRESHOLD = 25.0
    RSI_LONG_MIN = 45.0
    RSI_LONG_MAX = 70.0
    RSI_SHORT_MIN = 30.0
    RSI_SHORT_MAX = 55.0
    VOLUME_MULTIPLIER = 1.2
    PULLBACK_TOLERANCE_ATR = 1.5  # how close to EMA20 counts as pullback
    TP1_MULTIPLIER = 1.5
    TP2_MULTIPLIER = 3.0

    def generate_signal(
        self,
        asset: str,
        timeframe: str,
        market_data: pd.DataFrame,
        context: MarketContext,
    ) -> SignalResult | None:
        """Generate a trend-following signal if conditions are met."""
        if market_data.empty or len(market_data) < 200:
            return None

        df = market_data.copy()
        last = df.iloc[-1]

        long_signal = self._check_long(df, last, context)
        if long_signal:
            return self._build_signal(asset, timeframe, last, "LONG", long_signal)

        short_signal = self._check_short(df, last, context)
        if short_signal:
            return self._build_signal(asset, timeframe, last, "SHORT", short_signal)

        return None

    def _check_long(
        self, df: pd.DataFrame, last: pd.Series, ctx: MarketContext
    ) -> dict | None:
        """Check all LONG entry conditions."""
        factors = []

        # 1. EMA alignment: EMA20 > EMA50 > EMA200
        ema20 = last.get("ema_20", 0)
        ema50 = last.get("ema_50", 0)
        ema200 = last.get("ema_200", 0)
        if not (ema20 > ema50 > ema200):
            return None
        factors.append({"name": "Bullish EMA Alignment", "weight": 0.3, "score": 0.9, "label": "BULLISH"})

        # 2. ADX > 25 (strong trend)
        adx = last.get("adx_14", 0)
        if adx < self.ADX_THRESHOLD:
            return None
        factors.append({"name": "Strong ADX Trend", "weight": 0.2, "score": min(adx / 50, 1.0), "label": "BULLISH"})

        # 3. RSI between 45-70 (not overbought)
        rsi = last.get("rsi_14", 50)
        if not (self.RSI_LONG_MIN <= rsi <= self.RSI_LONG_MAX):
            return None

        # 4. Price pullback to EMA20
        close = last.get("close", 0)
        atr = last.get("atr_14", 0)
        if atr > 0:
            distance_to_ema20 = abs(close - ema20) / atr
            if distance_to_ema20 > self.PULLBACK_TOLERANCE_ATR:
                return None
        factors.append({"name": "EMA20 Pullback Entry", "weight": 0.2, "score": 0.8, "label": "BULLISH"})

        # 5. Volume confirmation
        volume_ratio = last.get("volume_vs_avg", 1.0)
        if volume_ratio < self.VOLUME_MULTIPLIER:
            return None
        factors.append({"name": "Volume Confirmation", "weight": 0.15, "score": min(volume_ratio / 2, 1.0), "label": "BULLISH"})

        # ADX divergence check: ADX declining while price moves strongly = weakening trend
        if len(df) >= 5:
            adx_slope = df["adx_14"].iloc[-1] - df["adx_14"].iloc[-5]
            price_slope = (df["close"].iloc[-1] - df["close"].iloc[-5]) / df["close"].iloc[-5]
            if adx_slope < 0 and abs(price_slope) > 0.02:
                factors.append({"name": "ADX Divergence Warning", "weight": -0.1, "score": 0.3, "label": "CAUTION"})

        return {"factors": factors, "direction": "LONG"}

    def _check_short(
        self, df: pd.DataFrame, last: pd.Series, ctx: MarketContext
    ) -> dict | None:
        """Check all SHORT entry conditions."""
        factors = []

        # 1. EMA alignment: EMA20 < EMA50 < EMA200
        ema20 = last.get("ema_20", 0)
        ema50 = last.get("ema_50", 0)
        ema200 = last.get("ema_200", 0)
        if not (ema20 < ema50 < ema200):
            return None
        factors.append({"name": "Bearish EMA Alignment", "weight": 0.3, "score": 0.9, "label": "BEARISH"})

        # 2. ADX > 25
        adx = last.get("adx_14", 0)
        if adx < self.ADX_THRESHOLD:
            return None
        factors.append({"name": "Strong ADX Trend", "weight": 0.2, "score": min(adx / 50, 1.0), "label": "BEARISH"})

        # 3. RSI between 30-55 (not oversold)
        rsi = last.get("rsi_14", 50)
        if not (self.RSI_SHORT_MIN <= rsi <= self.RSI_SHORT_MAX):
            return None

        # 4. Price pullback to EMA20
        close = last.get("close", 0)
        atr = last.get("atr_14", 0)
        if atr > 0:
            distance_to_ema20 = abs(close - ema20) / atr
            if distance_to_ema20 > self.PULLBACK_TOLERANCE_ATR:
                return None
        factors.append({"name": "EMA20 Pullback Entry", "weight": 0.2, "score": 0.8, "label": "BEARISH"})

        # 5. Volume confirmation
        volume_ratio = last.get("volume_vs_avg", 1.0)
        if volume_ratio < self.VOLUME_MULTIPLIER:
            return None
        factors.append({"name": "Volume Confirmation", "weight": 0.15, "score": min(volume_ratio / 2, 1.0), "label": "BEARISH"})

        # ADX divergence check: ADX declining while price moves strongly = weakening trend
        if len(df) >= 5:
            adx_slope = df["adx_14"].iloc[-1] - df["adx_14"].iloc[-5]
            price_slope = (df["close"].iloc[-1] - df["close"].iloc[-5]) / df["close"].iloc[-5]
            if adx_slope < 0 and abs(price_slope) > 0.02:
                factors.append({"name": "ADX Divergence Warning", "weight": -0.1, "score": 0.3, "label": "CAUTION"})

        return {"factors": factors, "direction": "SHORT"}

    def _build_signal(
        self,
        asset: str,
        timeframe: str,
        last: pd.Series,
        direction: str,
        check_result: dict,
    ) -> SignalResult:
        """Build a SignalResult with entry, SL, TP levels."""
        close = float(last.get("close", 0))
        atr = float(last.get("atr_14", 0))
        ema50 = float(last.get("ema_50", 0))

        if direction == "LONG":
            # SL: below last swing low or EMA50 - 1 ATR
            stop_loss = min(
                float(last.get("low", close - atr)),
                ema50 - atr,
            )
            risk = close - stop_loss
            tp1 = close + risk * self.TP1_MULTIPLIER
            tp2 = close + risk * self.TP2_MULTIPLIER
        else:
            # SL: above last swing high or EMA50 + 1 ATR
            stop_loss = max(
                float(last.get("high", close + atr)),
                ema50 + atr,
            )
            risk = stop_loss - close
            tp1 = close - risk * self.TP1_MULTIPLIER
            tp2 = close - risk * self.TP2_MULTIPLIER

        risk_reward = (abs(tp1 - close) / risk) if risk > 0 else 0
        confidence = self._calculate_confidence(check_result["factors"], last)

        return SignalResult(
            asset=asset,
            timeframe=timeframe,
            direction=direction,
            confidence=confidence,
            entry_price=close,
            stop_loss=round(stop_loss, 8),
            take_profit_1=round(tp1, 8),
            take_profit_2=round(tp2, 8),
            risk_reward=round(risk_reward, 2),
            factors=check_result["factors"],
            strategy_name=self.name,
        )

    def _calculate_confidence(self, factors: list[dict], last: pd.Series) -> float:
        """Calculate confidence score from factor weights and scores."""
        weighted_sum = sum(f["weight"] * f["score"] for f in factors)
        total_weight = sum(f["weight"] for f in factors)
        base = (weighted_sum / total_weight * 100) if total_weight > 0 else 50

        # Boost from ADX strength
        adx = float(last.get("adx_14", 25))
        adx_boost = min((adx - 25) * 0.3, 10) if adx > 25 else 0

        return round(min(base + adx_boost, 95), 1)
