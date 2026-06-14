"""Unit tests for RegimeClassifier — rule-based prediction and data validation.

The classifier has two paths:
1. _predict_rules(features: dict) — pure rule-based, no ML model required.
2. predict_df(df: pd.DataFrame) — end-to-end from raw OHLCV (uses rule-based
   fallback when no trained model is present, which is always true in CI).

Tests are designed to work without a trained LightGBM model on disk.
"""

import numpy as np
import pandas as pd
import pytest

from app.ai.regime.classifier import (
    FEATURE_COLUMNS,
    REGIMES,
    RegimeClassifier,
    RegimePrediction,
    compute_extra_features,
    label_regime,
)


# ── Feature fixtures ──────────────────────────────────────────────────────


def _feature_dict(
    adx: float = 30.0,
    ema_signal: float = 1.0,
    price_vs_ema200: float = 0.05,
    atr_norm: float = 0.01,
) -> dict[str, float]:
    """Build a minimal feature dict for classifier input."""
    return {
        "adx_14": adx,
        "ema_cross_signal": ema_signal,
        "price_vs_ema200": price_vs_ema200,
        "slope_ema50": 0.001,
        "atr_normalized": atr_norm,
        "bb_width": 0.02,
        "hv_20": 0.15,
        "volume_vs_avg": 1.2,
        "obv_trend": 0.01,
        "hh_hl_count": 5,
        "lh_ll_count": 2,
        "range_vs_atr": 1.0,
    }


def _feature_df(n: int = 200, trend: str = "bull") -> pd.DataFrame:
    """Build a feature DataFrame with the columns that label_regime expects."""
    rng = np.random.default_rng(42)

    if trend == "bull":
        closes = 30_000 + np.arange(n) * 25 + rng.normal(0, 50, n)
        adx = np.clip(rng.normal(35, 5, n), 0, 100)
        ema_signal = np.ones(n)
        price_vs_ema200 = np.full(n, 0.05)
        atr_norm = np.full(n, 0.01)
    elif trend == "bear":
        closes = 30_000 - np.arange(n) * 25 + rng.normal(0, 50, n)
        adx = np.clip(rng.normal(35, 5, n), 0, 100)
        ema_signal = np.full(n, -1.0)
        price_vs_ema200 = np.full(n, -0.05)
        atr_norm = np.full(n, 0.01)
    else:  # flat
        closes = 30_000 + rng.normal(0, 50, n)
        adx = np.clip(rng.normal(15, 5, n), 0, 100)
        ema_signal = np.zeros(n)
        price_vs_ema200 = rng.normal(0, 0.005, n)
        atr_norm = np.full(n, 0.015)

    closes = np.maximum(closes, 1.0)
    highs = closes * 1.005
    lows = closes * 0.995
    opens = closes * (1 + rng.uniform(-0.002, 0.002, n))
    volumes = rng.uniform(100, 5000, n)

    ema20 = pd.Series(closes).ewm(span=20).mean().values
    ema50 = pd.Series(closes).ewm(span=50).mean().values
    ema200 = pd.Series(closes).ewm(span=200).mean().values
    atr_14 = (highs - lows) * 0.5  # simplified ATR proxy

    return pd.DataFrame(
        {
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes,
            "adx_14": adx,
            "ema_cross_signal": ema_signal,
            "price_vs_ema200": price_vs_ema200,
            "atr_normalized": atr_norm,
            "ema_20": ema20,
            "ema_50": ema50,
            "ema_200": ema200,
            "atr_14": atr_14,
            "bb_width": np.full(n, 0.02),
            "hv_20": np.full(n, 0.15),
            "volume_vs_avg": rng.uniform(0.8, 1.5, n),
            "obv": np.cumsum(volumes * np.sign(ema_signal)),
        }
    )


# ── RegimePrediction ──────────────────────────────────────────────────────


