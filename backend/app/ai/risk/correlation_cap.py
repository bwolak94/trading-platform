"""C6: Correlated position exposure cap.

Before approving a new signal, checks if the total open exposure to assets
with |correlation| > 0.8 against the proposed asset exceeds 20 % of the
portfolio.  If so, the signal is rejected to prevent over-concentration in
correlated bets.

Usage::

    cap = CorrelationCap(max_correlated_exposure_pct=20.0)
    allowed = cap.check(
        new_asset="SOL/USDT",
        new_exposure_pct=5.0,
        open_positions={"BTC/USDT": 10.0, "ETH/USDT": 8.0},
        correlation_matrix={"SOL/USDT": {"BTC/USDT": 0.85, "ETH/USDT": 0.78}},
    )
"""

from dataclasses import dataclass
from typing import Mapping

from app.core.logging import get_logger

logger = get_logger(__name__)

CORRELATION_THRESHOLD = 0.8
DEFAULT_MAX_CORRELATED_EXPOSURE_PCT = 20.0


@dataclass
class CorrelationCapResult:
    """Result of a correlation exposure check."""

    allowed: bool
    new_asset: str
    correlated_assets: list[str]
    current_correlated_exposure_pct: float
    max_correlated_exposure_pct: float
    reason: str


class CorrelationCap:
    """Guard that rejects signals when correlated exposure is too high.

    Args:
        max_correlated_exposure_pct: Maximum allowed total exposure to
            correlated assets as a percentage of portfolio.
        correlation_threshold: |r| above which two assets are considered
            correlated (default 0.8).
    """

    def __init__(
        self,
        max_correlated_exposure_pct: float = DEFAULT_MAX_CORRELATED_EXPOSURE_PCT,
        correlation_threshold: float = CORRELATION_THRESHOLD,
    ) -> None:
        self.max_correlated_exposure_pct = max_correlated_exposure_pct
        self.correlation_threshold = correlation_threshold

    def check(
        self,
        new_asset: str,
        new_exposure_pct: float,
        open_positions: Mapping[str, float],
        correlation_matrix: Mapping[str, Mapping[str, float]],
    ) -> CorrelationCapResult:
        """Evaluate whether adding a new position breaches the correlation cap.

        Args:
            new_asset:          Symbol of the asset about to be signalled.
            new_exposure_pct:   Proposed position size as a percentage of
                                portfolio (e.g. 5.0 for 5 %).
            open_positions:     Mapping of {symbol: exposure_pct} for all
                                currently open positions.
            correlation_matrix: Nested mapping of pairwise Pearson correlations
                                e.g. ``{"BTC/USDT": {"ETH/USDT": 0.92, ...}}``.

        Returns:
            :class:`CorrelationCapResult` with ``allowed`` bool and details.
        """
        row = correlation_matrix.get(new_asset, {})

        correlated_assets: list[str] = []
        correlated_exposure = 0.0

        for asset, exposure in open_positions.items():
            if asset == new_asset:
                correlated_exposure += exposure
                correlated_assets.append(asset)
                continue

            corr = abs(row.get(asset, 0.0))
            # Also check the transpose
            if corr < self.correlation_threshold:
                corr = abs(
                    correlation_matrix.get(asset, {}).get(new_asset, 0.0)
                )

            if corr >= self.correlation_threshold:
                correlated_exposure += exposure
                correlated_assets.append(asset)

        # Projected exposure if signal is approved
        projected = correlated_exposure + new_exposure_pct
        allowed = projected <= self.max_correlated_exposure_pct

        reason = (
            f"OK — projected correlated exposure {projected:.1f}% ≤ {self.max_correlated_exposure_pct:.1f}%"
            if allowed
            else (
                f"REJECTED — projected correlated exposure {projected:.1f}% > "
                f"{self.max_correlated_exposure_pct:.1f}% "
                f"(correlated assets: {correlated_assets})"
            )
        )

        if not allowed:
            logger.warning(
                "CorrelationCap: %s %s | %s",
                new_asset,
                "BLOCKED" if not allowed else "ALLOWED",
                reason,
            )

        return CorrelationCapResult(
            allowed=allowed,
            new_asset=new_asset,
            correlated_assets=correlated_assets,
            current_correlated_exposure_pct=round(correlated_exposure, 2),
            max_correlated_exposure_pct=self.max_correlated_exposure_pct,
            reason=reason,
        )
