"""Ornstein-Uhlenbeck Mean Reversion Probability estimator.

Fits an OU process to price deviations from mean and estimates the probability
of mean reversion within N periods. Used to boost confidence for MeanReversion strategy.

The OU process models: dX = theta(mu - X)dt + sigma*dW
where theta = mean reversion speed, mu = long-run mean, sigma = volatility.
"""

from __future__ import annotations

import math
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)


def fit_ou_process(prices: list[float]) -> dict[str, float]:
    """Fit OU process parameters to a price series.

    Uses OLS regression on the discrete-time representation:
        X[t+1] - X[t] = a + b*X[t] + epsilon
    where: theta = -log(1 + b*dt), mu = -a/b, sigma estimated from residuals

    Args:
        prices: List of prices (at least 30 data points recommended)

    Returns:
        Dict with theta (mean reversion speed), mu (mean price), sigma (vol),
        half_life_periods (expected half-life in periods), r_squared
    """
    if len(prices) < 20:
        return {
            "theta": 0.0,
            "mu": 0.0,
            "sigma": 0.0,
            "half_life_periods": 999.0,
            "r_squared": 0.0,
        }

    n = len(prices) - 1
    x = prices[:-1]
    y = prices[1:]

    # OLS regression: y = a + b*x
    sum_x = sum(x)
    sum_y = sum(y)
    sum_xy = sum(xi * yi for xi, yi in zip(x, y))
    sum_xx = sum(xi**2 for xi in x)

    denom = n * sum_xx - sum_x**2
    if abs(denom) < 1e-12:
        return {
            "theta": 0.0,
            "mu": float(sum(prices) / len(prices)),
            "sigma": 0.0,
            "half_life_periods": 999.0,
            "r_squared": 0.0,
        }

    b = (n * sum_xy - sum_x * sum_y) / denom
    a = (sum_y - b * sum_x) / n

    # Mean reversion speed and long-run mean
    theta = -math.log(max(b, 1e-10)) if b > 0 else 0.0
    mu = -a / b if abs(b) > 1e-10 else float(sum(prices) / len(prices))
    half_life = math.log(2) / theta if theta > 0 else 999.0

    # Residual standard deviation
    residuals = [yi - (a + b * xi) for xi, yi in zip(x, y)]
    sigma = (sum(r**2 for r in residuals) / max(n - 2, 1)) ** 0.5

    # R-squared
    ss_res = sum(r**2 for r in residuals)
    ss_tot = sum((yi - sum_y / n) ** 2 for yi in y)
    r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0

    return {
        "theta": round(theta, 4),
        "mu": round(mu, 6),
        "sigma": round(sigma, 6),
        "half_life_periods": round(min(half_life, 999.0), 2),
        "r_squared": round(max(0, min(1, r_squared)), 4),
    }


def mean_reversion_probability(
    current_price: float,
    ou_params: dict[str, float],
    periods: int = 5,
) -> dict[str, Any]:
    """Estimate probability of mean reversion within N periods.

    Args:
        current_price: Current asset price
        ou_params: Result from fit_ou_process()
        periods: Forecast horizon in periods

    Returns:
        Dict with probability (0-1), expected_reversion_pct, deviation_from_mean_pct, signal
    """
    mu = ou_params.get("mu", current_price)
    theta = ou_params.get("theta", 0.0)
    sigma = ou_params.get("sigma", 1.0)
    r_squared = ou_params.get("r_squared", 0.0)

    if theta <= 0 or sigma <= 0 or r_squared < 0.3:
        return {
            "probability": 0.5,
            "expected_reversion_pct": 0.0,
            "deviation_from_mean_pct": 0.0,
            "signal": "NEUTRAL",
            "insufficient_data": True,
        }

    # Deviation from mean
    deviation = (current_price - mu) / mu if mu != 0 else 0.0
    deviation_pct = deviation * 100

    # Expected price after `periods` steps: E[X_t] = mu + (X_0 - mu) * e^(-theta*t)
    expected_price = mu + (current_price - mu) * math.exp(-theta * periods)
    reversion_pct = (expected_price - current_price) / current_price * 100

    # Probability of touching mean: approximate using half-life
    half_life = ou_params.get("half_life_periods", 999.0)
    if half_life <= 0:
        prob = 0.5
    else:
        # Higher probability when current deviation is large and half-life is short
        prob = 1 - math.exp(-periods * math.log(2) / half_life)
        # Adjust for magnitude of deviation: normalize to ±5% = full probability boost
        deviation_factor = min(abs(deviation) / 0.05, 1.0)
        prob = min(0.95, prob * (0.5 + 0.5 * deviation_factor))

    # Signal based on deviation direction
    signal = "LONG" if deviation < -0.01 else ("SHORT" if deviation > 0.01 else "NEUTRAL")

    return {
        "probability": round(prob, 3),
        "expected_reversion_pct": round(reversion_pct, 3),
        "deviation_from_mean_pct": round(deviation_pct, 3),
        "signal": signal,
        "mu": round(mu, 6),
        "half_life_periods": round(half_life, 2),
        "r_squared": round(r_squared, 4),
    }
