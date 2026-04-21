"""Market data endpoints."""

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.market_regime import MarketRegime
from app.models.onchain_event import OnChainEvent
from app.models.sentiment_data import SentimentData
from app.schemas.signal import OnChainEventResponse, RegimeResponse, SentimentResponse

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/regime", response_model=list[RegimeResponse])
async def get_all_regimes(
    db: AsyncSession = Depends(get_db),
) -> list[RegimeResponse]:
    """Get current regime for all assets (latest per asset)."""
    # Subquery: latest regime per asset
    from sqlalchemy import func

    subq = (
        select(
            MarketRegime.asset,
            func.max(MarketRegime.started_at).label("max_started"),
        )
        .where(MarketRegime.ended_at.is_(None))
        .group_by(MarketRegime.asset)
        .subquery()
    )

    query = select(MarketRegime).join(
        subq,
        (MarketRegime.asset == subq.c.asset)
        & (MarketRegime.started_at == subq.c.max_started),
    )

    result = await db.execute(query)
    regimes = result.scalars().all()
    return [RegimeResponse.model_validate(r) for r in regimes]


@router.get("/regime/{asset}", response_model=RegimeResponse)
async def get_asset_regime(
    asset: str,
    db: AsyncSession = Depends(get_db),
) -> RegimeResponse:
    """Get current regime for a specific asset."""
    result = await db.execute(
        select(MarketRegime)
        .where(MarketRegime.asset == asset, MarketRegime.ended_at.is_(None))
        .order_by(MarketRegime.started_at.desc())
        .limit(1)
    )
    regime = result.scalar_one_or_none()
    if not regime:
        raise HTTPException(status_code=404, detail=f"No regime found for {asset}")
    return RegimeResponse.model_validate(regime)


@router.get("/sentiment", response_model=list[SentimentResponse])
async def get_sentiment(
    db: AsyncSession = Depends(get_db),
) -> list[SentimentResponse]:
    """Get latest sentiment scores (most recent per asset)."""
    from sqlalchemy import func

    subq = (
        select(
            SentimentData.asset,
            func.max(SentimentData.created_at).label("max_created"),
        )
        .group_by(SentimentData.asset)
        .subquery()
    )

    query = select(SentimentData).join(
        subq,
        (SentimentData.asset == subq.c.asset)
        & (SentimentData.created_at == subq.c.max_created),
    )

    result = await db.execute(query)
    rows = result.scalars().all()
    return [SentimentResponse.model_validate(r) for r in rows]


@router.get("/onchain", response_model=list[OnChainEventResponse])
async def get_onchain_events(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
) -> list[OnChainEventResponse]:
    """Get recent on-chain events."""
    result = await db.execute(
        select(OnChainEvent)
        .order_by(OnChainEvent.timestamp.desc())
        .limit(limit)
    )
    events = result.scalars().all()
    return [OnChainEventResponse.model_validate(e) for e in events]


FOREX_SYMBOLS = {"EURUSD", "GBPUSD", "XAUUSD", "GBPJPY", "EUR/USD", "GBP/USD", "XAU/USD", "GBP/JPY"}
FOREX_MAP = {"EURUSD": "EUR/USD", "GBPUSD": "GBP/USD", "XAUUSD": "XAU/USD", "GBPJPY": "GBP/JPY"}


@router.get("/symbols")
async def get_all_symbols() -> dict:
    """Return all active Binance USDT perpetual futures symbols plus forex pairs.

    Uses the cached dynamic symbol list (refreshed hourly from Binance).
    """
    from app.core.symbols import get_active_crypto_symbols
    from app.core.symbols import FOREX_SYMBOLS

    crypto = get_active_crypto_symbols()
    return {
        "crypto": [{"label": s, "value": s.replace("/", "")} for s in crypto],
        "forex": [{"label": s, "value": s.replace("/", "")} for s in FOREX_SYMBOLS],
        "total": len(crypto) + len(FOREX_SYMBOLS),
    }


@router.get("/klines")
async def get_klines(
    asset: str = Query(default="BTCUSDT", description="Trading pair symbol"),
    interval: str = Query(default="1h", description="Kline interval"),
    limit: int = Query(default=300, ge=1, le=1000, description="Number of candles"),
) -> list[dict]:
    """Get kline data — routes to Binance for crypto, Forex provider for FX/Gold."""
    # Check if this is a forex pair
    normalized = asset.upper().replace("/", "")
    forex_key = FOREX_MAP.get(normalized) or (asset if asset in FOREX_SYMBOLS else None)

    if forex_key:
        # Load Yahoo historical first (for deep chart history)
        yahoo_candles = await _fetch_yahoo_historical(forex_key, interval, limit)

        # Then append any recent tick-based candles from our forex provider
        from app.data.fetchers.forex_provider import get_forex_provider
        provider = get_forex_provider()
        tick_candles = provider.get_candles(forex_key, interval, 50)

        if yahoo_candles and tick_candles:
            # Merge: use Yahoo for history, tick candles for most recent
            last_yahoo_time = yahoo_candles[-1]["time"] if yahoo_candles else 0
            new_ticks = [c for c in tick_candles if c["time"] > last_yahoo_time]
            combined = yahoo_candles + new_ticks
            return combined[-limit:]
        elif yahoo_candles:
            return yahoo_candles
        elif tick_candles:
            return tick_candles
        return []

    # Binance crypto klines
    binance_url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": asset, "interval": interval, "limit": limit}

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(binance_url, params=params)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=exc.response.status_code,
                detail=f"Binance API error: {exc.response.text}",
            ) from exc
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Failed to reach Binance API: {exc}",
            ) from exc

    raw_klines: list[list] = response.json()
    return [
        {
            "time": int(k[0]) // 1000,
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5]),
        }
        for k in raw_klines
    ]


