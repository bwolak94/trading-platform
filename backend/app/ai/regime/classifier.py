"""Market Regime Classifier — rule-based labeling + LightGBM model."""

import logging
import pickle
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

MODEL_DIR = Path(__file__).parent / "models"
MODEL_PATH = MODEL_DIR / "regime_classifier.pkl"

REGIMES = ["TREND_BULL", "TREND_BEAR", "CONSOLIDATION", "HIGH_VOL_CHOPPY"]

FEATURE_COLUMNS = [
    "adx_14",
    "ema_cross_signal",
    "price_vs_ema200",
    "slope_ema50",
    "atr_normalized",
    "bb_width",
    "hv_20",
    "volume_vs_avg",
    "obv_trend",
    "hh_hl_count",
    "lh_ll_count",
    "range_vs_atr",
]


class RegimePrediction:
    """Result of a regime classification."""

    def __init__(
        self,
        regime: str,
        confidence: float,
        probabilities: dict[str, float],
    ) -> None:
        self.regime = regime
        self.confidence = confidence
        self.probabilities = probabilities

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "regime": self.regime,
            "confidence": round(self.confidence, 2),
            "probabilities": {k: round(v, 4) for k, v in self.probabilities.items()},
        }


def label_regime(df: pd.DataFrame) -> pd.Series:
    """Rule-based regime labeling for training data bootstrap.

    Expects columns: adx_14, ema_cross_signal, price_vs_ema200,
                     atr_normalized, ema_20, ema_50, ema_200.
    """
    labels = pd.Series("CONSOLIDATION", index=df.index)

    # TREND_BULL: ADX > 25, bullish EMA alignment, price above EMA200
    bull_mask = (
        (df["adx_14"] > 25)
        & (df["ema_cross_signal"] == 1)
        & (df["price_vs_ema200"] > 0)
    )
    labels[bull_mask] = "TREND_BULL"

    # TREND_BEAR: ADX > 25, bearish EMA alignment, price below EMA200
    bear_mask = (
        (df["adx_14"] > 25)
        & (df["ema_cross_signal"] == -1)
        & (df["price_vs_ema200"] < 0)
    )
    labels[bear_mask] = "TREND_BEAR"

    # HIGH_VOL_CHOPPY: high volatility without direction
    choppy_mask = (df["atr_normalized"] > 0.03) & (df["adx_14"] < 25)
    # Only override if not already a trend
    choppy_only = choppy_mask & (labels == "CONSOLIDATION")
    labels[choppy_only] = "HIGH_VOL_CHOPPY"

    return labels


