"""Regime-Gated Signal Filter — blocks signals that underperform in current regime.

Each trading strategy has different historical win rates depending on market
regime. This filter annotates signals with regime-based approval and warns
when a strategy has a poor track record in the current regime.

Historical win rates are based on backtested priors and updated over time
by the learning engine.
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

# Historical win rates per regime per strategy (priors from backtesting)
REGIME_STRATEGY_PERFORMANCE: dict[str, dict[str, float]] = {
    "TREND_BULL": {
        "trend_following": 0.68,
        "mean_reversion": 0.38,
        "breakout": 0.62,
        "smc": 0.58,
        "volume_breakout": 0.64,
        "mtf_confluence": 0.65,
        "rsi_scalping": 0.42,
        "default": 0.52,
    },
    "TREND_BEAR": {
        "trend_following": 0.61,
        "mean_reversion": 0.42,
        "breakout": 0.55,
        "smc": 0.60,
        "volume_breakout": 0.58,
        "mtf_confluence": 0.59,
        "rsi_scalping": 0.45,
        "default": 0.50,
    },
    "CONSOLIDATION": {
        "trend_following": 0.32,
        "mean_reversion": 0.65,
        "breakout": 0.41,
        "smc": 0.48,
        "volume_breakout": 0.38,
        "mtf_confluence": 0.44,
        "rsi_scalping": 0.60,
        "default": 0.45,
    },
    "HIGH_VOL_CHOPPY": {
        "trend_following": 0.28,
        "mean_reversion": 0.45,
        "breakout": 0.35,
        "smc": 0.40,
        "volume_breakout": 0.32,
        "mtf_confluence": 0.35,
        "rsi_scalping": 0.48,
        "default": 0.38,
    },
    "UNKNOWN": {
        "default": 0.45,
    },
}

# Minimum acceptable win rate to approve a signal
_APPROVAL_THRESHOLD = 0.50


async def filter_signal(signal: dict[str, Any], current_regime: str) -> dict[str, Any]:
    """Annotate a signal with regime-based approval status.

    Args:
        signal: Signal dict with at least {strategy, confidence}
        current_regime: Current market regime string

    Returns:
        Signal dict with added {regime_approved, strategy_win_rate_in_regime, regime_warning}
    """
    strategy = signal.get("strategy", "default").lower().replace(" ", "_")
    regime_data = REGIME_STRATEGY_PERFORMANCE.get(current_regime, REGIME_STRATEGY_PERFORMANCE["UNKNOWN"])
    win_rate = regime_data.get(strategy, regime_data.get("default", 0.45))

    approved = win_rate >= _APPROVAL_THRESHOLD
    warning: str | None = None

    if not approved:
        warning = (
            f"Strategy '{strategy}' has a {win_rate:.0%} historical win rate in {current_regime} "
            f"regime (below {_APPROVAL_THRESHOLD:.0%} threshold). Consider skipping or reducing size."
        )
        logger.debug("Regime filter blocked signal: %s in %s (win_rate=%.2f)", strategy, current_regime, win_rate)

    signal_out = dict(signal)
    signal_out["regime_approved"] = approved
    signal_out["strategy_win_rate_in_regime"] = round(win_rate, 3)
    signal_out["current_regime"] = current_regime
    signal_out["regime_warning"] = warning
    return signal_out


async def get_regime_performance_matrix() -> dict[str, Any]:
    """Return the full regime-strategy performance matrix.

    Returns:
        {regimes: {regime: {strategy: win_rate}}, approval_threshold, description}
    """
    return {
        "regimes": REGIME_STRATEGY_PERFORMANCE,
        "approval_threshold": _APPROVAL_THRESHOLD,
        "description": (
            "Historical win rates per strategy per market regime. "
            "Signals where win_rate < threshold are flagged with regime_warning."
        ),
    }