async def _fetch_yahoo_historical(symbol: str, interval: str, limit: int) -> list[dict]:
    """Fetch historical candles from Yahoo Finance for forex pairs."""
    yahoo_map = {"EUR/USD": "EURUSD=X", "GBP/USD": "GBPUSD=X", "XAU/USD": "GC=F", "GBP/JPY": "GBPJPY=X"}
    yahoo_sym = yahoo_map.get(symbol, symbol.replace("/", "") + "=X")
    yahoo_interval = {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "60m", "4h": "60m", "1d": "1d"}.get(interval, "60m")
    yahoo_range = {"1m": "1d", "5m": "5d", "15m": "5d", "1h": "1mo", "4h": "3mo", "1d": "1y"}.get(interval, "1mo")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_sym}",
                params={"interval": yahoo_interval, "range": yahoo_range},
                headers={"User-Agent": "Mozilla/5.0"},
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
            result = data.get("chart", {}).get("result", [])
            if not result:
                return []

            timestamps = result[0].get("timestamp", [])
            quotes = result[0].get("indicators", {}).get("quote", [{}])[0]
            opens = quotes.get("open", [])
            highs = quotes.get("high", [])
            lows = quotes.get("low", [])
            closes = quotes.get("close", [])
            volumes = quotes.get("volume", [])

            candles = []
            for i in range(len(timestamps)):
                if opens[i] is None or closes[i] is None:
                    continue
                candles.append({
                    "time": timestamps[i],
                    "open": round(opens[i], 5),
                    "high": round(highs[i], 5),
                    "low": round(lows[i], 5),
                    "close": round(closes[i], 5),
                    "volume": volumes[i] or 0,
                })
            return candles[-limit:]
    except Exception:
        return []


