"""Professional Technical Analysis Chat — deep multi-source analysis with Claude."""

import base64
import json
import logging
from datetime import datetime, timezone
from typing import Any

import httpx
import pandas as pd
from anthropic import AsyncAnthropic
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.ai.regime.classifier import RegimeClassifier
from app.ai.strategies.smc_strategy import find_order_blocks, find_fair_value_gaps
from app.core.config import settings
from app.data.processors.feature_engineer import compute_features

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/pro-analysis", tags=["pro-analysis"])

SYMBOL_MAP = {s: s.replace("/", "") for s in [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
    "DOGE/USDT", "ADA/USDT", "AVAX/USDT", "DOT/USDT", "LINK/USDT",
    "EUR/USD", "GBP/USD", "XAU/USD", "GBP/JPY",
]}

classifier = RegimeClassifier()

PRO_SYSTEM_PROMPT = """You are a PROFESSIONAL TRADER with 20+ years of experience in crypto and forex markets. You are known for your precise technical analysis and disciplined risk management.

When analyzing a chart or pair, you MUST provide:

## 1. MARKET STRUCTURE ANALYSIS
- Current trend (Higher Highs/Higher Lows or Lower Highs/Lower Lows)
- Key support and resistance levels with exact prices
- Market regime classification

## 2. TECHNICAL INDICATORS SUMMARY
Present as a table:
| Indicator | Value | Signal |
|-----------|-------|--------|
| RSI(14) | XX.X | Overbought/Oversold/Neutral |
| MACD | XX.X | Bullish/Bearish Cross |
| ADX(14) | XX.X | Trend Strength |
| EMA Cross | 20/50/200 alignment | Bullish/Bearish |
| BB Position | X.XX | Upper/Middle/Lower |
| Volume | X.Xx avg | Above/Below Average |

## 3. ORDER FLOW & LIQUIDITY
- Order Block zones (demand/supply)
- Fair Value Gaps (unfilled)
- Liquidation clusters above/below price
- Volume profile (Point of Control)

## 4. PROBABILITY ASSESSMENT
Calculate and show:
- P(LONG success) = XX% — show the math breakdown
- P(SHORT success) = XX% — show the math breakdown
- Formula: P = (trend_weight × trend_score + momentum_weight × momentum_score + volume_weight × volume_score + structure_weight × structure_score) × regime_multiplier

## 5. TRADE RECOMMENDATION
If probability > 60%:
```json
{"recommendation": {
  "action": "LONG" or "SHORT",
  "entry": exact_price,
  "stop_loss": exact_price,
  "take_profit_1": exact_price,
  "take_profit_2": exact_price,
  "take_profit_3": exact_price,
  "risk_reward": X.X,
  "position_size_pct": X.X,
  "confidence": XX,
  "timeframe": "suggested holding period"
}}
```

## 6. NEWS & SENTIMENT
- Recent news affecting this pair
- Social sentiment score
- Macro factors (FED, geopolitics)

## 7. RISK WARNINGS
- Key invalidation levels
- Correlated assets to watch
- Upcoming events that could affect the trade

Always be specific with numbers. Never say "around" — give exact levels. Format your response with clear markdown headers and tables. If the user provides a chart image, analyze the visible patterns, candlesticks, and any drawn indicators."""


class ProAnalysisRequest(BaseModel):
    message: str
    asset: str = "BTC/USDT"
    timeframe: str = "4h"
    image_base64: str | None = None  # Optional chart screenshot
    history: list[dict[str, str]] = []


class ProAnalysisResponse(BaseModel):
    analysis: str
    recommendation: dict | None = None
    market_data: dict = {}
    probability: dict = {}


