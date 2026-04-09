"""Feature engineering — computes technical indicators from OHLCV data."""

import logging

import numpy as np
import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import ADXIndicator, EMAIndicator, MACD
from ta.volatility import AverageTrueRange, BollingerBands
from ta.volume import OnBalanceVolumeIndicator

logger = logging.getLogger(__name__)


def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute all technical indicators on an OHLCV DataFrame.

    Expects columns: open, high, low, close, volume.
    Returns the DataFrame with new indicator columns appended.
    Rows with insufficient history for the longest window are dropped.
    """
    df = df.copy()
    _validate_columns(df)

    _add_trend_indicators(df)
    _add_momentum_indicators(df)
    _add_volatility_indicators(df)
    _add_volume_indicators(df)
    _add_derived_indicators(df)

    df.dropna(inplace=True)
    logger.info("Computed %d features on %d rows", _feature_count(), len(df))
    return df


def _validate_columns(df: pd.DataFrame) -> None:
    """Ensure required OHLCV columns exist."""
    required = {"open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")


def _add_trend_indicators(df: pd.DataFrame) -> None:
    """EMA 20/50/200 and ADX 14."""
    close = df["close"]

    # EMA
    df["ema_20"] = EMAIndicator(close, window=20).ema_indicator()
    df["ema_50"] = EMAIndicator(close, window=50).ema_indicator()
    df["ema_200"] = EMAIndicator(close, window=200).ema_indicator()

    # ADX
    adx = ADXIndicator(df["high"], df["low"], close, window=14)
    df["adx_14"] = adx.adx()
    df["adx_pos"] = adx.adx_pos()
    df["adx_neg"] = adx.adx_neg()


def _add_momentum_indicators(df: pd.DataFrame) -> None:
    """RSI 14 and MACD."""
    close = df["close"]

    df["rsi_14"] = RSIIndicator(close, window=14).rsi()

    macd = MACD(close)
    df["macd"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["macd_diff"] = macd.macd_diff()


def _add_volatility_indicators(df: pd.DataFrame) -> None:
    """ATR 14, Bollinger Bands, and historical volatility."""
    close = df["close"]
    high = df["high"]
    low = df["low"]

    df["atr_14"] = AverageTrueRange(high, low, close, window=14).average_true_range()

    bb = BollingerBands(close, window=20, window_dev=2)
    df["bb_upper"] = bb.bollinger_hband()
    df["bb_middle"] = bb.bollinger_mavg()
    df["bb_lower"] = bb.bollinger_lband()
    df["bb_width"] = bb.bollinger_wband()

    # Historical volatility (20-period annualized std of log returns)
    log_returns = np.log(close / close.shift(1))
    df["hv_20"] = log_returns.rolling(window=20).std() * np.sqrt(252)


def _add_volume_indicators(df: pd.DataFrame) -> None:
    """OBV and volume SMA 20."""
    df["obv"] = OnBalanceVolumeIndicator(df["close"], df["volume"]).on_balance_volume()
    df["volume_sma_20"] = df["volume"].rolling(window=20).mean()


def _add_derived_indicators(df: pd.DataFrame) -> None:
    """Manually derived composite indicators."""
    close = df["close"]

    # ATR normalized (ATR as % of price)
    df["atr_normalized"] = df["atr_14"] / close

    # Price position relative to EMA200
    df["price_vs_ema200"] = (close - df["ema_200"]) / df["ema_200"]

    # Volume relative to 20-period average
    df["volume_vs_avg"] = df["volume"] / df["volume_sma_20"]

    # EMA cross signal: 1 (bullish), -1 (bearish), 0 (neutral)
    ema20_above_50 = df["ema_20"] > df["ema_50"]
    ema50_above_200 = df["ema_50"] > df["ema_200"]
    df["ema_cross_signal"] = np.where(
        ema20_above_50 & ema50_above_200,
        1,
        np.where(~ema20_above_50 & ~ema50_above_200, -1, 0),
    )

    # Bollinger Band position: where the price sits within the bands (0 = lower, 1 = upper)
    bb_range = df["bb_upper"] - df["bb_lower"]
    df["bb_position"] = np.where(
        bb_range > 0,
        (close - df["bb_lower"]) / bb_range,
        0.5,
    )


def _feature_count() -> int:
    """Return total number of features this module produces."""
    return 22