@router.get("/indicators")
async def get_indicators(
    asset: str = Query(default="BTCUSDT"),
    interval: str = Query(default="1h"),
    limit: int = Query(default=300, ge=50, le=1000),
) -> dict:
    """Compute technical indicators on live Binance data.

    Returns EMA, Bollinger Bands, Order Blocks, FVGs, liquidation estimates.
    """
    import numpy as np
    from app.ai.strategies.smc_strategy import find_order_blocks, find_fair_value_gaps
    from app.data.processors.feature_engineer import compute_features

    # Fetch klines
    binance_url = "https://api.binance.com/api/v3/klines"
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(binance_url, params={"symbol": asset, "interval": interval, "limit": limit})
        resp.raise_for_status()
    raw = resp.json()

    import pandas as pd
    from datetime import datetime, timezone

    df = pd.DataFrame([{
        "timestamp": datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc),
        "open": float(k[1]), "high": float(k[2]), "low": float(k[3]),
        "close": float(k[4]), "volume": float(k[5]),
    } for k in raw])

    featured = compute_features(df)
    if featured.empty:
        return {"error": "Insufficient data"}

    times = [int(t.timestamp()) for t in featured["timestamp"]]

    # EMAs
    ema_20 = [{"time": t, "value": round(v, 2)} for t, v in zip(times, featured["ema_20"])]
    ema_50 = [{"time": t, "value": round(v, 2)} for t, v in zip(times, featured["ema_50"])]
    ema_200 = [{"time": t, "value": round(v, 2)} for t, v in zip(times, featured["ema_200"])]

    # Bollinger Bands
    bb_upper = [{"time": t, "value": round(v, 2)} for t, v in zip(times, featured["bb_upper"])]
    bb_middle = [{"time": t, "value": round(v, 2)} for t, v in zip(times, featured["bb_middle"])]
    bb_lower = [{"time": t, "value": round(v, 2)} for t, v in zip(times, featured["bb_lower"])]

    # RSI (for separate pane)
    rsi = [{"time": t, "value": round(v, 2)} for t, v in zip(times, featured["rsi_14"])]

    # MACD
    macd_line = [{"time": t, "value": round(v, 4)} for t, v in zip(times, featured["macd"])]
    macd_signal = [{"time": t, "value": round(v, 4)} for t, v in zip(times, featured["macd_signal"])]
    macd_hist = [{"time": t, "value": round(v, 4)} for t, v in zip(times, featured["macd_diff"])]

    # Order Blocks — with clear LONG/SHORT signal
    obs = find_order_blocks(featured, lookback=40)
    order_blocks = []
    last_close = float(featured.iloc[-1]["close"])
    for ob in obs:
        idx = ob["index"]
        row_pos = featured.index.get_loc(idx)
        if row_pos < len(times):
            # Bullish OB below price = LONG zone, Bearish OB above price = SHORT zone
            if ob["type"] == "bullish":
                signal = "LONG" if ob["mid"] < last_close else "WATCH_LONG"
                status = "active" if ob["mid"] < last_close else "broken"
            else:
                signal = "SHORT" if ob["mid"] > last_close else "WATCH_SHORT"
                status = "active" if ob["mid"] > last_close else "broken"

            order_blocks.append({
                "time": times[row_pos],
                "type": ob["type"],
                "signal": signal,
                "status": status,
                "high": round(ob["high"], 2),
                "low": round(ob["low"], 2),
                "mid": round(ob["mid"], 2),
                "strength": round(ob["strength"], 2),
                "distance_pct": round(abs(last_close - ob["mid"]) / last_close * 100, 2),
            })

    # Fair Value Gaps — with LONG/SHORT signal
    fvgs = find_fair_value_gaps(featured, lookback=40)
    fair_value_gaps = []
    for fvg in fvgs:
        idx = fvg["index"]
        row_pos = featured.index.get_loc(idx)
        if row_pos < len(times):
            if fvg["type"] == "bullish":
                signal = "LONG" if fvg["mid"] < last_close else "WATCH"
            else:
                signal = "SHORT" if fvg["mid"] > last_close else "WATCH"

            filled = (fvg["type"] == "bullish" and last_close < fvg["bottom"]) or \
                     (fvg["type"] == "bearish" and last_close > fvg["top"])
            fair_value_gaps.append({
                "time": times[row_pos],
                "type": fvg["type"],
                "signal": signal,
                "filled": filled,
                "top": round(fvg["top"], 2),
                "bottom": round(fvg["bottom"], 2),
                "mid": round((fvg["top"] + fvg["bottom"]) / 2, 2),
                "size_pct": round(abs(fvg["top"] - fvg["bottom"]) / last_close * 100, 3),
            })

    # Volume Profile — aggregate volume at price levels for heatmap
    atr = float(featured.iloc[-1]["atr_14"])
    price_min = float(featured["low"].min())
    price_max = float(featured["high"].max())
    bucket_size = atr * 0.5  # each bucket = 0.5 ATR
    num_buckets = max(int((price_max - price_min) / bucket_size) + 1, 1)
    volume_profile = []
    for i in range(num_buckets):
        bucket_low = price_min + i * bucket_size
        bucket_high = bucket_low + bucket_size
        # Sum volume of candles that touch this price range
        mask = (featured["high"] >= bucket_low) & (featured["low"] <= bucket_high)
        vol = float(featured.loc[mask, "volume"].sum())
        buy_vol = float(featured.loc[mask & (featured["close"] >= featured["open"]), "volume"].sum())
        sell_vol = vol - buy_vol
        volume_profile.append({
            "price_low": round(bucket_low, 2),
            "price_high": round(bucket_high, 2),
            "price_mid": round((bucket_low + bucket_high) / 2, 2),
            "total_volume": round(vol, 2),
            "buy_volume": round(buy_vol, 2),
            "sell_volume": round(sell_vol, 2),
            "pct_of_max": 0,  # filled below
        })

    # Normalize volume profile
    max_vol = max((vp["total_volume"] for vp in volume_profile), default=1)
    for vp in volume_profile:
        vp["pct_of_max"] = round(vp["total_volume"] / max_vol * 100, 1) if max_vol > 0 else 0

    # POC (Point of Control) — price level with highest volume
    poc = max(volume_profile, key=lambda x: x["total_volume"]) if volume_profile else None

    # Liquidation heatmap — estimated levels with intensity
    liquidation_levels = []
    leverage_levels = [5, 10, 25, 50, 100]
    for lev in leverage_levels:
        # Long liquidation = price - (price / leverage)
        long_liq = round(last_close * (1 - 1 / lev), 2)
        # Short liquidation = price + (price / leverage)
        short_liq = round(last_close * (1 + 1 / lev), 2)
        # Intensity based on how common this leverage is (lower = more common)
        intensity = min(100, int(200 / lev))
        liquidation_levels.append({
            "price": long_liq, "side": "long", "leverage": lev,
            "distance_pct": round((last_close - long_liq) / last_close * 100, 2),
            "intensity": intensity,
        })
        liquidation_levels.append({
            "price": short_liq, "side": "short", "leverage": lev,
            "distance_pct": round((short_liq - last_close) / last_close * 100, 2),
            "intensity": intensity,
        })

    # Ichimoku Cloud
    ichimoku_tenkan = [{"time": t, "value": round(v, 2)} for t, v in zip(times, featured["ichimoku_tenkan"]) if not pd.isna(v)]
    ichimoku_kijun = [{"time": t, "value": round(v, 2)} for t, v in zip(times, featured["ichimoku_kijun"]) if not pd.isna(v)]
    ichimoku_senkou_a = [{"time": t, "value": round(v, 2)} for t, v in zip(times, featured["ichimoku_senkou_a"]) if not pd.isna(v)]
    ichimoku_senkou_b = [{"time": t, "value": round(v, 2)} for t, v in zip(times, featured["ichimoku_senkou_b"]) if not pd.isna(v)]
    ichimoku_chikou = [{"time": t, "value": round(v, 2)} for t, v in zip(times, featured["ichimoku_chikou"]) if not pd.isna(v)]

    # Fibonacci levels
    from app.data.processors.feature_engineer import compute_fibonacci_levels, compute_support_resistance, compute_money_flow_markers, compute_divergences
    from app.data.processors.pattern_detector import detect_patterns

    # Chart patterns (Double Top/Bottom, H&S, Triangles)
    raw_patterns = detect_patterns(featured)
    chart_patterns = []
    for pat in raw_patterns:
        entry: dict = {**pat}
        if pat["start_idx"] < len(times):
            entry["start_time"] = times[pat["start_idx"]]
        if pat["end_idx"] < len(times):
            entry["end_time"] = times[pat["end_idx"]]
        chart_patterns.append(entry)

    fibonacci = compute_fibonacci_levels(featured, lookback=100)

    # Support / Resistance levels
    support_resistance = compute_support_resistance(featured, lookback=200)

    # Money Flow markers
    money_flow_markers = compute_money_flow_markers(featured)

    # VWAP line and bands
    vwap = [{"time": t, "value": round(v, 2)} for t, v in zip(times, featured["vwap"]) if not pd.isna(v)]
    vwap_upper_1 = [{"time": t, "value": round(v, 2)} for t, v in zip(times, featured["vwap_upper_1"]) if not pd.isna(v)]
    vwap_lower_1 = [{"time": t, "value": round(v, 2)} for t, v in zip(times, featured["vwap_lower_1"]) if not pd.isna(v)]

    # Divergence scanner
    divergences = compute_divergences(featured, lookback=50)

    # RSI Scalping indicators (Stochastic + DMI Stochastic)
    from app.ai.strategies.rsi_scalping import compute_rsi_scalping_indicators
    scalp_df = compute_rsi_scalping_indicators(featured)
    scalp_times = [int(t.timestamp()) for t in scalp_df["timestamp"]] if "timestamp" in scalp_df.columns else times[-len(scalp_df):]

    stoch_k = [{"time": t, "value": round(v, 2)} for t, v in zip(scalp_times, scalp_df["stoch_k"]) if not pd.isna(v)]
    stoch_d = [{"time": t, "value": round(v, 2)} for t, v in zip(scalp_times, scalp_df["stoch_d"]) if not pd.isna(v)]
    dmi_stoch = [{"time": t, "value": round(v, 2)} for t, v in zip(scalp_times, scalp_df["dmi_stoch"]) if not pd.isna(v)]

    # Buy/Sell markers from DMI Stoch crossovers
    scalp_signals = []
    for i, row in scalp_df.iterrows():
        if row.get("cross_up", 0) == 1:
            idx = scalp_df.index.get_loc(i)
            if idx < len(scalp_times):
                scalp_signals.append({"time": scalp_times[idx], "type": "BUY", "price": round(float(row["close"]), 2)})
        if row.get("cross_down", 0) == 1:
            idx = scalp_df.index.get_loc(i)
            if idx < len(scalp_times):
                scalp_signals.append({"time": scalp_times[idx], "type": "SELL", "price": round(float(row["close"]), 2)})

    return {
        "ema_20": ema_20,
        "ema_50": ema_50,
        "ema_200": ema_200,
        "bb_upper": bb_upper,
        "bb_middle": bb_middle,
        "bb_lower": bb_lower,
        "rsi": rsi,
        "macd_line": macd_line,
        "macd_signal": macd_signal,
        "macd_hist": macd_hist,
        "stoch_k": stoch_k,
        "stoch_d": stoch_d,
        "dmi_stoch": dmi_stoch,
        "scalp_signals": scalp_signals,
        "order_blocks": order_blocks,
        "fair_value_gaps": fair_value_gaps,
        "liquidation_levels": liquidation_levels,
        "volume_profile": volume_profile,
        "poc": poc,
        "current_price": last_close,
        "ichimoku_tenkan": ichimoku_tenkan,
        "ichimoku_kijun": ichimoku_kijun,
        "ichimoku_senkou_a": ichimoku_senkou_a,
        "ichimoku_senkou_b": ichimoku_senkou_b,
        "ichimoku_chikou": ichimoku_chikou,
        "fibonacci": fibonacci,
        "support_resistance": support_resistance,
        "money_flow_markers": money_flow_markers,
        "vwap": vwap,
        "vwap_upper_1": vwap_upper_1,
        "vwap_lower_1": vwap_lower_1,
        "divergences": divergences,
        "patterns": chart_patterns,
    }


