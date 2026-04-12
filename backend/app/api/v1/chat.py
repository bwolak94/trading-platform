"""AI Trading Chat — RAG-powered chat with live market data context."""

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
from app.ai.strategies.base import MarketContext
from app.ai.strategies.mean_reversion import MeanReversionStrategy
from app.ai.strategies.smc_strategy import SMCStrategy, find_order_blocks, find_fair_value_gaps
from app.ai.strategies.trend_following import TrendFollowingStrategy
from app.ai.strategies.volume_breakout import VolumeBreakoutStrategy
from app.core.config import settings
from app.data.processors.feature_engineer import compute_features

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

SYMBOL_MAP = {"BTC/USDT": "BTCUSDT", "ETH/USDT": "ETHUSDT", "SOL/USDT": "SOLUSDT"}
STRATEGIES = {
    "trend_following": TrendFollowingStrategy(),
    "mean_reversion": MeanReversionStrategy(),
    "smc": SMCStrategy(),
    "volume_breakout": VolumeBreakoutStrategy(),
}
classifier = RegimeClassifier()

SYSTEM_PROMPT = """You are an expert crypto/forex trading analyst AI assistant. You have access to live market data, technical indicators, order flow analysis, and strategy signals.

Your role:
- Analyze markets and provide clear, actionable trading advice
- Always specify exact Entry, Stop Loss, and Take Profit levels
- Explain your reasoning with technical factors
- Warn about risks and never guarantee profits
- When suggesting trades, output a JSON block with chart annotations

When you recommend a trade, include this JSON block (the frontend will draw it on the chart):
```json
{"annotations": [
  {"type": "entry", "price": 71000, "label": "LONG Entry"},
  {"type": "stop_loss", "price": 69500, "label": "Stop Loss"},
  {"type": "take_profit", "price": 73000, "label": "Take Profit 1"},
  {"type": "take_profit", "price": 75000, "label": "Take Profit 2"}
]}
```

Always be specific with numbers. Use the live data provided to make your analysis current and accurate. Format your response with clear sections."""


class ChatRequest(BaseModel):
    """Chat message from the user."""
    message: str
    asset: str = "BTC/USDT"
    timeframe: str = "4h"
    history: list[dict[str, str]] = []


class ChatResponse(BaseModel):
    """Chat response with analysis and optional chart annotations."""
    message: str
    annotations: list[dict[str, Any]] = []
    market_context: dict[str, Any] = {}


async def _fetch_klines(symbol: str, interval: str, limit: int = 500) -> pd.DataFrame:
    """Fetch klines from Binance."""
    binance_sym = SYMBOL_MAP.get(symbol, symbol.replace("/", ""))
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get("https://api.binance.com/api/v3/klines",
                                params={"symbol": binance_sym, "interval": interval, "limit": limit})
        resp.raise_for_status()
        raw = resp.json()
    return pd.DataFrame([{
        "timestamp": datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc),
        "open": float(k[1]), "high": float(k[2]), "low": float(k[3]),
        "close": float(k[4]), "volume": float(k[5]),
    } for k in raw])


async def _fetch_recent_news(symbol: str) -> list[dict[str, str]]:
    """Fetch recent crypto news headlines from CoinGecko (free, no key needed)."""
    try:
        coin_map = {"BTC/USDT": "bitcoin", "ETH/USDT": "ethereum", "SOL/USDT": "solana"}
        coin = coin_map.get(symbol, "bitcoin")
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"https://api.coingecko.com/api/v3/coins/{coin}",
                                    params={"localization": "false", "tickers": "false",
                                            "market_data": "true", "community_data": "false",
                                            "developer_data": "false"})
            if resp.status_code == 200:
                data = resp.json()
                market = data.get("market_data", {})
                return [{
                    "source": "CoinGecko",
                    "price_change_24h": f"{market.get('price_change_percentage_24h', 0):.2f}%",
                    "price_change_7d": f"{market.get('price_change_percentage_7d', 0):.2f}%",
                    "price_change_30d": f"{market.get('price_change_percentage_30d', 0):.2f}%",
                    "market_cap_rank": str(data.get("market_cap_rank", "N/A")),
                    "sentiment_up": f"{data.get('sentiment_votes_up_percentage', 0):.0f}%",
                    "sentiment_down": f"{data.get('sentiment_votes_down_percentage', 0):.0f}%",
                }]
    except Exception as exc:
        logger.warning("News fetch failed: %s", exc)
    return []


