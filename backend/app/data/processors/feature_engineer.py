"""Feature engineering — computes technical indicators from OHLCV data."""

import logging
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import ADXIndicator, EMAIndicator, MACD
from ta.volatility import AverageTrueRange, BollingerBands
from ta.volume import OnBalanceVolumeIndicator

logger = logging.getLogger(__name__)

_feature_cache: dict[str, tuple[float, pd.DataFrame]] = {}
CACHE_TTL = 15  # seconds


def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute all technical indicators on an OHLCV DataFrame.

    Expects columns: open, high, low, close, volume.
    Returns the DataFrame with new indicator columns appended.
    Rows with insufficient history for the longest window are dropped.
    Uses an in-memory cache with 15s TTL to avoid redundant recomputation.
    """
    # Generate cache key from shape and last close price
    cache_key = f"{len(df)}_{df.iloc[-1]['close'] if not df.empty else 0}"
    now = datetime.now(timezone.utc).timestamp()

    if cache_key in _feature_cache:
        cached_time, cached_df = _feature_cache[cache_key]
        if now - cached_time < CACHE_TTL:
            return cached_df.copy()

    result = _compute_features_impl(df)
    _feature_cache[cache_key] = (now, result)

    # Evict old entries
    if len(_feature_cache) > 100:
        oldest = min(_feature_cache, key=lambda k: _feature_cache[k][0])
        del _feature_cache[oldest]

    return result


def _compute_features_impl(df: pd.DataFrame) -> pd.DataFrame:
    """Compute all technical indicators (internal implementation).

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
    _add_ichimoku_indicators(df)
    df = _add_vwap_indicator(df)

    # Drop NaN but preserve Ichimoku columns (they have intentional NaN from shift)
    ichimoku_cols = ["ichimoku_tenkan", "ichimoku_kijun", "ichimoku_senkou_a", "ichimoku_senkou_b", "ichimoku_chikou",
                     "vwap", "vwap_upper_1", "vwap_lower_1", "vwap_upper_2", "vwap_lower_2"]
    existing_ichimoku = [c for c in ichimoku_cols if c in df.columns]
    non_ichimoku = [c for c in df.columns if c not in existing_ichimoku]
    df.dropna(subset=non_ichimoku, inplace=True)
    logger.info("Computed %d features on %d rows", _feature_count(), len(df))
    return df


