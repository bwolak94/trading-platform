"""Unit tests for new risk modules.

Covers: correlation_cap, daily_loss_limit, equity_curve_filter, vol_adaptive_sizing.
Each module is tested with at least one happy-path and one edge-case scenario.
"""

import pytest


# ---------------------------------------------------------------------------
# correlation_cap
# ---------------------------------------------------------------------------

class TestCorrelationCap:
    def test_allows_uncorrelated_signals(self):
        from app.ai.risk.correlation_cap import CorrelationCap

        cap = CorrelationCap(max_correlation=0.7, max_correlated_positions=2)
        # Two uncorrelated assets should both be allowed
        result_btc = cap.can_add_position("BTCUSDT", existing_positions=[])
        result_eth = cap.can_add_position("ETHUSDT", existing_positions=["BTCUSDT"])
        assert result_btc is True
        assert result_eth is True

    def test_blocks_highly_correlated_signals(self):
        from app.ai.risk.correlation_cap import CorrelationCap

        cap = CorrelationCap(max_correlation=0.7, max_correlated_positions=1)
        # With 1 BTC position already open, adding another BTC-correlated asset should be blocked
        result = cap.can_add_position(
            "BTCUSDT",
            existing_positions=["BTCUSDT"],
        )
        assert result is False

    def test_empty_positions_always_allowed(self):
        from app.ai.risk.correlation_cap import CorrelationCap

        cap = CorrelationCap(max_correlation=0.5, max_correlated_positions=1)
        assert cap.can_add_position("SOLUSDT", existing_positions=[]) is True


# ---------------------------------------------------------------------------
# daily_loss_limit
# ---------------------------------------------------------------------------

class TestDailyLossLimit:
    def test_within_limit_returns_true(self):
        from app.ai.risk.daily_loss_limit import DailyLossLimit

        limit = DailyLossLimit(max_daily_loss_pct=2.0)
        assert limit.can_trade(current_daily_loss_pct=1.5) is True

    def test_exceeds_limit_returns_false(self):
        from app.ai.risk.daily_loss_limit import DailyLossLimit

        limit = DailyLossLimit(max_daily_loss_pct=2.0)
        assert limit.can_trade(current_daily_loss_pct=2.5) is False

    def test_exactly_at_limit_returns_false(self):
        from app.ai.risk.daily_loss_limit import DailyLossLimit

        limit = DailyLossLimit(max_daily_loss_pct=2.0)
        assert limit.can_trade(current_daily_loss_pct=2.0) is False

    def test_zero_loss_always_allowed(self):
        from app.ai.risk.daily_loss_limit import DailyLossLimit

        limit = DailyLossLimit(max_daily_loss_pct=1.0)
        assert limit.can_trade(current_daily_loss_pct=0.0) is True


# ---------------------------------------------------------------------------
# equity_curve_filter
# ---------------------------------------------------------------------------

class TestEquityCurveFilter:
    def test_rising_curve_allows_trading(self):
        from app.ai.risk.equity_curve_filter import EquityCurveFilter

        f = EquityCurveFilter(lookback=5)
        # Steadily rising equity
        equity = [10000, 10100, 10200, 10300, 10400, 10500]
        assert f.can_trade(equity_curve=equity) is True

    def test_falling_curve_blocks_trading(self):
        from app.ai.risk.equity_curve_filter import EquityCurveFilter

        f = EquityCurveFilter(lookback=5)
        # Steadily falling equity — below moving average
        equity = [10000, 9900, 9800, 9700, 9600, 9500]
        assert f.can_trade(equity_curve=equity) is False

    def test_insufficient_data_allows_trading(self):
        from app.ai.risk.equity_curve_filter import EquityCurveFilter

        f = EquityCurveFilter(lookback=20)
        # Only 3 data points — not enough to filter
        assert f.can_trade(equity_curve=[10000, 10100, 10200]) is True


# ---------------------------------------------------------------------------
# vol_adaptive_sizing
# ---------------------------------------------------------------------------

class TestVolAdaptiveSizing:
    def test_high_vol_reduces_size(self):
        from app.ai.risk.vol_adaptive_sizing import VolAdaptiveSizing

        sizer = VolAdaptiveSizing(base_risk_pct=1.0, target_vol_pct=1.0)
        # Current volatility is 3× the target — size should be reduced
        size = sizer.adjusted_risk_pct(current_vol_pct=3.0)
        assert size < 1.0

    def test_low_vol_increases_size(self):
        from app.ai.risk.vol_adaptive_sizing import VolAdaptiveSizing

        sizer = VolAdaptiveSizing(base_risk_pct=1.0, target_vol_pct=1.0)
        # Current volatility is half the target — size should be increased
        size = sizer.adjusted_risk_pct(current_vol_pct=0.5)
        assert size > 1.0

    def test_at_target_vol_returns_base(self):
        from app.ai.risk.vol_adaptive_sizing import VolAdaptiveSizing

        sizer = VolAdaptiveSizing(base_risk_pct=1.5, target_vol_pct=1.0)
        size = sizer.adjusted_risk_pct(current_vol_pct=1.0)
        assert abs(size - 1.5) < 0.01

    def test_size_never_exceeds_cap(self):
        from app.ai.risk.vol_adaptive_sizing import VolAdaptiveSizing

        sizer = VolAdaptiveSizing(base_risk_pct=1.0, target_vol_pct=1.0, max_risk_pct=2.0)
        # Extremely low vol should be capped
        size = sizer.adjusted_risk_pct(current_vol_pct=0.01)
        assert size <= 2.0
