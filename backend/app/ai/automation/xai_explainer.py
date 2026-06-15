"""Explainable AI Signal Report — feature importance for trading signals.

Implements a simplified SHAP-like feature contribution analysis without
external dependencies. Uses weighted sensitivity analysis to determine
which input features drove the signal generation.
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

# Feature definitions: {name: {typical_bullish_range, typical_bearish_range, weight}}
SIGNAL_FEATURES: dict[str, dict[str, Any]] = {
    "rsi": {
        "bullish_zone": (0, 35),
        "bearish_zone": (65, 100),
        "neutral_zone": (40, 60),
        "weight": 0.18,
        "description": "RSI momentum indicator",
    },
    "macd": {
        "bullish_zone": (0.001, float("inf")),
        "bearish_zone": (float("-inf"), -0.001),
        "neutral_zone": (-0.001, 0.001),
        "weight": 0.15,
        "description": "MACD trend momentum",
    },
    "ema_trend": {
        "bullish_zone": (1, float("inf")),    # 1 = above EMA
        "bearish_zone": (float("-inf"), -1),  # -1 = below EMA
        "neutral_zone": (-0.5, 0.5),
        "weight": 0.20,
        "description": "Price vs EMA20 trend direction",
    },
    "volume_ratio": {
        "bullish_zone": (1.5, float("inf")),
        "bearish_zone": (float("-inf"), 0.7),
        "neutral_zone": (0.8, 1.3),
        "weight": 0.12,
        "description": "Volume vs average volume ratio",
    },
    "atr_pct": {
        "bullish_zone": (0, 1.5),   # low vol = good for trend trades
        "bearish_zone": (4, float("inf")),  # high vol = risky
        "neutral_zone": (1.5, 4),
        "weight": 0.10,
        "description": "ATR as % of price",
    },
    "regime": {
        "bullish_zone": (1, 1),  # encoded: 1=BULL
        "bearish_zone": (-1, -1),
        "neutral_zone": (0, 0),
        "weight": 0.15,
        "description": "Market regime classification",
    },
    "confluence_score": {
        "bullish_zone": (70, 100),
        "bearish_zone": (0, 30),
        "neutral_zone": (30, 70),
        "weight": 0.10,
        "description": "Multi-timeframe confluence score",
    },
}

_REGIME_ENCODING: dict[str, float] = {
    "TREND_BULL": 1.0,
    "TREND_BEAR": -1.0,
    "CONSOLIDATION": 0.0,
    "HIGH_VOL_CHOPPY": -0.5,
    "UNKNOWN": 0.0,
}


def compute_feature_importance(signal: dict[str, Any]) -> dict[str, Any]:
    """Compute feature importance for a signal using weighted contribution analysis.

    Args:
        signal: Signal dict with feature values

    Returns:
        {feature_importances, top_3_drivers, explanation, confidence_breakdown}
    """
    importances: list[dict[str, Any]] = []
    total_contribution = 0.0

    # Extract and encode feature values
    feature_values: dict[str, float] = {
        "rsi": float(signal.get("rsi", 50)),
        "macd": float(signal.get("macd", 0)),
        "ema_trend": float(signal.get("ema_signal", 0)),
        "volume_ratio": float(signal.get("volume_ratio", 1.0)),
        "atr_pct": float(signal.get("atr_pct", 2.0)),
        "regime": _REGIME_ENCODING.get(signal.get("regime", "UNKNOWN"), 0.0),
        "confluence_score": float(signal.get("confluence_score", 50)),
    }

    direction = signal.get("direction", "LONG")
    direction_sign = 1 if direction == "LONG" else -1

    for feat_name, feat_def in SIGNAL_FEATURES.items():
        value = feature_values.get(feat_name, 0.0)
        weight = feat_def["weight"]

        b_lo, b_hi = feat_def["bullish_zone"]
        bear_lo, bear_hi = feat_def["bearish_zone"]

        if b_lo <= value <= b_hi:
            raw_contribution = direction_sign * weight  # supports direction
            impact_direction = "POSITIVE"
        elif bear_lo <= value <= bear_hi:
            raw_contribution = -direction_sign * weight  # opposes direction
            impact_direction = "NEGATIVE"
        else:
            raw_contribution = 0.0
            impact_direction = "NEUTRAL"

        importances.append({
            "feature": feat_name,
            "value": value,
            "contribution": round(raw_contribution, 4),
            "direction": impact_direction,
            "weight": weight,
            "description": feat_def["description"],
        })
        total_contribution += abs(raw_contribution)

    # Normalize and rank
    importances.sort(key=lambda x: abs(x["contribution"]), reverse=True)
    for rank, item in enumerate(importances, 1):
        item["importance_rank"] = rank
        if total_contribution > 0:
            item["importance_pct"] = round(abs(item["contribution"]) / total_contribution * 100, 1)
        else:
            item["importance_pct"] = 0.0

    top_3 = [i["feature"] for i in importances[:3]]
    explanation = generate_signal_explanation(signal, importances)

    return {
        "feature_importances": importances,
        "top_3_drivers": top_3,
        "explanation": explanation,
        "confidence_breakdown": {
            feat["feature"]: feat["contribution"]
            for feat in importances
        },
    }


def generate_signal_explanation(
    signal: dict[str, Any],
    importances: list[dict[str, Any]] | None = None,
) -> str:
    """Generate a human-readable explanation of why a signal was generated.

    Args:
        signal: Signal dict
        importances: Pre-computed importance list (computed if None)

    Returns:
        Human-readable explanation string
    """
    if importances is None:
        report = compute_feature_importance(signal)
        importances = report["feature_importances"]

    direction = signal.get("direction", "LONG")
    strategy = signal.get("strategy", "unknown").replace("_", " ").title()
    confidence = signal.get("confidence", 0.5)

    top_3 = importances[:3]
    drivers = []
    for i, feat in enumerate(top_3, 1):
        impact = "high" if abs(feat["contribution"]) > 0.12 else ("medium" if abs(feat["contribution"]) > 0.06 else "low")
        drivers.append(f"({i}) {feat['feature'].replace('_', ' ')} = {feat['value']:.2f} [{impact} impact]")

    return (
        f"{direction} {strategy} signal (confidence: {confidence:.0%}). "
        f"Primary drivers: {', '.join(drivers)}."
    )


def get_shap_like_report(signal: dict[str, Any]) -> dict[str, Any]:
    """Full XAI report with feature importances and visualization-ready data.

    Args:
        signal: Signal dict

    Returns:
        Complete XAI report dict
    """
    importance_data = compute_feature_importance(signal)
    explanation = importance_data["explanation"]

    # Visualization data: sorted bars for a horizontal bar chart
    chart_data = [
        {
            "feature": item["feature"],
            "value": item["contribution"],
            "abs_value": abs(item["contribution"]),
            "color": "green" if item["contribution"] > 0 else ("red" if item["contribution"] < 0 else "gray"),
            "label": item["description"],
            "importance_pct": item["importance_pct"],
        }
        for item in importance_data["feature_importances"]
    ]

    return {
        **importance_data,
        "explanation": explanation,
        "chart_data": chart_data,
        "signal_summary": {
            "symbol": signal.get("symbol"),
            "direction": signal.get("direction"),
            "confidence": signal.get("confidence"),
            "strategy": signal.get("strategy"),
        },
    }
