"""On-demand market analysis — runs regime classifier + strategies on live data."""

import logging
from datetime import datetime, timezone

import httpx
import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from app.ai.regime.classifier import RegimeClassifier
from app.ai.strategies.base import MarketContext, SignalResult
from app.ai.strategies.mean_reversion import MeanReversionStrategy
from app.ai.strategies.smc_strategy import SMCStrategy
from app.ai.strategies.trend_following import TrendFollowingStrategy
from app.ai.strategies.trend_trader import TrendTraderStrategy
from app.ai.strategies.volume_breakout import VolumeBreakoutStrategy
from app.core.symbols import ALL_SYMBOLS, VALID_TIMEFRAMES
from app.data.processors.feature_engineer import compute_features

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analyze", tags=["analyze"])

VALID_ASSETS = set(ALL_SYMBOLS)

from app.ai.strategies.rsi_scalping import RSIScalpingStrategy

STRATEGIES = {
    "trend_following": TrendFollowingStrategy(),
    "mean_reversion": MeanReversionStrategy(),
    "smc": SMCStrategy(),
    "volume_breakout": VolumeBreakoutStrategy(),
    "rsi_scalping": RSIScalpingStrategy(),
    "trend_trader": TrendTraderStrategy(),
}

STRATEGY_DESCRIPTIONS = {
    "trend_following": "Detects strong trends using EMA alignment, ADX filter, and RSI pullbacks. Best in trending markets.",
    "mean_reversion": "Identifies oversold/overbought conditions using RSI divergence and Bollinger Bands. Best in consolidation.",
    "smc": "Smart Money Concepts — finds Order Blocks and Fair Value Gaps for institutional-level entries. Best in trends.",
    "volume_breakout": "Detects range breakouts confirmed by volume spikes. Works in all market conditions.",
    "rsi_scalping": "RSI + Stochastic + DMI Stochastic crossover scalping. BUY when DMI Stoch crosses above 10, SELL when crosses below 90. Works in all regimes.",
    "trend_trader": "Ichimoku Cloud + Fibonacci + S/R confluence strategy. Uses TK cross above/below cloud with Fib level and S/R support. Works in all regimes.",
}

SYMBOL_MAP = {
    "BTC/USDT": "BTCUSDT",
    "ETH/USDT": "ETHUSDT",
    "SOL/USDT": "SOLUSDT",
}

classifier = RegimeClassifier()


async def _fetch_binance_klines(symbol: str, interval: str, limit: int = 500) -> pd.DataFrame:
    """Fetch klines directly from Binance and return as DataFrame."""
    binance_symbol = SYMBOL_MAP.get(symbol, symbol.replace("/", ""))
    url = "https://api.binance.com/api/v3/klines"

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, params={"symbol": binance_symbol, "interval": interval, "limit": limit})
        resp.raise_for_status()
        raw = resp.json()

    rows = []
    for k in raw:
        rows.append({
            "timestamp": datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc),
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5]),
        })
    return pd.DataFrame(rows)


def _signal_to_dict(signal: SignalResult) -> dict:
    """Convert SignalResult to JSON-serializable dict."""
    return {
        "asset": signal.asset,
        "direction": signal.direction,
        "confidence": round(signal.confidence, 1),
        "entry_price": round(signal.entry_price, 2),
        "stop_loss": round(signal.stop_loss, 2),
        "take_profit_1": round(signal.take_profit_1, 2),
        "take_profit_2": round(signal.take_profit_2, 2),
        "risk_reward": round(signal.risk_reward, 2),
        "strategy_name": signal.strategy_name,
        "factors": signal.factors,
    }


