"""SMC Strategy — Order Blocks + Fair Value Gaps."""

import logging

import numpy as np
import pandas as pd

from app.ai.strategies.base import BaseStrategy, MarketContext, SignalResult

logger = logging.getLogger(__name__)


def find_order_blocks(
    df: pd.DataFrame, lookback: int = 20
) -> list[dict]:
    """Detect order blocks — last opposing candle before an impulse move.

    Bullish OB: last bearish candle before a strong bullish impulse.
    Bearish OB: last bullish candle before a strong bearish impulse.

    Returns list of dicts: {type, high, low, mid, index, strength}.
    """
    blocks: list[dict] = []
    if len(df) < lookback:
        return blocks

    recent = df.iloc[-lookback:]
    close = recent["close"].values
    open_ = recent["open"].values
    high = recent["high"].values
    low = recent["low"].values
    atr = recent["atr_14"].values if "atr_14" in recent.columns else np.ones(len(recent))

    for i in range(1, len(recent) - 1):
        body = abs(close[i] - open_[i])
        prev_body = abs(close[i - 1] - open_[i - 1])
        impulse_ratio = body / atr[i] if atr[i] > 0 else 0

        # Bullish OB: previous candle bearish, current candle strong bullish impulse
        if (
            close[i] > open_[i]
            and close[i - 1] < open_[i - 1]
            and impulse_ratio > 1.5
        ):
            blocks.append({
                "type": "bullish",
                "high": float(open_[i - 1]),
                "low": float(close[i - 1]),
                "mid": float((open_[i - 1] + close[i - 1]) / 2),
                "index": recent.index[i - 1],
                "strength": float(impulse_ratio),
            })

        # Bearish OB: previous candle bullish, current candle strong bearish impulse
        if (
            close[i] < open_[i]
            and close[i - 1] > open_[i - 1]
            and impulse_ratio > 1.5
        ):
            blocks.append({
                "type": "bearish",
                "high": float(close[i - 1]),
                "low": float(open_[i - 1]),
                "mid": float((open_[i - 1] + close[i - 1]) / 2),
                "index": recent.index[i - 1],
                "strength": float(impulse_ratio),
            })

    return blocks


def find_fair_value_gaps(
    df: pd.DataFrame, lookback: int = 20
) -> list[dict]:
    """Detect Fair Value Gaps (FVG) — three-candle pattern with price imbalance.

    Bullish FVG: candle[i-2].high < candle[i].low (gap up).
    Bearish FVG: candle[i-2].low > candle[i].high (gap down).

    Returns list of dicts: {type, top, bottom, mid, index}.
    """
    gaps: list[dict] = []
    if len(df) < max(lookback, 3):
        return gaps

    recent = df.iloc[-lookback:]
    high = recent["high"].values
    low = recent["low"].values

    for i in range(2, len(recent)):
        # Bullish FVG
        if low[i] > high[i - 2]:
            gaps.append({
                "type": "bullish",
                "top": float(low[i]),
                "bottom": float(high[i - 2]),
                "mid": float((low[i] + high[i - 2]) / 2),
                "index": recent.index[i],
            })

        # Bearish FVG
        if high[i] < low[i - 2]:
            gaps.append({
                "type": "bearish",
                "top": float(low[i - 2]),
                "bottom": float(high[i]),
                "mid": float((low[i - 2] + high[i]) / 2),
                "index": recent.index[i],
            })

    return gaps