class TestRegimePrediction:
    def test_to_dict_contains_required_keys(self):
        pred = RegimePrediction(
            regime="TREND_BULL",
            confidence=85.0,
            probabilities={r: 0.25 for r in REGIMES},
        )
        d = pred.to_dict()
        assert set(d.keys()) >= {"regime", "confidence", "probabilities"}

    def test_confidence_is_rounded_to_two_decimals(self):
        pred = RegimePrediction("CONSOLIDATION", 77.777, {r: 0.25 for r in REGIMES})
        assert pred.to_dict()["confidence"] == 77.78

    def test_probabilities_are_rounded_to_four_decimals(self):
        probs = {
            "TREND_BULL": 0.123456,
            "TREND_BEAR": 0.600000,
            "CONSOLIDATION": 0.200000,
            "HIGH_VOL_CHOPPY": 0.076544,
        }
        pred = RegimePrediction("TREND_BEAR", 60.0, probs)
        for v in pred.to_dict()["probabilities"].values():
            decimal_places = len(str(v).rstrip("0").split(".")[-1]) if "." in str(v) else 0
            assert decimal_places <= 4

    def test_regime_attribute_is_correct(self):
        pred = RegimePrediction("HIGH_VOL_CHOPPY", 55.0, {r: 0.25 for r in REGIMES})
        assert pred.regime == "HIGH_VOL_CHOPPY"

    def test_confidence_attribute_is_correct(self):
        pred = RegimePrediction("CONSOLIDATION", 72.5, {r: 0.25 for r in REGIMES})
        assert pred.confidence == 72.5


# ── RegimeClassifier._predict_rules ──────────────────────────────────────


class TestRegimeClassifierRules:
    """Tests for the rule-based fallback (always used in CI without a model)."""

    def _clf(self) -> RegimeClassifier:
        return RegimeClassifier()

    def test_strong_bull_features_produce_trend_bull(self):
        clf = self._clf()
        features = _feature_dict(adx=40, ema_signal=1, price_vs_ema200=0.08, atr_norm=0.01)
        pred = clf._predict_rules(features)
        assert pred.regime == "TREND_BULL"

    def test_strong_bear_features_produce_trend_bear(self):
        clf = self._clf()
        features = _feature_dict(adx=40, ema_signal=-1, price_vs_ema200=-0.08, atr_norm=0.01)
        pred = clf._predict_rules(features)
        assert pred.regime == "TREND_BEAR"

    def test_low_adx_high_vol_produces_choppy(self):
        clf = self._clf()
        features = _feature_dict(adx=15, ema_signal=0, price_vs_ema200=0.0, atr_norm=0.05)
        pred = clf._predict_rules(features)
        assert pred.regime == "HIGH_VOL_CHOPPY"

    def test_low_adx_low_vol_produces_consolidation(self):
        clf = self._clf()
        features = _feature_dict(adx=10, ema_signal=0, price_vs_ema200=0.0, atr_norm=0.01)
        pred = clf._predict_rules(features)
        assert pred.regime == "CONSOLIDATION"

    def test_regime_is_known_value(self):
        clf = self._clf()
        for adx in (10, 25, 40):
            for ema_sig in (-1, 0, 1):
                pred = clf._predict_rules(
                    _feature_dict(adx=adx, ema_signal=ema_sig)
                )
                assert pred.regime in REGIMES

    def test_confidence_between_0_and_100(self):
        clf = self._clf()
        for adx in (5, 25, 50, 100):
            pred = clf._predict_rules(_feature_dict(adx=adx))
            assert 0.0 <= pred.confidence <= 100.0, (
                f"Confidence out of bounds for adx={adx}: {pred.confidence}"
            )

    def test_probabilities_cover_all_regimes(self):
        clf = self._clf()
        pred = clf._predict_rules(_feature_dict())
        assert set(pred.probabilities.keys()) == set(REGIMES)

    def test_probabilities_sum_approximately_to_1(self):
        clf = self._clf()
        pred = clf._predict_rules(_feature_dict(adx=35, ema_signal=1, price_vs_ema200=0.06))
        total = sum(pred.probabilities.values())
        assert abs(total - 1.0) < 0.02

    def test_predicted_regime_has_highest_probability(self):
        clf = self._clf()
        pred = clf._predict_rules(_feature_dict(adx=40, ema_signal=1, price_vs_ema200=0.08))
        top = max(pred.probabilities, key=pred.probabilities.__getitem__)
        assert pred.regime == top

    def test_empty_features_uses_defaults_and_does_not_crash(self):
        clf = self._clf()
        pred = clf._predict_rules({})
        assert pred.regime in REGIMES


