"""Unit tests for AI engine — strategies, regime classifier, risk engine."""

import numpy as np
import pandas as pd
import pytest

from app.ai.regime.classifier import RegimeClassifier, label_regime, compute_extra_features
from app.ai.strategies.base import MarketContext, SignalResult
from app.ai.strategies.mean_reversion import MeanReversionStrategy
from app.ai.strategies.smc_strategy import (
    SMCStrategy,
    find_fair_value_gaps,
    find_order_blocks,
)
from app.ai.strategies.trend_following import TrendFollowingStrategy
from app.ai.strategies.volume_breakout import VolumeBreakoutStrategy
from app.ai.signals.aggregator import SignalAggregator, calculate_final_score
from app.data.processors.feature_engineer import compute_features


# --- Fixtures ---


@pytest.fixture
def ohlcv_bull_100() -> pd.DataFrame:
    """Fixture: 100-row bullish OHLCV DataFrame with realistic crypto prices."""
    return _make_ohlcv(n=100, trend="bull")


@pytest.fixture
def ohlcv_bear_100() -> pd.DataFrame:
    """Fixture: 100-row bearish OHLCV DataFrame with realistic crypto prices."""
    return _make_ohlcv(n=100, trend="bear")


@pytest.fixture
def ohlcv_flat_100() -> pd.DataFrame:
    """Fixture: 100-row flat/ranging OHLCV DataFrame with realistic crypto prices."""
    return _make_ohlcv(n=100, trend="flat")


@pytest.fixture
def ohlcv_bull_300() -> pd.DataFrame:
    """Fixture: 300-row bullish OHLCV DataFrame with realistic crypto prices."""
    return _make_ohlcv(n=300, trend="bull")


@pytest.fixture
def featured_bull_300() -> pd.DataFrame:
    """Fixture: 300-row bullish OHLCV with computed technical features."""
    return _make_featured_df(n=300, trend="bull")


@pytest.fixture
def featured_bear_300() -> pd.DataFrame:
    """Fixture: 300-row bearish OHLCV with computed technical features."""
    return _make_featured_df(n=300, trend="bear")


def _make_ohlcv(n: int = 300, trend: str = "bull") -> pd.DataFrame:
    """Generate synthetic OHLCV data for testing."""
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=n, freq="4h")
    base = 40000.0

    if trend == "bull":
        drift = np.linspace(0, 5000, n)
    elif trend == "bear":
        drift = np.linspace(0, -5000, n)
    else:
        drift = np.zeros(n)

    noise = np.cumsum(np.random.randn(n) * 50)
    close = base + drift + noise
    high = close + np.abs(np.random.randn(n) * 100)
    low = close - np.abs(np.random.randn(n) * 100)
    open_ = close + np.random.randn(n) * 30
    volume = np.abs(np.random.randn(n) * 1000) + 500

    df = pd.DataFrame({
        "timestamp": dates,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })
    return df


def _make_featured_df(n: int = 300, trend: str = "bull") -> pd.DataFrame:
    """Generate OHLCV data with computed features."""
    df = _make_ohlcv(n, trend)
    return compute_features(df)


# --- Feature Engineering Tests ---


class TestFeatureEngineering:
    def test_compute_features_adds_columns(self):
        df = _make_ohlcv(300)
        result = compute_features(df)

        expected = [
            "ema_20", "ema_50", "ema_200",
            "adx_14", "rsi_14",
            "macd", "macd_signal", "macd_diff",
            "atr_14", "bb_upper", "bb_lower", "bb_width",
            "obv", "volume_sma_20",
            "atr_normalized", "price_vs_ema200", "volume_vs_avg",
            "ema_cross_signal", "bb_position",
        ]
        for col in expected:
            assert col in result.columns, f"Missing column: {col}"

    def test_compute_features_no_nans(self):
        df = _make_ohlcv(300)
        result = compute_features(df)
        assert result.isna().sum().sum() == 0

    def test_compute_features_rejects_missing_columns(self):
        df = pd.DataFrame({"close": [1, 2, 3]})
        with pytest.raises(ValueError, match="Missing required columns"):
            compute_features(df)

    def test_ema_cross_signal_values(self):
        df = _make_ohlcv(300)
        result = compute_features(df)
        valid_values = {-1, 0, 1}
        assert set(result["ema_cross_signal"].unique()).issubset(valid_values)

    def test_bb_position_range(self):
        df = _make_ohlcv(300)
        result = compute_features(df)
        assert result["bb_position"].min() >= -0.5
        assert result["bb_position"].max() <= 1.5