async def _fetch_klines(symbol: str, interval: str, limit: int = 500) -> pd.DataFrame:
    binance_sym = SYMBOL_MAP.get(symbol, symbol.replace("/", ""))

    # Try Binance first
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get("https://api.binance.com/api/v3/klines",
                params={"symbol": binance_sym, "interval": interval, "limit": limit})
            if resp.status_code == 200:
                raw = resp.json()
                return pd.DataFrame([{
                    "timestamp": datetime.fromtimestamp(k[0]/1000, tz=timezone.utc),
                    "open": float(k[1]), "high": float(k[2]), "low": float(k[3]),
                    "close": float(k[4]), "volume": float(k[5]),
                } for k in raw])
    except Exception:
        pass

    # Fallback to Yahoo for forex
    try:
        yahoo_map = {"EUR/USD": "EURUSD=X", "GBP/USD": "GBPUSD=X", "XAU/USD": "GC=F", "GBP/JPY": "GBPJPY=X"}
        yahoo_sym = yahoo_map.get(symbol, binance_sym + "=X")
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_sym}",
                params={"interval": "60m", "range": "1mo"}, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200:
                data = resp.json()
                result = data.get("chart", {}).get("result", [])
                if result:
                    ts = result[0].get("timestamp", [])
                    q = result[0].get("indicators", {}).get("quote", [{}])[0]
                    rows = []
                    for i in range(len(ts)):
                        if q.get("open", [None])[i] is not None:
                            rows.append({
                                "timestamp": datetime.fromtimestamp(ts[i], tz=timezone.utc),
                                "open": float(q["open"][i]), "high": float(q["high"][i]),
                                "low": float(q["low"][i]), "close": float(q["close"][i]),
                                "volume": float(q.get("volume", [0])[i] or 0),
                            })
                    return pd.DataFrame(rows)
    except Exception:
        pass

    return pd.DataFrame()


def _build_full_context(df: pd.DataFrame, featured: pd.DataFrame, asset: str) -> dict:
    """Build comprehensive market context for the LLM."""
    last = featured.iloc[-1]
    regime = classifier.predict_df(featured)

    obs = find_order_blocks(featured, lookback=30)
    fvgs = find_fair_value_gaps(featured, lookback=30)

    close = float(last["close"])

    # Calculate probability components
    rsi = float(last.get("rsi_14", 50))
    adx = float(last.get("adx_14", 0))
    ema_cross = int(last.get("ema_cross_signal", 0))
    vol_ratio = float(last.get("volume_vs_avg", 1))
    bb_pos = float(last.get("bb_position", 0.5))

    # Trend score (-1 to +1)
    trend_score = ema_cross * min(adx / 50, 1.0)
    # Momentum score
    momentum_score = (50 - rsi) / 50 if rsi < 50 else (50 - rsi) / 50  # negative when overbought
    # Volume score
    volume_score = min((vol_ratio - 1) * 0.5, 1.0) if vol_ratio > 1 else max((vol_ratio - 1) * 0.5, -1.0)
    # Structure score
    bull_obs = len([ob for ob in obs if ob["type"] == "bullish" and ob["mid"] < close])
    bear_obs = len([ob for ob in obs if ob["type"] == "bearish" and ob["mid"] > close])
    structure_score = (bull_obs - bear_obs) / max(bull_obs + bear_obs, 1)

    # Regime multiplier
    regime_mult = {"TREND_BULL": 1.1, "TREND_BEAR": 1.1, "CONSOLIDATION": 0.8, "HIGH_VOL_CHOPPY": 0.6}.get(regime.regime, 1.0)

    # Weighted probability
    raw_score = (0.30 * trend_score + 0.25 * momentum_score + 0.20 * volume_score + 0.25 * structure_score) * regime_mult
    p_long = round(max(0, min(100, 50 + raw_score * 50)), 1)
    p_short = round(100 - p_long, 1)

    # Recent price action
    recent = featured.tail(20)

    return {
        "asset": asset,
        "current_price": round(close, 8),
        "regime": regime.to_dict(),
        "indicators": {
            "rsi_14": round(rsi, 1),
            "adx_14": round(adx, 1),
            "macd": round(float(last.get("macd", 0)), 4),
            "macd_signal": round(float(last.get("macd_signal", 0)), 4),
            "macd_diff": round(float(last.get("macd_diff", 0)), 4),
            "ema_20": round(float(last.get("ema_20", 0)), 2),
            "ema_50": round(float(last.get("ema_50", 0)), 2),
            "ema_200": round(float(last.get("ema_200", 0)), 2),
            "ema_cross_signal": ema_cross,
            "atr_14": round(float(last.get("atr_14", 0)), 4),
            "atr_pct": round(float(last.get("atr_normalized", 0)) * 100, 3),
            "bb_upper": round(float(last.get("bb_upper", 0)), 2),
            "bb_lower": round(float(last.get("bb_lower", 0)), 2),
            "bb_position": round(bb_pos, 3),
            "volume_vs_avg": round(vol_ratio, 2),
            "hv_20": round(float(last.get("hv_20", 0)), 4),
        },
        "price_action": {
            "24h_high": round(float(recent["high"].max()), 2),
            "24h_low": round(float(recent["low"].min()), 2),
            "24h_change_pct": round((close - float(recent.iloc[0]["close"])) / float(recent.iloc[0]["close"]) * 100, 2),
        },
        "order_blocks": {
            "bullish": [{"price": f"${ob['low']:.2f}-${ob['high']:.2f}", "strength": ob["strength"]} for ob in obs if ob["type"] == "bullish"][-5:],
            "bearish": [{"price": f"${ob['low']:.2f}-${ob['high']:.2f}", "strength": ob["strength"]} for ob in obs if ob["type"] == "bearish"][-5:],
        },
        "fvg": {
            "bullish_gaps": len([f for f in fvgs if f["type"] == "bullish"]),
            "bearish_gaps": len([f for f in fvgs if f["type"] == "bearish"]),
            "nearest": [{"type": f["type"], "range": f"${f['bottom']:.2f}-${f['top']:.2f}"} for f in fvgs[-3:]],
        },
        "probability": {
            "long": p_long,
            "short": p_short,
            "components": {
                "trend_score": round(trend_score, 3),
                "momentum_score": round(momentum_score, 3),
                "volume_score": round(volume_score, 3),
                "structure_score": round(structure_score, 3),
                "regime_multiplier": regime_mult,
            },
        },
    }


