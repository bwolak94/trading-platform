"""Modern Portfolio Theory optimizer using scipy."""
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class PortfolioWeights:
    """Result of MPT portfolio optimization."""

    weights: dict[str, float]       # symbol -> weight (0-1)
    expected_return: float          # annualized %
    volatility: float               # annualized %
    sharpe_ratio: float
    optimization_type: str          # "max_sharpe" | "min_variance" | "equal_weight"


def optimize_portfolio(
    symbols: list[str],
    returns_matrix: list[list[float]],  # rows = time, cols = symbols
    risk_free_rate: float = 0.05,
    optimization_type: str = "max_sharpe",
) -> Optional[PortfolioWeights]:
    """Modern Portfolio Theory portfolio optimizer.

    Uses scipy minimize to find the optimal portfolio weights that either
    maximise the Sharpe ratio, minimise variance, or distribute equally.

    Args:
        symbols: list of symbol names (must match columns in returns_matrix)
        returns_matrix: daily returns for each symbol (rows=time, cols=symbols)
        risk_free_rate: annual risk-free rate as a decimal (default 5% = 0.05)
        optimization_type: one of "max_sharpe" | "min_variance" | "equal_weight"

    Returns:
        PortfolioWeights dataclass or None if optimization fails.
    """
    try:
        import numpy as np
        from scipy.optimize import minimize

        ret = np.array(returns_matrix)
        if ret.shape[0] < 10 or ret.shape[1] < 2:
            return None

        n = len(symbols)
        mean_returns = np.mean(ret, axis=0) * 252   # annualized
        cov_matrix = np.cov(ret.T) * 252

        def portfolio_stats(weights: "np.ndarray") -> tuple[float, float, float]:
            """Compute annualised (return, volatility, sharpe) for a weight vector."""
            w = np.array(weights)
            port_return = float(np.dot(w, mean_returns))
            port_vol = float(np.sqrt(np.dot(w.T, np.dot(cov_matrix, w))))
            sharpe = (port_return - risk_free_rate) / port_vol if port_vol > 0 else 0.0
            return port_return, port_vol, sharpe

        constraints = [{"type": "eq", "fun": lambda w: float(np.sum(w)) - 1}]
        bounds = [(0.01, 0.5)] * n
        x0 = np.ones(n) / n

        if optimization_type == "equal_weight":
            weights = x0
            ret_, vol, sharpe = portfolio_stats(weights)
        elif optimization_type == "min_variance":
            def objective(w: "np.ndarray") -> float:
                _, vol, _ = portfolio_stats(w)
                return vol

            result = minimize(objective, x0, bounds=bounds, constraints=constraints, method="SLSQP")
            weights = result.x
            ret_, vol, sharpe = portfolio_stats(weights)
        else:  # max_sharpe (default)
            def neg_sharpe(w: "np.ndarray") -> float:
                _, _, s = portfolio_stats(w)
                return -s

            result = minimize(neg_sharpe, x0, bounds=bounds, constraints=constraints, method="SLSQP")
            weights = result.x
            ret_, vol, sharpe = portfolio_stats(weights)

        weight_dict = {sym: round(float(w), 4) for sym, w in zip(symbols, weights)}

        return PortfolioWeights(
            weights=weight_dict,
            expected_return=round(ret_ * 100, 2),
            volatility=round(vol * 100, 2),
            sharpe_ratio=round(sharpe, 3),
            optimization_type=optimization_type,
        )
    except Exception as exc:
        logger.warning("MPT optimization failed: %s", exc)
        return None
