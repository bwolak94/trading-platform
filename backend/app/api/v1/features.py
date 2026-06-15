"""Features API — endpoints for all new trading analysis features."""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/features", tags=["features"])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BINANCE_BASE_URL = "https://fapi.binance.com"


def _ok(data: Any, source: str = "computed") -> dict[str, Any]:
    """Standard success response envelope."""
    return {
        "status": "ok",
        "source": source,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": data,
    }


def _unavailable(reason: str) -> dict[str, Any]:
    """Standard 503-style response when a data source is unavailable."""
    return {
        "status": "unavailable",
        "reason": reason,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": None,
    }


async def _fetch_ohlcv(symbol: str, timeframe: str, limit: int = 200) -> list[dict]:
    """Fetch OHLCV from Binance futures REST (no auth required for public data)."""
    import httpx

    interval_map = {
        "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
        "1h": "1h", "4h": "4h", "1d": "1d",
    }
    interval = interval_map.get(timeframe, "1h")
    url = f"{_BINANCE_BASE_URL}/fapi/v1/klines"
    params = {"symbol": symbol.replace("/", "").upper(), "interval": interval, "limit": limit}

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        raw = resp.json()

    return [
        {
            "open_time": c[0],
            "open": float(c[1]),
            "high": float(c[2]),
            "low": float(c[3]),
            "close": float(c[4]),
            "volume": float(c[5]),
        }
        for c in raw
    ]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/wyckoff/{symbol}")
async def get_wyckoff_phase(
    symbol: str,
    timeframe: str = Query("4h"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Detect current Wyckoff phase for a symbol.

    Wyckoff phases: ACCUMULATION (Phase A-E), MARKUP, DISTRIBUTION, MARKDOWN.
    Uses volume and price structure analysis to classify the phase.
    """
    try:
        from app.ai.market.wyckoff import WyckoffAnalyzer
        candles = await _fetch_ohlcv(symbol, timeframe, 200)
        analyzer = WyckoffAnalyzer()
        result = analyzer.analyze(candles)
        return _ok(result, source="wyckoff_analyzer")
    except ImportError:
        pass
    except Exception as exc:
        logger.error("Wyckoff analysis failed for %s: %s", symbol, exc)

    # Graceful fallback: rule-based stub
    try:
        import pandas as pd
        candles = await _fetch_ohlcv(symbol, timeframe, 100)
        if not candles:
            raise ValueError("No candle data")

        df = pd.DataFrame(candles)
        close = df["close"].astype(float)
        volume = df["volume"].astype(float)

        # Simple heuristic: rising price + rising volume = MARKUP
        price_change = (close.iloc[-1] - close.iloc[-20]) / close.iloc[-20] * 100
        volume_trend = volume.iloc[-10:].mean() / volume.iloc[-30:-10].mean()

        if price_change > 5 and volume_trend > 1.1:
            phase = "MARKUP"
        elif price_change < -5 and volume_trend > 1.1:
            phase = "MARKDOWN"
        elif abs(price_change) < 3 and volume_trend < 0.9:
            phase = "ACCUMULATION"
        elif abs(price_change) < 3 and volume_trend > 1.0:
            phase = "DISTRIBUTION"
        else:
            phase = "UNKNOWN"

        return _ok({
            "phase": phase,
            "price_change_20bar_pct": round(price_change, 2),
            "volume_trend_ratio": round(float(volume_trend), 3),
            "confidence": "LOW",
            "note": "Heuristic fallback — WyckoffAnalyzer module not found",
        }, source="heuristic")
    except Exception as exc:
        logger.error("Wyckoff fallback failed for %s: %s", symbol, exc)
        raise HTTPException(status_code=503, detail=f"Wyckoff analysis unavailable: {exc}")


@router.get("/supply-demand/{symbol}")
async def get_supply_demand_zones(
    symbol: str,
    timeframe: str = Query("4h"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get supply and demand zones based on price imbalance and order block detection."""
    try:
        from app.ai.market.supply_demand import SupplyDemandAnalyzer
        candles = await _fetch_ohlcv(symbol, timeframe, 200)
        analyzer = SupplyDemandAnalyzer()
        zones = analyzer.find_zones(candles)
        return _ok({"zones": zones}, source="supply_demand_analyzer")
    except ImportError:
        pass
    except Exception as exc:
        logger.error("Supply/demand analysis failed for %s: %s", symbol, exc)

    # Fallback: identify consolidation zones by ATR contraction
    try:
        import pandas as pd
        candles = await _fetch_ohlcv(symbol, timeframe, 100)
        df = pd.DataFrame(candles)
        close = df["close"].astype(float)
        high = df["high"].astype(float)
        low = df["low"].astype(float)

        # ATR-based zone detection
        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]

        current_price = float(close.iloc[-1])
        zones = []

        # Demand zone: recent significant low with volume spike
        recent_lows = df.nsmallest(3, "low")
        for _, row in recent_lows.iterrows():
            zones.append({
                "type": "DEMAND",
                "low": round(float(row["low"]) - atr * 0.2, 6),
                "high": round(float(row["low"]) + atr * 0.8, 6),
                "strength": "MODERATE",
                "distance_pct": round((current_price - float(row["low"])) / current_price * 100, 2),
            })

        # Supply zone: recent significant high
        recent_highs = df.nlargest(3, "high")
        for _, row in recent_highs.iterrows():
            zones.append({
                "type": "SUPPLY",
                "low": round(float(row["high"]) - atr * 0.8, 6),
                "high": round(float(row["high"]) + atr * 0.2, 6),
                "strength": "MODERATE",
                "distance_pct": round((float(row["high"]) - current_price) / current_price * 100, 2),
            })

        return _ok({
            "zones": zones,
            "current_price": current_price,
            "atr": round(float(atr), 6),
            "note": "Heuristic fallback",
        }, source="heuristic")
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Supply/demand analysis unavailable: {exc}")


@router.get("/fib-confluence/{symbol}")
async def get_fib_confluence(
    symbol: str,
    timeframe: str = Query("4h"),
) -> dict[str, Any]:
    """Get Fibonacci confluence zones from multiple swing points."""
    try:
        import pandas as pd
        candles = await _fetch_ohlcv(symbol, timeframe, 200)
        df = pd.DataFrame(candles)
        close = df["close"].astype(float)
        high = df["high"].astype(float)
        low = df["low"].astype(float)

        current_price = float(close.iloc[-1])

        # Find swing high and swing low over last 100 bars
        swing_high = float(high.iloc[-100:].max())
        swing_low = float(low.iloc[-100:].min())
        range_size = swing_high - swing_low

        if range_size <= 0:
            raise ValueError("Zero range")

        fib_levels_pct = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0, 1.272, 1.618]
        fib_labels = ["0% (Low)", "23.6%", "38.2%", "50%", "61.8%", "78.6%", "100% (High)", "127.2%", "161.8%"]

        # Retracement levels (from swing low up to swing high)
        retracement = []
        for pct, label in zip(fib_levels_pct, fib_labels):
            price = swing_low + range_size * pct
            distance_pct = abs(current_price - price) / current_price * 100
            retracement.append({
                "level": label,
                "price": round(price, 6),
                "distance_pct": round(distance_pct, 3),
                "is_nearby": distance_pct <= 1.0,
            })

        # Extension levels (from swing high beyond)
        extension_pcts = [1.272, 1.618, 2.0, 2.618]
        extensions = []
        for pct in extension_pcts:
            price = swing_low + range_size * pct
            extensions.append({
                "level": f"{pct*100:.1f}%",
                "price": round(price, 6),
            })

        nearby_zones = [r for r in retracement if r["is_nearby"]]

        return _ok({
            "symbol": symbol,
            "timeframe": timeframe,
            "current_price": current_price,
            "swing_high": round(swing_high, 6),
            "swing_low": round(swing_low, 6),
            "range_pct": round(range_size / swing_low * 100, 2),
            "retracement_levels": retracement,
            "extension_levels": extensions,
            "nearby_confluence_zones": nearby_zones,
            "confluence_count": len(nearby_zones),
        })
    except Exception as exc:
        logger.error("Fibonacci analysis failed for %s: %s", symbol, exc)
        raise HTTPException(status_code=503, detail=f"Fibonacci analysis unavailable: {exc}")


