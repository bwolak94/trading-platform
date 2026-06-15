"""Funding Rate Mean Reversion Strategy — fades extreme perpetual funding rates."""

import numpy as np
import pandas as pd

from app.ai.strategies.base import BaseStrategy, MarketContext, SignalResult
from app.core.logging import get_logger

logger = get_logger(__name__)


def _calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Calculate RSI from a price series."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calculate ATR from OHLCV DataFrame."""
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.ewm(com=period - 1, min_periods=period).mean()


class FundingMeanReversionStrategy(BaseStrategy):
    """Strategy based on extreme perpetual swap funding rates.

    Rationale: When funding rate is very positive (+0.08%+), longs are paying
    shorts heavily. This means the market is overleveraged long. Mean reversion
    often follows as longs get squeezed.

    Similarly, very negative funding (-0.05%-) means shorts are paying longs
    heavily → overleveraged short → potential short squeeze → LONG signal.

    Entry rules:
    LONG:  funding_rate < -0.05% AND RSI < 50 AND price near support
    SHORT: funding_rate > +0.08% AND RSI > 50 AND price near resistance

    This strategy works in ALL regimes (including HIGH_VOL_CHOPPY where most
    strategies are disabled) because it is a pure mean-reversion play.
    """

    name = "funding_mean_reversion"
    supported_regimes = ["TREND_BULL", "TREND_BEAR", "CONSOLIDATION", "HIGH_VOL_CHOPPY"]
    min_confidence = 55.0

    # Funding rate thresholds (per 8-hour period, expressed as decimal)
    EXTREME_POSITIVE_FUNDING = 0.0008    # 0.08% — extreme long bias → SHORT signal
    MODERATE_POSITIVE_FUNDING = 0.0005  # 0.05%
    EXTREME_NEGATIVE_FUNDING = -0.0005  # -0.05% — extreme short bias → LONG signal
    MODERATE_NEGATIVE_FUNDING = -0.0003  # -0.03%

    # ATR multipliers for risk levels
    SL_ATR_MULTIPLIER = 1.5
    TP1_ATR_MULTIPLIER = 2.0
    TP2_ATR_MULTIPLIER = 4.0

    def generate_signal(
        self,
        asset: str,
        timeframe: str,
        market_data: pd.DataFrame,
        context: MarketContext,
    ) -> SignalResult | None:
        """Generate signal based on funding rate extremes.

        Requires market_data to have these columns:
        - close, high, low, open, volume (standard OHLCV)
        - funding_rate (optional — falls back to context)
        - rsi_14 (optional — will be calculated if absent)
        - atr_14 (optional — will be calculated if absent)

        Steps:
        1. Get funding_rate from market_data['funding_rate'] or context
        2. Filter: only signal if funding is truly extreme
        3. Calculate RSI and check direction alignment
        4. Check price vs EMA20 for trend context
        5. Build SignalResult with ATR-based stops
        """
        if market_data.empty or len(market_data) < 20:
            logger.debug("Insufficient market data for %s — skipping", asset)
            return None

        df = market_data.copy()
        last = df.iloc[-1]

        # --- 1. Resolve funding rate ---
        funding_rate = self._get_funding_rate(last, context)
        if funding_rate is None:
            logger.debug("No funding rate available for %s — skipping", asset)
            return None

        # --- 2. Gate: funding must be at least moderately extreme ---
        is_extreme_long = funding_rate >= self.EXTREME_POSITIVE_FUNDING
        is_moderate_long = self.MODERATE_POSITIVE_FUNDING <= funding_rate < self.EXTREME_POSITIVE_FUNDING
        is_extreme_short = funding_rate <= self.EXTREME_NEGATIVE_FUNDING
        is_moderate_short = self.EXTREME_NEGATIVE_FUNDING < funding_rate <= self.MODERATE_NEGATIVE_FUNDING

        if not (is_extreme_long or is_moderate_long or is_extreme_short or is_moderate_short):
            return None

        # --- 3. Calculate technical indicators ---
        rsi = self._get_rsi(df, last)
        atr = self._get_atr(df, last)
        if atr <= 0:
            logger.debug("ATR is zero for %s — cannot set stops", asset)
            return None

        close = float(last.get("close", 0))
        if close <= 0:
            return None

        ema20 = df["close"].ewm(span=20, adjust=False).mean().iloc[-1]

        # --- 4. Direction logic ---
        # HIGH positive funding → market overleveraged LONG → fade with SHORT
        # HIGH negative funding → market overleveraged SHORT → fade with LONG
        if (is_extreme_long or is_moderate_long) and rsi > 50:
            result = self._check_short(
                df, last, close, rsi, atr, ema20, funding_rate,
                is_extreme=is_extreme_long,
            )
            if result:
                return self._build_signal(asset, timeframe, close, atr, "SHORT", result, context)

        elif (is_extreme_short or is_moderate_short) and rsi < 50:
            result = self._check_long(
                df, last, close, rsi, atr, ema20, funding_rate,
                is_extreme=is_extreme_short,
            )
            if result:
                return self._build_signal(asset, timeframe, close, atr, "LONG", result, context)

        return None

    def _check_long(
        self,
        df: pd.DataFrame,
        last: pd.Series,
        close: float,
        rsi: float,
        atr: float,
        ema20: float,
        funding_rate: float,
        is_extreme: bool,
    ) -> dict | None:
        """Check LONG conditions when funding is extremely negative."""
        factors: list[dict] = []

        # Core funding signal
        funding_pct = funding_rate * 100
        funding_score = min(abs(funding_rate) / abs(self.EXTREME_NEGATIVE_FUNDING), 1.5)
        funding_score = min(funding_score, 1.0)
        factors.append({
            "name": f"Extreme Negative Funding ({funding_pct:.4f}%)",
            "weight": 0.40,
            "score": funding_score,
            "label": "BULLISH",
        })

        # RSI confirmation: oversold / neutral territory
        if rsi > 50:
            return None  # RSI should be below 50 for long on mean-reversion
        rsi_score = max(0.5, (50 - rsi) / 50)
        factors.append({
            "name": f"RSI Bearish Territory ({rsi:.0f})",
            "weight": 0.20,
            "score": rsi_score,
            "label": "BULLISH",
        })

        # Price near support: below EMA20 (oversold vs short-term trend)
        distance_to_ema20 = (close - ema20) / (atr if atr > 0 else 1)
        if distance_to_ema20 < -0.5:
            factors.append({
                "name": "Price Below EMA20 Support",
                "weight": 0.20,
                "score": min(abs(distance_to_ema20) / 3, 1.0),
                "label": "BULLISH",
            })
        elif distance_to_ema20 <= 0:
            factors.append({
                "name": "Price at EMA20",
                "weight": 0.15,
                "score": 0.6,
                "label": "BULLISH",
            })
        else:
            # Price above EMA20 when funding is negative — less ideal
            factors.append({
                "name": "Price Above EMA20 (Weaker Setup)",
                "weight": 0.10,
                "score": 0.4,
                "label": "CAUTION",
            })

        # Extreme vs moderate bonus
        if is_extreme:
            factors.append({
                "name": "Extreme Funding Level Bonus",
                "weight": 0.20,
                "score": 0.9,
                "label": "BULLISH",
            })

        # Volume surge check: high volume during funding extreme = capitulation
        volume_ratio = float(last.get("volume_vs_avg", 1.0))
        if volume_ratio > 1.5:
            factors.append({
                "name": f"Volume Surge ({volume_ratio:.1f}x avg)",
                "weight": 0.15,
                "score": min(volume_ratio / 3, 1.0),
                "label": "BULLISH",
            })

        return {"factors": factors, "direction": "LONG"}

    def _check_short(
        self,
        df: pd.DataFrame,
        last: pd.Series,
        close: float,
        rsi: float,
        atr: float,
        ema20: float,
        funding_rate: float,
        is_extreme: bool,
    ) -> dict | None:
        """Check SHORT conditions when funding is extremely positive."""
        factors: list[dict] = []

        # Core funding signal
        funding_pct = funding_rate * 100
        funding_score = min(funding_rate / self.EXTREME_POSITIVE_FUNDING, 1.5)
        funding_score = min(funding_score, 1.0)
        factors.append({
            "name": f"Extreme Positive Funding ({funding_pct:.4f}%)",
            "weight": 0.40,
            "score": funding_score,
            "label": "BEARISH",
        })

        # RSI: overbought / above 50 confirms long crowd is extended
        if rsi < 50:
            return None  # RSI should be above 50 for short on mean-reversion
        rsi_score = max(0.5, (rsi - 50) / 50)
        factors.append({
            "name": f"RSI Bullish Territory ({rsi:.0f})",
            "weight": 0.20,
            "score": rsi_score,
            "label": "BEARISH",
        })

        # Price near resistance: above EMA20 (overbought vs short-term trend)
        distance_to_ema20 = (close - ema20) / (atr if atr > 0 else 1)
        if distance_to_ema20 > 0.5:
            factors.append({
                "name": "Price Above EMA20 Resistance",
                "weight": 0.20,
                "score": min(distance_to_ema20 / 3, 1.0),
                "label": "BEARISH",
            })
        elif distance_to_ema20 >= 0:
            factors.append({
                "name": "Price at EMA20",
                "weight": 0.15,
                "score": 0.6,
                "label": "BEARISH",
            })
        else:
            factors.append({
                "name": "Price Below EMA20 (Weaker Setup)",
                "weight": 0.10,
                "score": 0.4,
                "label": "CAUTION",
            })

        # Extreme vs moderate bonus
        if is_extreme:
            factors.append({
                "name": "Extreme Funding Level Bonus",
                "weight": 0.20,
                "score": 0.9,
                "label": "BEARISH",
            })

        # Volume divergence: funding high but volume declining = exhaustion
        volume_ratio = float(last.get("volume_vs_avg", 1.0))
        if volume_ratio < 0.8:
            factors.append({
                "name": "Low Volume at Extreme (Exhaustion)",
                "weight": 0.10,
                "score": 0.8,
                "label": "BEARISH",
            })

        return {"factors": factors, "direction": "SHORT"}

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
        """Build a SignalResult with ATR-based stops and confidence."""
        # Dynamic ATR multiplier: HIGH_VOL_CHOPPY → wider stops
        sl_mult = self.SL_ATR_MULTIPLIER
        if context is not None and context.regime == "HIGH_VOL_CHOPPY":
            sl_mult *= 1.3

        levels = self.calculate_atr_based_stops(
            entry_price=close,
            atr=atr,
            direction=direction,
            atr_multiplier_sl=sl_mult,
            atr_multiplier_tp1=self.TP1_ATR_MULTIPLIER,
            atr_multiplier_tp2=self.TP2_ATR_MULTIPLIER,
        )

        confidence = self._calculate_confidence(check_result["factors"])

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
            trailing_stop_pct=0.012,
            partial_tp_schedule=[
                {"pct_close": 40, "price": tp1, "label": "TP1 (Funding Revert)"},
                {"pct_close": 30, "price": mid_tp, "label": "TP1.5"},
                {"pct_close": 30, "price": tp2, "label": "TP2 (Full Revert)"},
            ],
        )

    def _calculate_confidence(self, factors: list[dict]) -> float:
        """Calculate confidence from factor weights and scores."""
        positive_weight = sum(
            f["weight"] * f["score"] for f in factors if f.get("label") not in ("CAUTION",)
        )
        total_weight = sum(abs(f["weight"]) for f in factors)
        if total_weight == 0:
            return 50.0

        base = (positive_weight / total_weight) * 100

        # Bonus if both extreme funding AND RSI confirmation present
        has_extreme = any("Extreme Funding Level Bonus" in f["name"] for f in factors)
        has_volume = any("Volume" in f["name"] for f in factors)
        bonus = 0.0
        if has_extreme:
            bonus += 5.0
        if has_volume:
            bonus += 3.0

        return round(min(base + bonus, 95.0), 1)

    # --- Helpers ---

    def _get_funding_rate(
        self, last: pd.Series, context: MarketContext
    ) -> float | None:
        """Extract funding rate from last bar or context. Returns None if unavailable."""
        # Try column on market_data first
        fr = last.get("funding_rate", None)
        if fr is not None and not (isinstance(fr, float) and np.isnan(fr)):
            return float(fr)

        # Try context attributes (set externally by the aggregator or API layer)
        if hasattr(context, "funding_rate") and context.funding_rate is not None:
            return float(context.funding_rate)

        # Try macro_events list for a funding_rate entry
        for event in (context.macro_events or []):
            if event.get("type") == "funding_rate" and "value" in event:
                return float(event["value"])

        return None

    def _get_rsi(self, df: pd.DataFrame, last: pd.Series) -> float:
        """Get RSI from pre-calculated column or compute it."""
        rsi_val = last.get("rsi_14", None)
        if rsi_val is not None and not (isinstance(rsi_val, float) and np.isnan(rsi_val)):
            return float(rsi_val)
        # Calculate from close prices
        if len(df) >= 15:
            rsi_series = _calculate_rsi(df["close"].astype(float), 14)
            return float(rsi_series.iloc[-1])
        return 50.0

    def _get_atr(self, df: pd.DataFrame, last: pd.Series) -> float:
        """Get ATR from pre-calculated column or compute it."""
        atr_val = last.get("atr_14", None)
        if atr_val is not None and not (isinstance(atr_val, float) and np.isnan(atr_val)):
            return float(atr_val)
        if len(df) >= 15:
            atr_series = _calculate_atr(df, 14)
            return float(atr_series.iloc[-1])
        return 0.0
