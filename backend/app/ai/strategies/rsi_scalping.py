"""RSI Scalping Strategy — RSI + Stochastic + DMI Stochastic crossover signals.

Port of TradingView "RSI Scalpin" indicator by Angel Chacon (AngelRChaconM).
Uses three oscillators to generate BUY/SELL signals:
  1. RSI(14) — trend filter (30/70 bands)
  2. Stochastic K/D (14,6,6) — momentum
  3. DMI Stochastic — directional momentum oscillator
     BUY when DMI Stoch crosses above 10 from below
     SELL when DMI Stoch crosses below 90 from above
"""

import logging

import numpy as np
import pandas as pd

from app.ai.strategies.base import BaseStrategy, MarketContext, SignalResult

logger = logging.getLogger(__name__)


def _wwma(series: pd.Series, length: int) -> pd.Series:
    """Welles Wilder Moving Average (same as RMA in TradingView)."""
    result = pd.Series(0.0, index=series.index)
    result.iloc[0] = series.iloc[0]
    for i in range(1, len(series)):
        result.iloc[i] = (result.iloc[i - 1] * (length - 1) + series.iloc[i]) / length
    return result


def compute_rsi_scalping_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Compute RSI, Stochastic, and DMI Stochastic indicators.

    Returns DataFrame with additional columns:
    rsi_scalp, stoch_k, stoch_d, dmi_stoch, cross_up, cross_down
    """
    df = df.copy()
    close = df["close"]
    high = df["high"]
    low = df["low"]

    # --- RSI (14) ---
    rsi_len = 14
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = _wwma(gain, rsi_len)
    avg_loss = _wwma(loss, rsi_len)
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["rsi_scalp"] = 100 - (100 / (1 + rs))
    df["rsi_scalp"] = df["rsi_scalp"].fillna(50)

    # --- Stochastic (K=14, D=6, Smooth=6) ---
    period_k = 14
    period_d = 6
    smooth_k = 6
    lowest_low = low.rolling(period_k).min()
    highest_high = high.rolling(period_k).max()
    raw_k = ((close - lowest_low) / (highest_high - lowest_low).replace(0, np.nan)) * 100
    df["stoch_k"] = raw_k.rolling(smooth_k).mean()
    df["stoch_d"] = df["stoch_k"].rolling(period_d).mean()

    # --- DMI Stochastic ---
    dmi_length = 20
    sto_length = 5

    hi_diff = high.diff()
    lo_diff = -low.diff()
    plus_dm = pd.Series(
        np.where((hi_diff > lo_diff) & (hi_diff > 0), hi_diff, 0.0),
        index=df.index,
    )
    minus_dm = pd.Series(
        np.where((lo_diff > hi_diff) & (lo_diff > 0), lo_diff, 0.0),
        index=df.index,
    )

    # True Range
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs(),
    ], axis=1).max(axis=1)

    atr_wwma = _wwma(tr, dmi_length)
    plus_di = 100 * _wwma(plus_dm, dmi_length) / atr_wwma.replace(0, np.nan)
    minus_di = 100 * _wwma(minus_dm, dmi_length) / atr_wwma.replace(0, np.nan)
    osc = plus_di - minus_di

    # DMI Stoch calculation
    osc_hi = osc.rolling(sto_length).max()
    osc_lo = osc.rolling(sto_length).min()
    osc_range = osc_hi - osc_lo
    dmi_stoch_sum_num = (osc - osc_lo).rolling(sto_length).sum()
    dmi_stoch_sum_den = osc_range.rolling(sto_length).sum()
    df["dmi_stoch"] = (dmi_stoch_sum_num / dmi_stoch_sum_den.replace(0, np.nan)) * 100
    df["dmi_stoch"] = df["dmi_stoch"].fillna(50)

    # --- Cross signals with filters ---
    prev_dmi = df["dmi_stoch"].shift(1)
    raw_cross_up = (prev_dmi < 10) & (df["dmi_stoch"] > 10)
    raw_cross_down = (prev_dmi > 90) & (df["dmi_stoch"] < 90)

    # Filter 1: RSI confirmation — BUY needs RSI < 45, SELL needs RSI > 55
    rsi_buy_ok = df["rsi_scalp"] < 45
    rsi_sell_ok = df["rsi_scalp"] > 55

    # Filter 2: Stochastic agreement — BUY needs K < 50, SELL needs K > 50
    stoch_buy_ok = df["stoch_k"] < 50
    stoch_sell_ok = df["stoch_k"] > 50

    filtered_up = raw_cross_up & rsi_buy_ok & stoch_buy_ok
    filtered_down = raw_cross_down & rsi_sell_ok & stoch_sell_ok

    # Filter 3: Minimum 5 candles between signals (debounce)
    df["cross_up"] = 0
    df["cross_down"] = 0
    last_signal_idx = -10
    for i in range(len(df)):
        if i - last_signal_idx < 5:
            continue
        if filtered_up.iloc[i]:
            df.iloc[i, df.columns.get_loc("cross_up")] = 1
            last_signal_idx = i
        elif filtered_down.iloc[i]:
            df.iloc[i, df.columns.get_loc("cross_down")] = 1
            last_signal_idx = i

    return df


class RSIScalpingStrategy(BaseStrategy):
    """RSI Scalping Strategy — BUY on DMI Stoch cross up from <10, SELL on cross down from >90.

    Supported regimes: all (scalping works in any market).
    """

    name = "rsi_scalping"
    supported_regimes = ["TREND_BULL", "TREND_BEAR", "CONSOLIDATION", "HIGH_VOL_CHOPPY"]
    min_confidence = 50.0

    def generate_signal(
        self,
        asset: str,
        timeframe: str,
        market_data: pd.DataFrame,
        context: MarketContext,
    ) -> SignalResult | None:
        """Generate RSI scalping signal."""
        if market_data.empty or len(market_data) < 30:
            return None

        df = compute_rsi_scalping_indicators(market_data)
        last = df.iloc[-1]

        rsi = float(last.get("rsi_scalp", 50))
        stoch_k = float(last.get("stoch_k", 50))
        stoch_d = float(last.get("stoch_d", 50))
        dmi_stoch = float(last.get("dmi_stoch", 50))
        cross_up = int(last.get("cross_up", 0))
        cross_down = int(last.get("cross_down", 0))
        close = float(last.get("close", 0))
        atr = float(last.get("atr_14", close * 0.01)) if "atr_14" in last.index else close * 0.01

        # BUY signal: DMI Stoch crosses above 10
        if cross_up:
            return self._build_long(asset, timeframe, df, last, close, atr, rsi, stoch_k, dmi_stoch)

        # SELL signal: DMI Stoch crosses below 90
        if cross_down:
            return self._build_short(asset, timeframe, df, last, close, atr, rsi, stoch_k, dmi_stoch)

        return None

    def _build_long(self, asset, timeframe, df, last, close, atr, rsi, stoch_k, dmi_stoch):
        factors = [
            {"name": "DMI Stoch Cross Up (<10→>10)", "weight": 0.4, "score": 0.9, "label": "BULLISH"},
        ]

        # RSI confirmation
        if rsi < 30:
            factors.append({"name": "RSI Oversold (<30)", "weight": 0.25, "score": 0.85, "label": "BULLISH"})
        elif rsi < 50:
            factors.append({"name": "RSI Below Midline", "weight": 0.15, "score": 0.6, "label": "BULLISH"})

        # Stochastic confirmation
        if stoch_k < 20:
            factors.append({"name": "Stoch K Oversold (<20)", "weight": 0.2, "score": 0.8, "label": "BULLISH"})
        if stoch_k > float(last.get("stoch_d", 50)):
            factors.append({"name": "Stoch K > D (Momentum Up)", "weight": 0.15, "score": 0.7, "label": "BULLISH"})

        stop_loss = round(close - atr * 1.5, 8)
        risk = close - stop_loss
        tp1 = round(close + risk * 1.5, 8)
        tp2 = round(close + risk * 3.0, 8)

        confidence = self._calc_confidence(factors, rsi, dmi_stoch, "LONG")

        return SignalResult(
            asset=asset, timeframe=timeframe, direction="LONG",
            confidence=confidence, entry_price=close,
            stop_loss=stop_loss, take_profit_1=tp1, take_profit_2=tp2,
            risk_reward=round(abs(tp1 - close) / max(risk, 0.0001), 2),
            factors=factors, strategy_name=self.name,
        )

    def _build_short(self, asset, timeframe, df, last, close, atr, rsi, stoch_k, dmi_stoch):
        factors = [
            {"name": "DMI Stoch Cross Down (>90→<90)", "weight": 0.4, "score": 0.9, "label": "BEARISH"},
        ]

        if rsi > 70:
            factors.append({"name": "RSI Overbought (>70)", "weight": 0.25, "score": 0.85, "label": "BEARISH"})
        elif rsi > 50:
            factors.append({"name": "RSI Above Midline", "weight": 0.15, "score": 0.6, "label": "BEARISH"})

        if stoch_k > 80:
            factors.append({"name": "Stoch K Overbought (>80)", "weight": 0.2, "score": 0.8, "label": "BEARISH"})
        if stoch_k < float(last.get("stoch_d", 50)):
            factors.append({"name": "Stoch K < D (Momentum Down)", "weight": 0.15, "score": 0.7, "label": "BEARISH"})

        stop_loss = round(close + atr * 1.5, 8)
        risk = stop_loss - close
        tp1 = round(close - risk * 1.5, 8)
        tp2 = round(close - risk * 3.0, 8)

        confidence = self._calc_confidence(factors, rsi, dmi_stoch, "SHORT")

        return SignalResult(
            asset=asset, timeframe=timeframe, direction="SHORT",
            confidence=confidence, entry_price=close,
            stop_loss=stop_loss, take_profit_1=tp1, take_profit_2=tp2,
            risk_reward=round(abs(close - tp1) / max(risk, 0.0001), 2),
            factors=factors, strategy_name=self.name,
        )

    def _calc_confidence(self, factors, rsi, dmi_stoch, direction):
        weighted = sum(f["weight"] * f["score"] for f in factors)
        total_w = sum(f["weight"] for f in factors)
        base = (weighted / total_w * 100) if total_w > 0 else 50

        # Boost for extreme RSI
        if direction == "LONG" and rsi < 25:
            base += 10
        if direction == "SHORT" and rsi > 75:
            base += 10

        return round(min(base, 95), 1)