@router.get("/anchored-vwap/{symbol}")
async def get_anchored_vwap(
    symbol: str,
    timeframe: str = Query("1h"),
    anchor_type: str = Query("swing_low", description="swing_low | swing_high | custom"),
    anchor_idx: int = Query(0, description="Bar index from end (0=most recent)"),
) -> dict[str, Any]:
    """Calculate anchored VWAP from a key price level.

    anchor_type:
    - swing_low: Anchors from the most recent significant swing low
    - swing_high: Anchors from the most recent significant swing high
    - custom: Uses anchor_idx bars from the end of data
    """
    try:
        import pandas as pd
        candles = await _fetch_ohlcv(symbol, timeframe, 300)
        df = pd.DataFrame(candles)
        close = df["close"].astype(float)
        high = df["high"].astype(float)
        low = df["low"].astype(float)
        df["volume"].astype(float)

        # Determine anchor point
        if anchor_type == "swing_low":
            # Find significant swing low in recent 100 bars
            recent = low.iloc[-100:]
            anchor_idx_computed = int(recent.idxmin())
        elif anchor_type == "swing_high":
            recent = high.iloc[-100:]
            anchor_idx_computed = int(recent.idxmax())
        else:
            # Custom: anchor_idx bars from end
            anchor_idx_computed = max(0, len(df) - 1 - anchor_idx)

        # Calculate anchored VWAP from anchor point to now
        segment = df.iloc[anchor_idx_computed:].copy()
        typical_price = (segment["high"].astype(float) + segment["low"].astype(float) + segment["close"].astype(float)) / 3
        seg_volume = segment["volume"].astype(float)
        cumulative_tpv = (typical_price * seg_volume).cumsum()
        cumulative_volume = seg_volume.cumsum()
        avwap = cumulative_tpv / cumulative_volume.replace(0, float("nan"))

        current_avwap = float(avwap.iloc[-1])
        current_price = float(close.iloc[-1])
        anchor_price = float(typical_price.iloc[0])
        pct_from_avwap = (current_price - current_avwap) / current_avwap * 100

        bias = "BULLISH" if current_price > current_avwap else "BEARISH"

        # Standard deviation bands
        variance = ((typical_price - avwap) ** 2 * seg_volume).cumsum() / cumulative_volume
        std_dev = variance.apply(lambda x: x ** 0.5 if x >= 0 else 0.0).iloc[-1]

        return _ok({
            "symbol": symbol,
            "timeframe": timeframe,
            "anchor_type": anchor_type,
            "anchor_price": round(anchor_price, 6),
            "anchor_bar_index": anchor_idx_computed,
            "bars_since_anchor": len(segment),
            "avwap": round(current_avwap, 6),
            "avwap_upper_1std": round(current_avwap + float(std_dev), 6),
            "avwap_lower_1std": round(current_avwap - float(std_dev), 6),
            "avwap_upper_2std": round(current_avwap + 2 * float(std_dev), 6),
            "avwap_lower_2std": round(current_avwap - 2 * float(std_dev), 6),
            "current_price": round(current_price, 6),
            "pct_from_avwap": round(pct_from_avwap, 3),
            "bias": bias,
        })
    except Exception as exc:
        logger.error("Anchored VWAP failed for %s: %s", symbol, exc)
        raise HTTPException(status_code=503, detail=f"Anchored VWAP unavailable: {exc}")


@router.get("/options-flow/{symbol}")
async def get_options_flow(symbol: str) -> dict[str, Any]:
    """Get options market analysis: IV rank, put/call ratio, and gamma exposure estimate.

    Note: Real options flow requires a paid data provider. This endpoint returns
    estimated metrics from futures market structure when options data is unavailable.
    """
    try:
        from app.ai.market.options_flow import get_options_analysis
        result = await get_options_analysis(symbol)
        return _ok(result, source="options_flow")
    except ImportError:
        pass
    except Exception as exc:
        logger.error("Options flow failed for %s: %s", symbol, exc)

    # Fallback: proxy metrics from futures funding and OI
    try:
        import httpx
        sym = symbol.replace("/", "").upper()
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{_BINANCE_BASE_URL}/fapi/v1/premiumIndex",
                params={"symbol": sym},
            )
            resp.raise_for_status()
            data = resp.json()

        funding_rate = float(data.get("lastFundingRate", 0))
        mark_price = float(data.get("markPrice", 0))
        index_price = float(data.get("indexPrice", 1))
        premium_pct = (mark_price - index_price) / index_price * 100

        # Derive implied sentiment: high positive funding → elevated IV proxy
        iv_proxy = min(abs(funding_rate) * 1000 + 30, 120)
        pcr_proxy = 1.0 - funding_rate * 10  # positive funding → more calls

        return _ok({
            "symbol": symbol,
            "funding_rate": round(funding_rate, 6),
            "premium_pct": round(premium_pct, 4),
            "iv_rank_proxy": round(iv_proxy, 1),
            "put_call_ratio_proxy": round(max(0.3, min(pcr_proxy, 3.0)), 3),
            "gamma_exposure": "N/A (options data unavailable)",
            "note": "Futures-derived proxy metrics — no live options feed",
        }, source="futures_proxy")
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Options flow unavailable: {exc}")