def _aggregate_orderflow_windows(
    raw_windows: list[dict], target_seconds: int,
) -> list[dict]:
    """Aggregate 1m order-flow windows into larger timeframes (5m, 15m, 1h).

    Groups windows by their target-timeframe bucket, merges clusters,
    and recalculates OHLC and delta.
    """
    if not raw_windows:
        return []

    buckets: dict[int, list[dict]] = {}
    for w in raw_windows:
        bucket_start = (w["time"] // target_seconds) * target_seconds
        buckets.setdefault(bucket_start, []).append(w)

    aggregated: list[dict] = []
    for bucket_start in sorted(buckets):
        group = buckets[bucket_start]
        # Merge clusters across all windows in this bucket
        merged_clusters: dict[float, dict] = {}
        for w in group:
            for c in w.get("clusters", []):
                price = c["price"]
                if price not in merged_clusters:
                    merged_clusters[price] = {
                        "price": price,
                        "bid_vol": 0.0,
                        "ask_vol": 0.0,
                        "delta": 0.0,
                        "trades": 0,
                        "imbalance": None,
                    }
                mc = merged_clusters[price]
                mc["bid_vol"] = round(mc["bid_vol"] + c.get("bid_vol", 0), 6)
                mc["ask_vol"] = round(mc["ask_vol"] + c.get("ask_vol", 0), 6)
                mc["delta"] = round(mc["ask_vol"] - mc["bid_vol"], 6)
                mc["trades"] += c.get("trades", 0)

        # Recalculate imbalances on merged clusters
        for mc in merged_clusters.values():
            if mc["bid_vol"] > 0 and mc["ask_vol"] / mc["bid_vol"] >= 3.0:
                mc["imbalance"] = "BUY"
            elif mc["ask_vol"] > 0 and mc["bid_vol"] / mc["ask_vol"] >= 3.0:
                mc["imbalance"] = "SELL"

        sorted_clusters = sorted(merged_clusters.values(), key=lambda c: c["price"])

        # OHLC from sub-windows
        opens = [w["open"] for w in group if w.get("open")]
        highs = [w["high"] for w in group if w.get("high")]
        lows = [w["low"] for w in group if w.get("low")]
        closes = [w["close"] for w in group if w.get("close")]

        total_vol = round(sum(w.get("total_volume", 0) for w in group), 6)
        total_delta = round(sum(w.get("delta", 0) for w in group), 6)

        aggregated.append({
            "time": bucket_start,
            "open": opens[0] if opens else 0,
            "high": max(highs) if highs else 0,
            "low": min(lows) if lows else 0,
            "close": closes[-1] if closes else 0,
            "total_volume": total_vol,
            "delta": total_delta,
            "clusters": sorted_clusters,
        })

    return aggregated


def _aggregate_delta_history(
    raw_history: list[dict], target_seconds: int,
) -> list[dict]:
    """Aggregate delta history entries into larger timeframe buckets.

    Takes the last entry's cumulative delta value per bucket.
    """
    if not raw_history:
        return []

    buckets: dict[int, dict] = {}
    for entry in raw_history:
        bucket_start = (entry["time"] // target_seconds) * target_seconds
        # Keep the last (most recent) value per bucket
        buckets[bucket_start] = {"time": bucket_start, "value": entry["value"]}

    return [buckets[k] for k in sorted(buckets)]


@router.get("/orderflow")
async def get_orderflow(
    asset: str = Query(default="BTCUSDT", description="Trading pair symbol, e.g. BTCUSDT"),
    timeframe: str = Query(default="1m", description="Aggregation window: 1m or 5m"),
    limit: int = Query(default=30, ge=1, le=200, description="Number of recent windows to return"),
) -> dict:
    """Get order flow data: price clusters, delta, and imbalances.

    Returns aggregated trade data bucketed into price levels within time
    windows, along with cumulative delta and detected imbalances.
    """
    from app.data.fetchers.orderflow_engine import get_orderflow_manager

    manager = get_orderflow_manager()
    engine = manager.get_engine(asset.upper())

    if engine is None:
        raise HTTPException(
            status_code=404,
            detail=f"No order flow engine running for {asset}. Available: {list(manager.list_engines().keys())}",
        )

    # Map timeframe string to seconds for aggregation
    tf_seconds = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600}.get(timeframe, 60)
    engine_window = engine.window_seconds  # base window size (typically 60s)

    # Fetch enough 1m windows to fill the requested limit of larger windows
    multiplier = max(1, tf_seconds // engine_window)
    raw_limit = limit * multiplier + multiplier  # extra to fill the last bucket
    raw_windows = engine.get_recent_windows(limit=raw_limit)

    # Aggregate into larger timeframes if needed
    if multiplier > 1 and raw_windows:
        windows = _aggregate_orderflow_windows(raw_windows, tf_seconds)[-limit:]
    else:
        windows = raw_windows[-limit:]

    imbalances = engine.detect_imbalances(threshold=3.0)

    # Aggregate delta history to match timeframe
    raw_delta = list(engine.session_delta_history)
    if multiplier > 1 and raw_delta:
        delta_history = _aggregate_delta_history(raw_delta, tf_seconds)[-limit:]
    else:
        delta_history = raw_delta[-limit:]

    return {
        "windows": windows,
        "cumulative_delta": engine.get_cumulative_delta(),
        "delta_history": delta_history,
        "imbalances": imbalances,
        "current_price": engine.current_price,
    }


@router.get("/orderflow/status")
async def get_orderflow_status() -> dict:
    """Get status of all running order flow engines."""
    from app.data.fetchers.orderflow_engine import get_orderflow_manager

    manager = get_orderflow_manager()
    engines = manager.list_engines()
    details = {}
    for symbol, running in engines.items():
        engine = manager.get_engine(symbol)
        if engine:
            details[symbol] = {
                "running": running,
                "cumulative_delta": engine.get_cumulative_delta(),
                "current_price": engine.current_price,
                "trade_count": engine._trade_count,
                "window_count": len(engine._finalized_windows),
            }
    return {"engines": details}


@router.get("/liquidation-heatmap")
async def get_liquidation_heatmap(
    asset: str = Query(default="BTCUSDT", description="Trading pair symbol, e.g. BTCUSDT"),
    range_pct: float = Query(default=5.0, ge=0.1, le=50.0, description="Percentage above/below current price"),
) -> dict:
    """Return liquidation heatmap data with intensity values.

    Returns bins with decayed liquidation intensity, recent force order
    liquidations, open interest, theoretical liquidation levels, and
    summary statistics.
    """
    from app.data.fetchers.liquidation_engine import get_liquidation_manager

    manager = get_liquidation_manager()
    engine = manager.engine

    if engine is None:
        raise HTTPException(
            status_code=503,
            detail="Liquidation engine not running. Data may be unavailable.",
        )

    return engine.get_heatmap_data(symbol=asset.upper(), price_range_pct=range_pct)


@router.get("/liquidations/recent")
async def get_recent_liquidations(
    asset: str = Query(default="BTCUSDT", description="Trading pair symbol, e.g. BTCUSDT"),
    limit: int = Query(default=50, ge=1, le=500, description="Number of recent liquidations to return"),
) -> list:
    """Return recent force order liquidations."""
    from app.data.fetchers.liquidation_engine import get_liquidation_manager

    manager = get_liquidation_manager()
    engine = manager.engine

    if engine is None:
        raise HTTPException(
            status_code=503,
            detail="Liquidation engine not running.",
        )

    return engine.get_recent_liquidations(symbol=asset.upper(), limit=limit)


@router.get("/orderbook")
async def get_orderbook(
    symbol: str = Query(default="BTCUSDT", description="Trading pair symbol, e.g. BTCUSDT"),
    limit: int = Query(default=100, ge=5, le=1000, description="Number of price levels per side"),
) -> dict:
    """Get order book depth snapshot from Binance.

    Returns bids, asks (each as [price, qty] lists), spread, and timestamp.
    """
    from app.data.fetchers.orderbook_fetcher import OrderBookFetcher

    fetcher = OrderBookFetcher()
    try:
        data = await fetcher.fetch_orderbook(symbol=symbol.upper(), limit=limit)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to fetch order book: {exc}",
        ) from exc
    finally:
        await fetcher.close()

    bids = data.get("bids", [])
    asks = data.get("asks", [])

    # Compute spread from best bid/ask
    spread = 0.0
    best_bid = float(bids[0][0]) if bids else 0.0
    best_ask = float(asks[0][0]) if asks else 0.0
    if best_bid > 0 and best_ask > 0:
        spread = best_ask - best_bid

    return {
        "bids": bids,
        "asks": asks,
        "spread": round(spread, 8),
        "best_bid": best_bid,
        "best_ask": best_ask,
        "timestamp": data.get("timestamp", 0),
        "symbol": data.get("symbol", symbol.upper()),
    }


@router.get("/forex/status")
async def get_forex_status() -> dict:
    """Get forex provider status — prices, tick counts, deltas."""
    from app.data.fetchers.forex_provider import get_forex_provider
    return get_forex_provider().get_status()


@router.get("/forex/klines")
async def get_forex_klines(
    asset: str = Query(default="EUR/USD"),
    interval: str = Query(default="1m"),
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[dict]:
    """Get aggregated forex candles from tick data."""
    from app.data.fetchers.forex_provider import get_forex_provider
    return get_forex_provider().get_candles(asset, interval, limit)


@router.get("/forex/ticks")
async def get_forex_ticks(
    asset: str = Query(default="EUR/USD"),
    limit: int = Query(default=500, ge=1, le=10000),
) -> dict:
    """Get raw forex ticks with tick delta."""
    from app.data.fetchers.forex_provider import get_forex_provider
    provider = get_forex_provider()
    return {
        "symbol": asset,
        "ticks": provider.get_ticks(asset, limit),
        "current_price": provider.get_current_price(asset),
        "cumulative_delta": provider.get_cumulative_delta(asset),
    }


@router.get("/funding-rates")
async def get_funding_rates(
    symbols: str | None = Query(
        default=None,
        description="Comma-separated trading pair symbols (e.g. BTCUSDT,ETHUSDT). Defaults to BTC, ETH, SOL.",
    ),
) -> list[dict]:
    """Get current funding rates from Binance Futures.

    Returns symbol, funding_rate, next_funding_time, and mark_price
    for each requested symbol.
    """
    from app.data.fetchers.funding_rate_fetcher import FundingRateFetcher

    symbol_list: list[str] | None = None
    if symbols:
        symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]

    fetcher = FundingRateFetcher()
    try:
        return await fetcher.fetch_funding_rates(symbol_list)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to fetch funding rates: {exc}",
        ) from exc


