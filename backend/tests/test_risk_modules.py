"""Unit tests for risk modules.

Covers: correlation_cap, daily_loss_limit, equity_curve_filter, vol_adaptive_sizing.
Each module is tested with happy-path and edge-case scenarios using the current API.
"""

import asyncio
import numpy as np
import pytest


# ---------------------------------------------------------------------------
# correlation_cap
# ---------------------------------------------------------------------------

class TestCorrelationCap:
    def test_allows_uncorrelated_asset(self):
        from app.ai.risk.correlation_cap import CorrelationCap

        cap = CorrelationCap(max_correlated_exposure_pct=20.0, correlation_threshold=0.8)
        result = cap.check(
            new_asset="SOLUSDT",
            new_exposure_pct=5.0,
            open_positions={"XRPUSDT": 5.0},  # unrelated asset
            correlation_matrix={"SOLUSDT": {"XRPUSDT": 0.3}},
        )
        assert result.allowed is True

    def test_blocks_when_correlated_exposure_exceeds_max(self):
        from app.ai.risk.correlation_cap import CorrelationCap

        cap = CorrelationCap(max_correlated_exposure_pct=20.0, correlation_threshold=0.8)
        # BTC + ETH are both highly correlated with SOL; their combined exposure is 25%
        result = cap.check(
            new_asset="SOLUSDT",
            new_exposure_pct=5.0,
            open_positions={"BTCUSDT": 15.0, "ETHUSDT": 10.0},
            correlation_matrix={
                "SOLUSDT": {"BTCUSDT": 0.9, "ETHUSDT": 0.85},
            },
        )
        assert result.allowed is False

    def test_allows_when_correlated_exposure_under_max(self):
        from app.ai.risk.correlation_cap import CorrelationCap

        cap = CorrelationCap(max_correlated_exposure_pct=30.0)
        result = cap.check(
            new_asset="SOLUSDT",
            new_exposure_pct=5.0,
            open_positions={"BTCUSDT": 10.0},
            correlation_matrix={"SOLUSDT": {"BTCUSDT": 0.9}},
        )
        assert result.allowed is True

    def test_empty_positions_always_allowed(self):
        from app.ai.risk.correlation_cap import CorrelationCap

        cap = CorrelationCap(max_correlated_exposure_pct=20.0)
        result = cap.check(
            new_asset="BTCUSDT",
            new_exposure_pct=5.0,
            open_positions={},
            correlation_matrix={},
        )
        assert result.allowed is True

    def test_result_contains_correlated_assets_list(self):
        from app.ai.risk.correlation_cap import CorrelationCap

        cap = CorrelationCap(max_correlated_exposure_pct=20.0, correlation_threshold=0.8)
        result = cap.check(
            new_asset="SOLUSDT",
            new_exposure_pct=5.0,
            open_positions={"BTCUSDT": 15.0},
            correlation_matrix={"SOLUSDT": {"BTCUSDT": 0.9}},
        )
        assert "BTCUSDT" in result.correlated_assets

    def test_low_correlation_asset_not_counted(self):
        from app.ai.risk.correlation_cap import CorrelationCap

        # threshold=0.8, correlation=0.5 → should not be counted as correlated
        cap = CorrelationCap(max_correlated_exposure_pct=20.0, correlation_threshold=0.8)
        result = cap.check(
            new_asset="SOLUSDT",
            new_exposure_pct=5.0,
            open_positions={"BTCUSDT": 30.0},  # large exposure but low correlation
            correlation_matrix={"SOLUSDT": {"BTCUSDT": 0.5}},
        )
        assert result.allowed is True


# ---------------------------------------------------------------------------
# daily_loss_limit (DailyLossCircuitBreaker)
# ---------------------------------------------------------------------------

class TestDailyLossLimit:
    def test_initially_not_tripped(self):
        from app.ai.risk.daily_loss_limit import DailyLossCircuitBreaker

        breaker = DailyLossCircuitBreaker(threshold_pct=3.0)
        assert breaker.is_open is False

    def test_small_losses_do_not_trip_breaker(self):
        from app.ai.risk.daily_loss_limit import DailyLossCircuitBreaker

        breaker = DailyLossCircuitBreaker(threshold_pct=3.0)
        asyncio.run(breaker.record_loss(-1.0))
        asyncio.run(breaker.record_loss(-1.0))
        assert breaker.is_open is False

    def test_exceeding_threshold_trips_breaker(self):
        from app.ai.risk.daily_loss_limit import DailyLossCircuitBreaker

        breaker = DailyLossCircuitBreaker(threshold_pct=3.0)
        asyncio.run(breaker.record_loss(-2.0))
        asyncio.run(breaker.record_loss(-2.0))  # total loss = 4% > 3% threshold
        assert breaker.is_open is True

    def test_profits_do_not_reduce_loss_counter(self):
        """Profits should not offset recorded losses (loss counter is one-way)."""
        from app.ai.risk.daily_loss_limit import DailyLossCircuitBreaker

        breaker = DailyLossCircuitBreaker(threshold_pct=3.0)
        asyncio.run(breaker.record_loss(-2.5))
        asyncio.run(breaker.record_loss(5.0))   # profit — should not undo loss
        assert breaker.realised_loss_pct == pytest.approx(2.5)

    def test_zero_loss_always_allowed(self):
        from app.ai.risk.daily_loss_limit import DailyLossCircuitBreaker

        breaker = DailyLossCircuitBreaker(threshold_pct=1.0)
        asyncio.run(breaker.record_loss(0.0))
        assert breaker.is_open is False

    def test_status_returns_dict_with_expected_keys(self):
        from app.ai.risk.daily_loss_limit import DailyLossCircuitBreaker

        breaker = DailyLossCircuitBreaker(threshold_pct=3.0)
        status = breaker.status()
        assert "limit_hit" in status
        assert "realised_loss_pct" in status
        assert "threshold_pct" in status