def _build_suggested_setup(
    strategy_name: str, featured: pd.DataFrame, last: pd.Series, regime: str
) -> dict:
    """Build suggested entry/SL/TP levels for a strategy regardless of signal."""
    close = round(float(last.get("close", 0)), 2)
    atr = float(last.get("atr_14", 0))
    ema20 = float(last.get("ema_20", close))
    ema50 = float(last.get("ema_50", close))
    ema200 = float(last.get("ema_200", close))
    rsi = float(last.get("rsi_14", 50))
    adx = float(last.get("adx_14", 0))
    bb_upper = float(last.get("bb_upper", close + atr))
    bb_lower = float(last.get("bb_lower", close - atr))
    float(last.get("bb_middle", close))

    if atr <= 0:
        atr = close * 0.01

    # Determine bias based on strategy logic
    if strategy_name == "trend_following":
        if ema20 > ema50 > ema200:
            bias = "LONG"
            entry = round(ema20, 2)  # pullback to EMA20
            sl = round(min(ema50 - atr, float(last.get("low", close)) - atr * 0.5), 2)
            conditions_met = [
                ("EMA Alignment (20>50>200)", True),
                ("ADX > 25", adx > 25),
                ("RSI 45-70", 45 <= rsi <= 70),
                ("Pullback to EMA20", abs(close - ema20) / atr < 1.5),
                ("Volume > 1.2x avg", float(last.get("volume_vs_avg", 0)) > 1.2),
            ]
        elif ema20 < ema50 < ema200:
            bias = "SHORT"
            entry = round(ema20, 2)
            sl = round(max(ema50 + atr, float(last.get("high", close)) + atr * 0.5), 2)
            conditions_met = [
                ("EMA Alignment (20<50<200)", True),
                ("ADX > 25", adx > 25),
                ("RSI 30-55", 30 <= rsi <= 55),
                ("Pullback to EMA20", abs(close - ema20) / atr < 1.5),
                ("Volume > 1.2x avg", float(last.get("volume_vs_avg", 0)) > 1.2),
            ]
        else:
            bias = "LONG" if close > ema200 else "SHORT"
            entry = close
            sl = round(close - atr * 1.5, 2) if bias == "LONG" else round(close + atr * 1.5, 2)
            conditions_met = [
                ("EMA Alignment", False),
                ("ADX > 25", adx > 25),
                ("RSI in range", 30 <= rsi <= 70),
            ]

    elif strategy_name == "mean_reversion":
        if rsi < 40 or close < bb_lower * 1.02:
            bias = "LONG"
            entry = round(bb_lower, 2)
            sl = round(bb_lower - atr * 0.5, 2)
            conditions_met = [
                ("Price near lower BB", close <= bb_lower * 1.02),
                ("RSI < 35", rsi < 35),
                ("Bullish divergence", False),  # complex check
                ("Reversal candle", float(last.get("close", 0)) > float(last.get("open", 0))),
            ]
        else:
            bias = "SHORT"
            entry = round(bb_upper, 2)
            sl = round(bb_upper + atr * 0.5, 2)
            conditions_met = [
                ("Price near upper BB", close >= bb_upper * 0.98),
                ("RSI > 65", rsi > 65),
                ("Bearish divergence", False),
                ("Reversal candle", float(last.get("close", 0)) < float(last.get("open", 0))),
            ]

    elif strategy_name == "smc":
        from app.ai.strategies.smc_strategy import find_order_blocks
        obs = find_order_blocks(featured, lookback=30)
        bull_obs = [ob for ob in obs if ob["type"] == "bullish" and ob["mid"] < close]
        bear_obs = [ob for ob in obs if ob["type"] == "bearish" and ob["mid"] > close]

        if bull_obs:
            ob = bull_obs[-1]
            bias = "LONG"
            entry = round(ob["mid"], 2)
            sl = round(ob["low"] * 0.997, 2)
            conditions_met = [
                ("Bullish OB found", True),
                (f"OB at ${ob['low']:.0f}-${ob['high']:.0f}", True),
                ("Price retesting OB", ob["low"] <= close <= ob["high"]),
                ("No supply zone above", len(bear_obs) == 0 or (bear_obs[0]["low"] - close) / close > 0.03),
            ]
        elif bear_obs:
            ob = bear_obs[-1]
            bias = "SHORT"
            entry = round(ob["mid"], 2)
            sl = round(ob["high"] * 1.003, 2)
            conditions_met = [
                ("Bearish OB found", True),
                (f"OB at ${ob['low']:.0f}-${ob['high']:.0f}", True),
                ("Price retesting OB", ob["low"] <= close <= ob["high"]),
                ("No demand zone below", len(bull_obs) == 0 or (close - bull_obs[-1]["high"]) / close > 0.03),
            ]
        else:
            bias = "LONG" if close > ema200 else "SHORT"
            entry = close
            sl = round(close - atr * 1.5, 2) if bias == "LONG" else round(close + atr * 1.5, 2)
            conditions_met = [("No Order Blocks detected", False)]

    elif strategy_name == "volume_breakout":
        # Look for consolidation range
        recent = featured.tail(15)
        range_high = round(float(recent["high"].max()), 2)
        range_low = round(float(recent["low"].min()), 2)
        range_size = (range_high - range_low) / atr

        if close > (range_high + range_low) / 2:
            bias = "LONG"
            entry = round(range_high, 2)
            sl = round(range_low - atr, 2)
        else:
            bias = "SHORT"
            entry = round(range_low, 2)
            sl = round(range_high + atr, 2)

        conditions_met = [
            (f"Range: ${range_low:,.0f}-${range_high:,.0f}", True),
            ("Range < 2x ATR (tight)", range_size < 2),
            ("Volume spike > 2x", float(last.get("volume_vs_avg", 0)) > 2),
            ("Breakout candle", close > range_high or close < range_low),
        ]
    else:
        bias = "LONG"
        entry = close
        sl = round(close - atr * 1.5, 2)
        conditions_met = []

    # Calculate TP levels
    risk = abs(entry - sl)
    if risk <= 0:
        risk = atr

    if bias == "LONG":
        tp1 = round(entry + risk * 1.5, 2)
        tp2 = round(entry + risk * 3.0, 2)
        tp3 = round(entry + risk * 5.0, 2)
    else:
        tp1 = round(entry - risk * 1.5, 2)
        tp2 = round(entry - risk * 3.0, 2)
        tp3 = round(entry - risk * 5.0, 2)

    rr = round(abs(tp1 - entry) / risk, 1) if risk > 0 else 0

    # Readiness score (how many conditions are met)
    met_count = sum(1 for _, met in conditions_met if met)
    total_count = max(len(conditions_met), 1)
    readiness = round(met_count / total_count * 100)

    return {
        "bias": bias,
        "entry": entry,
        "stop_loss": sl,
        "take_profit_1": tp1,
        "take_profit_2": tp2,
        "take_profit_3": tp3,
        "risk_reward": rr,
        "risk_usd_per_unit": round(risk, 2),
        "readiness": readiness,
        "conditions": [{"label": label, "met": met} for label, met in conditions_met],
    }