@router.get("/correlations")
async def get_correlations(
    symbols: str = Query(
        default="BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT",
        description="Comma-separated list of Binance trading pair symbols",
    ),
    timeframe: str = Query(default="4h", description="Kline interval (e.g. 1h, 4h, 1d)"),
    lookback_days: int = Query(default=30, ge=1, le=365, description="Number of days of historical data"),
) -> dict:
    """Compute Pearson correlation matrix of close-price returns for the given symbols.

    Useful for portfolio diversification analysis and detecting correlated moves.
    """
    from app.data.processors.correlation import compute_correlation_matrix

    symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if len(symbol_list) < 2:
        raise HTTPException(
            status_code=400,
            detail="At least 2 symbols are required to compute correlations.",
        )

    return await compute_correlation_matrix(
        symbols=symbol_list,
        timeframe=timeframe,
        lookback_days=lookback_days,
    )


@router.get("/fear-greed")
async def get_fear_greed() -> dict:
    """Get Fear & Greed Index (cached 1h from alternative.me)."""
    from app.data.fetchers.fear_greed_fetcher import get_fear_greed_index
    return await get_fear_greed_index()


@router.get("/calendar")
async def get_macro_calendar(
    hours_ahead: int = Query(default=24, ge=1, le=168, description="Hours ahead to look for events"),
    impact: str | None = Query(default=None, description="Filter by impact level: HIGH, MEDIUM, LOW"),
    currency: str | None = Query(default=None, description="Filter by currency, e.g. USD, EUR, GBP"),
) -> dict:
    """Get upcoming macro economic events from the economic calendar.

    Returns scheduled economic releases (NFP, CPI, rate decisions, etc.)
    with their impact level, forecast, and previous values.
    """
    from app.data.fetchers.macro_calendar import get_macro_calendar_fetcher

    fetcher = get_macro_calendar_fetcher()

    try:
        result = await fetcher.fetch_upcoming_events(hours_ahead=hours_ahead)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to fetch economic calendar: {exc}",
        ) from exc

    events = result.events

    # Apply optional filters
    if impact:
        impact_upper = impact.upper()
        events = [e for e in events if e.impact.value == impact_upper]

    if currency:
        currency_upper = currency.upper()
        events = [e for e in events if e.currency.upper() == currency_upper]

    return {
        "events": [e.model_dump() for e in events],
        "fetched_at": result.fetched_at,
        "source": result.source,
        "hours_ahead": result.hours_ahead,
        "total": len(events),
    }