# ---------------------------------------------------------------------------
# equity_curve_filter (standalone functions)
# ---------------------------------------------------------------------------

class TestEquityCurveFilter:
    def test_rising_curve_above_sma_returns_full_scale(self):
        from app.ai.risk.equity_curve_filter import get_equity_curve_scale

        # 21 points steadily rising — last point will be above SMA(20)
        equity = [10_000 + i * 100 for i in range(21)]
        assert get_equity_curve_scale(equity) == 1.0

    def test_falling_curve_below_sma_returns_half_scale(self):
        from app.ai.risk.equity_curve_filter import get_equity_curve_scale

        # 21 points steadily falling — last point will be below SMA(20)
        equity = [12_000 - i * 100 for i in range(21)]
        assert get_equity_curve_scale(equity) == 0.5

    def test_insufficient_data_returns_full_scale(self):
        from app.ai.risk.equity_curve_filter import get_equity_curve_scale

        # Only 3 points — not enough for SMA(20) → default to 1.0
        assert get_equity_curve_scale([10_000, 9_000, 8_000]) == 1.0

    def test_should_allow_new_signals_rising_curve(self):
        from app.ai.risk.equity_curve_filter import should_allow_new_signals

        equity = [10_000 + i * 100 for i in range(21)]
        assert should_allow_new_signals(equity) is True

    def test_should_allow_new_signals_falling_curve(self):
        """Even in a falling curve signals are allowed — only sizing is reduced."""
        from app.ai.risk.equity_curve_filter import should_allow_new_signals

        equity = [12_000 - i * 100 for i in range(21)]
        # scale = 0.5 > 0, so allow is still True
        assert should_allow_new_signals(equity) is True

    def test_single_value_returns_full_scale(self):
        from app.ai.risk.equity_curve_filter import get_equity_curve_scale

        assert get_equity_curve_scale([10_000]) == 1.0

    def test_scale_is_either_1_or_05(self):
        from app.ai.risk.equity_curve_filter import get_equity_curve_scale

        for equity in [
            [10_000 + i * 50 for i in range(25)],
            [12_000 - i * 50 for i in range(25)],
        ]:
            scale = get_equity_curve_scale(equity)
            assert scale in (0.5, 1.0)


# ---------------------------------------------------------------------------
# vol_adaptive_sizing (functional API)
# ---------------------------------------------------------------------------

def _make_price_series(n: int = 20, base: float = 30_000.0, vol: float = 200.0):
    rng = np.random.default_rng(0)
    closes = base + rng.normal(0, vol, n)
    closes = np.maximum(closes, 1.0)
    highs = closes * 1.005
    lows = closes * 0.995
    return list(highs), list(lows), list(closes)


class TestVolAdaptiveSizing:
    def test_high_vol_reduces_risk_pct(self):
        from app.ai.risk.vol_adaptive_sizing import vol_adaptive_risk_pct

        highs, lows, closes = _make_price_series(n=20, vol=600)  # high vol
        result = vol_adaptive_risk_pct(
            base_risk_pct=1.0, highs=highs, lows=lows, closes=closes,
            target_vol_pct=0.5,  # low target vs high actual → scale < 1
        )
        # adjusted_risk_pct should be at or below base due to high vol
        assert result.adjusted_risk_pct <= result.base_risk_pct or result.adjusted_risk_pct == result.base_risk_pct

    def test_low_vol_may_increase_risk_pct(self):
        from app.ai.risk.vol_adaptive_sizing import vol_adaptive_risk_pct

        # Very small price noise → low ATR
        highs, lows, closes = _make_price_series(n=20, vol=10)
        result = vol_adaptive_risk_pct(
            base_risk_pct=1.0, highs=highs, lows=lows, closes=closes,
            target_vol_pct=2.0,  # high target vs low actual → scale > 1
        )
        assert result.adjusted_risk_pct >= result.base_risk_pct

    def test_result_contains_expected_fields(self):
        from app.ai.risk.vol_adaptive_sizing import vol_adaptive_risk_pct

        highs, lows, closes = _make_price_series()
        result = vol_adaptive_risk_pct(
            base_risk_pct=1.0, highs=highs, lows=lows, closes=closes
        )
        assert hasattr(result, "adjusted_risk_pct")
        assert hasattr(result, "scale_factor")
        assert hasattr(result, "current_atr_pct")

    def test_size_is_clamped_to_max(self):
        from app.ai.risk.vol_adaptive_sizing import vol_adaptive_risk_pct, MAX_RISK_PCT

        # Extremely low vol should be capped at MAX_RISK_PCT
        highs, lows, closes = _make_price_series(n=20, vol=1)
        result = vol_adaptive_risk_pct(
            base_risk_pct=1.0, highs=highs, lows=lows, closes=closes,
            target_vol_pct=100.0,  # absurdly large target → would scale up massively
        )
        assert result.adjusted_risk_pct <= MAX_RISK_PCT

    def test_raises_on_insufficient_data(self):
        from app.ai.risk.vol_adaptive_sizing import vol_adaptive_risk_pct

        with pytest.raises(ValueError):
            vol_adaptive_risk_pct(
                base_risk_pct=1.0,
                highs=[30000.0] * 5,
                lows=[29900.0] * 5,
                closes=[30000.0] * 5,
                atr_period=14,
            )
