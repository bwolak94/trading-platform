"""C4: Equity curve trading filter.

Only allow new signals when the portfolio equity is above its own 20-day SMA.
When in a drawdown trend (equity < SMA) position sizes are automatically halved.

This is integrated into the SignalAggregator via the ``equity_curve_scale``
parameter — call :func:`get_equity_curve_scale` and pass the result there.
"""

from typing import Sequence

from app.core.logging import get_logger

logger = get_logger(__name__)

# Number of data points (e.g. daily equity snapshots) for the moving average
SMA_PERIOD = 20


def compute_sma(values: Sequence[float], period: int) -> float | None:
    """Return the simple moving average of the last ``period`` values.

    Returns ``None`` if there are fewer than ``period`` data points.
    """
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def get_equity_curve_scale(equity_history: Sequence[float]) -> float:
    """Determine the position-size scale factor based on equity curve position.

    Args:
        equity_history: Chronological sequence of portfolio equity values
            (oldest first, most-recent last).  At minimum 2 values are needed.

    Returns:
        ``1.0``  — equity is above its 20-day SMA (normal sizing).
        ``0.5``  — equity is at or below SMA (halve position sizes).
        ``1.0``  — insufficient history to determine trend (default safe).
    """
    if len(equity_history) < 2:
        return 1.0

    sma = compute_sma(equity_history, SMA_PERIOD)
    if sma is None:
        # Not enough history yet — trade normally until we have 20 data points
        return 1.0

    current_equity = equity_history[-1]
    if current_equity > sma:
        logger.debug(
            "Equity curve filter: equity %.2f > SMA %.2f — normal sizing",
            current_equity, sma,
        )
        return 1.0

    logger.info(
        "Equity curve filter: equity %.2f <= SMA %.2f — halving position sizes",
        current_equity, sma,
    )
    return 0.5


def should_allow_new_signals(equity_history: Sequence[float]) -> bool:
    """Return True if new signals are permitted under the equity curve filter.

    Signals are allowed regardless of the equity trend; the scale factor
    controls sizing instead of hard-blocking.  Call :func:`get_equity_curve_scale`
    to get the sizing multiplier for the aggregator.

    This function exists as a convenience gate for callers that want a simple
    boolean (e.g. quick health checks or dashboard display).
    """
    return get_equity_curve_scale(equity_history) > 0
