"""Trend Trader Strategy — Ichimoku Cloud + Fibonacci + S/R confluence."""

import logging
from typing import Any

import numpy as np
import pandas as pd

from app.ai.strategies.base import BaseStrategy, MarketContext, SignalResult

logger = logging.getLogger(__name__)


class TrendTraderStrategy(BaseStrategy):
    """Combines Ichimoku Cloud, Fibonacci retracement, and S/R for entries.

    LONG: price above cloud + TK bullish cross + near Fib 61.8% support
    SHORT: price below cloud + TK bearish cross + near Fib 38.2% resistance
    SL: below Kijun (LONG), above Kijun (SHORT)
    TP1: opposite side of cloud, TP2: swing high/low
    """

    name = "trend_trader"
    supported_regimes = ["TREND_BULL", "TREND_BEAR", "CONSOLIDATION", "HIGH_VOL_CHOPPY"]
    min_confidence = 45.0

    # Ichimoku params
    TENKAN_PERIOD = 9
    KIJUN_PERIOD = 26
    SENKOU_SPAN = 26
    SENKOU_SPAN_B_PERIOD = 52
    CHIKOU_SHIFT = 26

    # Fib params
    FIB_LOOKBACK = 100
    FIB_PROXIMITY_ATR = 1.5  # how close price needs to be to a fib level (in ATR units)
    FIB_LEVELS = {
        "0.0": 0.0,
        "23.6": 0.236,
        "38.2": 0.382,
        "50.0": 0.500,
        "61.8": 0.618,
        "78.6": 0.786,
        "88.6": 0.886,
        "100.0": 1.0,
    }

    # S/R params
    SR_LOOKBACK = 200
    SR_TOUCH_MIN = 2

    # RSI filter thresholds
    RSI_OVERBOUGHT = 75
    RSI_OVERSOLD = 25
    RSI_HEALTHY_LONG_LOW = 40
    RSI_HEALTHY_LONG_HIGH = 65
    RSI_HEALTHY_SHORT_LOW = 35
    RSI_HEALTHY_SHORT_HIGH = 60

    # Volume confirmation threshold
    VOLUME_THRESHOLD = 1.2

    def generate_signal(
        self,
        asset: str,
        timeframe: str,
        market_data: pd.DataFrame,
        context: MarketContext,
    ) -> SignalResult | None:
        """Generate signal using Ichimoku + Fib + S/R confluence."""
        if market_data.empty or len(market_data) < 200:
            return None

        df = market_data.copy()
        last = df.iloc[-1]
        close = float(last["close"])
        atr = float(last.get("atr_14", 0))
        if atr == 0:
            return None

        # Get Ichimoku values from feature-engineered columns
        tenkan = last.get("ichimoku_tenkan")
        kijun = last.get("ichimoku_kijun")
        senkou_a = last.get("ichimoku_senkou_a")
        senkou_b = last.get("ichimoku_senkou_b")

        # If ichimoku columns not present, compute them locally
        if tenkan is None or pd.isna(tenkan):
            tenkan, kijun, senkou_a, senkou_b = self._compute_ichimoku_local(df)
            if tenkan is None:
                return None

        tenkan = float(tenkan)
        kijun = float(kijun)
        senkou_a = float(senkou_a) if senkou_a is not None and not pd.isna(senkou_a) else None
        senkou_b = float(senkou_b) if senkou_b is not None and not pd.isna(senkou_b) else None

        if senkou_a is None or senkou_b is None:
            return None

        cloud_top = max(senkou_a, senkou_b)
        cloud_bottom = min(senkou_a, senkou_b)

        # Compute fibonacci levels
        fib_levels = self._compute_fib_levels(df)

        # Compute S/R levels
        sr_levels = self._compute_sr_levels(df)

        # Check LONG
        long_result = self._check_long(df, last, close, atr, tenkan, kijun, senkou_a, senkou_b, cloud_top, cloud_bottom, fib_levels, sr_levels, context)
        if long_result:
            return self._build_signal(asset, timeframe, last, "LONG", long_result, close, atr, kijun, cloud_top, cloud_bottom, df)

        # Check SHORT
        short_result = self._check_short(df, last, close, atr, tenkan, kijun, senkou_a, senkou_b, cloud_top, cloud_bottom, fib_levels, sr_levels, context)
        if short_result:
            return self._build_signal(asset, timeframe, last, "SHORT", short_result, close, atr, kijun, cloud_top, cloud_bottom, df)

        return None

    def _compute_ichimoku_local(self, df: pd.DataFrame) -> tuple:
        """Compute Ichimoku values locally if not in DataFrame."""
        if len(df) < self.KIJUN_PERIOD + self.SENKOU_SPAN:
            return None, None, None, None

        high = df["high"]
        low = df["low"]

        # Tenkan-sen (Conversion Line)
        tenkan = (high.rolling(self.TENKAN_PERIOD).max() + low.rolling(self.TENKAN_PERIOD).min()) / 2
        # Kijun-sen (Base Line)
        kijun = (high.rolling(self.KIJUN_PERIOD).max() + low.rolling(self.KIJUN_PERIOD).min()) / 2
        # Senkou Span A
        senkou_a = ((tenkan + kijun) / 2).shift(self.SENKOU_SPAN)
        # Senkou Span B
        senkou_b = ((high.rolling(self.SENKOU_SPAN_B_PERIOD).max() + low.rolling(self.SENKOU_SPAN_B_PERIOD).min()) / 2).shift(self.SENKOU_SPAN)

        last_tenkan = tenkan.iloc[-1]
        last_kijun = kijun.iloc[-1]
        last_senkou_a = senkou_a.iloc[-1]
        last_senkou_b = senkou_b.iloc[-1]

        if pd.isna(last_tenkan) or pd.isna(last_kijun):
            return None, None, None, None

        return last_tenkan, last_kijun, last_senkou_a, last_senkou_b

    def _compute_fib_levels(self, df: pd.DataFrame) -> dict[str, float]:
        """Compute Fibonacci retracement levels from auto swing H/L detection."""
        lookback = min(self.FIB_LOOKBACK, len(df))
        recent = df.tail(lookback)
        swing_high = float(recent["high"].max())
        swing_low = float(recent["low"].min())
        diff = swing_high - swing_low

        if diff <= 0:
            return {}

        return {
            name: swing_low + diff * ratio
            for name, ratio in self.FIB_LEVELS.items()
        }

    def _compute_sr_levels(self, df: pd.DataFrame) -> list[dict]:
        """Compute support/resistance levels via pivot clustering."""
        lookback = min(self.SR_LOOKBACK, len(df))
        recent = df.tail(lookback)

        # Find local pivots (swing highs and lows)
        pivots = []
        for i in range(2, len(recent) - 2):
            h = float(recent.iloc[i]["high"])
            l = float(recent.iloc[i]["low"])
            # Swing high
            if h >= float(recent.iloc[i-1]["high"]) and h >= float(recent.iloc[i-2]["high"]) and h >= float(recent.iloc[i+1]["high"]) and h >= float(recent.iloc[i+2]["high"]):
                pivots.append({"price": h, "type": "resistance"})
            # Swing low
            if l <= float(recent.iloc[i-1]["low"]) and l <= float(recent.iloc[i-2]["low"]) and l <= float(recent.iloc[i+1]["low"]) and l <= float(recent.iloc[i+2]["low"]):
                pivots.append({"price": l, "type": "support"})

        if not pivots:
            return []

        # Cluster nearby pivots
        atr = float(df.iloc[-1].get("atr_14", 1))
        cluster_threshold = atr * 0.5
        clusters: list[dict] = []

        sorted_pivots = sorted(pivots, key=lambda p: p["price"])
        current_cluster = [sorted_pivots[0]]

        for p in sorted_pivots[1:]:
            if abs(p["price"] - current_cluster[-1]["price"]) < cluster_threshold:
                current_cluster.append(p)
            else:
                avg_price = sum(pp["price"] for pp in current_cluster) / len(current_cluster)
                role = "resistance" if sum(1 for pp in current_cluster if pp["type"] == "resistance") > len(current_cluster) / 2 else "support"
                clusters.append({
                    "price": avg_price,
                    "touches": len(current_cluster),
                    "role": role,
                    "strength": min(len(current_cluster) / 5, 1.0),
                })
                current_cluster = [p]

        # Don't forget last cluster
        if current_cluster:
            avg_price = sum(pp["price"] for pp in current_cluster) / len(current_cluster)
            role = "resistance" if sum(1 for pp in current_cluster if pp["type"] == "resistance") > len(current_cluster) / 2 else "support"
            clusters.append({
                "price": avg_price,
                "touches": len(current_cluster),
                "role": role,
                "strength": min(len(current_cluster) / 5, 1.0),
            })

        # Filter by minimum touches
        return [c for c in clusters if c["touches"] >= self.SR_TOUCH_MIN]

    def _check_long(self, df, last, close, atr, tenkan, kijun, senkou_a, senkou_b, cloud_top, cloud_bottom, fib_levels, sr_levels, context) -> dict | None:
        """Check LONG entry conditions."""
        factors = []

        # 1. Price above cloud
        if close <= cloud_top:
            return None
        factors.append({"name": "Price Above Ichimoku Cloud", "weight": 0.25, "score": 0.9, "label": "BULLISH"})

        # 2. TK bullish cross (Tenkan > Kijun)
        if tenkan <= kijun:
            return None
        tk_spread = (tenkan - kijun) / atr
        factors.append({"name": "Bullish TK Cross", "weight": 0.20, "score": min(tk_spread * 0.5 + 0.5, 1.0), "label": "BULLISH"})

        # 3. Near Fibonacci support (61.8% or 50%)
        fib_confluence = False
        if fib_levels:
            for level_name in ["61.8", "50.0", "78.6"]:
                level = fib_levels.get(level_name, 0)
                if level > 0 and abs(close - level) / atr < self.FIB_PROXIMITY_ATR:
                    fib_confluence = True
                    factors.append({"name": f"Fib {level_name}% Support", "weight": 0.20, "score": 0.85, "label": "BULLISH"})
                    break

        # 4. S/R support nearby
        sr_confluence = False
        for sr in sr_levels:
            if sr["role"] == "support" and 0 < (close - sr["price"]) / atr < self.FIB_PROXIMITY_ATR:
                sr_confluence = True
                factors.append({"name": f"S/R Support ({sr['touches']} touches)", "weight": 0.15, "score": sr["strength"], "label": "BULLISH"})
                break

        # Need at least fib or S/R confluence
        if not fib_confluence and not sr_confluence:
            return None

        # 5. Volume confirmation (optional bonus)
        volume_ratio = float(last.get("volume_vs_avg", 1.0))
        if volume_ratio > self.VOLUME_THRESHOLD:
            factors.append({"name": "Volume Confirmation", "weight": 0.10, "score": min(volume_ratio / 2, 1.0), "label": "BULLISH"})

        # 6. RSI filter — not overbought
        rsi = float(last.get("rsi_14", 50))
        if rsi > self.RSI_OVERBOUGHT:
            return None
        if self.RSI_HEALTHY_LONG_LOW <= rsi <= self.RSI_HEALTHY_LONG_HIGH:
            factors.append({"name": "RSI Healthy Range", "weight": 0.10, "score": 0.7, "label": "BULLISH"})

        return {"factors": factors}

    def _check_short(self, df, last, close, atr, tenkan, kijun, senkou_a, senkou_b, cloud_top, cloud_bottom, fib_levels, sr_levels, context) -> dict | None:
        """Check SHORT entry conditions."""
        factors = []

        # 1. Price below cloud
        if close >= cloud_bottom:
            return None
        factors.append({"name": "Price Below Ichimoku Cloud", "weight": 0.25, "score": 0.9, "label": "BEARISH"})

        # 2. TK bearish cross (Tenkan < Kijun)
        if tenkan >= kijun:
            return None
        tk_spread = (kijun - tenkan) / atr
        factors.append({"name": "Bearish TK Cross", "weight": 0.20, "score": min(tk_spread * 0.5 + 0.5, 1.0), "label": "BEARISH"})

        # 3. Near Fibonacci resistance (38.2% or 50%)
        fib_confluence = False
        if fib_levels:
            for level_name in ["38.2", "50.0", "23.6"]:
                level = fib_levels.get(level_name, 0)
                if level > 0 and abs(close - level) / atr < self.FIB_PROXIMITY_ATR:
                    fib_confluence = True
                    factors.append({"name": f"Fib {level_name}% Resistance", "weight": 0.20, "score": 0.85, "label": "BEARISH"})
                    break

        # 4. S/R resistance nearby
        sr_confluence = False
        for sr in sr_levels:
            if sr["role"] == "resistance" and 0 < (sr["price"] - close) / atr < self.FIB_PROXIMITY_ATR:
                sr_confluence = True
                factors.append({"name": f"S/R Resistance ({sr['touches']} touches)", "weight": 0.15, "score": sr["strength"], "label": "BEARISH"})
                break

        if not fib_confluence and not sr_confluence:
            return None

        # 5. Volume confirmation
        volume_ratio = float(last.get("volume_vs_avg", 1.0))
        if volume_ratio > self.VOLUME_THRESHOLD:
            factors.append({"name": "Volume Confirmation", "weight": 0.10, "score": min(volume_ratio / 2, 1.0), "label": "BEARISH"})

        # 6. RSI filter — not oversold
        rsi = float(last.get("rsi_14", 50))
        if rsi < self.RSI_OVERSOLD:
            return None
        if self.RSI_HEALTHY_SHORT_LOW <= rsi <= self.RSI_HEALTHY_SHORT_HIGH:
            factors.append({"name": "RSI Healthy Range", "weight": 0.10, "score": 0.7, "label": "BEARISH"})

        return {"factors": factors}

    def _build_signal(
        self, asset, timeframe, last, direction, check_result, close, atr, kijun, cloud_top, cloud_bottom, df,
    ) -> SignalResult:
        """Build SignalResult with Ichimoku-based SL/TP."""
        factors = check_result["factors"]

        # SL based on Kijun
        if direction == "LONG":
            stop_loss = min(kijun - atr * 0.5, close - atr * 1.5)
            # TP1: opposite side of cloud (senkou_b if above cloud)
            tp1 = cloud_top + (cloud_top - cloud_bottom) * 0.5
            # TP2: recent swing high
            tp2 = float(df.tail(self.FIB_LOOKBACK)["high"].max())
            if tp2 <= close:
                tp2 = close + atr * 3.0
        else:
            stop_loss = max(kijun + atr * 0.5, close + atr * 1.5)
            # TP1: opposite side of cloud
            tp1 = cloud_bottom - (cloud_top - cloud_bottom) * 0.5
            # TP2: recent swing low
            tp2 = float(df.tail(self.FIB_LOOKBACK)["low"].min())
            if tp2 >= close:
                tp2 = close - atr * 3.0

        risk = abs(close - stop_loss)
        risk_reward = abs(tp1 - close) / risk if risk > 0 else 0

        confidence = self._calculate_confidence(factors)

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
            factors=factors,
            strategy_name=self.name,
            trailing_stop_pct=0.02,
            partial_tp_schedule=[
                {"pct_close": 30, "price": round(tp1, 8), "label": "TP1"},
                {"pct_close": 30, "price": round((tp1 + tp2) / 2, 8), "label": "TP1.5"},
                {"pct_close": 40, "price": round(tp2, 8), "label": "TP2"},
            ],
        )

    @staticmethod
    def _calculate_confidence(factors: list[dict]) -> float:
        """Calculate confidence from weighted factors."""
        weighted_sum = sum(f["weight"] * f["score"] for f in factors)
        total_weight = sum(f["weight"] for f in factors)
        base = (weighted_sum / total_weight * 100) if total_weight > 0 else 50
        return round(min(base, 95), 1)
