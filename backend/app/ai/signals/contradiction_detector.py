"""D8: Contradictory signal detector.

Detects when LONG and SHORT signals exist simultaneously for the same asset
across different strategies.  When a contradiction is found:
  - A warning is emitted to the application log.
  - The weaker signal (lower confidence) is suppressed.
  - The stronger signal is returned.

Usage in the aggregator::

    from app.ai.signals.contradiction_detector import check_for_contradiction

    cleaned = check_for_contradiction(candidate_signals)
"""

from dataclasses import dataclass
from typing import Sequence

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ContradictionResult:
    """Result of a contradiction check."""

    had_contradiction: bool
    asset: str
    long_signal_strategy: str | None
    short_signal_strategy: str | None
    long_confidence: float
    short_confidence: float
    winner: str | None  # "LONG" | "SHORT" | None (no contradiction)


def check_for_contradiction(
    signals: Sequence,
    asset: str | None = None,
) -> ContradictionResult:
    """Detect contradictory LONG/SHORT signals for the same asset.

    Args:
        signals: Sequence of :class:`~app.ai.strategies.base.SignalResult`
                 objects for a single asset.
        asset:   Asset symbol for logging (inferred from signals if not given).

    Returns:
        :class:`ContradictionResult` describing any contradiction found.
    """
    longs = [s for s in signals if getattr(s, "direction", None) == "LONG"]
    shorts = [s for s in signals if getattr(s, "direction", None) == "SHORT"]

    if not longs or not shorts:
        sym = asset or (signals[0].asset if signals else "UNKNOWN")
        return ContradictionResult(
            had_contradiction=False,
            asset=sym,
            long_signal_strategy=None,
            short_signal_strategy=None,
            long_confidence=0.0,
            short_confidence=0.0,
            winner=None,
        )

    # Pick the strongest representative of each side
    best_long = max(longs, key=lambda s: s.confidence)
    best_short = max(shorts, key=lambda s: s.confidence)
    sym = asset or best_long.asset

    winner = "LONG" if best_long.confidence >= best_short.confidence else "SHORT"

    logger.warning(
        "ContradictionDetector: %s has LONG (conf=%.1f from %s) vs SHORT (conf=%.1f from %s) — "
        "suppressing weaker %s signal",
        sym,
        best_long.confidence,
        getattr(best_long, "strategy_name", "unknown"),
        best_short.confidence,
        getattr(best_short, "strategy_name", "unknown"),
        "SHORT" if winner == "LONG" else "LONG",
    )

    return ContradictionResult(
        had_contradiction=True,
        asset=sym,
        long_signal_strategy=getattr(best_long, "strategy_name", "unknown"),
        short_signal_strategy=getattr(best_short, "strategy_name", "unknown"),
        long_confidence=best_long.confidence,
        short_confidence=best_short.confidence,
        winner=winner,
    )


def filter_contradictions(signals: list) -> list:
    """Remove the weaker side of any LONG/SHORT contradiction per asset.

    Args:
        signals: Mixed list of SignalResult objects across multiple assets.

    Returns:
        Filtered list with contradictions resolved by keeping the stronger side.
    """
    from collections import defaultdict

    by_asset: dict[str, list] = defaultdict(list)
    for sig in signals:
        by_asset[sig.asset].append(sig)

    filtered: list = []
    for asset_signals in by_asset.values():
        result = check_for_contradiction(asset_signals)
        if not result.had_contradiction:
            filtered.extend(asset_signals)
        else:
            # Keep only signals matching the winning direction
            winners = [s for s in asset_signals if s.direction == result.winner]
            filtered.extend(winners)

    return filtered