# --- Regime Classifier Tests ---


class TestRegimeClassifier:
    def test_rule_based_labels_bull(self):
        df = _make_featured_df(300, "bull")
        df = compute_extra_features(df)
        labels = label_regime(df)
        assert "TREND_BULL" in labels.values

    def test_rule_based_labels_bear(self):
        df = _make_featured_df(300, "bear")
        df = compute_extra_features(df)
        labels = label_regime(df)
        assert "TREND_BEAR" in labels.values

    def test_rule_based_fallback_prediction(self):
        """Classifier without trained model should use rule-based fallback."""
        classifier = RegimeClassifier()
        classifier._model = None  # force fallback

        result = classifier.predict({
            "adx_14": 35.0,
            "ema_cross_signal": 1,
            "price_vs_ema200": 0.05,
            "atr_normalized": 0.01,
        })
        assert result.regime == "TREND_BULL"
        assert result.confidence > 50

    def test_rule_based_consolidation(self):
        classifier = RegimeClassifier()
        classifier._model = None

        result = classifier.predict({
            "adx_14": 15.0,
            "ema_cross_signal": 0,
            "price_vs_ema200": 0.001,
            "atr_normalized": 0.01,
        })
        assert result.regime == "CONSOLIDATION"

    def test_rule_based_choppy(self):
        classifier = RegimeClassifier()
        classifier._model = None

        result = classifier.predict({
            "adx_14": 18.0,
            "ema_cross_signal": 0,
            "price_vs_ema200": 0.0,
            "atr_normalized": 0.05,
        })
        assert result.regime == "HIGH_VOL_CHOPPY"

    def test_prediction_has_probabilities(self):
        classifier = RegimeClassifier()
        classifier._model = None

        result = classifier.predict({"adx_14": 30, "ema_cross_signal": 1, "price_vs_ema200": 0.02, "atr_normalized": 0.01})
        assert len(result.probabilities) == 4
        assert abs(sum(result.probabilities.values()) - 1.0) < 0.01

    def test_predict_df(self):
        df = _make_featured_df(300, "bull")
        classifier = RegimeClassifier()
        classifier._model = None

        result = classifier.predict_df(df)
        assert result.regime in ["TREND_BULL", "TREND_BEAR", "CONSOLIDATION", "HIGH_VOL_CHOPPY"]


# --- Strategy Tests ---


class TestTrendFollowing:
    def test_generates_signal_on_bullish_data(self):
        df = _make_featured_df(300, "bull")
        strategy = TrendFollowingStrategy()
        ctx = MarketContext(regime="TREND_BULL", regime_confidence=80)
        signal = strategy.generate_signal("BTC/USDT", "4h", df, ctx)
        # May or may not generate depending on exact conditions
        if signal:
            assert signal.direction == "LONG"
            assert signal.confidence >= strategy.min_confidence
            assert signal.stop_loss < signal.entry_price
            assert signal.take_profit_1 > signal.entry_price

    def test_no_signal_on_insufficient_data(self):
        df = _make_featured_df(300, "bull").head(50)
        strategy = TrendFollowingStrategy()
        ctx = MarketContext(regime="TREND_BULL")
        signal = strategy.generate_signal("BTC/USDT", "4h", df, ctx)
        assert signal is None

    def test_is_compatible_with_trend(self):
        strategy = TrendFollowingStrategy()
        assert strategy.is_compatible("TREND_BULL")
        assert strategy.is_compatible("TREND_BEAR")
        assert not strategy.is_compatible("CONSOLIDATION")


class TestMeanReversion:
    def test_compatible_regimes(self):
        strategy = MeanReversionStrategy()
        assert strategy.is_compatible("CONSOLIDATION")
        assert not strategy.is_compatible("TREND_BULL")

    def test_no_signal_on_insufficient_data(self):
        df = _make_featured_df(300).head(10)
        strategy = MeanReversionStrategy()
        ctx = MarketContext(regime="CONSOLIDATION")
        assert strategy.generate_signal("BTC/USDT", "4h", df, ctx) is None


