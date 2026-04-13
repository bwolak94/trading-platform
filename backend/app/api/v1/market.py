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
        "order_blocks": order_blocks,
        "fair_value_gaps": fair_value_gaps,
        "liquidation_levels": liquidation_levels,
        "volume_profile": volume_profile,
        "poc": poc,
        "current_price": last_close,
    }


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

    windows = engine.get_recent_windows(limit=limit)
    imbalances = engine.detect_imbalances(threshold=3.0)
    delta_history = list(engine.session_delta_history)[-limit:]

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


@router.get("/calendar")
async def get_macro_calendar() -> dict:
    """Get upcoming macro economic events.

    Placeholder — requires external calendar API integration.
    """
    return {"data": []}