@router.get("/btc-dominance")
async def get_btc_dominance_endpoint() -> dict:
    """Get BTC market dominance and global crypto stats (cached 5min from CoinGecko)."""
    from app.data.fetchers.coingecko_fetcher import get_btc_dominance
    return await get_btc_dominance()


@router.get("/breadth")
async def get_market_breadth_endpoint() -> dict:
    """Get % of Binance futures pairs above 20/50/200 EMA (cached 5min)."""
    from app.ai.signals.market_breadth import get_market_breadth
    return await get_market_breadth()


@router.get("/momentum-rank")
async def get_momentum_rank(top_n: int = Query(default=20, ge=5, le=50)) -> dict:
    """Get symbols ranked by multi-timeframe momentum score (cached 15min).

    Scores each symbol across 1h (30%), 4h (40%), and 1d (30%) timeframes
    using EMA20 position, ROC-5, ROC-20, and RSI. Returns top_n results
    sorted by absolute score strength.
    """
    from app.ai.signals.momentum_scorer import get_momentum_rankings

    rankings = await get_momentum_rankings(top_n=top_n)
    return {"rankings": rankings, "count": len(rankings)}


@router.get("/long-short-ratio/{symbol}")
async def get_long_short_ratio_endpoint(
    symbol: str,
    period: str = Query(default="1h", description="Timeframe: 5m, 15m, 30m, 1h, 4h, 1d"),
    limit: int = Query(default=10, ge=1, le=100),
) -> dict:
    """Get global long/short account ratio for a futures symbol from Binance."""
    from app.data.fetchers.binance_fetcher import get_long_short_ratio
    data = await get_long_short_ratio(symbol.upper(), period=period, limit=limit)
    # Flag extreme positioning
    extreme_long = False
    extreme_short = False
    if data:
        latest = data[-1]
        long_pct = latest["long_account"] * 100
        extreme_long = long_pct > 75
        extreme_short = long_pct < 25
    return {
        "symbol": symbol.upper(),
        "data": data,
        "extreme_long": extreme_long,
        "extreme_short": extreme_short,
    }


@router.get("/taker-ratio/{symbol}")
async def get_taker_ratio_endpoint(
    symbol: str,
    period: str = Query(default="1h", description="Timeframe: 5m, 15m, 30m, 1h, 4h, 1d"),
    limit: int = Query(default=10, ge=1, le=100),
) -> dict:
    """Get taker buy/sell volume ratio for a futures symbol from Binance."""
    from app.data.fetchers.binance_fetcher import get_taker_buysell_ratio
    data = await get_taker_buysell_ratio(symbol.upper(), period=period, limit=limit)
    # Current ratio
    current_ratio = data[-1]["buy_sell_ratio"] if data else 1.0
    return {
        "symbol": symbol.upper(),
        "data": data,
        "current_ratio": round(current_ratio, 3),
        "buyers_dominant": current_ratio > 1.1,
        "sellers_dominant": current_ratio < 0.9,
    }


@router.get("/regime-changes")
async def get_regime_changes(limit: int = Query(default=10, ge=1, le=50)) -> dict:
    """Get recent regime change events detected by the alerter."""
    from app.ai.regime.regime_change_alerter import get_regime_change_alerter
    alerter = get_regime_change_alerter()
    return {
        "changes": alerter.get_recent_changes(limit=limit),
        "current_regimes": alerter.get_current_regimes(),
    }


@router.get("/cvd")
async def get_cvd(
    asset: str = Query(..., description="Asset symbol e.g. BTCUSDT"),
    interval: str = Query(default="1h"),
    limit: int = Query(default=100, ge=20, le=500),
) -> dict:
    """Get Cumulative Volume Delta for an asset (approximated from OHLCV)."""
    from app.ai.signals.cvd_calculator import calculate_cvd_from_ohlcv, detect_cvd_divergence

    binance_url = "https://api.binance.com/api/v3/klines"
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(binance_url, params={"symbol": asset.upper(), "interval": interval, "limit": limit})
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=exc.response.status_code,
                detail=f"Binance API error: {exc.response.text}",
            ) from exc
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"Failed to reach Binance API: {exc}") from exc

    raw_klines: list[list] = resp.json()
    if not raw_klines:
        raise HTTPException(status_code=404, detail=f"No data found for {asset}")

    candles = [
        {
            "time": int(k[0]) // 1000,
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5]),
        }
        for k in raw_klines
    ]

    cvd_series = calculate_cvd_from_ohlcv(candles)
    divergences = detect_cvd_divergence(candles, cvd_series)

    return {
        "asset": asset.upper(),
        "interval": interval,
        "cvd": cvd_series,
        "divergences": divergences,
        "current_cvd": cvd_series[-1]["cvd"] if cvd_series else 0,
    }


@router.get("/open-interest/{symbol}")
async def get_open_interest_endpoint(
    symbol: str,
    period: str = Query(default="1h"),
    limit: int = Query(default=50, ge=10, le=200),
) -> dict:
    """Get open interest history for a futures symbol."""
    from app.data.fetchers.binance_fetcher import get_open_interest_history
    data = await get_open_interest_history(symbol.upper(), period=period, limit=limit)
    return {"symbol": symbol.upper(), "data": data, "count": len(data)}


@router.get("/sector-momentum")
async def get_sector_momentum_endpoint() -> dict:
    """Get momentum scores for each crypto sector (cached 10 min).

    Returns sectors ranked by weighted 1d/7d momentum score, including
    average changes and top 3 performing symbols per sector.
    """
    from app.ai.signals.sector_rotation import get_sector_momentum

    sectors = await get_sector_momentum()
    return {
        "sectors": [
            {
                "sector": s.sector,
                "momentum_score": s.momentum_score,
                "avg_1d_change": s.avg_1d_change,
                "avg_7d_change": s.avg_7d_change,
                "top_performers": s.top_performers,
                "symbol_count": s.symbol_count,
            }
            for s in sectors
        ]
    }


