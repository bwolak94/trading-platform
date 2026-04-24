"""Strategy Parameter Optimizer — uses Optuna for hyperparameter tuning.

Finds optimal strategy parameters via Bayesian optimisation (TPE sampler) with
walk-forward OOS validation to guard against curve-fitting.

Key safeguards:
- Minimum out-of-sample Sharpe (MIN_OOS_SHARPE = 0.3): rejects fits that only
  work in-sample.
- Maximum overfitting score (MAX_OVERFITTING = 0.4): flags when in-sample
  performance greatly exceeds OOS.
- Parameter importance analysis via Optuna's built-in feature importance.

Graceful degradation: if ``optuna`` is not installed the module returns a
:class:`OptimizationResult` built from the strategy's default parameters so
the rest of the system continues to function.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import numpy as np

from app.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class OptimizationResult:
    """Result of parameter optimization."""

    strategy_name: str
    best_params: dict[str, Any]
    best_score: float           # Sharpe ratio or profit factor
    n_trials: int
    improvement_pct: float      # improvement vs default params
    is_valid: bool              # passes OOS validation
    oos_sharpe: float           # out-of-sample Sharpe
    is_sharpe: float            # in-sample Sharpe
    overfitting_score: float    # 0=no overfit, 1=severe overfit
    param_importance: dict[str, float]  # which params mattered most


@dataclass
class ParamSpace:
    """Definition of a single hyperparameter search space."""

    name: str
    param_type: str             # "int" | "float" | "categorical"
    low: Any = None
    high: Any = None
    choices: list = field(default_factory=list)
    log: bool = False           # log scale for float/int params


# ---------------------------------------------------------------------------
# Default parameter spaces
# ---------------------------------------------------------------------------

_PARAM_SPACES: dict[str, list[ParamSpace]] = {
    "trend_following": [
        ParamSpace("adx_threshold",       "float",       20.0, 35.0),
        ParamSpace("rsi_low",             "float",       35.0, 55.0),
        ParamSpace("rsi_high",            "float",       55.0, 75.0),
        ParamSpace("atr_sl_multiplier",   "float",        1.5,  3.0),
        ParamSpace("atr_tp1_multiplier",  "float",        1.0,  2.5),
        ParamSpace("volume_threshold",    "float",        1.0,  2.0),
        ParamSpace("ema_fast",            "int",           15,   30),
        ParamSpace("ema_slow",            "int",           40,   70),
    ],
    "mean_reversion": [
        ParamSpace("bb_window",           "int",           15,   30),
        ParamSpace("bb_std",              "float",        1.5,  2.5),
        ParamSpace("rsi_oversold",        "float",       20.0, 40.0),
        ParamSpace("rsi_overbought",      "float",       60.0, 80.0),
    ],
    "rsi_scalping": [
        ParamSpace("rsi_period",          "int",            7,   21),
        ParamSpace("rsi_entry_low",       "float",       25.0, 45.0),
        ParamSpace("rsi_entry_high",      "float",       55.0, 75.0),
        ParamSpace("atr_multiplier",      "float",        1.0,  2.5),
    ],
    "smc": [
        ParamSpace("swing_lookback",      "int",            5,   20),
        ParamSpace("fvg_min_size_atr",    "float",        0.3,  1.5),
        ParamSpace("ob_lookback",         "int",           10,   40),
        ParamSpace("confluences_required","int",            2,    4),
    ],
}

# Default parameter values for each strategy (used as baseline comparison)
_DEFAULT_PARAMS: dict[str, dict[str, Any]] = {
    "trend_following": {
        "adx_threshold": 25.0,
        "rsi_low": 45.0,
        "rsi_high": 65.0,
        "atr_sl_multiplier": 2.0,
        "atr_tp1_multiplier": 1.5,
        "volume_threshold": 1.3,
        "ema_fast": 21,
        "ema_slow": 50,
    },
    "mean_reversion": {
        "bb_window": 20,
        "bb_std": 2.0,
        "rsi_oversold": 30.0,
        "rsi_overbought": 70.0,
    },
    "rsi_scalping": {
        "rsi_period": 14,
        "rsi_entry_low": 35.0,
        "rsi_entry_high": 65.0,
        "atr_multiplier": 1.5,
    },
    "smc": {
        "swing_lookback": 10,
        "fvg_min_size_atr": 0.7,
        "ob_lookback": 20,
        "confluences_required": 3,
    },
}


# ---------------------------------------------------------------------------
# Simplified backtester for objective evaluation
# ---------------------------------------------------------------------------

def _simple_backtest(
    df: Any,
    strategy_name: str,
    params: dict[str, Any],
) -> dict[str, float]:
    """Run a rule-based simplified backtest on a price DataFrame.

    This is a lightweight proxy for a full backtest — it uses the parameter
    values to generate simulated signals based on indicator thresholds and
    computes Sharpe and profit factor from those simulated outcomes.

    Args:
        df: pandas DataFrame with at minimum ``close`` column.
        strategy_name: Strategy identifier.
        params: Parameter dict to test.

    Returns:
        Dict with keys: ``sharpe``, ``profit_factor``, ``win_rate``, ``n_trades``.
    """
    try:
        import pandas as pd

        close = df["close"].dropna().values.astype(float)
        if len(close) < 50:
            return {"sharpe": 0.0, "profit_factor": 1.0, "win_rate": 0.5, "n_trades": 0}

        # Compute simple log returns
        log_rets = np.diff(np.log(close))

        # Generate simple directional signal based on EMA crossover proxy
        if strategy_name == "trend_following":
            fast = int(params.get("ema_fast", 21))
            slow = int(params.get("ema_slow", 50))
        elif strategy_name == "mean_reversion":
            fast = int(params.get("bb_window", 20)) // 2
            slow = int(params.get("bb_window", 20))
        else:
            fast = 14
            slow = 28

        fast = max(2, fast)
        slow = max(fast + 1, slow)

        fast_ma = pd.Series(close).rolling(fast).mean().values
        slow_ma = pd.Series(close).rolling(slow).mean().values

        # Signal: +1 long when fast > slow, -1 short when fast < slow
        signals = np.where(fast_ma > slow_ma, 1.0, -1.0)
        signals = signals[slow:]  # align with log_rets
        rets_aligned = log_rets[slow - 1:]

        n = min(len(signals), len(rets_aligned))
        strategy_rets = signals[:n] * rets_aligned[:n]

        # Apply an adx/confidence-like noise filter — higher threshold = fewer trades
        threshold = float(params.get("adx_threshold", params.get("rsi_period", 14))) / 100.0
        active = np.abs(strategy_rets) > threshold / 10.0
        filtered_rets = strategy_rets[active]

        if len(filtered_rets) < 5:
            return {"sharpe": 0.0, "profit_factor": 1.0, "win_rate": 0.5, "n_trades": 0}

        # Sharpe (annualised assuming daily bars)
        mean_ret = np.mean(filtered_rets)
        std_ret = np.std(filtered_rets)
        sharpe = (mean_ret / max(std_ret, 1e-10)) * np.sqrt(252) if std_ret > 0 else 0.0

        wins = filtered_rets[filtered_rets > 0]
        losses = filtered_rets[filtered_rets < 0]
        profit_factor = (
            float(np.sum(wins)) / max(abs(float(np.sum(losses))), 1e-10)
            if len(losses) > 0 else 2.0
        )
        win_rate = len(wins) / len(filtered_rets) if len(filtered_rets) > 0 else 0.5

        return {
            "sharpe": round(float(sharpe), 4),
            "profit_factor": round(float(profit_factor), 4),
            "win_rate": round(float(win_rate), 4),
            "n_trades": int(len(filtered_rets)),
        }

    except Exception as exc:
        logger.exception("_simple_backtest error: %s", exc)
        return {"sharpe": 0.0, "profit_factor": 1.0, "win_rate": 0.5, "n_trades": 0}


# ---------------------------------------------------------------------------
# Main optimizer
# ---------------------------------------------------------------------------

class StrategyOptimizer:
    """Uses Optuna to find optimal strategy parameters.

    Implements:
    - Walk-forward validation to prevent overfitting
    - Minimum performance filters
    - Parameter importance analysis

    Usage::

        optimizer = StrategyOptimizer()
        result = await optimizer.optimize(
            strategy_name="trend_following",
            train_data=df_train,
            test_data=df_test,
            n_trials=100,
        )
        if result.is_valid:
            use_params(result.best_params)
    """

    MIN_OOS_SHARPE: float = 0.3
    MAX_OVERFITTING: float = 0.4
    PARAM_SPACES: dict[str, list[ParamSpace]] = _PARAM_SPACES

    # ------------------------------------------------------------------- public

    async def optimize(
        self,
        strategy_name: str,
        train_data: Any,
        test_data: Any,
        n_trials: int = 100,
        objective: str = "sharpe",
        param_spaces: Optional[list[ParamSpace]] = None,
    ) -> OptimizationResult:
        """Run Optuna optimisation with walk-forward OOS validation.

        Steps:
        1. Build search space from PARAM_SPACES or custom ``param_spaces``
        2. Run Optuna study — objective maximises the requested metric
        3. Validate best params on ``test_data``
        4. Compute overfitting score
        5. Calculate parameter importance
        6. Return :class:`OptimizationResult`

        Args:
            strategy_name: Strategy identifier (must exist in PARAM_SPACES or
                provide ``param_spaces``).
            train_data: In-sample pandas DataFrame.
            test_data: Out-of-sample pandas DataFrame.
            n_trials: Number of Optuna trials.
            objective: "sharpe" | "profit_factor" | "win_rate"
            param_spaces: Custom parameter spaces; overrides defaults.

        Returns:
            :class:`OptimizationResult`. Falls back to default params when
            Optuna is not installed.
        """
        try:
            import optuna
            optuna.logging.set_verbosity(optuna.logging.WARNING)
        except ImportError:
            logger.warning(
                "Optuna not installed — returning default params for '%s'. "
                "Install with: pip install optuna",
                strategy_name,
            )
            return self._default_result(strategy_name)

        spaces = param_spaces or self.PARAM_SPACES.get(strategy_name, [])
        if not spaces:
            logger.warning(
                "No param space defined for strategy '%s' — returning defaults",
                strategy_name,
            )
            return self._default_result(strategy_name)

        # Baseline score using default params
        default_params = self.get_default_params(strategy_name)
        default_bt = _simple_backtest(train_data, strategy_name, default_params)
        default_score = default_bt.get(objective, 0.0)

        # ----- Optuna study -----
        def optuna_objective(trial: Any) -> float:
            """Inner objective function for Optuna."""
            params = self._suggest_params(trial, spaces)
            bt = _simple_backtest(train_data, strategy_name, params)
            score = bt.get(objective, 0.0)
            # Optuna minimises — negate to maximise
            return -score

        try:
            study = optuna.create_study(
                direction="minimize",
                sampler=optuna.samplers.TPESampler(seed=42),
            )
            study.optimize(
                optuna_objective,
                n_trials=n_trials,
                show_progress_bar=False,
            )
        except Exception as exc:
            logger.exception("Optuna study failed: %s", exc)
            return self._default_result(strategy_name)

        best_params = study.best_params
        is_sharpe = -study.best_value  # un-negate

        # ----- OOS validation -----
        oos_bt = _simple_backtest(test_data, strategy_name, best_params)
        oos_sharpe = oos_bt.get("sharpe", 0.0)

        overfitting_score = self._overfitting_score(is_sharpe, oos_sharpe)
        is_valid = (
            oos_sharpe >= self.MIN_OOS_SHARPE
            and overfitting_score <= self.MAX_OVERFITTING
        )

        improvement_pct = (
            ((is_sharpe - default_score) / abs(default_score) * 100)
            if default_score != 0 else 0.0
        )

        # ----- Parameter importance -----
        try:
            param_importance = optuna.importance.get_param_importances(study)
            param_importance = {k: round(float(v), 4) for k, v in param_importance.items()}
        except Exception:
            param_importance = {p.name: 0.0 for p in spaces}

        logger.info(
            "Optimization complete: strategy=%s is_sharpe=%.3f oos_sharpe=%.3f "
            "overfitting=%.3f is_valid=%s n_trials=%d",
            strategy_name,
            is_sharpe,
            oos_sharpe,
            overfitting_score,
            is_valid,
            n_trials,
        )

        return OptimizationResult(
            strategy_name=strategy_name,
            best_params=best_params,
            best_score=round(is_sharpe, 4),
            n_trials=n_trials,
            improvement_pct=round(improvement_pct, 2),
            is_valid=is_valid,
            oos_sharpe=round(oos_sharpe, 4),
            is_sharpe=round(is_sharpe, 4),
            overfitting_score=round(overfitting_score, 4),
            param_importance=param_importance,
        )

    def get_default_params(self, strategy_name: str) -> dict[str, Any]:
        """Return the current default parameters for a strategy.

        Args:
            strategy_name: Strategy identifier.

        Returns:
            Parameter dict; empty dict if strategy not found.
        """
        return _DEFAULT_PARAMS.get(strategy_name, {}).copy()

    # ------------------------------------------------------------------ private

    def _run_backtest_with_params(
        self,
        strategy_name: str,
        params: dict[str, Any],
        data: Any,
    ) -> float:
        """Run simplified backtest and return the objective metric (Sharpe).

        Args:
            strategy_name: Strategy identifier.
            params: Parameter dict to test.
            data: OHLCV DataFrame.

        Returns:
            Sharpe ratio float.
        """
        bt = _simple_backtest(data, strategy_name, params)
        return bt.get("sharpe", 0.0)

    def _overfitting_score(
        self, is_sharpe: float, oos_sharpe: float
    ) -> float:
        """Calculate overfitting score: 0 = no overfit, 1 = severe overfit.

        Formula:
            score = max(0, (is_sharpe - oos_sharpe) / max(|is_sharpe|, ε))

        Args:
            is_sharpe: In-sample Sharpe ratio.
            oos_sharpe: Out-of-sample Sharpe ratio.

        Returns:
            Overfitting score [0, 1].
        """
        if is_sharpe <= 0:
            return 0.0
        score = max(0.0, (is_sharpe - oos_sharpe) / max(abs(is_sharpe), 1e-8))
        return round(min(score, 1.0), 4)

    def _suggest_params(
        self, trial: Any, spaces: list[ParamSpace]
    ) -> dict[str, Any]:
        """Ask Optuna to suggest values for all parameters in the search space.

        Args:
            trial: Optuna Trial object.
            spaces: List of :class:`ParamSpace` definitions.

        Returns:
            Dict of parameter name → suggested value.
        """
        params: dict[str, Any] = {}
        for space in spaces:
            if space.param_type == "int":
                params[space.name] = trial.suggest_int(
                    space.name, int(space.low), int(space.high), log=space.log
                )
            elif space.param_type == "float":
                params[space.name] = trial.suggest_float(
                    space.name, float(space.low), float(space.high), log=space.log
                )
            elif space.param_type == "categorical":
                params[space.name] = trial.suggest_categorical(
                    space.name, space.choices
                )
        return params

    def _default_result(self, strategy_name: str) -> OptimizationResult:
        """Build an :class:`OptimizationResult` using default strategy parameters.

        Used as a graceful fallback when Optuna is unavailable or optimisation
        fails.

        Args:
            strategy_name: Strategy identifier.

        Returns:
            :class:`OptimizationResult` marked as not validated.
        """
        defaults = self.get_default_params(strategy_name)
        spaces = self.PARAM_SPACES.get(strategy_name, [])
        return OptimizationResult(
            strategy_name=strategy_name,
            best_params=defaults,
            best_score=0.0,
            n_trials=0,
            improvement_pct=0.0,
            is_valid=False,
            oos_sharpe=0.0,
            is_sharpe=0.0,
            overfitting_score=0.0,
            param_importance={p.name: 0.0 for p in spaces},
        )


# Module-level singleton
_optimizer: StrategyOptimizer | None = None


def get_strategy_optimizer() -> StrategyOptimizer:
    """Return the global :class:`StrategyOptimizer` singleton.

    Returns:
        Shared StrategyOptimizer instance.
    """
    global _optimizer
    if _optimizer is None:
        _optimizer = StrategyOptimizer()
    return _optimizer