def _validate_columns(df: pd.DataFrame) -> None:
    """Ensure required OHLCV columns exist."""
    required = {"open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    # Check data quality
    if df.isna().sum().sum() / df.size > 0.1:
        logger.warning("DataFrame has >10%% NaN values, results may be unreliable")
    if (df["volume"] == 0).sum() > len(df) * 0.5:
        logger.warning("More than 50%% of candles have zero volume")
    # Fix invalid OHLC (repair instead of just warning)
    bad_mask = (df["low"] > df["close"]) | (df["low"] > df["open"]) | (df["high"] < df["close"]) | (df["high"] < df["open"])
    bad_count = bad_mask.sum()
    if bad_count > 0:
        logger.warning("OHLC REPAIR: Fixing %d candles with invalid OHLC order", bad_count)
        (df["open"] + df["high"] + df["low"] + df["close"]) / 4
        df.loc[bad_mask, "low"] = df.loc[bad_mask, ["open", "high", "low", "close"]].min(axis=1)
        df.loc[bad_mask, "high"] = df.loc[bad_mask, ["open", "high", "low", "close"]].max(axis=1)

    # Check data freshness
    if "timestamp" in df.columns and len(df) > 0:
        last_ts = df["timestamp"].iloc[-1]
        if hasattr(last_ts, "timestamp"):
            from datetime import datetime, timezone
            last_dt = last_ts.to_pydatetime()
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
            age_minutes = (datetime.now(timezone.utc) - last_dt).total_seconds() / 60
            if age_minutes > 30:
                logger.warning("STALE DATA: Last candle is %.0f minutes old", age_minutes)

    # Check for data gaps
    if "timestamp" in df.columns and len(df) > 2:
        diffs = df["timestamp"].diff().dropna()
        median_diff = diffs.median()
        gaps = diffs[diffs > median_diff * 2]
        if len(gaps) > 0:
            logger.warning("DATA GAPS: %d gaps detected (>2x normal interval)", len(gaps))

    # Flag extreme volume spikes
    if "volume" in df.columns:
        vol_median = df["volume"].rolling(20).median()
        spikes = df["volume"] > vol_median * 10
        spike_count = spikes.sum()
        if spike_count > 0:
            logger.warning("VOLUME SPIKES: %d candles with volume >10x median", spike_count)


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


def _add_ichimoku_indicators(df: pd.DataFrame) -> None:
    """Ichimoku Cloud — Tenkan(9), Kijun(26), Senkou A/B(shifted 26), Chikou(shifted -26)."""
    high = df["high"]
    low = df["low"]

    tenkan_period = 9
    kijun_period = 26
    senkou_span = 26

    # Tenkan-sen (Conversion Line)
    df["ichimoku_tenkan"] = (high.rolling(tenkan_period).max() + low.rolling(tenkan_period).min()) / 2
    # Kijun-sen (Base Line)
    df["ichimoku_kijun"] = (high.rolling(kijun_period).max() + low.rolling(kijun_period).min()) / 2
    # Senkou Span A (shifted forward 26 periods)
    df["ichimoku_senkou_a"] = ((df["ichimoku_tenkan"] + df["ichimoku_kijun"]) / 2).shift(senkou_span)
    # Senkou Span B (shifted forward 26 periods)
    df["ichimoku_senkou_b"] = ((high.rolling(senkou_span * 2).max() + low.rolling(senkou_span * 2).min()) / 2).shift(senkou_span)
    # Chikou Span (close shifted back 26 periods)
    df["ichimoku_chikou"] = df["close"].shift(-senkou_span)


def _add_vwap_indicator(df: pd.DataFrame) -> pd.DataFrame:
    """Compute VWAP with 1-sigma and 2-sigma bands.

    VWAP = cumsum(typical_price * volume) / cumsum(volume).
    Bands are derived from a rolling standard deviation of the
    volume-weighted typical price, using a 20-period window.

    Adds columns: vwap, vwap_upper_1, vwap_lower_1, vwap_upper_2, vwap_lower_2.
    """
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    cum_vol = df["volume"].cumsum()
    cum_tp_vol = (typical_price * df["volume"]).cumsum()

    # Avoid division by zero for rows with no cumulative volume
    vwap = np.where(cum_vol > 0, cum_tp_vol / cum_vol, typical_price)
    df["vwap"] = vwap

    # Rolling volume-weighted standard deviation of typical price (20-period)
    window = 20
    tp_sq_vol = (typical_price ** 2) * df["volume"]
    tp_sq_vol.cumsum()
    # variance = E[X^2] - E[X]^2, weighted by volume
    rolling_cum_vol = df["volume"].rolling(window, min_periods=1).sum()
    rolling_tp_vol = (typical_price * df["volume"]).rolling(window, min_periods=1).sum()
    rolling_tp_sq_vol = tp_sq_vol.rolling(window, min_periods=1).sum()

    rolling_mean = np.where(rolling_cum_vol > 0, rolling_tp_vol / rolling_cum_vol, 0)
    rolling_mean_sq = np.where(rolling_cum_vol > 0, rolling_tp_sq_vol / rolling_cum_vol, 0)
    variance = np.maximum(rolling_mean_sq - rolling_mean ** 2, 0)
    std = np.sqrt(variance)

    df["vwap_upper_1"] = df["vwap"] + std
    df["vwap_lower_1"] = df["vwap"] - std
    df["vwap_upper_2"] = df["vwap"] + 2 * std
    df["vwap_lower_2"] = df["vwap"] - 2 * std

    return df


def compute_divergences(df: pd.DataFrame, lookback: int = 50) -> list[dict]:
    """Detect RSI and MACD histogram divergences on price.

    Scans for local swing lows/highs in price and the corresponding
    indicator values, flagging bullish and bearish divergences.

    Returns a list of dicts with keys:
        type        — 'bullish' or 'bearish'
        indicator   — 'RSI' or 'MACD'
        start_idx   — integer index of the first swing point
        end_idx     — integer index of the second swing point
        strength    — float 0-1 measuring the magnitude of divergence
    """
    required_cols = {"close", "rsi_14", "macd_diff"}
    if not required_cols.issubset(df.columns):
        logger.warning("compute_divergences: missing columns %s", required_cols - set(df.columns))
        return []

    lookback = min(lookback, len(df))
    recent = df.tail(lookback).copy()

    if len(recent) < 10:
        return []

    divergences: list[dict] = []
    close = recent["close"].values
    indices = recent.index.tolist()

    indicator_map = {
        "RSI": recent["rsi_14"].values,
        "MACD": recent["macd_diff"].values,
    }

    for indicator_name, indicator_vals in indicator_map.items():
        # Find local swing lows (for bullish divergence)
        swing_lows = _find_swing_points(close, mode="low")
        for i in range(len(swing_lows) - 1):
            a, b = swing_lows[i], swing_lows[i + 1]
            if np.isnan(indicator_vals[a]) or np.isnan(indicator_vals[b]):
                continue
            # Bullish: price makes lower low, indicator makes higher low
            if close[b] < close[a] and indicator_vals[b] > indicator_vals[a]:
                price_change = abs(close[b] - close[a]) / close[a]
                ind_change = abs(indicator_vals[b] - indicator_vals[a])
                strength = min(1.0, (price_change + ind_change / 100) * 5)
                divergences.append({
                    "type": "bullish",
                    "indicator": indicator_name,
                    "start_idx": int(indices[a]),
                    "end_idx": int(indices[b]),
                    "strength": round(strength, 2),
                })

        # Find local swing highs (for bearish divergence)
        swing_highs = _find_swing_points(close, mode="high")
        for i in range(len(swing_highs) - 1):
            a, b = swing_highs[i], swing_highs[i + 1]
            if np.isnan(indicator_vals[a]) or np.isnan(indicator_vals[b]):
                continue
            # Bearish: price makes higher high, indicator makes lower high
            if close[b] > close[a] and indicator_vals[b] < indicator_vals[a]:
                price_change = abs(close[b] - close[a]) / close[a]
                ind_change = abs(indicator_vals[b] - indicator_vals[a])
                strength = min(1.0, (price_change + ind_change / 100) * 5)
                divergences.append({
                    "type": "bearish",
                    "indicator": indicator_name,
                    "start_idx": int(indices[a]),
                    "end_idx": int(indices[b]),
                    "strength": round(strength, 2),
                })

    return divergences


def _find_swing_points(data: np.ndarray, mode: str = "low", order: int = 3) -> list[int]:
    """Find local swing highs or lows in a 1-D array.

    Args:
        data: Price or indicator values.
        mode: 'low' for swing lows, 'high' for swing highs.
        order: Number of neighbours on each side to compare.

    Returns:
        List of integer indices where swing points occur.
    """
    swings: list[int] = []
    for i in range(order, len(data) - order):
        if np.isnan(data[i]):
            continue
        window = data[i - order: i + order + 1]
        if np.any(np.isnan(window)):
            continue
        if mode == "low" and data[i] == np.min(window):
            swings.append(i)
        elif mode == "high" and data[i] == np.max(window):
            swings.append(i)
    return swings


def compute_fibonacci_levels(df: pd.DataFrame, lookback: int = 100) -> dict:
    """Compute Fibonacci retracement levels from auto swing H/L detection.

    Returns dict with level percentages as keys and prices as values,
    plus swing_high and swing_low metadata.
    """
    lookback = min(lookback, len(df))
    recent = df.tail(lookback)
    swing_high = float(recent["high"].max())
    swing_low = float(recent["low"].min())
    diff = swing_high - swing_low

    if diff <= 0:
        return {"swing_high": swing_high, "swing_low": swing_low, "levels": []}

    fib_ratios = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 0.886, 1.0]
    levels = []
    for ratio in fib_ratios:
        price = swing_low + diff * ratio
        levels.append({
            "ratio": ratio,
            "label": f"{ratio * 100:.1f}%",
            "price": round(price, 8),
        })

    return {
        "swing_high": swing_high,
        "swing_low": swing_low,
        "levels": levels,
    }