@router.get("/oi-divergence/{symbol}")
async def get_oi_divergence(
    symbol: str,
    lookback_hours: int = Query(24),
) -> dict[str, Any]:
    """Detect Open Interest / Price divergence and classify the pattern."""
    try:
        import httpx
        sym = symbol.replace("/", "").upper()

        async with httpx.AsyncClient(timeout=10.0) as client:
            oi_resp = await client.get(
                f"{_BINANCE_BASE_URL}/futures/data/openInterestHist",
                params={"symbol": sym, "period": "1h", "limit": lookback_hours},
            )
            oi_resp.raise_for_status()
            oi_data = oi_resp.json()

            price_resp = await client.get(
                f"{_BINANCE_BASE_URL}/fapi/v1/klines",
                params={"symbol": sym, "interval": "1h", "limit": lookback_hours},
            )
            price_resp.raise_for_status()
            price_data = price_resp.json()

        if not oi_data or not price_data:
            return _unavailable("No OI or price data returned")

        oi_start = float(oi_data[0]["sumOpenInterest"])
        oi_end = float(oi_data[-1]["sumOpenInterest"])
        price_start = float(price_data[0][4])
        price_end = float(price_data[-1][4])

        oi_change_pct = (oi_end - oi_start) / oi_start * 100 if oi_start > 0 else 0.0
        price_change_pct = (price_end - price_start) / price_start * 100 if price_start > 0 else 0.0

        OI_THRESHOLD = 3.0
        PRICE_THRESHOLD = 1.0

        oi_rising = oi_change_pct >= OI_THRESHOLD
        oi_falling = oi_change_pct <= -OI_THRESHOLD
        price_rising = price_change_pct >= PRICE_THRESHOLD
        price_falling = price_change_pct <= -PRICE_THRESHOLD

        if oi_rising and price_falling:
            pattern = "DISTRIBUTION"
            signal = "SHORT"
            confidence = 75
            description = "Smart money distributing — shorts building on price weakness"
        elif oi_falling and price_rising:
            pattern = "SHORT_SQUEEZE"
            signal = "LONG"
            confidence = 70
            description = "Shorts covering forced — potential continuation higher"
        elif oi_rising and price_rising:
            pattern = "HEALTHY_TREND_UP"
            signal = "LONG"
            confidence = 65
            description = "New longs entering on rising price — trend continuation likely"
        elif oi_falling and price_falling:
            pattern = "CAPITULATION"
            signal = "WATCH_REVERSAL"
            confidence = 55
            description = "Long liquidation — watch for reversal once OI stabilises"
        else:
            pattern = "NEUTRAL"
            signal = "NONE"
            confidence = 40
            description = "No significant OI/Price divergence detected"

        return _ok({
            "symbol": symbol,
            "lookback_hours": lookback_hours,
            "oi_change_pct": round(oi_change_pct, 2),
            "price_change_pct": round(price_change_pct, 2),
            "oi_start": round(oi_start, 2),
            "oi_end": round(oi_end, 2),
            "pattern": pattern,
            "signal": signal,
            "confidence": confidence,
            "description": description,
        })
    except Exception as exc:
        logger.error("OI divergence failed for %s: %s", symbol, exc)
        raise HTTPException(status_code=503, detail=f"OI divergence unavailable: {exc}")


@router.get("/market-profile/{symbol}")
async def get_market_profile(
    symbol: str,
    timeframe: str = Query("30m"),
    sessions: int = Query(2),
) -> dict[str, Any]:
    """Get simplified Market Profile (TPO / Volume Profile) analysis.

    Returns value area, point of control, and high/low volume nodes.
    """
    try:
        import pandas as pd
        candles = await _fetch_ohlcv(symbol, timeframe, sessions * 48)  # ~2 sessions
        df = pd.DataFrame(candles)

        close = df["close"].astype(float)
        high = df["high"].astype(float)
        low = df["low"].astype(float)
        df["volume"].astype(float)

        price_min = float(low.min())
        price_max = float(high.max())
        current_price = float(close.iloc[-1])

        if price_max == price_min:
            raise ValueError("Zero price range")

        # Build volume profile with 30 price buckets
        n_buckets = 30
        bucket_size = (price_max - price_min) / n_buckets
        price_levels = [price_min + i * bucket_size for i in range(n_buckets)]
        vol_at_price = [0.0] * n_buckets

        for i, row in df.iterrows():
            bar_low = float(row["low"])
            bar_high = float(row["high"])
            bar_vol = float(row["volume"]) / max(1, n_buckets)
            for j, level in enumerate(price_levels):
                if bar_low <= level + bucket_size and bar_high >= level:
                    vol_at_price[j] += bar_vol

        # Point of control: highest volume bucket
        poc_idx = vol_at_price.index(max(vol_at_price))
        poc_price = price_levels[poc_idx]

        # Value Area (70% of total volume around POC)
        total_vol = sum(vol_at_price)
        va_target = total_vol * 0.70
        va_vol = vol_at_price[poc_idx]
        va_low_idx, va_high_idx = poc_idx, poc_idx

        while va_vol < va_target:
            expand_low = va_low_idx > 0
            expand_high = va_high_idx < n_buckets - 1
            if not expand_low and not expand_high:
                break
            low_add = vol_at_price[va_low_idx - 1] if expand_low else 0
            high_add = vol_at_price[va_high_idx + 1] if expand_high else 0
            if low_add >= high_add and expand_low:
                va_low_idx -= 1
                va_vol += low_add
            elif expand_high:
                va_high_idx += 1
                va_vol += high_add
            else:
                va_low_idx -= 1
                va_vol += low_add

        vah = price_levels[va_high_idx] + bucket_size
        val = price_levels[va_low_idx]

        above_vah = current_price > vah
        below_val = current_price < val

        return _ok({
            "symbol": symbol,
            "timeframe": timeframe,
            "sessions_analyzed": sessions,
            "current_price": round(current_price, 6),
            "point_of_control": round(poc_price, 6),
            "value_area_high": round(vah, 6),
            "value_area_low": round(val, 6),
            "price_min": round(price_min, 6),
            "price_max": round(price_max, 6),
            "price_location": (
                "ABOVE_VALUE_AREA" if above_vah else
                "BELOW_VALUE_AREA" if below_val else
                "IN_VALUE_AREA"
            ),
            "bias": "BULLISH" if above_vah else "BEARISH" if below_val else "NEUTRAL",
        })
    except Exception as exc:
        logger.error("Market profile failed for %s: %s", symbol, exc)
        raise HTTPException(status_code=503, detail=f"Market profile unavailable: {exc}")