# ── RegimeClassifier.predict_df ───────────────────────────────────────────


class TestRegimeClassifierPredictDf:
    """Tests for the end-to-end predict_df path."""

    def test_returns_regime_prediction(self):
        clf = RegimeClassifier()
        df = _feature_df(200, "bull")
        pred = clf.predict_df(df)
        assert isinstance(pred, RegimePrediction)

    def test_regime_is_known_value(self):
        clf = RegimeClassifier()
        for trend in ("bull", "bear", "flat"):
            pred = clf.predict_df(_feature_df(200, trend))
            assert pred.regime in REGIMES

    def test_confidence_in_bounds(self):
        clf = RegimeClassifier()
        pred = clf.predict_df(_feature_df(200, "bull"))
        assert 0.0 <= pred.confidence <= 100.0

    def test_empty_dataframe_returns_consolidation_fallback(self):
        clf = RegimeClassifier()
        pred = clf.predict_df(pd.DataFrame())
        assert pred.regime == "CONSOLIDATION"
        assert pred.confidence == 50.0


# ── label_regime ──────────────────────────────────────────────────────────


class TestLabelRegime:
    """Tests for the rule-based labeling function (uses pre-computed features)."""

    def test_returns_series_of_same_length(self):
        df = _feature_df(200, "bull")
        labels = label_regime(df)
        assert len(labels) == len(df)

    def test_labels_contain_only_known_regimes(self):
        df = _feature_df(200, "bull")
        labels = label_regime(df)
        unknown = set(labels.unique()) - set(REGIMES)
        assert not unknown

    def test_bull_df_produces_trend_bull_labels(self):
        df = _feature_df(200, "bull")
        labels = label_regime(df)
        assert (labels == "TREND_BULL").sum() > 50

    def test_bear_df_produces_trend_bear_labels(self):
        df = _feature_df(200, "bear")
        labels = label_regime(df)
        assert (labels == "TREND_BEAR").sum() > 50

    def test_flat_df_produces_consolidation_or_choppy(self):
        df = _feature_df(200, "flat")
        labels = label_regime(df)
        non_trend = labels.isin(["CONSOLIDATION", "HIGH_VOL_CHOPPY"])
        assert non_trend.sum() > 0


# ── compute_extra_features ────────────────────────────────────────────────


class TestComputeExtraFeatures:
    def test_adds_slope_ema50_column(self):
        df = _feature_df(200, "bull")
        out = compute_extra_features(df)
        assert "slope_ema50" in out.columns

    def test_adds_obv_trend_column(self):
        df = _feature_df(200, "bull")
        out = compute_extra_features(df)
        assert "obv_trend" in out.columns

    def test_adds_hh_hl_and_lh_ll_counts(self):
        df = _feature_df(200, "bull")
        out = compute_extra_features(df)
        assert "hh_hl_count" in out.columns
        assert "lh_ll_count" in out.columns

    def test_adds_range_vs_atr_column(self):
        df = _feature_df(200, "bull")
        out = compute_extra_features(df)
        assert "range_vs_atr" in out.columns

    def test_does_not_mutate_original_dataframe(self):
        df = _feature_df(200, "bull")
        original_cols = set(df.columns)
        compute_extra_features(df)
        assert set(df.columns) == original_cols
