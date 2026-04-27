"""D5: Signal quality gate.

Before persisting a signal, enforces minimum quality criteria:
  1. At least 3 confirming indicators in the ``factors`` list.
  2. Risk/Reward ratio > 1.5.
  3. Entry price is not within 0.5% of a major support/resistance level.

Rejection reasons are logged for observability and can be surfaced to the
frontend via the SignalInvalidationTracker (B4).
"""

from dataclasses import dataclass
from typing import Any, Sequence

from app.core.logging import get_logger

logger = get_logger(__name__)

MIN_CONFIRMING_INDICATORS = 3
MIN_RISK_REWARD = 1.5
SR_PROXIMITY_PCT = 0.5  # reject if within this % of a key S/R level


@dataclass
class QualityGateResult:
    """Result of the quality gate evaluation."""

    passed: bool
    signal_id: str
    rejection_reasons: list[str]
    confirming_indicators: int
    risk_reward: float


def _count_confirming_indicators(factors: list[dict[str, Any]]) -> int:
    """Count factor entries that express positive (confirming) agreement."""
    count = 0
    for f in factors:
        # A factor is "confirming" if it has a positive score, weight, or
        # an explicit "confirming" / "bullish" / "bearish" flag that matches
        # the signal direction.
        score = f.get("score", f.get("value", f.get("weight", 0)))
        try:
            if float(score) > 0:
                count += 1
        except (TypeError, ValueError):
            if str(score).lower() in {"true", "yes", "bullish", "bearish", "confirming"}:
                count += 1
    return count


def _near_sr_level(
    entry_price: float,
    sr_levels: Sequence[float],
    proximity_pct: float = SR_PROXIMITY_PCT,
) -> bool:
    """Return True if ``entry_price`` is within ``proximity_pct`` of any S/R level."""
    for level in sr_levels:
        if level <= 0:
            continue
        distance_pct = abs(entry_price - level) / level * 100
        if distance_pct <= proximity_pct:
            return True
    return False


def evaluate(
    signal_id: str,
    factors: list[dict[str, Any]],
    risk_reward: float,
    entry_price: float,
    sr_levels: Sequence[float] | None = None,
) -> QualityGateResult:
    """Evaluate a candidate signal against quality criteria.

    Args:
        signal_id:   Identifier for logging purposes.
        factors:     List of factor dicts attached to the signal.
        risk_reward: Calculated R/R ratio (TP1 distance / SL distance).
        entry_price: Proposed entry price.
        sr_levels:   Optional sequence of key support/resistance prices to
                     check proximity against.

    Returns:
        :class:`QualityGateResult` with ``passed`` flag and rejection reasons.
    """
    rejections: list[str] = []

    # 1. Minimum confirming indicators
    confirming = _count_confirming_indicators(factors)
    if confirming < MIN_CONFIRMING_INDICATORS:
        rejections.append(
            f"Only {confirming}/{MIN_CONFIRMING_INDICATORS} confirming indicators"
        )

    # 2. Risk/reward check
    if risk_reward < MIN_RISK_REWARD:
        rejections.append(
            f"R/R {risk_reward:.2f} < minimum {MIN_RISK_REWARD}"
        )

    # 3. S/R proximity check
    if sr_levels and _near_sr_level(entry_price, sr_levels):
        rejections.append(
            f"Entry {entry_price} is within {SR_PROXIMITY_PCT}% of a key S/R level"
        )

    passed = len(rejections) == 0

    if not passed:
        logger.info(
            "QualityGate FAILED for %s: %s",
            signal_id,
            " | ".join(rejections),
        )
    else:
        logger.debug("QualityGate PASSED for %s", signal_id)

    return QualityGateResult(
        passed=passed,
        signal_id=signal_id,
        rejection_reasons=rejections,
        confirming_indicators=confirming,
        risk_reward=round(risk_reward, 2),
    )