def compute_support_resistance(df: pd.DataFrame, lookback: int = 200) -> list[dict]:
    """Compute support/resistance levels via pivot clustering.

    Returns list of dicts with price, touches, role ('support'/'resistance'), strength.
    """
    lookback = min(lookback, len(df))
    recent = df.tail(lookback)

    if len(recent) < 5:
        return []

    # Find local pivots (swing highs and lows)
    pivots: list[dict] = []
    for i in range(2, len(recent) - 2):
        h = float(recent.iloc[i]["high"])
        l = float(recent.iloc[i]["low"])
        if (h >= float(recent.iloc[i-1]["high"]) and h >= float(recent.iloc[i-2]["high"])
                and h >= float(recent.iloc[i+1]["high"]) and h >= float(recent.iloc[i+2]["high"])):
            pivots.append({"price": h, "type": "resistance"})
        if (l <= float(recent.iloc[i-1]["low"]) and l <= float(recent.iloc[i-2]["low"])
                and l <= float(recent.iloc[i+1]["low"]) and l <= float(recent.iloc[i+2]["low"])):
            pivots.append({"price": l, "type": "support"})

    if not pivots:
        return []

    # Cluster nearby pivots using ATR
    atr = float(df.iloc[-1].get("atr_14", 1))
    cluster_threshold = atr * 0.5
    sorted_pivots = sorted(pivots, key=lambda p: p["price"])
    clusters: list[dict] = []
    current_cluster = [sorted_pivots[0]]

    for p in sorted_pivots[1:]:
        if abs(p["price"] - current_cluster[-1]["price"]) < cluster_threshold:
            current_cluster.append(p)
        else:
            _add_cluster(clusters, current_cluster)
            current_cluster = [p]

    _add_cluster(clusters, current_cluster)

    # Filter by minimum touches and score by proximity to current price
    last_close = float(df.iloc[-1]["close"])
    result = []
    for c in clusters:
        if c["touches"] < 2:
            continue
        distance_pct = abs(c["price"] - last_close) / last_close * 100
        c["distance_pct"] = round(distance_pct, 2)
        c["color"] = "#ef4444" if c["role"] == "resistance" else "#3b82f6"
        result.append(c)

    return sorted(result, key=lambda x: x["price"])