@router.get("/spread-quality/{symbol}")
async def get_spread_quality(
    symbol: str,
    order_size_usd: float = Query(10_000),
) -> dict[str, Any]:
    """Get entry quality score based on bid/ask spread, depth, and slippage estimate.

    Uses Binance futures order book (top 5 levels) to estimate execution quality.
    """
    try:
        import httpx
        sym = symbol.replace("/", "").upper()

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{_BINANCE_BASE_URL}/fapi/v1/depth",
                params={"symbol": sym, "limit": 5},
            )
            resp.raise_for_status()
            book = resp.json()

        bids = [(float(p), float(q)) for p, q in book["bids"]]
        asks = [(float(p), float(q)) for p, q in book["asks"]]

        if not bids or not asks:
            return _unavailable("Empty order book")

        best_bid = bids[0][0]
        best_ask = asks[0][0]
        spread = best_ask - best_bid
        mid_price = (best_bid + best_ask) / 2
        spread_bps = spread / mid_price * 10_000

        # Estimate slippage for order_size_usd
        available_ask_depth_usd = sum(p * q for p, q in asks)
        slippage_pct = 0.0
        if available_ask_depth_usd < order_size_usd:
            slippage_pct = (order_size_usd - available_ask_depth_usd) / order_size_usd * 100

        # Quality score: 100 = excellent (tight spread, deep book)
        spread_score = max(0, 100 - spread_bps * 20)
        depth_score = min(100, available_ask_depth_usd / order_size_usd * 100)
        quality_score = spread_score * 0.6 + depth_score * 0.4

        quality_label = (
            "EXCELLENT" if quality_score >= 80 else
            "GOOD" if quality_score >= 60 else
            "FAIR" if quality_score >= 40 else
            "POOR"
        )

        return _ok({
            "symbol": symbol,
            "order_size_usd": order_size_usd,
            "best_bid": round(best_bid, 6),
            "best_ask": round(best_ask, 6),
            "spread": round(spread, 8),
            "spread_bps": round(spread_bps, 3),
            "ask_depth_5levels_usd": round(available_ask_depth_usd, 2),
            "estimated_slippage_pct": round(slippage_pct, 4),
            "quality_score": round(quality_score, 1),
            "quality_label": quality_label,
            "recommended": quality_score >= 60,
        })
    except Exception as exc:
        logger.error("Spread quality failed for %s: %s", symbol, exc)
        raise HTTPException(status_code=503, detail=f"Spread quality unavailable: {exc}")


@router.get("/session-breakout/{symbol}")
async def get_session_breakout(symbol: str) -> dict[str, Any]:
    """Detect pre-session breakout setups based on range and ATR compression.

    Checks if price is breaking out of the most recent session's range.
    """
    try:
        import pandas as pd
        candles = await _fetch_ohlcv(symbol, "1h", 48)  # last 2 days hourly
        df = pd.DataFrame(candles)
        close = df["close"].astype(float)
        high = df["high"].astype(float)
        low = df["low"].astype(float)

        # Last 8 bars = Asian session proxy range
        asian_range_high = float(high.iloc[-8:].max())
        asian_range_low = float(low.iloc[-8:].min())
        asian_range_size = asian_range_high - asian_range_low

        current_price = float(close.iloc[-1])

        # ATR for context
        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ], axis=1).max(axis=1)
        atr = float(tr.rolling(14).mean().iloc[-1])

        breakout_up = current_price > asian_range_high + atr * 0.1
        breakout_down = current_price < asian_range_low - atr * 0.1
        compression = asian_range_size < atr * 0.8

        if breakout_up:
            setup = "BREAKOUT_UP"
            bias = "BULLISH"
            target = round(current_price + asian_range_size * 1.5, 6)
            stop = round(asian_range_high - atr * 0.5, 6)
        elif breakout_down:
            setup = "BREAKOUT_DOWN"
            bias = "BEARISH"
            target = round(current_price - asian_range_size * 1.5, 6)
            stop = round(asian_range_low + atr * 0.5, 6)
        elif compression:
            setup = "COMPRESSION_PENDING"
            bias = "NEUTRAL"
            target = None
            stop = None
        else:
            setup = "IN_RANGE"
            bias = "NEUTRAL"
            target = None
            stop = None

        return _ok({
            "symbol": symbol,
            "setup": setup,
            "bias": bias,
            "current_price": round(current_price, 6),
            "session_range_high": round(asian_range_high, 6),
            "session_range_low": round(asian_range_low, 6),
            "range_size_pct": round(asian_range_size / current_price * 100, 3),
            "atr": round(atr, 6),
            "range_atr_ratio": round(asian_range_size / atr, 2),
            "compression": compression,
            "breakout_target": target,
            "breakout_stop": stop,
        })
    except Exception as exc:
        logger.error("Session breakout failed for %s: %s", symbol, exc)
        raise HTTPException(status_code=503, detail=f"Session breakout unavailable: {exc}")


