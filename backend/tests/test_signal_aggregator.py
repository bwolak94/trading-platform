"""Unit tests for calculate_final_score and apply_regime_weights.

The full SignalAggregator.aggregate() path requires a live feature DataFrame
and triggers many strategy imports — covered in test_strategies.py.
Here we focus on the pure helper functions that can be tested in isolation.
"""

import pytest

from app.ai.signals.aggregator import (
    WEIGHTS,
    calculate_final_score,
    apply_regime_weights,
)
from app.ai.strategies.base import SignalResult


# ── Fixtures ──────────────────────────────────────────────────────────────


def _make_signal(
    direction: str = "LONG",
    confidence: float = 70.0,
    strategy_name: str = "trend_following",
) -> SignalResult:
    """Build a minimal SignalResult for testing."""
    return SignalResult(
        asset="BTCUSDT",
        timeframe="1h",
        direction=direction,
        confidence=confidence,
        entry_price=65000.0,
        stop_loss=63000.0,
        take_profit_1=68000.0,
        take_profit_2=71000.0,
        risk_reward=1.5,
        strategy_name=strategy_name,
        factors=[],
    )


# ── calculate_final_score ─────────────────────────────────────────────────


class TestCalculateFinalScore:
    """calculate_final_score(components: dict[str, float]) → float in [0, 100]."""

    def test_all_positive_components_above_50(self):
        """All bullish components should push confidence above the neutral 50."""
        components = {"technical": 0.8, "onchain": 0.6, "sentiment": 0.7, "macro": 0.5}
        score = calculate_final_score(components)
        assert score > 50.0

    def test_all_negative_components_below_50(self):
        components = {"technical": -0.8, "onchain": -0.6, "sentiment": -0.7, "macro": -0.5}
        score = calculate_final_score(components)
        assert score < 50.0

    def test_neutral_components_return_exactly_50(self):
        components = {"technical": 0.0, "onchain": 0.0, "sentiment": 0.0, "macro": 0.0}
        score = calculate_final_score(components)
        assert score == 50.0

    def test_empty_components_return_50(self):
        """Missing keys default to 0.0 → neutral 50."""
        assert calculate_final_score({}) == 50.0

    def test_score_is_within_0_100_for_extreme_inputs(self):
        components = {"technical": 1.0, "onchain": 1.0, "sentiment": 1.0, "macro": 1.0}
        assert calculate_final_score(components) == 100.0

        components = {"technical": -1.0, "onchain": -1.0, "sentiment": -1.0, "macro": -1.0}
        assert calculate_final_score(components) == 0.0

    def test_result_is_rounded_to_two_decimals(self):
        components = {"technical": 0.333, "onchain": 0.0, "sentiment": 0.0, "macro": 0.0}
        score = calculate_final_score(components)
        # Should have at most 2 decimal places
        assert score == round(score, 2)

    def test_unknown_keys_are_ignored(self):
        """Extra keys not in WEIGHTS should have no effect."""
        base = {"technical": 0.5, "onchain": 0.0, "sentiment": 0.0, "macro": 0.0}
        with_extra = {**base, "unknown_source": 0.9999}
        assert calculate_final_score(base) == calculate_final_score(with_extra)

    def test_technical_has_highest_weight(self):
        """WEIGHTS["technical"] should be the largest single weight."""
        assert WEIGHTS["technical"] == max(WEIGHTS.values())

    def test_weights_sum_to_1(self):
        assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9


# ── apply_regime_weights ──────────────────────────────────────────────────


class TestApplyRegimeWeights:
    """apply_regime_weights scales signal confidence by regime-strategy multipliers."""

    def test_returns_list_of_same_length(self):
        signals = [_make_signal("LONG", 70, "trend_following")]
        result = apply_regime_weights(signals, "TREND_BULL")
        assert len(result) == len(signals)

    def test_trend_following_boosted_in_trend_bull(self):
        sig = _make_signal("LONG", 60.0, "trend_following")
        [boosted] = apply_regime_weights([sig], "TREND_BULL")
        assert boosted.confidence > sig.confidence

    def test_mean_reversion_penalized_in_trend_bull(self):
        sig = _make_signal("LONG", 60.0, "mean_reversion")
        [penalized] = apply_regime_weights([sig], "TREND_BULL")
        assert penalized.confidence < sig.confidence

    def test_mean_reversion_boosted_in_consolidation(self):
        sig = _make_signal("LONG", 60.0, "mean_reversion")
        [boosted] = apply_regime_weights([sig], "CONSOLIDATION")
        assert boosted.confidence > sig.confidence

    def test_confidence_clamped_to_100(self):
        sig = _make_signal("LONG", 99.0, "trend_following")
        [result] = apply_regime_weights([sig], "TREND_BULL")
        assert result.confidence <= 100.0

    def test_confidence_clamped_to_0(self):
        sig = _make_signal("LONG", 1.0, "trend_following")
        [result] = apply_regime_weights([sig], "HIGH_VOL_CHOPPY")
        assert result.confidence >= 0.0

    def test_empty_signals_list_returns_empty(self):
        result = apply_regime_weights([], "TREND_BULL")
        assert result == []

    def test_unknown_regime_returns_signals_unchanged(self):
        sig = _make_signal("LONG", 60.0, "trend_following")
        result = apply_regime_weights([sig], "UNKNOWN_REGIME")
        assert result[0].confidence == sig.confidence

    def test_unknown_strategy_name_returns_signal_unchanged(self):
        sig = _make_signal("SHORT", 55.0, "my_custom_strategy_xyz")
        [result] = apply_regime_weights([sig], "TREND_BULL")
        assert result.confidence == sig.confidence

    def test_original_signals_not_mutated(self):
        sig = _make_signal("LONG", 70.0, "trend_following")
        original_confidence = sig.confidence
        apply_regime_weights([sig], "TREND_BULL")
        assert sig.confidence == original_confidence

    def test_multiple_signals_processed_independently(self):
        signals = [
            _make_signal("LONG", 60.0, "trend_following"),
            _make_signal("SHORT", 55.0, "mean_reversion"),
        ]
        results = apply_regime_weights(signals, "TREND_BULL")
        # trend_following should be boosted more than mean_reversion (which is penalized)
        assert results[0].confidence > results[1].confidence