@router.get("/macro")
async def get_macro() -> dict:
    """Get macro overlay data: DXY, US10Y, SPX, BTC/DXY correlation (cached 1h).

    Data is fetched from Yahoo Finance via yfinance. Returns None for any
    indicator that is unavailable or could not be fetched.
    """
    from app.data.fetchers.macro_fetcher import get_macro_data

    data = await get_macro_data()
    return {
        "dxy_price": data.dxy_price,
        "dxy_change_pct": data.dxy_change_pct,
        "us10y_yield": data.us10y_yield,
        "us10y_change_pct": data.us10y_change_pct,
        "spx_price": data.spx_price,
        "spx_change_pct": data.spx_change_pct,
        "btc_correlation_dxy": data.btc_correlation_dxy,
        "last_updated": data.last_updated,
    }


@router.get("/news-velocity")
async def get_news_velocity_endpoint() -> dict:
    """Get news velocity — article count per crypto symbol from CryptoPanic RSS.

    Returns per-symbol mention counts (last ~50 articles), total article count,
    and the 10 most recent relevant article titles. Results are cached 5min.
    """
    from app.data.fetchers.news_fetcher import get_news_velocity
    return await get_news_velocity()


@router.get("/stablecoin-ratio")
async def get_stablecoin_ratio() -> dict:
    """Get Stablecoin Supply Ratio (SSR) — (USDT + USDC mcap) / total crypto mcap.

    High SSR (> 0.15) signals bullish dry powder; low SSR (< 0.06) signals
    most capital already deployed. Results are cached 15min.
    """
    from app.data.fetchers.coingecko_fetcher import get_stablecoin_supply_ratio
    return await get_stablecoin_supply_ratio()


@router.get("/elliott-wave/{symbol}")
async def get_elliott_wave(symbol: str, tf: str = "4h") -> dict:
    """Return the current Elliott Wave count and projected target for a symbol.

    Args:
        symbol: Trading pair (e.g. BTCUSDT).
        tf: Timeframe string accepted by Binance (e.g. 1h, 4h, 1d).
    """
    from app.ai.signals.elliott_wave import count_elliott_waves
    from app.data.fetchers.binance_fetcher import get_binance_fetcher

    fetcher = get_binance_fetcher()
    candles = await fetcher.get_klines(symbol.upper(), tf, limit=200)
    if not candles:
        return {"error": "No data"}

    closes = [float(c[4]) for c in candles]
    wave = count_elliott_waves(closes, closes[-1])

    if not wave:
        return {"symbol": symbol, "wave_context": None}

    return {
        "symbol": symbol,
        "timeframe": tf,
        "wave_context": {
            "current_wave": wave.current_wave,
            "wave_type": wave.wave_type,
            "wave_label": wave.wave_label,
            "projected_target": wave.projected_target,
            "confidence": wave.confidence,
            "pivot_count": len(wave.pivots),
        },
    }


@router.get("/harmonic-patterns/{symbol}")
async def get_harmonic_patterns_endpoint(symbol: str, tf: str = "4h") -> dict:
    """Detect Gartley, Bat, Crab, and Butterfly harmonic patterns for a symbol.

    Args:
        symbol: Trading pair (e.g. BTCUSDT).
        tf: Timeframe string accepted by Binance (e.g. 1h, 4h, 1d).
    """
    from app.ai.signals.harmonic_patterns import get_harmonic_patterns
    from app.data.fetchers.binance_fetcher import get_binance_fetcher

    fetcher = get_binance_fetcher()
    candles = await fetcher.get_klines(symbol.upper(), tf, limit=200)
    if not candles:
        return {"patterns": []}

    closes = [float(c[4]) for c in candles]
    patterns = get_harmonic_patterns(closes)

    return {
        "symbol": symbol,
        "timeframe": tf,
        "patterns": [
            {
                "pattern_name": p.pattern_name,
                "bias": p.bias,
                "completion_zone_min": p.completion_zone[0],
                "completion_zone_max": p.completion_zone[1],
                "confidence": p.confidence,
                "current_leg": p.current_leg,
            }
            for p in patterns[:5]  # Top 5 by confidence
        ],
    }


@router.get("/mean-reversion/{symbol}")
async def get_mean_reversion(
    symbol: str,
    tf: str = Query(default="1h", description="Kline interval, e.g. 1h, 4h, 1d"),
    limit: int = Query(default=100, ge=20, le=500, description="Number of candles for OU fit"),
) -> dict:
    """Fit Ornstein-Uhlenbeck process and return mean reversion probability.

    Estimates the probability that the current price will revert toward its
    historical mean within the next N periods, based on the fitted OU speed
    (theta), long-run mean (mu), and deviation from mean.
    """
    from app.ai.signals.ou_process import fit_ou_process, mean_reversion_probability

    binance_url = "https://api.binance.com/api/v3/klines"
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(
                binance_url,
                params={"symbol": symbol.upper(), "interval": tf, "limit": limit},
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=exc.response.status_code,
                detail=f"Binance API error: {exc.response.text}",
            ) from exc
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Failed to reach Binance API: {exc}",
            ) from exc

    raw_klines: list[list] = resp.json()
    if not raw_klines:
        raise HTTPException(status_code=404, detail=f"No data found for {symbol}")

    closes = [float(k[4]) for k in raw_klines]
    ou_params = fit_ou_process(closes)
    current_price = closes[-1]
    prob_data = mean_reversion_probability(current_price, ou_params)

    return {
        "symbol": symbol.upper(),
        "timeframe": tf,
        "current_price": round(current_price, 6),
        "ou_params": ou_params,
        **prob_data,
    }


@router.get("/volatility/{symbol}")
async def get_volatility_forecast(
    symbol: str,
    tf: str = Query(default="1d", description="Kline interval, e.g. 1h, 4h, 1d"),
    limit: int = Query(default=60, ge=25, le=500, description="Number of candles"),
) -> dict:
    """EWMA volatility forecast and regime classification.

    Uses RiskMetrics EWMA (lambda=0.94) to compute realized annualized
    volatility and classify the current vol regime. Returns a signal:
    'risk_off' for high/extreme vol, 'breakout_setup' for compressed vol,
    'neutral' otherwise.
    """
    from app.ai.signals.volatility_forecaster import forecast_volatility

    binance_url = "https://api.binance.com/api/v3/klines"
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(
                binance_url,
                params={"symbol": symbol.upper(), "interval": tf, "limit": limit},
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=exc.response.status_code,
                detail=f"Binance API error: {exc.response.text}",
            ) from exc
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Failed to reach Binance API: {exc}",
            ) from exc

    raw_klines: list[list] = resp.json()
    if not raw_klines:
        raise HTTPException(status_code=404, detail=f"No data found for {symbol}")

    closes = [float(k[4]) for k in raw_klines]
    forecast = forecast_volatility(closes)
    if not forecast:
        raise HTTPException(status_code=422, detail="Insufficient data for volatility forecast")

    return {
        "symbol": symbol.upper(),
        "timeframe": tf,
        "current_vol_pct": forecast.current_vol_pct,
        "forecast_vol_pct": forecast.forecast_vol_pct,
        "vol_regime": forecast.vol_regime,
        "expanding": forecast.expanding,
        "signal": forecast.signal,
    }