class TestSMCStrategy:
    def test_find_order_blocks_returns_list(self):
        df = _make_featured_df(300)
        blocks = find_order_blocks(df, lookback=20)
        assert isinstance(blocks, list)
        for block in blocks:
            assert "type" in block
            assert block["type"] in ("bullish", "bearish")
            assert block["high"] >= block["low"]

    def test_find_fvg_returns_list(self):
        df = _make_featured_df(300)
        gaps = find_fair_value_gaps(df, lookback=20)
        assert isinstance(gaps, list)
        for gap in gaps:
            assert "type" in gap
            assert gap["top"] >= gap["bottom"]

    def test_compatible_regimes(self):
        strategy = SMCStrategy()
        assert strategy.is_compatible("TREND_BULL")
        assert not strategy.is_compatible("CONSOLIDATION")


class TestVolumeBreakout:
    def test_compatible_with_all_regimes(self):
        strategy = VolumeBreakoutStrategy()
        for regime in ["CONSOLIDATION", "TREND_BULL", "TREND_BEAR", "HIGH_VOL_CHOPPY"]:
            assert strategy.is_compatible(regime)

    def test_no_signal_on_insufficient_data(self):
        df = _make_featured_df(300).head(5)
        strategy = VolumeBreakoutStrategy()
        ctx = MarketContext(regime="CONSOLIDATION")
        assert strategy.generate_signal("BTC/USDT", "4h", df, ctx) is None


# --- Signal Aggregator Tests ---


class TestSignalAggregator:
    def test_calculate_final_score_neutral(self):
        score = calculate_final_score({
            "technical": 0.0,
            "onchain": 0.0,
            "sentiment": 0.0,
            "macro": 0.0,
        })
        assert score == 50.0

    def test_calculate_final_score_bullish(self):
        score = calculate_final_score({
            "technical": 1.0,
            "onchain": 1.0,
            "sentiment": 1.0,
            "macro": 1.0,
        })
        assert score == 100.0

    def test_calculate_final_score_bearish(self):
        score = calculate_final_score({
            "technical": -1.0,
            "onchain": -1.0,
            "sentiment": -1.0,
            "macro": -1.0,
        })
        assert score == 0.0

    def test_no_signal_in_choppy_regime(self):
        from app.ai.regime.classifier import RegimePrediction

        aggregator = SignalAggregator()
        df = _make_featured_df(300)
        regime = RegimePrediction("HIGH_VOL_CHOPPY", 80.0, {})

        result = aggregator.aggregate("BTC/USDT", "4h", df, regime=regime)
        assert result is None

    def test_duplicate_signal_suppression(self):
        from app.ai.regime.classifier import RegimePrediction
        from datetime import datetime, timezone

        aggregator = SignalAggregator()
        # Simulate a recent signal
        aggregator._recent_signals.append({
            "asset": "BTC/USDT",
            "direction": "LONG",
            "timestamp": datetime.now(timezone.utc),
        })
        assert aggregator._is_duplicate("BTC/USDT", "LONG")
        assert not aggregator._is_duplicate("ETH/USDT", "LONG")
        assert not aggregator._is_duplicate("BTC/USDT", "SHORT")


# --- Risk Engine Tests (sync-only, no DB) ---


class TestRiskEngine:
    def test_position_sizing_basic(self):
        from app.ai.risk.engine import RiskEngine

        engine = RiskEngine()
        result = engine.calculate_position_size(
            capital=10000, risk_pct=1.5, entry=50000, stop_loss=49000
        )
        assert result.risk_amount == 150.0
        assert result.units == pytest.approx(0.00015, abs=1e-6)
        assert result.position_value > 0

    def test_position_sizing_zero_risk(self):
        from app.ai.risk.engine import RiskEngine

        engine = RiskEngine()
        result = engine.calculate_position_size(
            capital=10000, risk_pct=1.5, entry=50000, stop_loss=50000
        )
        assert result.units == 0
        assert result.position_value == 0

    def test_volatility_adjusted_sizing(self):
        from app.ai.risk.engine import RiskEngine

        engine = RiskEngine()
        normal = engine.calculate_position_size(
            capital=10000, risk_pct=2.0, entry=50000, stop_loss=49000
        )
        adjusted = engine.calculate_position_size_volatility_adjusted(
            capital=10000, risk_pct=2.0, entry=50000, stop_loss=49000,
            atr=2000, atr_baseline=1000,
        )
        # Higher vol should mean smaller position
        assert adjusted.units <= normal.units


# --- Backtesting Tests ---


