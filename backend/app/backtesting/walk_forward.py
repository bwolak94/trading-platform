"""Walk-Forward Backtester — rolling train/test window evaluation."""

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

from app.ai.regime.classifier import RegimeClassifier
from app.ai.strategies.base import BaseStrategy, MarketContext, SignalResult
from app.data.processors.feature_engineer import compute_features

logger = logging.getLogger(__name__)


def calculate_overfitting_score(is_sharpe: float, oos_sharpe: float) -> float:
    """Compare in-sample vs out-of-sample Sharpe ratio.

    Returns 0.0 (no overfitting) to 1.0 (severe overfitting).
    Negative OOS Sharpe with positive IS = near 1.0.
    """
    if is_sharpe <= 0:
        return 0.0
    if oos_sharpe <= 0:
        return 1.0
    ratio = oos_sharpe / is_sharpe
    return round(max(0.0, min(1.0, 1.0 - ratio)), 3)


def calculate_sortino_ratio(
    returns: list[float],
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252,
) -> float:
    """Sortino ratio — only penalizes downside deviation."""
    if not returns or len(returns) < 2:
        return 0.0
    arr = np.array(returns)
    excess = arr - risk_free_rate / periods_per_year
    downside = excess[excess < 0]
    if len(downside) == 0:
        return 10.0  # No downside = very high
    downside_std = float(np.std(downside)) * np.sqrt(periods_per_year)
    if downside_std == 0:
        return 0.0
    mean_excess = float(np.mean(excess)) * periods_per_year
    return round(mean_excess / downside_std, 3)


@dataclass
class Trade:
    """Represents a single completed trade from backtesting."""

    asset: str
    direction: str
    entry_price: float
    exit_price: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    entry_date: date
    exit_date: date
    pnl_pct: float
    result: str  # "TP1_HIT", "TP2_HIT", "SL_HIT"
    strategy_name: str


@dataclass
class Metrics:
    """Performance metrics from a set of trades."""

    total_trades: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    calmar_ratio: float = 0.0
    avg_win_pct: float = 0.0
    avg_loss_pct: float = 0.0
    total_return_pct: float = 0.0


@dataclass
class BacktestResult:
    """Full result of a walk-forward backtest run."""

    strategy_name: str
    asset: str
    timeframe: str
    period_start: date
    period_end: date
    metrics: Metrics
    trades: list[Trade] = field(default_factory=list)
    equity_curve: list[dict[str, Any]] = field(default_factory=list)
    window_results: list[dict[str, Any]] = field(default_factory=list)


