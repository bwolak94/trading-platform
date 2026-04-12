"""On-demand market analysis — runs regime classifier + strategies on live data."""

import logging
from datetime import datetime, timedelta, timezone

import httpx
import pandas as pd
from fastapi import APIRouter, Query

from app.ai.regime.classifier import RegimeClassifier
from app.ai.strategies.base import MarketContext, SignalResult
from app.ai.strategies.mean_reversion import MeanReversionStrategy
from app.ai.strategies.smc_strategy import SMCStrategy
from app.ai.strategies.trend_following import TrendFollowingStrategy
from app.ai.strategies.volume_breakout import VolumeBreakoutStrategy
from app.data.processors.feature_engineer import compute_features

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analyze", tags=["analyze"])

STRATEGIES = {
    "trend_following": TrendFollowingStrategy(),
    "mean_reversion": MeanReversionStrategy(),
    "smc": SMCStrategy(),
    "volume_breakout": VolumeBreakoutStrategy(),
}

STRATEGY_DESCRIPTIONS = {
    "trend_following": "Detects strong trends using EMA alignment, ADX filter, and RSI pullbacks. Best in trending markets.",
    "mean_reversion": "Identifies oversold/overbought conditions using RSI divergence and Bollinger Bands. Best in consolidation.",
    "smc": "Smart Money Concepts — finds Order Blocks and Fair Value Gaps for institutional-level entries. Best in trends.",
    "volume_breakout": "Detects range breakouts confirmed by volume spikes. Works in all market conditions.",
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


@router.get("/run")
async def run_analysis(
    asset: str = Query(default="BTC/USDT", description="Trading pair"),
    timeframe: str = Query(default="4h", description="Timeframe"),
    strategy: str | None = Query(default=None, description="Specific strategy or null for all"),
) -> dict:
    """Run full market analysis on live Binance data.

    Returns regime classification, strategy signals, and market summary.
    """
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
