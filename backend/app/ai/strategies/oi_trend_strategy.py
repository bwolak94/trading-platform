"""OI Trend Divergence Strategy — trades Open Interest / Price divergences."""

import numpy as np
import pandas as pd

from app.ai.strategies.base import BaseStrategy, MarketContext, SignalResult
from app.core.logging import get_logger

logger = get_logger(__name__)


class OITrendDivergenceStrategy(BaseStrategy):
    """Strategy based on Open Interest and price trend divergence.

    Pattern matrix (most profitable crypto patterns):
    1. OI_RISING + PRICE_FALLING = DISTRIBUTION → SHORT (highest confidence: 75%)
    2. OI_FALLING + PRICE_RISING = SHORT_SQUEEZE → LONG (high confidence: 70%)
    3. OI_RISING + PRICE_RISING = HEALTHY_TREND → follow trend direction
    4. OI_FALLING + PRICE_FALLING = CAPITULATION → potential reversal soon

    Requires 'oi_change_pct' column in market_data or context.
    """

    name = "oi_trend_divergence"
    supported_regimes = ["TREND_BULL", "TREND_BEAR", "CONSOLIDATION"]
    min_confidence = 60.0

    OI_SIGNIFICANT_CHANGE = 3.0    # % change in OI to be significant
    PRICE_SIGNIFICANT_CHANGE = 1.0  # % price change to be significant

    # ATR multipliers
    SL_ATR_MULTIPLIER = 2.0
    TP1_ATR_MULTIPLIER = 2.0
    TP2_ATR_MULTIPLIER = 4.0

    # Lookback window to measure OI and price change
    LOOKBACK_BARS = 6

    def generate_signal(
        self,
        asset: str,
        timeframe: str,
        market_data: pd.DataFrame,
        context: MarketContext,
    ) -> SignalResult | None:
        """Generate signal from OI/price divergence pattern.

        Steps:
        1. Extract OI change % and price change % over lookback window
        2. Classify the OI/price pattern
        3. Apply RSI and volume filters
        4. Emit the appropriate directional signal
        """
        if market_data.empty or len(market_data) < max(self.LOOKBACK_BARS + 2, 20):
            logger.debug("Insufficient market data for OI strategy on %s", asset)
            return None

        df = market_data.copy()
        last = df.iloc[-1]

        # --- 1. Resolve OI change ---
        oi_change_pct = self._get_oi_change(df, last, context)
        if oi_change_pct is None:
            return None

        # --- 2. Compute price change over same lookback ---
        lookback = min(self.LOOKBACK_BARS, len(df) - 1)
        price_now = float(df["close"].iloc[-1])
        price_past = float(df["close"].iloc[-1 - lookback])
        if price_past == 0:
            return None
        price_change_pct = (price_now - price_past) / price_past * 100

        # --- 3. Classify pattern ---
        oi_rising = oi_change_pct >= self.OI_SIGNIFICANT_CHANGE
        oi_falling = oi_change_pct <= -self.OI_SIGNIFICANT_CHANGE
        price_rising = price_change_pct >= self.PRICE_SIGNIFICANT_CHANGE
        price_falling = price_change_pct <= -self.PRICE_SIGNIFICANT_CHANGE

        atr = self._get_atr(df, last)
        if atr <= 0:
            return None

        rsi = self._get_rsi(df, last)
        volume_ratio = float(last.get("volume_vs_avg", 1.0))

        # Pattern 1: OI rising + price falling = DISTRIBUTION → SHORT
        if oi_rising and price_falling:
            result = self._build_distribution_short(
                last, oi_change_pct, price_change_pct, rsi, volume_ratio
            )
            if result:
                return self._build_signal(
                    asset, timeframe, price_now, atr, "SHORT", result, context
                )

        # Pattern 2: OI falling + price rising = SHORT_SQUEEZE → LONG
        elif oi_falling and price_rising:
            result = self._build_squeeze_long(
                last, oi_change_pct, price_change_pct, rsi, volume_ratio
            )
            if result:
                return self._build_signal(
                    asset, timeframe, price_now, atr, "LONG", result, context
                )

        # Pattern 3a: OI rising + price rising = HEALTHY BULL TREND → LONG
        elif oi_rising and price_rising and context.regime == "TREND_BULL":
            result = self._build_trend_confirmation(
                "LONG", oi_change_pct, price_change_pct, rsi, volume_ratio
            )
            if result:
                return self._build_signal(
                    asset, timeframe, price_now, atr, "LONG", result, context
                )

        # Pattern 3b: OI rising + price falling aggressively = TREND_BEAR acceleration → SHORT
        elif oi_rising and price_falling and context.regime == "TREND_BEAR":
            result = self._build_trend_confirmation(
                "SHORT", oi_change_pct, price_change_pct, rsi, volume_ratio
            )
            if result:
                return self._build_signal(
                    asset, timeframe, price_now, atr, "SHORT", result, context
                )

        return None

    def _build_distribution_short(
        self,
        last: pd.Series,
        oi_change_pct: float,
        price_change_pct: float,
        rsi: float,
        volume_ratio: float,
    ) -> dict | None:
        """OI rising + price falling = smart money distributing into strength."""
        factors: list[dict] = []

        # Core divergence factor
        divergence_strength = min(
            (abs(oi_change_pct) / self.OI_SIGNIFICANT_CHANGE) *
            (abs(price_change_pct) / self.PRICE_SIGNIFICANT_CHANGE),
            2.0,
        ) / 2.0
        factors.append({
            "name": f"OI Rising +{oi_change_pct:.1f}% / Price Falling {price_change_pct:.1f}% (Distribution)",
            "weight": 0.40,
            "score": min(divergence_strength + 0.4, 1.0),
            "label": "BEARISH",
        })

        # RSI: ideally still above 45 (hasn't fully flushed yet)
        if rsi > 55:
            factors.append({
                "name": f"RSI Extended ({rsi:.0f}) — Room to Fall",
                "weight": 0.20,
                "score": min((rsi - 50) / 50, 1.0),
                "label": "BEARISH",
            })
        elif 40 <= rsi <= 55:
            factors.append({
                "name": f"RSI Neutral ({rsi:.0f})",
                "weight": 0.10,
                "score": 0.6,
                "label": "BEARISH",
            })
        else:
            # RSI already oversold — late distribution, weaker signal
            factors.append({
                "name": f"RSI Oversold ({rsi:.0f}) — Late Stage",
                "weight": -0.10,
                "score": 0.3,
                "label": "CAUTION",
            })

        # Volume: high volume on down bars = distribution confirmed
        if volume_ratio > 1.3:
            factors.append({
                "name": f"High Volume Distribution ({volume_ratio:.1f}x)",
                "weight": 0.25,
                "score": min(volume_ratio / 2, 1.0),
                "label": "BEARISH",
            })
        elif volume_ratio >= 0.8:
            factors.append({
                "name": "Average Volume Distribution",
                "weight": 0.15,
                "score": 0.55,
                "label": "BEARISH",
            })
        else:
            # Low volume selling — less reliable
            factors.append({
                "name": "Low Volume Selling (Weak Confirmation)",
                "weight": 0.05,
                "score": 0.4,
                "label": "CAUTION",
            })

        return {"factors": factors, "pattern": "DISTRIBUTION"}

    def _build_squeeze_long(
        self,
        last: pd.Series,
        oi_change_pct: float,
        price_change_pct: float,
        rsi: float,
        volume_ratio: float,
    ) -> dict | None:
        """OI falling + price rising = shorts being squeezed out."""
        factors: list[dict] = []

        # Core divergence factor: falling OI means shorts covering into rising price
        divergence_strength = min(
            (abs(oi_change_pct) / self.OI_SIGNIFICANT_CHANGE) *
            (abs(price_change_pct) / self.PRICE_SIGNIFICANT_CHANGE),
            2.0,
        ) / 2.0
        factors.append({
            "name": f"OI Falling {oi_change_pct:.1f}% / Price Rising +{price_change_pct:.1f}% (Short Squeeze)",
            "weight": 0.40,
            "score": min(divergence_strength + 0.4, 1.0),
            "label": "BULLISH",
        })

        # RSI: not yet overbought = squeeze still has legs
        if rsi < 45:
            factors.append({
                "name": f"RSI Oversold ({rsi:.0f}) — Squeeze Early Stage",
                "weight": 0.20,
                "score": min((50 - rsi) / 50, 1.0),
                "label": "BULLISH",
            })
        elif 45 <= rsi <= 60:
            factors.append({
                "name": f"RSI Neutral ({rsi:.0f}) — Room to Run",
                "weight": 0.15,
                "score": 0.65,
                "label": "BULLISH",
            })
        else:
            factors.append({
                "name": f"RSI Extended ({rsi:.0f}) — Late Squeeze",
                "weight": -0.05,
                "score": 0.4,
                "label": "CAUTION",
            })

        # Volume acceleration with price rally = genuine momentum
        if volume_ratio > 1.5:
            factors.append({
                "name": f"Volume Surge During Squeeze ({volume_ratio:.1f}x)",
                "weight": 0.25,
                "score": min(volume_ratio / 2.5, 1.0),
                "label": "BULLISH",
            })
        elif volume_ratio >= 1.0:
            factors.append({
                "name": "Moderate Volume on Rally",
                "weight": 0.15,
                "score": 0.6,
                "label": "BULLISH",
            })

        # OI falling sharply = capitulation of shorts
        if abs(oi_change_pct) > self.OI_SIGNIFICANT_CHANGE * 2:
            factors.append({
                "name": f"Rapid OI Decline ({oi_change_pct:.1f}%) — Forced Short Covering",
                "weight": 0.20,
                "score": 0.9,
                "label": "BULLISH",
            })

        return {"factors": factors, "pattern": "SHORT_SQUEEZE"}

    def _build_trend_confirmation(
        self,
        direction: str,
        oi_change_pct: float,
        price_change_pct: float,
        rsi: float,
        volume_ratio: float,
    ) -> dict | None:
        """OI rising + price moving in trend direction = healthy trend continuation."""
        label = "BULLISH" if direction == "LONG" else "BEARISH"
        factors: list[dict] = []

        factors.append({
            "name": f"OI Rising +{oi_change_pct:.1f}% with Trend (Healthy Continuation)",
            "weight": 0.35,
            "score": min(oi_change_pct / (self.OI_SIGNIFICANT_CHANGE * 2), 1.0),
            "label": label,
        })

        # RSI in trend zone
        if direction == "LONG" and 45 <= rsi <= 70:
            factors.append({
                "name": f"RSI in Bullish Zone ({rsi:.0f})",
                "weight": 0.25,
                "score": 0.75,
                "label": "BULLISH",
            })
        elif direction == "SHORT" and 30 <= rsi <= 55:
            factors.append({
                "name": f"RSI in Bearish Zone ({rsi:.0f})",
                "weight": 0.25,
                "score": 0.75,
                "label": "BEARISH",
            })
        else:
            # RSI not aligned — weaker continuation signal
            factors.append({
                "name": "RSI Not in Ideal Zone",
                "weight": -0.05,
                "score": 0.4,
                "label": "CAUTION",
            })

        if volume_ratio > 1.2:
            factors.append({
                "name": f"Volume Confirming Trend ({volume_ratio:.1f}x)",
                "weight": 0.25,
                "score": min(volume_ratio / 2, 1.0),
                "label": label,
            })

        # Only emit if we have at least 2 positive factors
        positive_factors = [f for f in factors if f.get("label") == label]
        if len(positive_factors) < 2:
            return None

        return {"factors": factors, "pattern": "TREND_CONTINUATION"}

    def _build_signal(
        self,
        asset: str,
        timeframe: str,
        close: float,
        atr: float,
        direction: str,
        check_result: dict,
        context: MarketContext | None,
    ) -> SignalResult:
        """Build the final SignalResult with ATR-based levels."""
        levels = self.calculate_atr_based_stops(
            entry_price=close,
            atr=atr,
            direction=direction,
            atr_multiplier_sl=self.SL_ATR_MULTIPLIER,
            atr_multiplier_tp1=self.TP1_ATR_MULTIPLIER,
            atr_multiplier_tp2=self.TP2_ATR_MULTIPLIER,
        )

        confidence = self._calculate_confidence(
            check_result["factors"], check_result.get("pattern", "UNKNOWN")
        )

        tp1 = levels["take_profit_1"]
        tp2 = levels["take_profit_2"]
        mid_tp = round((tp1 + tp2) / 2, 8)

        return SignalResult(
            asset=asset,
            timeframe=timeframe,
            direction=direction,
            confidence=confidence,
            entry_price=close,
            stop_loss=levels["stop_loss"],
            take_profit_1=tp1,
            take_profit_2=tp2,
            risk_reward=levels["risk_reward"],
            factors=check_result["factors"],
            strategy_name=self.name,
            trailing_stop_pct=0.018,
            partial_tp_schedule=[
                {"pct_close": 33, "price": tp1, "label": "TP1 (OI Target)"},
                {"pct_close": 33, "price": mid_tp, "label": "TP1.5"},
                {"pct_close": 34, "price": tp2, "label": "TP2 (Extension)"},
            ],
        )

    def _calculate_confidence(self, factors: list[dict], pattern: str) -> float:
        """Calculate confidence from weighted factors with pattern bonus."""
        weighted_sum = sum(f["weight"] * f["score"] for f in factors)
        total_weight = sum(abs(f["weight"]) for f in factors)
        base = (weighted_sum / total_weight * 100) if total_weight > 0 else 50.0

        # Pattern-specific confidence bounds
        pattern_base: dict[str, float] = {
            "DISTRIBUTION": 75.0,
            "SHORT_SQUEEZE": 70.0,
            "TREND_CONTINUATION": 65.0,
            "UNKNOWN": 60.0,
        }
        # Blend base with pattern reference
        ref = pattern_base.get(pattern, 60.0)
        blended = base * 0.6 + ref * 0.4

        return round(min(blended, 95.0), 1)

    # --- Helpers ---

    def _get_oi_change(
        self, df: pd.DataFrame, last: pd.Series, context: MarketContext
    ) -> float | None:
        """Resolve OI change % from column, context, or calculated from oi column."""
        # Direct oi_change_pct column
        val = last.get("oi_change_pct", None)
        if val is not None and not (isinstance(val, float) and np.isnan(val)):
            return float(val)

        # Calculate from oi column over lookback
        if "oi" in df.columns:
            lookback = min(self.LOOKBACK_BARS, len(df) - 1)
            oi_now = float(df["oi"].iloc[-1])
            oi_past = float(df["oi"].iloc[-1 - lookback])
            if oi_past > 0:
                return (oi_now - oi_past) / oi_past * 100

        # Try context macro_events
        for event in (context.macro_events or []):
            if event.get("type") == "oi_change_pct" and "value" in event:
                return float(event["value"])

        return None

    def _get_rsi(self, df: pd.DataFrame, last: pd.Series) -> float:
        """Get RSI from pre-calculated column or compute it."""
        val = last.get("rsi_14", None)
        if val is not None and not (isinstance(val, float) and np.isnan(val)):
            return float(val)
        if len(df) >= 15:
            delta = df["close"].astype(float).diff()
            gain = delta.clip(lower=0).ewm(com=13, min_periods=14).mean()
            loss = (-delta.clip(upper=0)).ewm(com=13, min_periods=14).mean()
            rs = gain / loss.replace(0, np.nan)
            rsi_series = 100 - (100 / (1 + rs))
            return float(rsi_series.iloc[-1])
        return 50.0

    def _get_atr(self, df: pd.DataFrame, last: pd.Series) -> float:
        """Get ATR from pre-calculated column or compute it."""
        val = last.get("atr_14", None)
        if val is not None and not (isinstance(val, float) and np.isnan(val)):
            return float(val)
        if len(df) >= 15:
            high = df["high"].astype(float)
            low = df["low"].astype(float)
            close = df["close"].astype(float)
            tr = pd.concat(
                [high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()],
                axis=1,
            ).max(axis=1)
            return float(tr.ewm(com=13, min_periods=14).mean().iloc[-1])
        return 0.0