def _add_cluster(clusters: list[dict], pivot_group: list[dict]) -> None:
    """Add a cluster from a group of nearby pivots."""
    avg_price = sum(p["price"] for p in pivot_group) / len(pivot_group)
    resistance_count = sum(1 for p in pivot_group if p["type"] == "resistance")
    role = "resistance" if resistance_count > len(pivot_group) / 2 else "support"
    clusters.append({
        "price": round(avg_price, 8),
        "touches": len(pivot_group),
        "role": role,
        "strength": round(min(len(pivot_group) / 5, 1.0), 2),
    })


def compute_money_flow_markers(df: pd.DataFrame) -> list[dict]:
    """Compute institutional money flow markers.

    $ marker: volume > 2x avg + body > 1.5 ATR
    $$$ marker: volume > 4x avg
    Returns list of dicts with time index, marker text, and direction.
    """
    if len(df) < 20:
        return []

    markers: list[dict] = []
    vol_avg = df["volume"].rolling(20).mean()
    atr = df.get("atr_14")
    if atr is None:
        return []

    for i in range(20, len(df)):
        row = df.iloc[i]
        vol = float(row["volume"])
        avg = float(vol_avg.iloc[i])
        current_atr = float(atr.iloc[i])

        if avg <= 0 or current_atr <= 0:
            continue

        vol_ratio = vol / avg
        body = abs(float(row["close"]) - float(row["open"]))
        body_atr_ratio = body / current_atr

        if vol_ratio < 2.0 or body_atr_ratio < 1.5:
            continue

        direction = "up" if float(row["close"]) > float(row["open"]) else "down"

        if vol_ratio >= 4.0:
            marker_text = "$$$"
            intensity = "extreme"
        elif vol_ratio >= 3.0:
            marker_text = "$$"
            intensity = "high"
        else:
            marker_text = "$"
            intensity = "medium"

        marker = {
            "index": int(df.index[i]),
            "text": marker_text,
            "direction": direction,
            "intensity": intensity,
            "volume_ratio": round(vol_ratio, 2),
            "body_atr": round(body_atr_ratio, 2),
        }

        # Add timestamp if available
        if "timestamp" in df.columns:
            ts = row["timestamp"]
            if hasattr(ts, "timestamp"):
                marker["time"] = int(ts.timestamp())

        markers.append(marker)

    return markers


def _feature_count() -> int:
    """Return total number of features this module produces."""
    return 32