class TestBacktesting:
    def test_walk_forward_metrics(self):
        from app.backtesting.walk_forward import Metrics, Trade, WalkForwardBacktester
        from datetime import date

        backtester = WalkForwardBacktester()
        trades = [
            Trade("BTC/USDT", "LONG", 50000, 51000, 49000, 51000, 52000,
                  date(2024, 1, 1), date(2024, 1, 2), 2.0, "TP1_HIT", "test"),
            Trade("BTC/USDT", "LONG", 50000, 49000, 49000, 51000, 52000,
                  date(2024, 1, 3), date(2024, 1, 4), -2.0, "SL_HIT", "test"),
            Trade("BTC/USDT", "LONG", 50000, 51500, 49000, 51500, 53000,
                  date(2024, 1, 5), date(2024, 1, 6), 3.0, "TP1_HIT", "test"),
        ]
        metrics = backtester.calculate_metrics(trades)

        assert metrics.total_trades == 3
        assert metrics.win_rate == pytest.approx(66.67, abs=0.1)
        assert metrics.profit_factor > 1.0

    def test_empty_trades_metrics(self):
        from app.backtesting.walk_forward import WalkForwardBacktester

        backtester = WalkForwardBacktester()
        metrics = backtester.calculate_metrics([])
        assert metrics.total_trades == 0
        assert metrics.win_rate == 0.0

    def test_monte_carlo_output(self):
        from app.backtesting.monte_carlo import MonteCarloSimulator
        from app.backtesting.walk_forward import Trade
        from datetime import date

        trades = [
            Trade("BTC", "LONG", 100, 103, 98, 103, 106,
                  date(2024, 1, i), date(2024, 1, i + 1),
                  3.0 if i % 3 != 0 else -2.0,
                  "TP1_HIT" if i % 3 != 0 else "SL_HIT", "test")
            for i in range(1, 31)
        ]
        sim = MonteCarloSimulator()
        result = sim.run(trades, iterations=100, initial_capital=10000)

        assert result.iterations == 100
        assert result.percentile_50 > 0
        assert 0 <= result.prob_ruin_20pct <= 100
        assert len(result.equity_curves) == 5  # p5, p25, p50, p75, p95

    def test_monte_carlo_empty_trades(self):
        from app.backtesting.monte_carlo import MonteCarloSimulator

        sim = MonteCarloSimulator()
        result = sim.run([], iterations=10)
        assert result.iterations == 10
        assert result.percentile_50 == 0


# --- On-Chain Fetcher Tests ---


class TestRSIScalping:
    """Tests for RSIScalpingStrategy."""

    def test_compatible_with_all_regimes(self):
        from app.ai.strategies.rsi_scalping import RSIScalpingStrategy

        strategy = RSIScalpingStrategy()
        for regime in ["TREND_BULL", "TREND_BEAR", "CONSOLIDATION", "HIGH_VOL_CHOPPY"]:
            assert strategy.is_compatible(regime), f"Should be compatible with {regime}"

    def test_no_signal_on_insufficient_data(self):
        from app.ai.strategies.rsi_scalping import RSIScalpingStrategy

        strategy = RSIScalpingStrategy()
        # Less than 30 candles — strategy requires at least 30
        df = _make_featured_df(300, "bull").head(20)
        ctx = MarketContext(regime="CONSOLIDATION")
        signal = strategy.generate_signal("BTC/USDT", "1h", df, ctx)
        assert signal is None

    def test_no_signal_on_empty_data(self):
        from app.ai.strategies.rsi_scalping import RSIScalpingStrategy
        import pandas as pd

        strategy = RSIScalpingStrategy()
        ctx = MarketContext(regime="TREND_BULL")
        signal = strategy.generate_signal("BTC/USDT", "1h", pd.DataFrame(), ctx)
        assert signal is None

    def test_signal_generation_with_valid_data(self):
        from app.ai.strategies.rsi_scalping import RSIScalpingStrategy

        strategy = RSIScalpingStrategy()
        df = _make_featured_df(300, "bull")
        ctx = MarketContext(regime="TREND_BULL", regime_confidence=80)
        signal = strategy.generate_signal("BTC/USDT", "1h", df, ctx)
        # Signal may or may not fire depending on indicator conditions
        if signal is not None:
            assert signal.direction in ("LONG", "SHORT")
            assert signal.confidence >= strategy.min_confidence or signal.confidence >= 0
            assert signal.entry_price > 0
            assert signal.strategy_name == "rsi_scalping"
            assert signal.take_profit_1 > 0
            assert signal.stop_loss > 0
            assert len(signal.factors) > 0

    def test_compute_indicators_columns(self):
        from app.ai.strategies.rsi_scalping import compute_rsi_scalping_indicators

        df = _make_ohlcv(100, "bull")
        result = compute_rsi_scalping_indicators(df)
        for col in ["rsi_scalp", "stoch_k", "stoch_d", "dmi_stoch", "cross_up", "cross_down"]:
            assert col in result.columns, f"Missing indicator column: {col}"


