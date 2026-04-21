"""Walk-forward backtesting utilities and Monte Carlo VaR estimation."""

from __future__ import annotations


def monte_carlo_var(
    trade_returns: list[float],
    confidence: float = 0.95,
    simulations: int = 1000,
    horizon: int = 20,
) -> dict:
    """Monte Carlo VaR estimation via bootstrap sampling.

    Estimates the Value at Risk for a forward horizon of trades by resampling
    from historical trade returns (preserves fat tails, no normality assumption).

    Args:
        trade_returns: list of trade return percentages (e.g., [2.5, -1.2, 3.1, ...])
        confidence: confidence level (0.95 or 0.99)
        simulations: number of Monte Carlo paths
        horizon: number of trades to simulate forward

    Returns:
        dict with var_95, var_99, expected_return, worst_case, best_case,
        median, simulations, horizon, confidence
    """
    import numpy as np

    if len(trade_returns) < 5:
        return {"error": "Insufficient trade history"}

    arr = np.array(trade_returns)
    mean_return = float(np.mean(arr))
    std_return = float(np.std(arr))

    # Bootstrap sampling (preserves fat tails)
    rng = np.random.default_rng(42)

    final_returns = []
    for _ in range(simulations):
        # Sample with replacement from historical returns
        path = rng.choice(arr, size=horizon, replace=True)
        final_returns.append(float(np.sum(path)))

    final_returns_arr = np.array(final_returns)

    return {
        "var_95": round(float(np.percentile(final_returns_arr, 5)), 2),   # 5th percentile (worst 5%)
        "var_99": round(float(np.percentile(final_returns_arr, 1)), 2),   # 1st percentile
        "expected_return": round(float(np.mean(final_returns_arr)), 2),
        "worst_case": round(float(np.min(final_returns_arr)), 2),
        "best_case": round(float(np.max(final_returns_arr)), 2),
        "median": round(float(np.median(final_returns_arr)), 2),
        "simulations": simulations,
        "horizon": horizon,
        "confidence": confidence,
    }
