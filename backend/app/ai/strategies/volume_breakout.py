"""Volume Breakout Strategy — consolidation range breakout with volume spike."""

import logging

import pandas as pd

from app.ai.strategies.base import BaseStrategy, MarketContext, SignalResult

logger = logging.getLogger(__name__)


class VolumeBreakoutStrategy(BaseStrategy):
    """Breakout detection from consolidation with volume confirmation.

    Supported regimes: all (priority: CONSOLIDATION).
    Logic from 04_AI_ENGINE.md — Strategy 4.
    """

    name = "volume_breakout"
    supported_regimes = ["CONSOLIDATION", "TREND_BULL", "TREND_BEAR", "HIGH_VOL_CHOPPY"]
    min_confidence = 50.0

    # Tunable parameters
    CONSOLIDATION_CANDLES = 10
    RANGE_ATR_THRESHOLD = 2.0  # range must be < 2x ATR to count as consolidation
    VOLUME_SPIKE_MULTIPLIER = 2.0
    SL_ATR_MULTIPLIER = 1.0
    TP1_MULTIPLIER = 1.5
    TP2_MULTIPLIER = 3.0

    def generate_signal(
        self,
        asset: str,
        timeframe: str,
        market_data: pd.DataFrame,
        context: MarketContext,
    ) -> SignalResult | None:
        """Generate a breakout signal if conditions are met."""
        if market_data.empty or len(market_data) < self.CONSOLIDATION_CANDLES + 5:
            return None

        df = market_data.copy()
        last = df.iloc[-1]

        consolidation = self._detect_consolidation(df)
        if not consolidation:
            return None

        breakout = self._detect_breakout(df, last, consolidation)
        if not breakout:
            return None

        return self._build_signal(asset, timeframe, last, consolidation, breakout)

    def _detect_consolidation(self, df: pd.DataFrame) -> dict | None:
        """Detect a consolidation range in the candles before the last one.

        Looks for CONSOLIDATION_CANDLES candles within a tight range (< 2x ATR).
        """
        # Exclude the last candle (potential breakout candle)
        window = df.iloc[-(self.CONSOLIDATION_CANDLES + 1) : -1]
        if len(window) < self.CONSOLIDATION_CANDLES:
            return None

        range_high = float(window["high"].max())
        range_low = float(window["low"].min())
        price_range = range_high - range_low

        atr = float(window["atr_14"].iloc[-1]) if "atr_14" in window.columns else 0
        if atr <= 0:
            return None

        # Range must be tight relative to ATR
        if price_range / atr > self.RANGE_ATR_THRESHOLD:
            return None

        return {
            "range_high": range_high,
            "range_low": range_low,
            "range_mid": (range_high + range_low) / 2,
            "atr": atr,
            "candles": self.CONSOLIDATION_CANDLES,
        }

    def _detect_breakout(
        self, df: pd.DataFrame, last: pd.Series, consolidation: dict
    ) -> dict | None:
        """Check if the last candle breaks out of the consolidation range with volume."""
        close = float(last.get("close", 0))
        volume_ratio = float(last.get("volume_vs_avg", 1.0))

        # Volume must spike
        if volume_ratio < self.VOLUME_SPIKE_MULTIPLIER:
            return None

        range_high = consolidation["range_high"]
        range_low = consolidation["range_low"]

        factors = []

        # Bullish breakout: close above range high
        if close > range_high:
            factors.append({
                "name": "Upside Range Breakout",
                "weight": 0.35,
                "score": min((close - range_high) / consolidation["atr"] * 0.5 + 0.6, 1.0),
                "label": "BULLISH",
            })
            factors.append({
                "name": "Volume Spike",
                "weight": 0.3,
                "score": min(volume_ratio / 4, 1.0),
                "label": "BULLISH",
            })
            factors.append({
                "name": "Consolidation Base",
                "weight": 0.2,
                "score": min(consolidation["candles"] / 20, 1.0),
                "label": "BULLISH",
            })
            return {"direction": "LONG", "factors": factors}

        # Bearish breakout: close below range low
        if close < range_low:
            factors.append({
                "name": "Downside Range Breakout",
                "weight": 0.35,
                "score": min((range_low - close) / consolidation["atr"] * 0.5 + 0.6, 1.0),
                "label": "BEARISH",
            })
            factors.append({
                "name": "Volume Spike",
                "weight": 0.3,
                "score": min(volume_ratio / 4, 1.0),
                "label": "BEARISH",
            })
            factors.append({
                "name": "Consolidation Base",
                "weight": 0.2,
                "score": min(consolidation["candles"] / 20, 1.0),
                "label": "BEARISH",
            })
            return {"direction": "SHORT", "factors": factors}

        return None

    def _build_signal(
        self,
        asset: str,
        timeframe: str,
        last: pd.Series,
        consolidation: dict,
        breakout: dict,
    ) -> SignalResult:
        """Build SignalResult with breakout levels."""
        close = float(last.get("close", 0))
        atr = consolidation["atr"]
        direction = breakout["direction"]

        if direction == "LONG":
            # SL just below the consolidation range
            stop_loss = consolidation["range_low"] - atr * self.SL_ATR_MULTIPLIER
            risk = close - stop_loss
            tp1 = close + risk * self.TP1_MULTIPLIER
            tp2 = close + risk * self.TP2_MULTIPLIER
        else:
            # SL just above the consolidation range
            stop_loss = consolidation["range_high"] + atr * self.SL_ATR_MULTIPLIER
            risk = stop_loss - close
            tp1 = close - risk * self.TP1_MULTIPLIER
            tp2 = close - risk * self.TP2_MULTIPLIER

        risk_abs = abs(close - stop_loss)
        risk_reward = abs(tp1 - close) / risk_abs if risk_abs > 0 else 0
        confidence = self._calculate_confidence(breakout["factors"])

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
            factors=breakout["factors"],
            strategy_name=self.name,
        )

    def _calculate_confidence(self, factors: list[dict]) -> float:
        """Calculate confidence from weighted factors."""
        weighted_sum = sum(f["weight"] * f["score"] for f in factors)
        total_weight = sum(f["weight"] for f in factors)
        base = (weighted_sum / total_weight * 100) if total_weight > 0 else 50
        return round(min(base, 95), 1)
