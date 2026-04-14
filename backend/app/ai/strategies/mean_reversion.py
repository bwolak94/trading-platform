"""Mean Reversion Strategy — RSI Divergence + Bollinger Bands."""

import logging

import numpy as np
import pandas as pd

from app.ai.strategies.base import BaseStrategy, MarketContext, SignalResult

logger = logging.getLogger(__name__)


class MeanReversionStrategy(BaseStrategy):
    """Mean reversion using RSI divergence and Bollinger Band extremes.

    Supported regimes: CONSOLIDATION.
    Logic from 04_AI_ENGINE.md — Strategy 2.
    """

    name = "mean_reversion"
    supported_regimes = ["CONSOLIDATION"]
    min_confidence = 50.0

    # Tunable parameters
    RSI_OVERSOLD = 35.0
    RSI_OVERBOUGHT = 65.0
    BB_PROXIMITY_PCT = 0.02  # within 2% of band
    DIVERGENCE_LOOKBACK = 14
    TP1_TARGET = "bb_middle"
    TP2_TARGET = "bb_opposite"
    SL_ATR_MULTIPLIER = 0.5

    def generate_signal(
        self,
        asset: str,
        timeframe: str,
        market_data: pd.DataFrame,
        context: MarketContext,
    ) -> SignalResult | None:
        """Generate a mean-reversion signal if conditions are met."""
        if market_data.empty or len(market_data) < 50:
            return None

        df = market_data.copy()
        last = df.iloc[-1]

        long_result = self._check_long(df, last)
        if long_result:
            return self._build_signal(asset, timeframe, df, last, "LONG", long_result)

        short_result = self._check_short(df, last)
        if short_result:
            return self._build_signal(asset, timeframe, df, last, "SHORT", short_result)

        return None

    def _check_long(self, df: pd.DataFrame, last: pd.Series) -> dict | None:
        """Check LONG conditions: price near lower BB, RSI oversold, bullish divergence."""
        factors = []
        close = last.get("close", 0)
        bb_lower = last.get("bb_lower", 0)
        bb_width = last.get("bb_width", 0)

        if bb_lower <= 0 or bb_width <= 0:
            return None

        # 1. Price near lower Bollinger Band (within 2%)
        distance_pct = (close - bb_lower) / close if close > 0 else 1
        if distance_pct > self.BB_PROXIMITY_PCT:
            return None
        factors.append({
            "name": "Lower BB Touch",
            "weight": 0.3,
            "score": max(0.5, 1.0 - distance_pct * 50),
            "label": "BULLISH",
        })

        # 2. RSI < 35 (oversold)
        rsi = last.get("rsi_14", 50)
        if rsi >= self.RSI_OVERSOLD:
            return None
        factors.append({
            "name": "RSI Oversold",
            "weight": 0.25,
            "score": max(0.5, (self.RSI_OVERSOLD - rsi) / self.RSI_OVERSOLD),
            "label": "BULLISH",
        })

        # 3. Bullish divergence (price lower low, RSI higher low)
        if self._has_bullish_divergence(df):
            factors.append({
                "name": "Bullish RSI Divergence",
                "weight": 0.3,
                "score": 0.85,
                "label": "BULLISH",
            })

        # 4. Reversal candle (close > open on last candle)
        candle_open = last.get("open", 0)
        if close <= candle_open:
            return None
        factors.append({
            "name": "Bullish Reversal Candle",
            "weight": 0.15,
            "score": 0.7,
            "label": "BULLISH",
        })

        return {"factors": factors}

    def _check_short(self, df: pd.DataFrame, last: pd.Series) -> dict | None:
        """Check SHORT conditions: price near upper BB, RSI overbought, bearish divergence."""
        factors = []
        close = last.get("close", 0)
        bb_upper = last.get("bb_upper", 0)
        bb_width = last.get("bb_width", 0)

        if bb_upper <= 0 or bb_width <= 0:
            return None

        # 1. Price near upper Bollinger Band (within 2%)
        distance_pct = (bb_upper - close) / close if close > 0 else 1
        if distance_pct > self.BB_PROXIMITY_PCT:
            return None
        factors.append({
            "name": "Upper BB Touch",
            "weight": 0.3,
            "score": max(0.5, 1.0 - distance_pct * 50),
            "label": "BEARISH",
        })

        # 2. RSI > 65 (overbought)
        rsi = last.get("rsi_14", 50)
        if rsi <= self.RSI_OVERBOUGHT:
            return None
        factors.append({
            "name": "RSI Overbought",
            "weight": 0.25,
            "score": max(0.5, (rsi - self.RSI_OVERBOUGHT) / (100 - self.RSI_OVERBOUGHT)),
            "label": "BEARISH",
        })

        # 3. Bearish divergence (price higher high, RSI lower high)
        if self._has_bearish_divergence(df):
            factors.append({
                "name": "Bearish RSI Divergence",
                "weight": 0.3,
                "score": 0.85,
                "label": "BEARISH",
            })

        # 4. Reversal candle (close < open on last candle)
        candle_open = last.get("open", 0)
        if close >= candle_open:
            return None
        factors.append({
            "name": "Bearish Reversal Candle",
            "weight": 0.15,
            "score": 0.7,
            "label": "BEARISH",
        })

        return {"factors": factors}

    def _has_bullish_divergence(self, df: pd.DataFrame) -> bool:
        """Detect bullish divergence: price makes lower low, RSI makes higher low."""
        lookback = self.DIVERGENCE_LOOKBACK
        if len(df) < lookback + 2:
            return False

        recent = df.iloc[-lookback:]
        close = recent["close"]
        rsi = recent.get("rsi_14")
        if rsi is None:
            return False

        # Find two local lows in price
        price_lows = _find_local_minima(close)
        rsi_lows = _find_local_minima(rsi)

        if len(price_lows) < 2 or len(rsi_lows) < 2:
            return False

        # Price: lower low
        price_lower = close.iloc[price_lows[-1]] < close.iloc[price_lows[-2]]
        # RSI: higher low
        rsi_higher = rsi.iloc[rsi_lows[-1]] > rsi.iloc[rsi_lows[-2]]

        return price_lower and rsi_higher

    def _has_bearish_divergence(self, df: pd.DataFrame) -> bool:
        """Detect bearish divergence: price makes higher high, RSI makes lower high."""
        lookback = self.DIVERGENCE_LOOKBACK
        if len(df) < lookback + 2:
            return False

        recent = df.iloc[-lookback:]
        close = recent["close"]
        rsi = recent.get("rsi_14")
        if rsi is None:
            return False

        price_highs = _find_local_maxima(close)
        rsi_highs = _find_local_maxima(rsi)

        if len(price_highs) < 2 or len(rsi_highs) < 2:
            return False

        price_higher = close.iloc[price_highs[-1]] > close.iloc[price_highs[-2]]
        rsi_lower = rsi.iloc[rsi_highs[-1]] < rsi.iloc[rsi_highs[-2]]

        return price_higher and rsi_lower

    def _build_signal(
        self,
        asset: str,
        timeframe: str,
        df: pd.DataFrame,
        last: pd.Series,
        direction: str,
        check_result: dict,
    ) -> SignalResult:
        """Build SignalResult with mean-reversion levels."""
        close = float(last.get("close", 0))
        atr = float(last.get("atr_14", 0))
        bb_middle = float(last.get("bb_middle", close))
        bb_upper = float(last.get("bb_upper", close))
        bb_lower = float(last.get("bb_lower", close))

        if direction == "LONG":
            low = float(last.get("low", close))
            stop_loss = low - atr * self.SL_ATR_MULTIPLIER
            tp1 = bb_middle
            tp2 = bb_upper
        else:
            high = float(last.get("high", close))
            stop_loss = high + atr * self.SL_ATR_MULTIPLIER
            tp1 = bb_middle
            tp2 = bb_lower

        risk = abs(close - stop_loss)
        reward = abs(tp1 - close)
        risk_reward = (reward / risk) if risk > 0 else 0

        confidence = self._calculate_confidence(check_result["factors"])

        # Early exit at mid-BB if quick bounce
        early_exit = bb_middle
        check_result["factors"].append({"name": "Early Exit Target", "weight": 0.0, "score": 0.0, "label": "INFO", "early_exit_price": round(early_exit, 8)})

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

    def _calculate_confidence(self, factors: list[dict]) -> float:
        """Calculate confidence from weighted factors."""
        weighted_sum = sum(f["weight"] * f["score"] for f in factors)
        total_weight = sum(f["weight"] for f in factors)
        base = (weighted_sum / total_weight * 100) if total_weight > 0 else 50

        # Divergence presence gives a boost
        has_divergence = any("Divergence" in f["name"] for f in factors)
        boost = 5.0 if has_divergence else 0.0

        return round(min(base + boost, 95), 1)


def _find_local_minima(series: pd.Series, order: int = 2) -> list[int]:
    """Find indices of local minima in a series."""
    minima = []
    values = series.values
    for i in range(order, len(values) - order):
        if all(values[i] <= values[i - j] for j in range(1, order + 1)) and \
           all(values[i] <= values[i + j] for j in range(1, order + 1)):
            minima.append(i)
    return minima


def _find_local_maxima(series: pd.Series, order: int = 2) -> list[int]:
    """Find indices of local maxima in a series."""
    maxima = []
    values = series.values
    for i in range(order, len(values) - order):
        if all(values[i] >= values[i - j] for j in range(1, order + 1)) and \
           all(values[i] >= values[i + j] for j in range(1, order + 1)):
            maxima.append(i)
    return maxima