@router.get("/run")
async def run_analysis(
    asset: str = Query(default="BTC/USDT", description="Trading pair"),
    timeframe: str = Query(default="4h", description="Timeframe"),
    strategy: str | None = Query(default=None, description="Specific strategy or null for all"),
) -> dict:
    """Run full market analysis on live Binance data.

    Returns regime classification, strategy signals, and market summary.
    """
    # Normalize asset: accept both "BTCUSDT" and "BTC/USDT" formats
    if asset not in VALID_ASSETS:
        _normalized = next((v for v in VALID_ASSETS if v.replace("/", "") == asset.upper()), None)
        if _normalized:
            asset = _normalized
        else:
            raise HTTPException(status_code=400, detail=f"Invalid asset. Valid: {sorted(VALID_ASSETS)}")
    if timeframe not in VALID_TIMEFRAMES:
        raise HTTPException(status_code=400, detail=f"Invalid timeframe. Valid: {sorted(VALID_TIMEFRAMES)}")

    # Fetch live data
    df = await _fetch_binance_klines(asset, timeframe, limit=500)
    if df.empty or len(df) < 50:
        return {"error": "Insufficient data", "asset": asset}

    # Compute features
    featured = compute_features(df)
    if featured.empty:
        return {"error": "Feature computation failed", "asset": asset}

    last = featured.iloc[-1]

    # Regime classification
    regime = classifier.predict_df(featured)

    # Build market context
    context = MarketContext(
        regime=regime.regime,
        regime_confidence=regime.confidence,
    )

    # Run strategies
    signals: list[dict] = []
    strategy_results: list[dict] = []

    strategies_to_run = {strategy: STRATEGIES[strategy]} if strategy and strategy in STRATEGIES else STRATEGIES

    for name, strat in strategies_to_run.items():
        compatible = strat.is_compatible(regime.regime)
        result_entry = {
            "name": name,
            "description": STRATEGY_DESCRIPTIONS.get(name, ""),
            "compatible_with_regime": compatible,
            "supported_regimes": strat.supported_regimes,
            "signal": None,
            "reason": None,
            "suggested_setup": None,
        }

        if not compatible:
            result_entry["reason"] = f"Not compatible with {regime.regime} regime"
        else:
            try:
                signal = strat.generate_signal(asset, timeframe, featured, context)
                if signal:
                    result_entry["signal"] = _signal_to_dict(signal)
                    signals.append(_signal_to_dict(signal))
                else:
                    result_entry["reason"] = "No signal — entry conditions not met"
            except Exception as exc:
                result_entry["reason"] = f"Error: {str(exc)}"
                logger.error("Strategy %s error: %s", name, exc)

        # Always provide a suggested setup with levels
        result_entry["suggested_setup"] = _build_suggested_setup(
            name, featured, last, regime.regime
        )

        strategy_results.append(result_entry)

    # Market summary
    summary = {
        "price": round(float(last.get("close", 0)), 2),
        "change_24h": round(float(last.get("close", 0)) - float(featured.iloc[0].get("close", 0)), 2) if len(featured) > 1 else 0,
        "rsi": round(float(last.get("rsi_14", 50)), 1),
        "adx": round(float(last.get("adx_14", 0)), 1),
        "atr": round(float(last.get("atr_14", 0)), 2),
        "atr_normalized": round(float(last.get("atr_normalized", 0)) * 100, 3),
        "ema_cross": int(last.get("ema_cross_signal", 0)),
        "bb_position": round(float(last.get("bb_position", 0.5)), 3),
        "volume_vs_avg": round(float(last.get("volume_vs_avg", 1)), 2),
    }

    return {
        "asset": asset,
        "timeframe": timeframe,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "regime": regime.to_dict(),
        "summary": summary,
        "strategies": strategy_results,
        "signals": signals,
    }


@router.get("/regimes")
async def get_live_regimes() -> list[dict]:
    """Get live regime classification for all supported assets."""
    results = []
    for asset in SYMBOL_MAP:
        try:
            df = await _fetch_binance_klines(asset, "4h", limit=300)
            if df.empty or len(df) < 50:
                continue
            featured = compute_features(df)
            if featured.empty:
                continue
            regime = classifier.predict_df(featured)
            last = featured.iloc[-1]
            results.append({
                "asset": asset,
                "regime": regime.regime,
                "confidence": round(regime.confidence, 1),
                "probabilities": regime.probabilities,
                "price": round(float(last.get("close", 0)), 2),
                "rsi": round(float(last.get("rsi_14", 50)), 1),
                "adx": round(float(last.get("adx_14", 0)), 1),
            })
        except Exception as exc:
            logger.error("Regime fetch failed for %s: %s", asset, exc)

    return results