@router.get("/anomalies/{symbol}")
async def get_anomalies(
    symbol: str,
    tf: str = Query(default="1h", description="Kline interval, e.g. 1h, 4h, 1d"),
    limit: int = Query(default=60, ge=15, le=500, description="Number of candles to analyze"),
    z_threshold: float = Query(default=2.5, ge=1.0, le=5.0, description="Z-score threshold for anomaly detection"),
) -> dict:
    """Detect anomalous candles using z-score analysis.

    Flags candles where volume, body size, or wick ratio is statistically
    unusual (above z_threshold sigma) relative to the recent window.
    Useful for identifying potential manipulation, momentum bursts, or
    key reversal candles.
    """
    from app.ai.signals.anomaly_detector import detect_anomalies

    binance_url = "https://api.binance.com/api/v3/klines"
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(
                binance_url,
                params={"symbol": symbol.upper(), "interval": tf, "limit": limit},
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=exc.response.status_code,
                detail=f"Binance API error: {exc.response.text}",
            ) from exc
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Failed to reach Binance API: {exc}",
            ) from exc

    raw_klines: list[list] = resp.json()
    if not raw_klines:
        return {"symbol": symbol.upper(), "timeframe": tf, "anomalies": [], "count": 0}

    # Convert raw Binance klines to dict format expected by detect_anomalies
    candles = [
        {
            "time": int(k[0]) // 1000,
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5]),
        }
        for k in raw_klines
    ]

    anomalies = detect_anomalies(candles, z_threshold=z_threshold)

    return {
        "symbol": symbol.upper(),
        "timeframe": tf,
        "anomalies": anomalies,
        "count": len(anomalies),
    }


@router.get("/portfolio-optimize")
async def optimize_portfolio_endpoint(
    symbols: str = "BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT",
    optimization: str = "max_sharpe",
    lookback_days: int = 90,
) -> dict:
    """MPT portfolio optimization for given symbols.

    Fetches daily OHLCV data from Binance, computes daily returns, then runs
    Modern Portfolio Theory optimization (max Sharpe, min variance, or equal weight).

    Args:
        symbols: comma-separated list of Binance symbols (max 10)
        optimization: one of "max_sharpe" | "min_variance" | "equal_weight"
        lookback_days: number of trading days of history to use (default 90)
    """
    import asyncio
    from app.data.fetchers.binance_fetcher import get_binance_fetcher
    from app.ai.portfolio.mpt_optimizer import optimize_portfolio

    sym_list = [s.strip().upper() for s in symbols.split(",")][:10]  # Max 10 symbols
    fetcher = get_binance_fetcher()

    # Fetch daily candles for all symbols concurrently
    candles_list = await asyncio.gather(
        *[fetcher.get_klines(sym, "1d", limit=lookback_days + 1) for sym in sym_list],
        return_exceptions=True,
    )

    # Build returns matrix — align all series to the shortest common length
    min_len: int | None = None
    returns_data: list[list[float]] = []
    valid_symbols: list[str] = []

    for sym, candles in zip(sym_list, candles_list):
        if isinstance(candles, Exception) or not candles or len(candles) < 10:
            continue
        closes = [float(c[4]) for c in candles]
        returns = [(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(1, len(closes))]
        returns_data.append(returns)
        valid_symbols.append(sym)
        if min_len is None or len(returns) < min_len:
            min_len = len(returns)

    if len(valid_symbols) < 2:
        return {"error": "Need at least 2 valid symbols"}

    # Align all return series to the same length
    matrix = [[r[i] for r in returns_data] for i in range(min_len)]

    result = optimize_portfolio(valid_symbols, matrix, optimization_type=optimization)
    if not result:
        return {"error": "Optimization failed"}

    return {
        "symbols": valid_symbols,
        "weights": result.weights,
        "expected_return_pct": result.expected_return,
        "volatility_pct": result.volatility,
        "sharpe_ratio": result.sharpe_ratio,
        "optimization_type": result.optimization_type,
    }


# ---------------------------------------------------------------------------
# Alert Rules — Feature 70: Conditional Alert Chains
# ---------------------------------------------------------------------------


@router.get("/alert-rules")
async def get_alert_rules_endpoint() -> dict:
    """Return all registered conditional alert rules."""
    from app.notifications.alert_rules import get_alert_rules

    rules = get_alert_rules()
    return {
        "rules": [
            {
                "id": r.id,
                "name": r.name,
                "symbol": r.symbol,
                "active": r.active,
                "message": r.message,
                "cooldown_seconds": r.cooldown_seconds,
                "conditions": [
                    {"field": c.field, "operator": c.operator, "value": c.value}
                    for c in r.conditions
                ],
            }
            for r in rules
        ]
    }


@router.post("/alert-rules")
async def create_alert_rule_endpoint(body: dict) -> dict:
    """Create or replace a conditional alert rule.

    Request body fields:
    - name (str, required)
    - conditions (list[{field, operator, value}], required)
    - symbol (str, optional) — restrict to a single symbol
    - message (str, optional)
    - cooldown_seconds (int, optional, default 3600)
    - id (str, optional) — auto-generated UUID if omitted
    """
    import uuid

    from app.notifications.alert_rules import AlertCondition, AlertRule, add_alert_rule

    raw_conditions = body.get("conditions", [])
    conditions = [AlertCondition(**c) for c in raw_conditions]

    rule = AlertRule(
        id=body.get("id", str(uuid.uuid4())),
        name=body["name"],
        symbol=body.get("symbol"),
        conditions=conditions,
        message=body.get("message", ""),
        cooldown_seconds=int(body.get("cooldown_seconds", 3600)),
    )
    add_alert_rule(rule)
    return {"status": "ok", "id": rule.id}


@router.delete("/alert-rules/{rule_id}")
async def delete_alert_rule_endpoint(rule_id: str) -> dict:
    """Remove an alert rule by ID."""
    from app.notifications.alert_rules import remove_alert_rule

    remove_alert_rule(rule_id)
    return {"status": "ok"}
