"""D6: XGBoost regime probability classifier.

Secondary regime classifier that outputs a probability vector for each regime
class using features derived from the last 20 candles.  Blends with the existing
rule-based classifier to produce a more robust regime estimate.

The model is loaded lazily on first call and gracefully degrades to returning
None if XGBoost is not installed or no trained model file exists.
"""

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.core.logging import get_logger

logger = get_logger(__name__)

MODEL_PATH = Path(__file__).parent.parent / "models" / "xgb_regime.json"
REGIME_CLASSES = ["TREND_BULL", "TREND_BEAR", "CONSOLIDATION", "HIGH_VOL_CHOPPY"]
FEATURE_WINDOW = 20


def _extract_features(df: pd.DataFrame, window: int = FEATURE_WINDOW) -> np.ndarray:
    """Extract a fixed-size feature vector from the last ``window`` candles.

    Features:
      - Return pct over window
      - Realised volatility (std of log returns)
      - Volume ratio (last candle vs window mean)
      - High-Low range ratio
      - Close position in range (close relative to high/low)
      - Trend strength proxy: abs(sum of returns) / sum(abs(returns))

    Args:
        df:     OHLCV DataFrame with columns open/high/low/close/volume.
        window: Number of trailing candles to use.

    Returns:
        1-D numpy array of shape (6,).
    """
    tail = df.tail(window + 1).copy()
    closes = tail["close"].values.astype(float)
    highs = tail["high"].values.astype(float)
    lows = tail["low"].values.astype(float)
    volumes = tail["volume"].values.astype(float)

    log_returns = np.diff(np.log(closes + 1e-9))
    ret_pct = (closes[-1] - closes[0]) / (closes[0] + 1e-9) * 100
    realised_vol = float(np.std(log_returns) * np.sqrt(252 * 24))  # annualised hourly vol
    vol_ratio = volumes[-1] / (np.mean(volumes[:-1]) + 1e-9)
    hl_range = np.mean((highs - lows) / (closes + 1e-9) * 100)
    last_close_pos = (closes[-1] - lows[-1]) / (highs[-1] - lows[-1] + 1e-9)
    abs_sum = np.sum(np.abs(log_returns)) + 1e-9
    trend_strength = abs(np.sum(log_returns)) / abs_sum

    return np.array([
        ret_pct,
        realised_vol,
        vol_ratio,
        hl_range,
        last_close_pos,
        trend_strength,
    ], dtype=np.float32)


class XGBRegimeClassifier:
    """XGBoost-based regime probability classifier.

    Lazily loads a pre-trained model from ``MODEL_PATH``.  If the model file
    does not exist (e.g. first run before training) the classifier returns None
    so callers can fall back to the rule-based classifier.

    Args:
        model_path: Override the default model file path.
    """

    def __init__(self, model_path: Path | None = None) -> None:
        self._model_path = model_path or MODEL_PATH
        self._model: Any = None
        self._available = False
        self._load_attempted = False

    def _try_load(self) -> None:
        """Attempt to load the XGBoost model on first call."""
        if self._load_attempted:
            return
        self._load_attempted = True

        if not self._model_path.exists():
            logger.info("XGBRegimeClassifier: no model at %s — using rule-based fallback", self._model_path)
            return

        try:
            import xgboost as xgb  # type: ignore

            self._model = xgb.XGBClassifier()
            self._model.load_model(str(self._model_path))
            self._available = True
            logger.info("XGBRegimeClassifier: model loaded from %s", self._model_path)
        except ImportError:
            logger.info("XGBRegimeClassifier: xgboost not installed — skipping")
        except Exception as exc:
            logger.warning("XGBRegimeClassifier: failed to load model: %s", exc)

    def predict_proba(self, df: pd.DataFrame) -> dict[str, float] | None:
        """Predict regime probabilities for the given OHLCV DataFrame.

        Args:
            df: OHLCV DataFrame with at least ``FEATURE_WINDOW + 1`` rows.

        Returns:
            Dict mapping regime label to probability (sums to 1.0), or None
            if the model is unavailable or the DataFrame is too short.
        """
        self._try_load()
        if not self._available:
            return None
        if len(df) < FEATURE_WINDOW + 1:
            return None

        features = _extract_features(df).reshape(1, -1)
        try:
            proba = self._model.predict_proba(features)[0]
            return {cls: round(float(p), 4) for cls, p in zip(REGIME_CLASSES, proba)}
        except Exception as exc:
            logger.warning("XGBRegimeClassifier.predict_proba failed: %s", exc)
            return None

    def predict(self, df: pd.DataFrame) -> str | None:
        """Return the most-probable regime label, or None if unavailable."""
        proba = self.predict_proba(df)
        if proba is None:
            return None
        return max(proba, key=lambda k: proba[k])


# Module-level singleton
_classifier: XGBRegimeClassifier | None = None


def get_xgb_classifier() -> XGBRegimeClassifier:
    """Return the module-level :class:`XGBRegimeClassifier` singleton."""
    global _classifier
    if _classifier is None:
        _classifier = XGBRegimeClassifier()
    return _classifier