def _extract_recommendation(text: str) -> dict | None:
    """Extract JSON recommendation from LLM response."""
    try:
        start = text.find('"recommendation"')
        if start == -1:
            return None
        brace = text.rfind("{", 0, start)
        if brace == -1:
            return None
        depth = 0
        end = brace
        for i in range(brace, len(text)):
            if text[i] == "{": depth += 1
            elif text[i] == "}": depth -= 1
            if depth == 0:
                end = i + 1
                break
        parsed = json.loads(text[brace:end])
        return parsed.get("recommendation")
    except (json.JSONDecodeError, KeyError):
        return None


@router.post("", response_model=ProAnalysisResponse)
async def pro_analysis(request: ProAnalysisRequest) -> ProAnalysisResponse:
    """Run professional-grade technical analysis using Claude with full market context."""
    if not settings.ANTHROPIC_API_KEY or settings.ANTHROPIC_API_KEY == "your_anthropic_api_key":
        raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY not configured")

    # Fetch multi-timeframe data
    df = await _fetch_klines(request.asset, request.timeframe, 500)
    if df.empty or len(df) < 30:
        raise HTTPException(status_code=400, detail=f"Insufficient data for {request.asset}")

    featured = compute_features(df)
    if featured.empty:
        raise HTTPException(status_code=400, detail="Feature computation failed")

    # Build comprehensive context
    ctx = _build_full_context(df, featured, request.asset)

    # Fetch news sentiment
    news_context = ""
    try:
        from app.data.fetchers.news_aggregator import get_news_aggregator
        agg = get_news_aggregator()
        sentiment = agg.get_sentiment_snapshot()
        recent_news = agg.get_news(limit=10)
        headlines = [n["title"] for n in recent_news[:5]]
        news_context = f"\nRECENT NEWS:\n" + "\n".join(f"- {h}" for h in headlines)
        news_context += f"\nGlobal Sentiment: {sentiment['global_sentiment']}"
        if sentiment["emergency_active"]:
            news_context += f"\n⚠️ EMERGENCY: {sentiment['emergency_reason']}"
    except Exception:
        pass

    # Build messages
    context_text = f"""LIVE MARKET DATA for {request.asset} ({request.timeframe}):
{json.dumps(ctx, indent=2, default=str)}
{news_context}"""

    messages = []
    for msg in request.history[-10:]:
        messages.append({"role": msg["role"], "content": msg["content"]})

    # Build current message content
    content_parts = []

    # Add image if provided
    if request.image_base64:
        content_parts.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": request.image_base64,
            },
        })

    content_parts.append({
        "type": "text",
        "text": f"{context_text}\n\nUSER REQUEST: {request.message}",
    })

    messages.append({"role": "user", "content": content_parts})

    # Call Claude
    try:
        client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4000,
            system=PRO_SYSTEM_PROMPT,
            messages=messages,
        )
        analysis_text = response.content[0].text
    except Exception as exc:
        logger.error("Claude API error: %s", exc)
        raise HTTPException(status_code=502, detail=f"AI service error: {exc}") from exc

    recommendation = _extract_recommendation(analysis_text)

    return ProAnalysisResponse(
        analysis=analysis_text,
        recommendation=recommendation,
        market_data=ctx,
        probability=ctx.get("probability", {}),
    )