def compute_extra_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute additional features required by the classifier beyond feature_engineer output."""
    df = df.copy()

    # Slope of EMA50 over last 10 candles
    if "ema_50" in df.columns:
        df["slope_ema50"] = df["ema_50"].diff(10) / df["ema_50"].shift(10)
    else:
        df["slope_ema50"] = 0.0

    # OBV trend (slope over last 10 candles)
    if "obv" in df.columns:
        obv_diff = df["obv"].diff(10)
        obv_shifted = df["obv"].shift(10).replace(0, np.nan)
        df["obv_trend"] = obv_diff / obv_shifted
        df["obv_trend"] = df["obv_trend"].fillna(0.0)
    else:
        df["obv_trend"] = 0.0

    # Higher Highs / Higher Lows count over last 10 candles
    if "high" in df.columns and "low" in df.columns:
        df["hh_hl_count"] = _count_hh_hl(df["high"], df["low"], lookback=10)
        df["lh_ll_count"] = _count_lh_ll(df["high"], df["low"], lookback=10)
    else:
        df["hh_hl_count"] = 0
        df["lh_ll_count"] = 0

    # Daily range vs ATR
    if "high" in df.columns and "low" in df.columns and "atr_14" in df.columns:
        daily_range = df["high"] - df["low"]
        df["range_vs_atr"] = np.where(
            df["atr_14"] > 0, daily_range / df["atr_14"], 1.0
        )
    else:
        df["range_vs_atr"] = 1.0

    return df


def _count_hh_hl(high: pd.Series, low: pd.Series, lookback: int) -> pd.Series:
    """Count higher-highs and higher-lows in a rolling window."""
    counts = pd.Series(0, index=high.index)
    for i in range(1, lookback):
        counts += (high > high.shift(i)).astype(int)
        counts += (low > low.shift(i)).astype(int)
    return counts


def _count_lh_ll(high: pd.Series, low: pd.Series, lookback: int) -> pd.Series:
    """Count lower-highs and lower-lows in a rolling window."""
    counts = pd.Series(0, index=high.index)
    for i in range(1, lookback):
        counts += (high < high.shift(i)).astype(int)
        counts += (low < low.shift(i)).astype(int)
    return counts


class RegimeClassifier:
    """Market regime classifier with rule-based fallback and LightGBM model."""

    def __init__(self) -> None:
        self._model: lgb.LGBMClassifier | None = None
        self._load_model()

    def _load_model(self) -> None:
        """Load trained model from disk if available."""
        if MODEL_PATH.exists():
            with open(MODEL_PATH, "rb") as f:
                self._model = pickle.load(f)
            logger.info("Loaded regime classifier model from %s", MODEL_PATH)
        else:
            logger.warning("No trained model found, using rule-based fallback")

    def predict(self, features: dict[str, float]) -> RegimePrediction:
        """Predict market regime from a feature dict."""
        if self._model is not None:
            return self._predict_ml(features)
        return self._predict_rules(features)

    def predict_df(self, df: pd.DataFrame) -> RegimePrediction:
        """Predict from the last row of a feature DataFrame."""
        if df.empty:
            return RegimePrediction("CONSOLIDATION", 50.0, {r: 0.25 for r in REGIMES})

        df = compute_extra_features(df)
        last_row = df.iloc[-1]
        features = {col: float(last_row.get(col, 0)) for col in FEATURE_COLUMNS}
        return self.predict(features)

    def _predict_ml(self, features: dict[str, float]) -> RegimePrediction:
        """Predict using the trained LightGBM model."""
        feature_arr = np.array([[features.get(c, 0) for c in FEATURE_COLUMNS]])
        probas = self._model.predict_proba(feature_arr)[0]
        classes = self._model.classes_

        proba_dict = {str(cls): float(p) for cls, p in zip(classes, probas)}
        best_idx = int(np.argmax(probas))
        regime = str(classes[best_idx])
        confidence = float(probas[best_idx]) * 100

        return RegimePrediction(regime, confidence, proba_dict)

    def _predict_rules(self, features: dict[str, float]) -> RegimePrediction:
        """Rule-based fallback when no ML model is available."""
        adx = features.get("adx_14", 0)
        ema_signal = features.get("ema_cross_signal", 0)
        price_vs_ema = features.get("price_vs_ema200", 0)
        atr_norm = features.get("atr_normalized", 0)

        if adx > 25 and ema_signal == 1 and price_vs_ema > 0:
            regime = "TREND_BULL"
            confidence = min(60 + adx, 95)
        elif adx > 25 and ema_signal == -1 and price_vs_ema < 0:
            regime = "TREND_BEAR"
            confidence = min(60 + adx, 95)
        elif atr_norm > 0.03 and adx < 25:
            regime = "HIGH_VOL_CHOPPY"
            confidence = min(55 + atr_norm * 500, 90)
        else:
            regime = "CONSOLIDATION"
            confidence = max(50, 80 - adx)

        # Build approximate probability distribution
        probabilities = {r: 0.05 for r in REGIMES}
        probabilities[regime] = confidence / 100
        remaining = 1.0 - probabilities[regime]
        others = [r for r in REGIMES if r != regime]
        for r in others:
            probabilities[r] = remaining / len(others)

        return RegimePrediction(regime, confidence, probabilities)

    def train(self, df: pd.DataFrame) -> dict[str, Any]:
        """Train LightGBM classifier on labeled feature data.

        Expects a DataFrame with FEATURE_COLUMNS + label_regime() output.
        Returns training metrics.
        """
        df = compute_extra_features(df)
        labels = label_regime(df)

        available = [c for c in FEATURE_COLUMNS if c in df.columns]
        X = df[available].dropna()
        y = labels.loc[X.index]

        model = lgb.LGBMClassifier(
            n_estimators=300,
            learning_rate=0.05,
            num_leaves=31,
            class_weight="balanced",
            verbose=-1,
        )
        model.fit(X, y)

        self._model = model

        # Save model
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        with open(MODEL_PATH, "wb") as f:
            pickle.dump(model, f)

        # Compute training metrics
        predictions = model.predict(X)
        accuracy = float(np.mean(predictions == y))
        logger.info("Regime classifier trained: accuracy=%.3f on %d samples", accuracy, len(X))

        return {
            "accuracy": round(accuracy, 4),
            "samples": len(X),
            "class_distribution": y.value_counts().to_dict(),
            "model_path": str(MODEL_PATH),
        }