class WalkForwardBacktester:
    """Walk-forward backtester with rolling train/test windows."""

    def run(
        self,
        strategy: BaseStrategy,
        market_data: pd.DataFrame,
        asset: str,
        timeframe: str,
        start_date: date,
        end_date: date,
        train_window_months: int = 6,
        test_window_months: int = 1,
        initial_capital: float = 10000.0,
        risk_per_trade_pct: float = 1.5,
    ) -> BacktestResult:
        """Run a walk-forward backtest.

        Splits data into rolling train/test windows. For each window:
        1. Train regime classifier on train data
        2. Generate signals on test data
        3. Simulate trades and collect metrics
        """
        df = self._prepare_data(market_data, start_date, end_date)
        if df.empty:
            logger.warning("No data available for backtest")
            return self._empty_result(strategy.name, asset, timeframe, start_date, end_date)

        classifier = RegimeClassifier()
        all_trades: list[Trade] = []
        window_results: list[dict[str, Any]] = []

        current_start = start_date
        train_delta = timedelta(days=train_window_months * 30)
        test_delta = timedelta(days=test_window_months * 30)

        window_num = 0
        while current_start + train_delta + test_delta <= end_date:
            train_end = current_start + train_delta
            test_start = train_end
            test_end = test_start + test_delta

            train_data = self._filter_dates(df, current_start, train_end)
            test_data = self._filter_dates(df, test_start, test_end)

            if train_data.empty or test_data.empty:
                current_start += test_delta
                continue

            # Train classifier on train window
            try:
                classifier.train(train_data)
            except Exception as exc:
                logger.warning("Classifier training failed on window %d: %s", window_num, exc)

            # Generate signals on test window
            window_trades = self._simulate_window(
                strategy, classifier, test_data, asset, timeframe, risk_per_trade_pct
            )
            all_trades.extend(window_trades)

            window_metrics = self.calculate_metrics(window_trades)
            window_results.append({
                "window": window_num,
                "train_start": str(current_start),
                "train_end": str(train_end),
                "test_start": str(test_start),
                "test_end": str(test_end),
                "trades": len(window_trades),
                "win_rate": window_metrics.win_rate,
            })

            current_start += test_delta
            window_num += 1

        # Calculate aggregate metrics
        metrics = self.calculate_metrics(all_trades)
        equity_curve = self._build_equity_curve(all_trades, initial_capital)

        logger.info(
            "Backtest complete: %s on %s %s | %d trades | WR=%.1f%% | MDD=%.1f%%",
            strategy.name, asset, timeframe, metrics.total_trades,
            metrics.win_rate, metrics.max_drawdown,
        )

        return BacktestResult(
            strategy_name=strategy.name,
            asset=asset,
            timeframe=timeframe,
            period_start=start_date,
            period_end=end_date,
            metrics=metrics,
            trades=all_trades,
            equity_curve=equity_curve,
            window_results=window_results,
        )

    def _prepare_data(
        self, df: pd.DataFrame, start_date: date, end_date: date
    ) -> pd.DataFrame:
        """Compute features and filter to date range."""
        if df.empty:
            return df

        df = compute_features(df)
        return self._filter_dates(df, start_date, end_date)

    def _filter_dates(
        self, df: pd.DataFrame, start: date, end: date
    ) -> pd.DataFrame:
        """Filter DataFrame by date range using the index or timestamp column."""
        if "timestamp" in df.columns:
            mask = (df["timestamp"].dt.date >= start) & (df["timestamp"].dt.date <= end)
            return df.loc[mask].copy()

        if isinstance(df.index, pd.DatetimeIndex):
            mask = (df.index.date >= start) & (df.index.date <= end)
            return df.loc[mask].copy()

        return df

    def _simulate_window(
        self,
        strategy: BaseStrategy,
        classifier: RegimeClassifier,
        test_data: pd.DataFrame,
        asset: str,
        timeframe: str,
        risk_per_trade_pct: float,
    ) -> list[Trade]:
        """Simulate trading on a test window using a sliding approach."""
        trades: list[Trade] = []
        min_lookback = 200

        if len(test_data) < min_lookback:
            return trades

        for i in range(min_lookback, len(test_data)):
            window = test_data.iloc[: i + 1]
            last = window.iloc[-1]

            regime = classifier.predict_df(window)
            context = MarketContext(
                regime=regime.regime,
                regime_confidence=regime.confidence,
            )

            try:
                signal = strategy.generate_signal(asset, timeframe, window, context)
            except Exception:
                continue

            if not signal:
                continue

            # Simulate trade outcome using future candles
            trade = self._resolve_trade(
                signal, test_data, i, asset, risk_per_trade_pct
            )
            if trade:
                trades.append(trade)

        return trades

    def _resolve_trade(
        self,
        signal: SignalResult,
        data: pd.DataFrame,
        entry_idx: int,
        asset: str,
        risk_pct: float,
    ) -> Trade | None:
        """Simulate a trade forward from entry to determine outcome."""
        entry = signal.entry_price
        sl = signal.stop_loss
        tp1 = signal.take_profit_1
        tp2 = signal.take_profit_2
        is_long = signal.direction == "LONG"

        entry_row = data.iloc[entry_idx]
        entry_date = self._row_date(entry_row)

        # Walk forward through subsequent candles
        max_bars = min(100, len(data) - entry_idx - 1)
        for j in range(1, max_bars + 1):
            bar = data.iloc[entry_idx + j]
            high = float(bar.get("high", 0))
            low = float(bar.get("low", 0))

            if is_long:
                if low <= sl:
                    pnl = (sl - entry) / entry * 100
                    return self._make_trade(signal, entry_date, bar, pnl, "SL_HIT")
                if high >= tp2:
                    pnl = (tp2 - entry) / entry * 100
                    return self._make_trade(signal, entry_date, bar, pnl, "TP2_HIT")
                if high >= tp1:
                    pnl = (tp1 - entry) / entry * 100
                    return self._make_trade(signal, entry_date, bar, pnl, "TP1_HIT")
            else:
                if high >= sl:
                    pnl = (entry - sl) / entry * 100
                    return self._make_trade(signal, entry_date, bar, pnl, "SL_HIT")
                if low <= tp2:
                    pnl = (entry - tp2) / entry * 100
                    return self._make_trade(signal, entry_date, bar, pnl, "TP2_HIT")
                if low <= tp1:
                    pnl = (entry - tp1) / entry * 100
                    return self._make_trade(signal, entry_date, bar, pnl, "TP1_HIT")

        return None  # No outcome within max_bars

    def _make_trade(
        self,
        signal: SignalResult,
        entry_date: date,
        exit_bar: pd.Series,
        pnl_pct: float,
        result: str,
    ) -> Trade:
        """Construct a Trade from signal and outcome."""
        return Trade(
            asset=signal.asset,
            direction=signal.direction,
            entry_price=signal.entry_price,
            exit_price=signal.stop_loss if result == "SL_HIT"
                else signal.take_profit_2 if result == "TP2_HIT"
                else signal.take_profit_1,
            stop_loss=signal.stop_loss,
            take_profit_1=signal.take_profit_1,
            take_profit_2=signal.take_profit_2,
            entry_date=entry_date,
            exit_date=self._row_date(exit_bar),
            pnl_pct=round(pnl_pct, 4),
            result=result,
            strategy_name=signal.strategy_name,
        )

    def _row_date(self, row: pd.Series) -> date:
        """Extract date from a row."""
        if "timestamp" in row.index:
            ts = row["timestamp"]
            if hasattr(ts, "date"):
                return ts.date()
        return date.today()

    def calculate_metrics(self, trades: list[Trade]) -> Metrics:
        """Calculate performance metrics from a list of completed trades."""
        if not trades:
            return Metrics()

        pnls = [t.pnl_pct for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]

        total = len(pnls)
        win_rate = (len(wins) / total) * 100 if total > 0 else 0
        avg_win = np.mean(wins) if wins else 0
        avg_loss = abs(np.mean(losses)) if losses else 0
        profit_factor = (sum(wins) / abs(sum(losses))) if losses and sum(losses) != 0 else float("inf")

        # Sharpe ratio (annualized, assuming daily returns)
        if len(pnls) > 1:
            pnl_arr = np.array(pnls)
            sharpe = (np.mean(pnl_arr) / np.std(pnl_arr)) * np.sqrt(252) if np.std(pnl_arr) > 0 else 0
        else:
            sharpe = 0

        # Max drawdown from cumulative returns
        cumulative = np.cumsum(pnls)
        peak = np.maximum.accumulate(cumulative)
        drawdowns = peak - cumulative
        max_dd = float(np.max(drawdowns)) if len(drawdowns) > 0 else 0

        # Calmar ratio
        total_return = sum(pnls)
        calmar = total_return / max_dd if max_dd > 0 else float("inf")

        return Metrics(
            total_trades=total,
            win_rate=round(win_rate, 2),
            profit_factor=round(profit_factor, 4),
            max_drawdown=round(max_dd, 2),
            sharpe_ratio=round(sharpe, 4),
            calmar_ratio=round(calmar, 4),
            avg_win_pct=round(avg_win, 4),
            avg_loss_pct=round(avg_loss, 4),
            total_return_pct=round(total_return, 4),
        )

    def _build_equity_curve(
        self, trades: list[Trade], initial_capital: float
    ) -> list[dict[str, Any]]:
        """Build equity curve from trade history."""
        curve = [{"date": str(trades[0].entry_date if trades else date.today()), "equity": initial_capital}]
        equity = initial_capital

        for trade in sorted(trades, key=lambda t: t.exit_date):
            pnl = equity * (trade.pnl_pct / 100)
            equity += pnl
            curve.append({
                "date": str(trade.exit_date),
                "equity": round(equity, 2),
            })

        return curve

    def _empty_result(
        self, strategy_name: str, asset: str, timeframe: str,
        start_date: date, end_date: date,
    ) -> BacktestResult:
        """Return an empty result when no data is available."""
        return BacktestResult(
            strategy_name=strategy_name,
            asset=asset,
            timeframe=timeframe,
            period_start=start_date,
            period_end=end_date,
            metrics=Metrics(),
        )