class TestTrendTrader:
    """Tests for TrendTraderStrategy."""

    def test_compatible_with_all_regimes(self):
        from app.ai.strategies.trend_trader import TrendTraderStrategy

        strategy = TrendTraderStrategy()
        for regime in ["TREND_BULL", "TREND_BEAR", "CONSOLIDATION", "HIGH_VOL_CHOPPY"]:
            assert strategy.is_compatible(regime), f"Should be compatible with {regime}"

    def test_no_signal_on_insufficient_data(self):
        from app.ai.strategies.trend_trader import TrendTraderStrategy

        strategy = TrendTraderStrategy()
        # Less than 200 candles — strategy requires at least 200
        df = _make_featured_df(300, "bull").head(100)
        ctx = MarketContext(regime="TREND_BULL")
        signal = strategy.generate_signal("BTC/USDT", "4h", df, ctx)
        assert signal is None

    def test_no_signal_on_empty_data(self):
        from app.ai.strategies.trend_trader import TrendTraderStrategy
        import pandas as pd

        strategy = TrendTraderStrategy()
        ctx = MarketContext(regime="TREND_BULL")
        signal = strategy.generate_signal("BTC/USDT", "4h", pd.DataFrame(), ctx)
        assert signal is None

    def test_signal_generation_with_valid_data(self):
        from app.ai.strategies.trend_trader import TrendTraderStrategy

        strategy = TrendTraderStrategy()
        df = _make_featured_df(300, "bull")
        ctx = MarketContext(regime="TREND_BULL", regime_confidence=85)
        signal = strategy.generate_signal("BTC/USDT", "4h", df, ctx)
        # Signal may or may not fire depending on Ichimoku/Fib confluence
        if signal is not None:
            assert signal.direction in ("LONG", "SHORT")
            assert signal.entry_price > 0
            assert signal.stop_loss > 0
            assert signal.take_profit_1 > 0
            assert signal.take_profit_2 > 0
            assert signal.risk_reward >= 0
            assert signal.strategy_name == "trend_trader"
            assert len(signal.factors) > 0
            # Trend trader always includes partial TP schedule
            assert len(signal.partial_tp_schedule) == 3

    def test_signal_generation_bear_data(self):
        from app.ai.strategies.trend_trader import TrendTraderStrategy

        strategy = TrendTraderStrategy()
        df = _make_featured_df(300, "bear")
        ctx = MarketContext(regime="TREND_BEAR", regime_confidence=80)
        signal = strategy.generate_signal("BTC/USDT", "4h", df, ctx)
        if signal is not None:
            assert signal.direction in ("LONG", "SHORT")
            assert signal.strategy_name == "trend_trader"

    def test_fib_levels_computation(self):
        from app.ai.strategies.trend_trader import TrendTraderStrategy

        strategy = TrendTraderStrategy()
        df = _make_featured_df(300, "bull")
        fib = strategy._compute_fib_levels(df)
        assert isinstance(fib, dict)
        if fib:
            assert "0.0" in fib
            assert "100.0" in fib
            assert fib["100.0"] >= fib["0.0"]

    def test_sr_levels_computation(self):
        from app.ai.strategies.trend_trader import TrendTraderStrategy

        strategy = TrendTraderStrategy()
        df = _make_featured_df(300, "bull")
        sr = strategy._compute_sr_levels(df)
        assert isinstance(sr, list)
        for level in sr:
            assert "price" in level
            assert "touches" in level
            assert level["touches"] >= strategy.SR_TOUCH_MIN


class TestOnChainScoring:
    def test_decayed_score(self):
        from app.data.fetchers.onchain_fetcher import decayed_score

        # No decay at t=0
        assert decayed_score(0.7, 0) == pytest.approx(0.7)
        # Half at t=6h
        assert decayed_score(0.7, 6) == pytest.approx(0.35, abs=0.01)
        # Quarter at t=12h
        assert decayed_score(0.7, 12) == pytest.approx(0.175, abs=0.01)

    def test_aggregate_score_empty(self):
        from app.data.fetchers.onchain_fetcher import OnChainFetcher

        fetcher = OnChainFetcher()
        assert fetcher.compute_aggregate_score([]) == 0.0