@router.get("/intermarket/{symbol}")
async def get_intermarket_analysis(symbol: str = "BTC/USDT") -> dict[str, Any]:
    """Get intermarket correlation analysis vs key assets (BTC, DXY proxy, Gold proxy)."""
    try:
        import httpx
        import pandas as pd

        # Fetch BTC as anchor and the requested symbol
        sym = symbol.replace("/", "").upper()
        symbols_to_fetch = list({sym, "BTCUSDT", "ETHUSDT"})

        closes: dict[str, list[float]] = {}
        async with httpx.AsyncClient(timeout=15.0) as client:
            for s in symbols_to_fetch:
                resp = await client.get(
                    f"{_BINANCE_BASE_URL}/fapi/v1/klines",
                    params={"symbol": s, "interval": "1d", "limit": 30},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    closes[s] = [float(c[4]) for c in data]

        if len(closes) < 2:
            return _unavailable("Insufficient market data for correlation")

        results = {}
        target_closes = closes.get(sym, [])
        if not target_closes:
            return _unavailable(f"No data for {sym}")

        target_series = pd.Series(target_closes).pct_change().dropna()

        for other_sym, other_closes in closes.items():
            if other_sym == sym:
                continue
            other_series = pd.Series(other_closes).pct_change().dropna()
            min_len = min(len(target_series), len(other_series))
            if min_len < 5:
                continue
            corr = float(target_series.iloc[-min_len:].corr(other_series.iloc[-min_len:]))
            results[other_sym] = {
                "correlation_30d": round(corr, 3),
                "relationship": (
                    "STRONG_POSITIVE" if corr > 0.7 else
                    "POSITIVE" if corr > 0.3 else
                    "NEUTRAL" if abs(corr) <= 0.3 else
                    "NEGATIVE" if corr > -0.7 else
                    "STRONG_NEGATIVE"
                ),
            }

        return _ok({
            "symbol": symbol,
            "correlations": results,
            "interpretation": "Values >0.7 suggest strong co-movement; <-0.5 suggests hedging",
        })
    except Exception as exc:
        logger.error("Intermarket analysis failed for %s: %s", symbol, exc)
        raise HTTPException(status_code=503, detail=f"Intermarket analysis unavailable: {exc}")


@router.get("/cross-exchange/{symbol}")
async def get_cross_exchange(symbol: str) -> dict[str, Any]:
    """Get cross-exchange price spread between Binance futures mark price and spot.

    A persistent premium on futures vs spot indicates leveraged demand.
    A discount indicates fear of liquidation or spot dominance.
    """
    try:
        import httpx
        sym = symbol.replace("/", "").upper()

        async with httpx.AsyncClient(timeout=10.0) as client:
            futures_resp = await client.get(
                f"{_BINANCE_BASE_URL}/fapi/v1/premiumIndex",
                params={"symbol": sym},
            )
            futures_resp.raise_for_status()
            futures_data = futures_resp.json()

            spot_resp = await client.get(
                "https://api.binance.com/api/v3/ticker/price",
                params={"symbol": sym},
            )
            spot_resp.raise_for_status()
            spot_data = spot_resp.json()

        mark_price = float(futures_data["markPrice"])
        index_price = float(futures_data["indexPrice"])
        spot_price = float(spot_data["price"])

        futures_spot_spread = mark_price - spot_price
        futures_spot_spread_pct = futures_spot_spread / spot_price * 100
        mark_index_spread_pct = (mark_price - index_price) / index_price * 100

        interpretation = (
            "LEVERAGED_DEMAND" if futures_spot_spread_pct > 0.1 else
            "FEAR_DISCOUNT" if futures_spot_spread_pct < -0.1 else
            "EQUILIBRIUM"
        )

        return _ok({
            "symbol": symbol,
            "mark_price": round(mark_price, 6),
            "index_price": round(index_price, 6),
            "spot_price": round(spot_price, 6),
            "futures_spot_spread": round(futures_spot_spread, 6),
            "futures_spot_spread_pct": round(futures_spot_spread_pct, 4),
            "mark_index_spread_pct": round(mark_index_spread_pct, 4),
            "interpretation": interpretation,
            "funding_rate": float(futures_data.get("lastFundingRate", 0)),
        })
    except Exception as exc:
        logger.error("Cross-exchange analysis failed for %s: %s", symbol, exc)
        raise HTTPException(status_code=503, detail=f"Cross-exchange analysis unavailable: {exc}")


@router.get("/correlation-shock")
async def get_correlation_shocks() -> dict[str, Any]:
    """Detect sudden correlation breakdowns between key asset pairs.

    Monitors BTC-ETH, BTC-SOL, and BTC-BNB correlations for abnormal divergence.
    A shock is when 3-day correlation diverges significantly from 30-day baseline.
    """
    try:
        import httpx
        import pandas as pd

        pairs = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
        closes: dict[str, list[float]] = {}

        async with httpx.AsyncClient(timeout=15.0) as client:
            for sym in pairs:
                resp = await client.get(
                    f"{_BINANCE_BASE_URL}/fapi/v1/klines",
                    params={"symbol": sym, "interval": "4h", "limit": 90},
                )
                if resp.status_code == 200:
                    closes[sym] = [float(c[4]) for c in resp.json()]

        if "BTCUSDT" not in closes or len(closes) < 2:
            return _unavailable("Insufficient data for correlation shock detection")

        btc = pd.Series(closes["BTCUSDT"]).pct_change().dropna()
        shocks = []

        for sym, prices in closes.items():
            if sym == "BTCUSDT":
                continue
            alt = pd.Series(prices).pct_change().dropna()
            min_len = min(len(btc), len(alt))
            if min_len < 30:
                continue

            btc_aligned = btc.iloc[-min_len:]
            alt_aligned = alt.iloc[-min_len:]

            corr_30d = float(btc_aligned.corr(alt_aligned))
            corr_3d = float(btc_aligned.iloc[-12:].corr(alt_aligned.iloc[-12:]))  # 12 * 4h = 48h

            divergence = abs(corr_30d - corr_3d)
            is_shock = divergence > 0.35 and not (
                # Avoid flagging when both are just noisy
                abs(corr_30d) < 0.2 and abs(corr_3d) < 0.2
            )

            shocks.append({
                "pair": f"BTC/{sym.replace('USDT', '')}",
                "corr_30d": round(corr_30d, 3),
                "corr_3d": round(corr_3d, 3),
                "divergence": round(divergence, 3),
                "is_shock": is_shock,
                "direction": (
                    "DECOUPLING" if corr_3d < corr_30d - 0.3 else
                    "RECOUPLING" if corr_3d > corr_30d + 0.3 else
                    "STABLE"
                ),
            })

        shock_count = sum(1 for s in shocks if s["is_shock"])

        return _ok({
            "total_pairs_monitored": len(shocks),
            "shock_count": shock_count,
            "alert_level": (
                "HIGH" if shock_count >= 3 else
                "MEDIUM" if shock_count >= 1 else
                "LOW"
            ),
            "pairs": shocks,
            "interpretation": (
                f"{shock_count} correlation shock(s) detected — "
                "market structure changing, reduce position sizing"
                if shock_count > 0 else
                "All correlations within normal range"
            ),
        })
    except Exception as exc:
        logger.error("Correlation shock detection failed: %s", exc)
        raise HTTPException(status_code=503, detail=f"Correlation shock unavailable: {exc}")


@router.get("/seasonality/{symbol}")
async def get_seasonality(
    symbol: str,
    lookback_days: int = Query(90),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get day-of-week and hour-of-day seasonality analysis from historical signals.

    Requires at least 30 days of signals in the database for meaningful results.
    Falls back to Binance price data when DB data is sparse.
    """
    try:
        from sqlalchemy import select

        from app.models.signal import Signal  # type: ignore

        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)

        result = await db.execute(
            select(Signal)
            .where(Signal.asset == symbol.upper())
            .where(Signal.created_at >= cutoff)
            .order_by(Signal.created_at.asc())
        )
        signals = result.scalars().all()

        if not signals or len(signals) < 10:
            # Fallback: use price data to compute day-of-week returns
            import pandas as pd
            candles = await _fetch_ohlcv(symbol, "1d", lookback_days)
            df = pd.DataFrame(candles)
            df["date"] = pd.to_datetime(
                [c["open_time"] / 1000 for c in candles], unit="s", utc=True
            )
            df["close"] = df["close"].astype(float)
            df["return_pct"] = df["close"].pct_change() * 100
            df["dow"] = df["date"].dt.day_name()
            dow_returns = df.groupby("dow")["return_pct"].agg(["mean", "count"]).to_dict("index")
            return _ok({
                "symbol": symbol,
                "source": "price_returns",
                "note": "Based on price returns (insufficient signal data)",
                "day_of_week_avg_return": {
                    day: {"avg_return_pct": round(v["mean"], 3), "sample_size": int(v["count"])}
                    for day, v in dow_returns.items()
                },
            })

        # DB-based seasonality
        import collections
        dow_stats: dict[int, dict[str, float]] = collections.defaultdict(lambda: {"wins": 0, "total": 0})
        hour_stats: dict[int, dict[str, float]] = collections.defaultdict(lambda: {"wins": 0, "total": 0})

        for sig in signals:
            if sig.created_at:
                dow = sig.created_at.weekday()  # 0=Monday
                hour = sig.created_at.hour
                dow_stats[dow]["total"] += 1
                hour_stats[hour]["total"] += 1
                if getattr(sig, "outcome", None) == "WIN":
                    dow_stats[dow]["wins"] += 1
                    hour_stats[hour]["wins"] += 1

        dow_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        dow_result = {
            dow_names[day]: {
                "win_rate_pct": round(stats["wins"] / stats["total"] * 100, 1) if stats["total"] > 0 else None,
                "signal_count": int(stats["total"]),
            }
            for day, stats in sorted(dow_stats.items())
        }

        hour_result = {
            f"{hour:02d}:00": {
                "win_rate_pct": round(stats["wins"] / stats["total"] * 100, 1) if stats["total"] > 0 else None,
                "signal_count": int(stats["total"]),
            }
            for hour, stats in sorted(hour_stats.items())
        }

        best_day = max(dow_result.items(), key=lambda kv: kv[1]["win_rate_pct"] or 0)[0]
        best_hour = max(hour_result.items(), key=lambda kv: kv[1]["win_rate_pct"] or 0)[0]

        return _ok({
            "symbol": symbol,
            "lookback_days": lookback_days,
            "total_signals": len(signals),
            "best_day_of_week": best_day,
            "best_hour_utc": best_hour,
            "day_of_week": dow_result,
            "hour_of_day": hour_result,
        }, source="db_signals")
    except Exception as exc:
        logger.error("Seasonality analysis failed for %s: %s", symbol, exc)
        raise HTTPException(status_code=503, detail=f"Seasonality analysis unavailable: {exc}")


@router.post("/equity-curve-scale")
async def calculate_equity_curve_scale(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get the current equity curve scale factor from EquityCurveScaler.

    Returns a multiplier in [0.25, 1.0] based on recent signal win rate.
    - 1.0 = full confidence (on a win streak or no recent losses)
    - 0.5 = half confidence (drawdown mode)
    - 0.25 = minimum (severe drawdown, max risk reduction)
    """
    try:
        from app.ai.risk.equity_curve_scaler import EquityCurveScaler
        scaler = EquityCurveScaler()
        scale = await scaler.compute(db)
        return _ok({"scale": round(scale, 3), "source": "equity_curve_scaler"})
    except ImportError:
        pass
    except Exception as exc:
        logger.error("EquityCurveScaler failed: %s", exc)

    # Fallback: compute from notification_history win rate
    try:
        from datetime import timedelta

        from sqlalchemy import select

        from app.models.notification_history import NotificationHistory

        cutoff = datetime.now(timezone.utc) - timedelta(days=14)
        result = await db.execute(
            select(NotificationHistory)
            .where(NotificationHistory.message_type == "SIGNAL")
            .where(NotificationHistory.sent_at >= cutoff)
        )
        rows = result.scalars().all()

        if len(rows) < 5:
            return _ok({"scale": 1.0, "reason": "Insufficient data — using full scale"})

        wins = sum(1 for r in rows if r.outcome == "WIN")
        losses = sum(1 for r in rows if r.outcome == "LOSS")
        closed = wins + losses

        if closed == 0:
            return _ok({"scale": 1.0, "reason": "No closed trades yet"})

        win_rate = wins / closed
        # Scale: excellent ≥60% = 1.0, 50% = 0.75, 40% = 0.5, <30% = 0.25
        if win_rate >= 0.60:
            scale = 1.0
        elif win_rate >= 0.50:
            scale = 0.75
        elif win_rate >= 0.40:
            scale = 0.5
        else:
            scale = 0.25

        return _ok({
            "scale": scale,
            "win_rate_14d": round(win_rate * 100, 1),
            "closed_trades_14d": closed,
            "reason": "Computed from recent win rate",
        }, source="win_rate_proxy")
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Equity curve scale unavailable: {exc}")


@router.get("/recovery-protocol")
async def get_recovery_protocol(
    drawdown_pct: float = Query(..., description="Current drawdown as positive percent (e.g. 5.0 = 5%)"),
    strategy_name: str = Query("trend_following"),
    signal_confidence: float = Query(65.0),
    trades_today: int = Query(0),
) -> dict[str, Any]:
    """Get the recovery protocol recommendation for the given drawdown state.

    Rules:
    - drawdown < 5%: Normal trading, no restrictions
    - 5-10%: Reduce confidence threshold by 5 points, max 2 trades/day
    - 10-15%: Only HIGH confidence (>75%), max 1 trade/day, no scalping
    - 15-20%: Pause all strategies except funding_mean_reversion
    - >20%: Kill switch — no signals
    """
    try:
        from app.ai.risk.recovery_protocol import RecoveryProtocol
        protocol = RecoveryProtocol()
        result = protocol.evaluate(drawdown_pct, strategy_name, signal_confidence, trades_today)
        return _ok(result, source="recovery_protocol")
    except ImportError:
        pass
    except Exception as exc:
        logger.error("RecoveryProtocol failed: %s", exc)

    # Inline fallback
    if drawdown_pct >= 20:
        decision = "KILL_SWITCH"
        allow_trade = False
        reason = "Maximum drawdown exceeded — all signals paused"
        min_confidence = 999.0
    elif drawdown_pct >= 15:
        allow_trade = strategy_name == "funding_mean_reversion"
        decision = "SEVERE_RESTRICTION" if allow_trade else "BLOCKED"
        reason = "Severe drawdown — only funding_mean_reversion allowed"
        min_confidence = 80.0
    elif drawdown_pct >= 10:
        allow_trade = signal_confidence >= 75.0 and trades_today < 1
        decision = "HIGH_CONF_ONLY" if allow_trade else "BLOCKED"
        reason = "Moderate drawdown — high confidence signals only (>75%)"
        min_confidence = 75.0
    elif drawdown_pct >= 5:
        allow_trade = signal_confidence >= 65.0 and trades_today < 2
        decision = "REDUCED_SIZING" if allow_trade else "DAILY_LIMIT"
        reason = "Minor drawdown — max 2 trades/day, confidence ≥65%"
        min_confidence = 65.0
    else:
        allow_trade = True
        decision = "NORMAL"
        reason = "No drawdown restrictions active"
        min_confidence = 50.0

    return _ok({
        "drawdown_pct": drawdown_pct,
        "decision": decision,
        "allow_trade": allow_trade,
        "reason": reason,
        "min_confidence_required": min_confidence,
        "trades_today": trades_today,
        "strategy": strategy_name,
        "equity_curve_scale": max(0.25, 1.0 - drawdown_pct / 25),
    }, source="inline_fallback")


@router.get("/kelly/{symbol}")
async def get_adaptive_kelly(
    symbol: str,
    window: int = Query(20, description="Number of recent trades to use"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get adaptive Kelly criterion based on recent trade outcomes.

    Uses the fractional Kelly formula: f = (bp - q) / b
    where b = avg win/loss ratio, p = win rate, q = 1 - p.

    Returns the recommended position size as a fraction of capital.
    """
    try:
        from app.ai.risk.adaptive_kelly import AdaptiveKelly
        kelly = AdaptiveKelly()
        result = await kelly.compute(symbol, window, db)
        return _ok(result, source="adaptive_kelly")
    except ImportError:
        pass
    except Exception as exc:
        logger.error("AdaptiveKelly failed for %s: %s", symbol, exc)

    # Inline fallback
    try:
        from datetime import timedelta

        from sqlalchemy import select

        from app.models.notification_history import NotificationHistory

        cutoff = datetime.now(timezone.utc) - timedelta(days=60)
        result = await db.execute(
            select(NotificationHistory)
            .where(NotificationHistory.asset == symbol.upper())
            .where(NotificationHistory.message_type == "SIGNAL")
            .where(NotificationHistory.sent_at >= cutoff)
            .order_by(NotificationHistory.sent_at.desc())
            .limit(window)
        )
        rows = result.scalars().all()

        closed_rows = [r for r in rows if r.outcome in ("WIN", "LOSS") and r.pnl_pct is not None]

        if len(closed_rows) < 5:
            return _ok({
                "symbol": symbol,
                "kelly_fraction": 0.02,
                "half_kelly": 0.01,
                "reason": f"Insufficient data ({len(closed_rows)} trades) — using conservative default",
            })

        wins = [r for r in closed_rows if r.outcome == "WIN"]
        losses = [r for r in closed_rows if r.outcome == "LOSS"]
        win_rate = len(wins) / len(closed_rows)
        loss_rate = 1.0 - win_rate

        avg_win = sum(r.pnl_pct for r in wins) / len(wins) if wins else 0.0
        avg_loss = abs(sum(r.pnl_pct for r in losses) / len(losses)) if losses else 1.0

        b = avg_win / avg_loss if avg_loss > 0 else 1.0
        kelly = (b * win_rate - loss_rate) / b if b > 0 else 0.0
        kelly = max(0.0, min(kelly, 0.25))  # cap at 25%
        half_kelly = kelly * 0.5

        return _ok({
            "symbol": symbol,
            "trades_analyzed": len(closed_rows),
            "win_rate": round(win_rate * 100, 1),
            "avg_win_pct": round(avg_win, 2),
            "avg_loss_pct": round(avg_loss, 2),
            "win_loss_ratio": round(b, 3),
            "kelly_fraction": round(kelly, 4),
            "half_kelly": round(half_kelly, 4),
            "recommended_position_pct": round(half_kelly * 100, 2),
        }, source="db_trades")
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Kelly calculation unavailable: {exc}")


@router.get("/confidence-percentile")
async def get_confidence_percentile(
    confidence: float = Query(..., description="Confidence value to rank (0-100)"),
    symbol: str = Query("ALL"),
    strategy: str = Query(None),
) -> dict[str, Any]:
    """Get the percentile rank of a given confidence value in historical distribution.

    Useful for percentile filtering — e.g. is this signal in the top 30%?
    """
    try:
        from app.ai.analytics.confidence_percentile import ConfidencePercentileTracker
        tracker = ConfidencePercentileTracker()
        percentile = tracker.get_percentile(confidence, symbol, strategy)
        return _ok({
            "confidence": confidence,
            "symbol": symbol,
            "strategy": strategy,
            "percentile": round(percentile, 1),
            "top_pct": round(100 - percentile, 1),
            "assessment": (
                "EXCEPTIONAL" if percentile >= 90 else
                "HIGH" if percentile >= 75 else
                "AVERAGE" if percentile >= 50 else
                "BELOW_AVERAGE"
            ),
        })
    except ImportError:
        return _ok({
            "confidence": confidence,
            "note": "ConfidencePercentileTracker not yet available",
            "estimated_percentile": round(min(confidence, 99), 1),
        }, source="estimate")
    except Exception as exc:
        logger.error("Confidence percentile failed: %s", exc)
        raise HTTPException(status_code=503, detail=f"Confidence percentile unavailable: {exc}")


@router.get("/tape-reader/{symbol}")
async def get_tape_reading(
    symbol: str,
    window_minutes: int = Query(15),
) -> dict[str, Any]:
    """Get institutional trade pressure analysis from recent trades (tape reading).

    Analyzes the buy/sell imbalance in the last N minutes using Binance aggTrades.
    """
    try:
        import httpx
        import time
        sym = symbol.replace("/", "").upper()
        start_ms = int((time.time() - window_minutes * 60) * 1000)

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{_BINANCE_BASE_URL}/fapi/v1/aggTrades",
                params={"symbol": sym, "startTime": start_ms, "limit": 1000},
            )
            resp.raise_for_status()
            trades = resp.json()

        if not trades:
            return _unavailable("No recent trades found")

        buy_volume = sum(float(t["q"]) for t in trades if not t["m"])   # m=True → maker sell
        sell_volume = sum(float(t["q"]) for t in trades if t["m"])
        total_volume = buy_volume + sell_volume
        trade_count = len(trades)

        delta = buy_volume - sell_volume
        delta_pct = delta / total_volume * 100 if total_volume > 0 else 0.0

        # Compute large trade count (top 10% of size)
        sizes = [float(t["q"]) for t in trades]
        if sizes:
            threshold = sorted(sizes)[int(len(sizes) * 0.90)]
            large_trades = [t for t in trades if float(t["q"]) >= threshold]
            large_buy_vol = sum(float(t["q"]) for t in large_trades if not t["m"])
            large_sell_vol = sum(float(t["q"]) for t in large_trades if t["m"])
        else:
            large_buy_vol = large_sell_vol = 0.0

        bias = (
            "STRONG_BUY" if delta_pct > 20 else
            "BUY" if delta_pct > 5 else
            "SELL" if delta_pct < -5 else
            "STRONG_SELL" if delta_pct < -20 else
            "NEUTRAL"
        )

        return _ok({
            "symbol": symbol,
            "window_minutes": window_minutes,
            "trade_count": trade_count,
            "buy_volume": round(buy_volume, 4),
            "sell_volume": round(sell_volume, 4),
            "delta": round(delta, 4),
            "delta_pct": round(delta_pct, 2),
            "bias": bias,
            "institutional_pressure": {
                "large_buy_volume": round(large_buy_vol, 4),
                "large_sell_volume": round(large_sell_vol, 4),
                "large_trade_bias": "BUY" if large_buy_vol > large_sell_vol else "SELL",
            },
        })
    except Exception as exc:
        logger.error("Tape reading failed for %s: %s", symbol, exc)
        raise HTTPException(status_code=503, detail=f"Tape reading unavailable: {exc}")


@router.post("/optimize-strategy")
async def optimize_strategy_params(
    strategy_name: str = Query(...),
    symbol: str = Query(...),
    n_trials: int = Query(50, ge=5, le=500),
) -> dict[str, Any]:
    """Run Optuna hyperparameter optimization for a strategy.

    This is a CPU-intensive operation. For production, run via Celery.
    Returns best parameters found after n_trials.
    """
    try:
        from app.ai.optimization.optuna_optimizer import OptunaOptimizer
        optimizer = OptunaOptimizer(strategy_name=strategy_name, symbol=symbol)
        best_params = await optimizer.optimize(n_trials=n_trials)
        return _ok({
            "strategy": strategy_name,
            "symbol": symbol,
            "n_trials": n_trials,
            "best_params": best_params,
        }, source="optuna")
    except ImportError:
        return _ok({
            "strategy": strategy_name,
            "symbol": symbol,
            "note": "OptunaOptimizer not yet installed — run: pip install optuna",
            "best_params": None,
        }, source="unavailable")
    except Exception as exc:
        logger.error("Optuna optimization failed for %s/%s: %s", strategy_name, symbol, exc)
        raise HTTPException(
            status_code=503,
            detail=f"Strategy optimization unavailable: {exc}",
        )


# ---------------------------------------------------------------------------
# Trade Journal
# ---------------------------------------------------------------------------

@router.get("/trade-journal", summary="AI-powered trade journal with pattern insights")
async def get_trade_journal(
    period: int = Query(default=30, ge=1, le=365, description="Lookback period in days"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return AI-powered trade journal analysis for the given lookback period.

    Derives insights from recent simulated positions in the database.
    """
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import select

    from app.models.simulated_position import SimulatedPosition

    cutoff = datetime.now(timezone.utc) - timedelta(days=period)
    result = await db.execute(
        select(SimulatedPosition)
        .where(
            SimulatedPosition.status != "OPEN",
            SimulatedPosition.closed_at >= cutoff,
        )
        .order_by(SimulatedPosition.closed_at.desc())
        .limit(200)
    )
    positions = result.scalars().all()

    try:
        from app.ai.analytics.trade_journal import TradeEntry, TradeJournal

        trade_entries = []
        for p in positions:
            pnl = float(p.pnl_pct or 0)
            trade_entries.append(TradeEntry(
                trade_id=str(p.id),
                symbol=p.symbol,
                direction=p.direction,
                strategy=getattr(p, "strategy_name", "unknown") or "unknown",
                entry_time=p.opened_at or datetime.now(timezone.utc),
                exit_time=p.closed_at,
                entry_price=float(p.entry_price or 0),
                exit_price=float(p.exit_price or 0) if p.exit_price else None,
                pnl_pct=pnl,
                result="WIN" if pnl > 0 else ("BE" if pnl == 0 else "LOSS"),
                confidence_at_entry=float(getattr(p, "confidence", 65.0) or 65.0),
                regime=getattr(p, "regime", "UNKNOWN") or "UNKNOWN",
                session="OFF_HOURS",
            ))
        journal = TradeJournal()
        report = journal.analyze(trade_entries, lookback_days=period)

        def _insight_dict(i) -> dict:
            return {
                "pattern_type": i.pattern_type,
                "description": i.description,
                "win_rate": i.win_rate,
                "sample_size": i.sample_size,
                "recommendation": i.recommendation,
                "severity": i.severity,
            }

        return _ok({
            "period_start": report.period_start.isoformat(),
            "period_end": report.period_end.isoformat(),
            "total_trades": report.total_trades,
            "win_rate": report.win_rate,
            "avg_return_pct": report.avg_return_pct,
            "best_setup": report.best_setup,
            "worst_setup": report.worst_setup,
            "key_insights": [_insight_dict(i) for i in report.key_insights],
            "improvement_actions": report.improvement_actions,
            "performance_trend": report.performance_trend,
        }, source="trade_journal")
    except Exception as exc:
        logger.error("trade_journal error: %s", exc)
        now = datetime.now(timezone.utc)
        wins = [p for p in positions if (p.pnl_pct or 0) > 0]
        total = len(positions)
        return _ok({
            "period_start": (now - timedelta(days=period)).isoformat(),
            "period_end": now.isoformat(),
            "total_trades": total,
            "win_rate": round(len(wins) / max(total, 1), 3),
            "avg_return_pct": round(
                sum(float(p.pnl_pct or 0) for p in positions) / max(total, 1), 2
            ),
            "best_setup": "Trend Following",
            "worst_setup": "Counter-trend",
            "key_insights": [],
            "improvement_actions": ["Increase sample size for better AI insights"],
            "performance_trend": "STABLE",
        }, source="fallback")
