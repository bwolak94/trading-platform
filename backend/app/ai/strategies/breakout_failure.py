"""Bull/Bear Trap — false breakout reversal strategy."""

import pandas as pd

from app.ai.strategies.base import (
    BaseStrategy,
    MarketContext,
    SignalResult,
    calculate_atr_based_stops,
)
from app.core.logging import get_logger

logger = get_logger(__name__)


class BreakoutFailureStrategy(BaseStrategy):
    """Detect false breakouts (bull/bear traps) and trade the reversal.

    Bull trap: price breaks ABOVE resistance, then closes back BELOW it → SHORT.
    Bear trap: price breaks BELOW support, then closes back ABOVE it → LONG.

    Supported regimes: CONSOLIDATION, TREND_BULL, TREND_BEAR.
    """

    name = "breakout_failure"
    supported_regimes = ["CONSOLIDATION", "TREND_BULL", "TREND_BEAR"]
    min_confidence = 60.0

    # Tunable parameters
    RANGE_LOOKBACK = 20          # candles used to define resistance/support range
    BREAKOUT_BUFFER_PCT = 0.001  # 0.1% — how far outside range counts as breakout
    ATR_SL_MULTIPLIER = 1.5      # tight stop — failure should reverse quickly
    RSI_OVERBOUGHT = 70.0
    RSI_OVERSOLD = 30.0
    VOLUME_SPIKE_RATIO = 2.0     # trap candle volume vs average

    def generate_signal(
        self,
        asset: str,
        timeframe: str,
        market_data: pd.DataFrame,
        context: MarketContext,
    ) -> SignalResult | None:
        """Generate a breakout-failure signal if a bull or bear trap is detected.

        Detection steps:
        1. Compute rolling 20-candle high (resistance) and low (support).
        2. Bull trap: previous candle closed above range_high + buffer,
                      current candle closes below range_high.
        3. Bear trap: previous candle closed below range_low - buffer,
                      current candle closes above range_low.
        4. Volume confirmation: breakout candle had elevated volume.
        5. RSI confirmation: overbought at bull trap, oversold at bear trap.
        """
        if market_data.empty or len(market_data) < self.RANGE_LOOKBACK + 5:
            return None

        df = market_data.copy()

        bull_trap = self._check_bull_trap(df)
        if bull_trap:
            return self._build_signal(asset, timeframe, df, "SHORT", bull_trap)

        bear_trap = self._check_bear_trap(df)
        if bear_trap:
            return self._build_signal(asset, timeframe, df, "LONG", bear_trap)

        return None

    # ------------------------------------------------------------------
    # Trap detection helpers
    # ------------------------------------------------------------------

    def _check_bull_trap(self, df: pd.DataFrame) -> dict | None:
        """Detect bull trap: breakout above resistance that closes back inside.

        Returns a dict with factors and metadata, or None if no trap detected.
        """
        prev = df.iloc[-2]
        curr = df.iloc[-1]

        # Define range from candles BEFORE the breakout candle (exclude last 2)
        range_window = df.iloc[-(self.RANGE_LOOKBACK + 2) : -2]
        if len(range_window) < 5:
            return None

        range_high = float(range_window["high"].max())
        range_low = float(range_window["low"].min())
        range_mid = (range_high + range_low) / 2.0

        prev_close = float(prev.get("close", 0))
        curr_close = float(curr.get("close", 0))
        breakout_level = range_high * (1 + self.BREAKOUT_BUFFER_PCT)

        # Condition 1: previous candle closed ABOVE resistance (breakout)
        if prev_close <= breakout_level:
            return None

        # Condition 2: current candle closes BACK BELOW range_high (failure)
        if curr_close >= range_high:
            return None

        factors: list[dict] = []
        confidence_boost = 0.0

        # Base factor: the trap pattern itself
        factors.append({
            "name": "Bull Trap Pattern",
            "weight": 0.40,
            "score": 0.85,
            "label": "BEARISH",
        })

        # Condition 3: RSI overbought on breakout candle
        rsi_prev = float(prev.get("rsi_14", 50))
        if rsi_prev > self.RSI_OVERBOUGHT:
            factors.append({
                "name": "RSI Overbought at Breakout",
                "weight": 0.25,
                "score": min(1.0, (rsi_prev - self.RSI_OVERBOUGHT) / 30.0 + 0.7),
                "label": "BEARISH",
            })
            confidence_boost += 10.0
        else:
            factors.append({
                "name": "RSI at Breakout",
                "weight": 0.15,
                "score": 0.4,
                "label": "NEUTRAL",
            })

        # Condition 4: elevated volume on the breakout/trap candle
        avg_vol = float(df.iloc[-self.RANGE_LOOKBACK - 2 : -2]["volume"].mean())
        trap_vol = float(prev.get("volume", 0))
        vol_ratio = (trap_vol / avg_vol) if avg_vol > 0 else 1.0

        if vol_ratio >= self.VOLUME_SPIKE_RATIO:
            factors.append({
                "name": "Volume Spike on Trap",
                "weight": 0.20,
                "score": min(1.0, vol_ratio / 3.0),
                "label": "BEARISH",
            })
            confidence_boost += 10.0
        else:
            factors.append({
                "name": "Volume on Trap",
                "weight": 0.10,
                "score": max(0.3, vol_ratio / self.VOLUME_SPIKE_RATIO),
                "label": "NEUTRAL",
            })

        # Condition 5: failure candle volume declining (conviction gone)
        curr_vol = float(curr.get("volume", 0))
        if curr_vol < trap_vol * 0.7:
            factors.append({
                "name": "Declining Failure Volume",
                "weight": 0.15,
                "score": 0.75,
                "label": "BEARISH",
            })
            confidence_boost += 5.0

        # HTF context: if regime is TREND_BEAR, adds conviction
        if context.regime == "TREND_BEAR":
            factors.append({
                "name": "HTF Bear Regime Alignment",
                "weight": 0.10,
                "score": 0.80,
                "label": "BEARISH",
            })
            confidence_boost += 5.0

        return {
            "factors": factors,
            "confidence_boost": confidence_boost,
            "range_high": range_high,
            "range_low": range_low,
            "range_mid": range_mid,
        }

    def _check_bear_trap(self, df: pd.DataFrame) -> dict | None:
        """Detect bear trap: breakdown below support that closes back inside.

        Returns a dict with factors and metadata, or None if no trap detected.
        """
        prev = df.iloc[-2]
        curr = df.iloc[-1]

        # Define range from candles BEFORE the breakdown candle (exclude last 2)
        range_window = df.iloc[-(self.RANGE_LOOKBACK + 2) : -2]
        if len(range_window) < 5:
            return None

        range_high = float(range_window["high"].max())
        range_low = float(range_window["low"].min())
        range_mid = (range_high + range_low) / 2.0

        prev_close = float(prev.get("close", 0))
        curr_close = float(curr.get("close", 0))
        breakdown_level = range_low * (1 - self.BREAKOUT_BUFFER_PCT)

        # Condition 1: previous candle closed BELOW support (breakdown)
        if prev_close >= breakdown_level:
            return None

        # Condition 2: current candle closes BACK ABOVE range_low (failure)
        if curr_close <= range_low:
            return None

        factors: list[dict] = []
        confidence_boost = 0.0

        # Base factor: the trap pattern itself
        factors.append({
            "name": "Bear Trap Pattern",
            "weight": 0.40,
            "score": 0.85,
            "label": "BULLISH",
        })

        # Condition 3: RSI oversold on breakdown candle
        rsi_prev = float(prev.get("rsi_14", 50))
        if rsi_prev < self.RSI_OVERSOLD:
            factors.append({
                "name": "RSI Oversold at Breakdown",
                "weight": 0.25,
                "score": min(1.0, (self.RSI_OVERSOLD - rsi_prev) / 30.0 + 0.7),
                "label": "BULLISH",
            })
            confidence_boost += 10.0
        else:
            factors.append({
                "name": "RSI at Breakdown",
                "weight": 0.15,
                "score": 0.4,
                "label": "NEUTRAL",
            })

        # Condition 4: elevated volume on the trap candle
        avg_vol = float(df.iloc[-self.RANGE_LOOKBACK - 2 : -2]["volume"].mean())
        trap_vol = float(prev.get("volume", 0))
        vol_ratio = (trap_vol / avg_vol) if avg_vol > 0 else 1.0

        if vol_ratio >= self.VOLUME_SPIKE_RATIO:
            factors.append({
                "name": "Volume Spike on Trap",
                "weight": 0.20,
                "score": min(1.0, vol_ratio / 3.0),
                "label": "BULLISH",
            })
            confidence_boost += 10.0
        else:
            factors.append({
                "name": "Volume on Trap",
                "weight": 0.10,
                "score": max(0.3, vol_ratio / self.VOLUME_SPIKE_RATIO),
                "label": "NEUTRAL",
            })

        # Condition 5: failure candle volume declining
        curr_vol = float(curr.get("volume", 0))
        if curr_vol < trap_vol * 0.7:
            factors.append({
                "name": "Declining Failure Volume",
                "weight": 0.15,
                "score": 0.75,
                "label": "BULLISH",
            })
            confidence_boost += 5.0

        # HTF context: if regime is TREND_BULL, adds conviction
        if context.regime == "TREND_BULL":
            factors.append({
                "name": "HTF Bull Regime Alignment",
                "weight": 0.10,
                "score": 0.80,
                "label": "BULLISH",
            })
            confidence_boost += 5.0

        return {
            "factors": factors,
            "confidence_boost": confidence_boost,
            "range_high": range_high,
            "range_low": range_low,
            "range_mid": range_mid,
        }

    # ------------------------------------------------------------------
    # Signal builder
    # ------------------------------------------------------------------

    def _build_signal(
        self,
        asset: str,
        timeframe: str,
        df: pd.DataFrame,
        direction: str,
        trap_data: dict,
    ) -> SignalResult:
        """Build SignalResult from trap data."""
        last = df.iloc[-1]
        close = float(last.get("close", 0))
        atr = float(last.get("atr_14", 0))

        range_high: float = trap_data["range_high"]
        range_low: float = trap_data["range_low"]
        range_mid: float = trap_data["range_mid"]

        # ATR-based stops with tight 1.5x multiplier
        if atr > 0:
            levels = calculate_atr_based_stops(
                entry_price=close,
                atr=atr,
                direction=direction,
                atr_multiplier_sl=self.ATR_SL_MULTIPLIER,
                atr_multiplier_tp1=2.0,
                atr_multiplier_tp2=4.0,
            )
            stop_loss = levels["stop_loss"]
            # TP1: back to range midpoint; TP2: opposite range extreme
            if direction == "SHORT":
                tp1 = range_mid
                tp2 = range_low
            else:
                tp1 = range_mid
                tp2 = range_high
        else:
            # Fallback when ATR is not available
            if direction == "SHORT":
                stop_loss = round(range_high * 1.005, 8)
                tp1 = range_mid
                tp2 = range_low
            else:
                stop_loss = round(range_low * 0.995, 8)
                tp1 = range_mid
                tp2 = range_high

        risk = abs(close - stop_loss)
        reward = abs(tp1 - close)
        risk_reward = round(reward / risk, 2) if risk > 0 else 0.0

        confidence = self._calculate_confidence(
            trap_data["factors"], trap_data["confidence_boost"]
        )

        logger.info(
            "Breakout failure signal",
            extra={
                "asset": asset,
                "direction": direction,
                "confidence": confidence,
                "range_high": range_high,
                "range_low": range_low,
            },
        )

        return SignalResult(
            asset=asset,
            timeframe=timeframe,
            direction=direction,
            confidence=confidence,
            entry_price=round(close, 8),
            stop_loss=round(stop_loss, 8),
            take_profit_1=round(tp1, 8),
            take_profit_2=round(tp2, 8),
            risk_reward=risk_reward,
            factors=trap_data["factors"],
            strategy_name=self.name,
        )

    def _calculate_confidence(self, factors: list[dict], boost: float) -> float:
        """Calculate weighted confidence from factors plus a flat boost."""
        weighted_sum = sum(f["weight"] * f["score"] for f in factors)
        total_weight = sum(f["weight"] for f in factors)
        base = (weighted_sum / total_weight * 100) if total_weight > 0 else 65.0
        return round(min(base + boost, 95.0), 1)