class SMCStrategy(BaseStrategy):
    """Smart Money Concepts — Order Block retest with FVG confluence.

    Supported regimes: TREND_BULL, TREND_BEAR.
    Logic from 04_AI_ENGINE.md — Strategy 3.
    """

    name = "smc"
    supported_regimes = ["TREND_BULL", "TREND_BEAR"]
    min_confidence = 50.0

    OB_LOOKBACK = 20
    FVG_LOOKBACK = 20
    SL_BUFFER_PCT = 0.003  # 0.3% below/above OB

    def generate_signal(
        self,
        asset: str,
        timeframe: str,
        market_data: pd.DataFrame,
        context: MarketContext,
    ) -> SignalResult | None:
        """Generate an SMC signal on OB retest with FVG confluence."""
        if market_data.empty or len(market_data) < self.OB_LOOKBACK + 5:
            return None

        df = market_data.copy()
        last = df.iloc[-1]
        close = float(last.get("close", 0))
        atr = float(last.get("atr_14", 0))

        order_blocks = find_order_blocks(df, self.OB_LOOKBACK)
        fvgs = find_fair_value_gaps(df, self.FVG_LOOKBACK)

        long_signal = self._check_long(close, atr, order_blocks, fvgs, df)
        if long_signal:
            return self._build_signal(asset, timeframe, last, "LONG", long_signal)

        short_signal = self._check_short(close, atr, order_blocks, fvgs, df)
        if short_signal:
            return self._build_signal(asset, timeframe, last, "SHORT", short_signal)

        return None

    def _check_long(
        self,
        close: float,
        atr: float,
        order_blocks: list[dict],
        fvgs: list[dict],
        df: pd.DataFrame,
    ) -> dict | None:
        """Check for bullish OB retest + FVG confluence."""
        bullish_obs = [ob for ob in order_blocks if ob["type"] == "bullish"]
        if not bullish_obs:
            return None

        # Find an OB that price is retesting (price within OB range)
        retested_ob = None
        for ob in reversed(bullish_obs):  # most recent first
            if ob["low"] <= close <= ob["high"]:
                retested_ob = ob
                break

        if not retested_ob:
            return None

        factors = [{
            "name": "Bullish Order Block Retest",
            "weight": 0.4,
            "score": min(retested_ob["strength"] / 3, 1.0),
            "label": "BULLISH",
        }]

        # Check for bullish FVG below current price (acts as magnet/support)
        bullish_fvgs = [
            fvg for fvg in fvgs
            if fvg["type"] == "bullish" and fvg["mid"] < close
        ]
        if bullish_fvgs:
            factors.append({
                "name": "Bullish FVG Confluence",
                "weight": 0.3,
                "score": 0.8,
                "label": "BULLISH",
            })

        # Check no major bearish OB overhead (supply zone)
        bearish_obs_above = [
            ob for ob in order_blocks
            if ob["type"] == "bearish" and ob["low"] > close
            and (ob["low"] - close) / close < 0.03  # within 3%
        ]
        if bearish_obs_above:
            return None  # supply zone too close

        factors.append({
            "name": "Clear Path (No Supply)",
            "weight": 0.15,
            "score": 0.75,
            "label": "BULLISH",
        })

        return {"factors": factors, "ob": retested_ob}

    def _check_short(
        self,
        close: float,
        atr: float,
        order_blocks: list[dict],
        fvgs: list[dict],
        df: pd.DataFrame,
    ) -> dict | None:
        """Check for bearish OB retest + FVG confluence."""
        bearish_obs = [ob for ob in order_blocks if ob["type"] == "bearish"]
        if not bearish_obs:
            return None

        retested_ob = None
        for ob in reversed(bearish_obs):
            if ob["low"] <= close <= ob["high"]:
                retested_ob = ob
                break

        if not retested_ob:
            return None

        factors = [{
            "name": "Bearish Order Block Retest",
            "weight": 0.4,
            "score": min(retested_ob["strength"] / 3, 1.0),
            "label": "BEARISH",
        }]

        # Check for bearish FVG above price (magnet/resistance)
        bearish_fvgs = [
            fvg for fvg in fvgs
            if fvg["type"] == "bearish" and fvg["mid"] > close
        ]
        if bearish_fvgs:
            factors.append({
                "name": "Bearish FVG Confluence",
                "weight": 0.3,
                "score": 0.8,
                "label": "BEARISH",
            })

        # Check no bullish OB below (demand zone)
        bullish_obs_below = [
            ob for ob in order_blocks
            if ob["type"] == "bullish" and ob["high"] < close
            and (close - ob["high"]) / close < 0.03
        ]
        if bullish_obs_below:
            return None

        factors.append({
            "name": "Clear Path (No Demand)",
            "weight": 0.15,
            "score": 0.75,
            "label": "BEARISH",
        })

        return {"factors": factors, "ob": retested_ob}

    def _build_signal(
        self,
        asset: str,
        timeframe: str,
        last: pd.Series,
        direction: str,
        check_result: dict,
    ) -> SignalResult:
        """Build SignalResult with OB-based levels."""
        ob = check_result["ob"]
        close = float(last.get("close", 0))
        atr = float(last.get("atr_14", 0))

        entry = ob["mid"]  # entry at middle of Order Block

        if direction == "LONG":
            stop_loss = ob["low"] * (1 - self.SL_BUFFER_PCT)
            # TP targets: next resistance / swing high
            risk = entry - stop_loss
            tp1 = entry + risk * 1.5
            tp2 = entry + risk * 3.0
        else:
            stop_loss = ob["high"] * (1 + self.SL_BUFFER_PCT)
            risk = stop_loss - entry
            tp1 = entry - risk * 1.5
            tp2 = entry - risk * 3.0

        risk_abs = abs(entry - stop_loss)
        risk_reward = abs(tp1 - entry) / risk_abs if risk_abs > 0 else 0
        confidence = self._calculate_confidence(check_result["factors"])

        return SignalResult(
            asset=asset,
            timeframe=timeframe,
            direction=direction,
            confidence=confidence,
            entry_price=round(entry, 8),
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

        has_fvg = any("FVG" in f["name"] for f in factors)
        boost = 7.0 if has_fvg else 0.0

        return round(min(base + boost, 95), 1)