def _build_market_context(df: pd.DataFrame, featured: pd.DataFrame, asset: str, timeframe: str) -> dict[str, Any]:
    """Build comprehensive market context for the LLM."""
    last = featured.iloc[-1]
    regime = classifier.predict_df(featured)

    # Order blocks & FVGs
    obs = find_order_blocks(featured, lookback=30)
    fvgs = find_fair_value_gaps(featured, lookback=30)

    # Run all strategies
    context = MarketContext(regime=regime.regime, regime_confidence=regime.confidence)
    strategy_signals = {}
    for name, strat in STRATEGIES.items():
        try:
            if strat.is_compatible(regime.regime):
                sig = strat.generate_signal(asset, timeframe, featured, context)
                if sig:
                    strategy_signals[name] = {
                        "direction": sig.direction, "confidence": round(sig.confidence, 1),
                        "entry": round(sig.entry_price, 2), "stop_loss": round(sig.stop_loss, 2),
                        "tp1": round(sig.take_profit_1, 2), "tp2": round(sig.take_profit_2, 2),
                        "risk_reward": round(sig.risk_reward, 2), "factors": sig.factors,
                    }
                else:
                    strategy_signals[name] = {"direction": "NONE", "reason": "conditions not met"}
            else:
                strategy_signals[name] = {"direction": "NONE", "reason": f"incompatible with {regime.regime}"}
        except Exception as exc:
            strategy_signals[name] = {"direction": "ERROR", "reason": str(exc)}

    # Recent price action (last 20 candles summary)
    recent = featured.tail(20)
    price_action = {
        "current_price": round(float(last["close"]), 2),
        "24h_high": round(float(recent["high"].max()), 2),
        "24h_low": round(float(recent["low"].min()), 2),
        "avg_volume_20": round(float(recent["volume"].mean()), 2),
        "last_volume": round(float(last["volume"]), 2),
        "volume_change": round(float(last.get("volume_vs_avg", 1)), 2),
    }

    # Key support/resistance from order blocks
    supports = [round(ob["low"], 2) for ob in obs if ob["type"] == "bullish"][-3:]
    resistances = [round(ob["high"], 2) for ob in obs if ob["type"] == "bearish"][-3:]

    return {
        "asset": asset,
        "timeframe": timeframe,
        "regime": regime.to_dict(),
        "indicators": {
            "rsi_14": round(float(last.get("rsi_14", 50)), 1),
            "adx_14": round(float(last.get("adx_14", 0)), 1),
            "macd": round(float(last.get("macd", 0)), 4),
            "macd_signal": round(float(last.get("macd_signal", 0)), 4),
            "macd_histogram": round(float(last.get("macd_diff", 0)), 4),
            "atr_14": round(float(last.get("atr_14", 0)), 2),
            "atr_pct": round(float(last.get("atr_normalized", 0)) * 100, 3),
            "bb_position": round(float(last.get("bb_position", 0.5)), 3),
            "bb_upper": round(float(last.get("bb_upper", 0)), 2),
            "bb_lower": round(float(last.get("bb_lower", 0)), 2),
            "ema_20": round(float(last.get("ema_20", 0)), 2),
            "ema_50": round(float(last.get("ema_50", 0)), 2),
            "ema_200": round(float(last.get("ema_200", 0)), 2),
            "ema_trend": int(last.get("ema_cross_signal", 0)),
            "volume_vs_avg": round(float(last.get("volume_vs_avg", 1)), 2),
        },
        "price_action": price_action,
        "order_blocks": {"bullish": obs[-5:] if obs else [], "count": len(obs)},
        "fair_value_gaps": {"list": fvgs[-5:] if fvgs else [], "count": len(fvgs)},
        "support_levels": supports,
        "resistance_levels": resistances,
        "strategy_signals": strategy_signals,
    }


def _extract_annotations(text: str) -> list[dict[str, Any]]:
    """Extract chart annotation JSON from LLM response."""
    annotations = []
    try:
        start = text.find('{"annotations"')
        if start == -1:
            start = text.find('"annotations"')
            if start != -1:
                start = text.rfind("{", 0, start)
        if start != -1:
            depth = 0
            end = start
            for i in range(start, len(text)):
                if text[i] == "{": depth += 1
                elif text[i] == "}": depth -= 1
                if depth == 0:
                    end = i + 1
                    break
            raw = text[start:end]
            parsed = json.loads(raw)
            annotations = parsed.get("annotations", [])
    except (json.JSONDecodeError, KeyError):
        pass
    return annotations


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """Process a chat message with full market context RAG."""
    if not settings.ANTHROPIC_API_KEY or settings.ANTHROPIC_API_KEY == "your_anthropic_api_key":
        raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY not configured. Add your key to .env file.")

    # Fetch live market data
    try:
        df = await _fetch_klines(request.asset, request.timeframe, 500)
        featured = compute_features(df)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch market data: {exc}") from exc

    # Build RAG context
    market_ctx = _build_market_context(df, featured, request.asset, request.timeframe)

    # Fetch news
    news = await _fetch_recent_news(request.asset)
    if news:
        market_ctx["news_sentiment"] = news

    # Build messages for Claude
    context_text = f"""LIVE MARKET DATA for {request.asset} ({request.timeframe}):
{json.dumps(market_ctx, indent=2, default=str)}"""

    messages: list[dict[str, str]] = []

    # Add conversation history
    for msg in request.history[-10:]:  # last 10 messages
        messages.append({"role": msg["role"], "content": msg["content"]})

    # Add current message with context
    user_content = f"""{context_text}

USER QUESTION: {request.message}"""
    messages.append({"role": "user", "content": user_content})

    # Call Claude
    try:
        client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            messages=messages,
        )
        reply = response.content[0].text
    except Exception as exc:
        logger.error("Claude API error: %s", exc)
        raise HTTPException(status_code=502, detail=f"AI service error: {exc}") from exc

    # Extract annotations for chart
    annotations = _extract_annotations(reply)

    return ChatResponse(
        message=reply,
        annotations=annotations,
        market_context={
            "regime": market_ctx["regime"],
            "price": market_ctx["price_action"]["current_price"],
            "rsi": market_ctx["indicators"]["rsi_14"],
            "adx": market_ctx["indicators"]["adx_14"],
        },
    )
