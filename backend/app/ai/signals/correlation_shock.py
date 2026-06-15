"""Correlation Shock Detector — alerts when asset correlations break down."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.core.logging import get_logger

logger = get_logger(__name__)

# Default correlation pairs to monitor across the crypto ecosystem
DEFAULT_PAIRS: list[tuple[str, str]] = [
    ("BTC/USDT", "ETH/USDT"),
    ("BTC/USDT", "SOL/USDT"),
    ("ETH/USDT", "SOL/USDT"),
    ("BTC/USDT", "BNB/USDT"),
    ("SOL/USDT", "AVAX/USDT"),
]


@dataclass
class CorrelationShockAlert:
    """Alert generated when a historically-correlated asset pair decouples."""

    asset_a: str
    asset_b: str
    current_correlation: float       # rolling short-window correlation
    historical_mean_correlation: float  # long-window baseline correlation
    correlation_drop: float          # how much correlation dropped below baseline
    leading_asset: str               # asset that moved independently
    lagging_asset: str               # asset expected to follow (mean reversion)
    expected_direction: str          # "LONG" or "SHORT" on the lagging asset
    confidence: float                # 0-100
    alert_type: str                  # "DECOUPLING" or "RECOUPLING"
    description: str


class CorrelationShockDetector:
    """Monitors asset-pair correlations and detects significant regime breaks.

    When two assets that normally move together suddenly decouple, it often
    precedes the lagging asset catching up (mean-reversion of correlation).
    This is a high-probability setup used in pairs trading.
    """

    LOOKBACK_SHORT: int = 10           # days for current (recent) correlation
    LOOKBACK_LONG: int = 60            # days for historical baseline correlation
    SHOCK_THRESHOLD: float = 0.25      # correlation drop > 0.25 triggers an alert
    MIN_BASELINE_CORRELATION: float = 0.6  # only pairs normally ≥ 0.6 correlated are monitored

    def detect(
        self,
        pairs: list[tuple[str, str]],
        price_data: dict[str, pd.DataFrame],
    ) -> list[CorrelationShockAlert]:
        """Detect correlation shocks across the provided asset pairs.

        For each pair:
        1. Calculate short-window rolling correlation (current regime).
        2. Calculate long-window baseline correlation (historical mean).
        3. Alert if the current correlation drops > ``SHOCK_THRESHOLD`` below baseline.
        4. Determine which asset is the "leader" (moved more in last 5 days).
        5. Expect the lagging asset to follow (mean-reversion trade).

        Args:
            pairs: List of (symbol_a, symbol_b) tuples to monitor.
            price_data: Dict mapping symbol → DataFrame with a ``close`` column and
                ``DatetimeIndex`` (daily frequency recommended, but hourly works too).

        Returns:
            List of :class:`CorrelationShockAlert` objects for triggered pairs.
            Empty list if no shocks are detected.
        """
        alerts: list[CorrelationShockAlert] = []

        for asset_a, asset_b in pairs:
            df_a = price_data.get(asset_a)
            df_b = price_data.get(asset_b)

            if df_a is None or df_b is None:
                logger.debug(
                    "CorrelationShock: missing price data for pair (%s, %s)", asset_a, asset_b
                )
                continue

            if "close" not in df_a.columns or "close" not in df_b.columns:
                logger.warning(
                    "CorrelationShock: 'close' column missing for (%s, %s)", asset_a, asset_b
                )
                continue

            min_rows = self.LOOKBACK_LONG + 5
            if len(df_a) < min_rows or len(df_b) < min_rows:
                logger.debug(
                    "CorrelationShock: insufficient data for (%s, %s) — need %d rows",
                    asset_a, asset_b, min_rows,
                )
                continue

            # Align both series on the same index
            returns_a = df_a["close"].pct_change().dropna()
            returns_b = df_b["close"].pct_change().dropna()
            aligned = pd.concat(
                [returns_a.rename("a"), returns_b.rename("b")], axis=1
            ).dropna()

            if len(aligned) < min_rows:
                continue

            current_corr = self._calculate_rolling_correlation(
                aligned["a"], aligned["b"], window=self.LOOKBACK_SHORT
            )
            historical_corr = self._calculate_rolling_correlation(
                aligned["a"], aligned["b"], window=self.LOOKBACK_LONG
            )

            # Only proceed if pair is normally highly correlated
            if abs(historical_corr) < self.MIN_BASELINE_CORRELATION:
                logger.debug(
                    "CorrelationShock: (%s, %s) baseline corr %.2f < %.2f — skipping",
                    asset_a, asset_b, historical_corr, self.MIN_BASELINE_CORRELATION,
                )
                continue

            correlation_drop = historical_corr - current_corr

            if correlation_drop <= self.SHOCK_THRESHOLD:
                continue  # No significant shock

            # Determine which asset is leading
            leading_asset, lagging_asset = self._determine_leader(
                asset_a, asset_b, df_a, df_b, window_days=5
            )

            # The lagging asset is expected to follow the leader
            # Determine direction: look at what the leader did recently
            leader_df = df_a if leading_asset == asset_a else df_b
            recent_leader_return = (
                leader_df["close"].iloc[-1] / leader_df["close"].iloc[-6] - 1
                if len(leader_df) >= 6
                else 0.0
            )
            expected_direction = "LONG" if recent_leader_return > 0 else "SHORT"

            # Confidence scales with the magnitude of the correlation drop
            raw_confidence = min(
                (correlation_drop - self.SHOCK_THRESHOLD) / (1.0 - self.SHOCK_THRESHOLD) * 80.0,
                80.0,
            )
            confidence = round(max(raw_confidence, 20.0), 2)

            description = (
                f"Correlation shock: {asset_a}/{asset_b} current_corr={current_corr:.2f} "
                f"vs baseline={historical_corr:.2f} (drop={correlation_drop:.2f}). "
                f"Leader: {leading_asset} ({recent_leader_return:+.1%}). "
                f"Expect {lagging_asset} to move {expected_direction}."
            )

            logger.info(
                "CorrelationShock alert: (%s, %s) drop=%.2f leader=%s direction=%s conf=%.1f",
                asset_a, asset_b, correlation_drop, leading_asset, expected_direction, confidence,
            )

            alerts.append(
                CorrelationShockAlert(
                    asset_a=asset_a,
                    asset_b=asset_b,
                    current_correlation=round(current_corr, 4),
                    historical_mean_correlation=round(historical_corr, 4),
                    correlation_drop=round(correlation_drop, 4),
                    leading_asset=leading_asset,
                    lagging_asset=lagging_asset,
                    expected_direction=expected_direction,
                    confidence=confidence,
                    alert_type="DECOUPLING",
                    description=description,
                )
            )

        return alerts

    def _calculate_rolling_correlation(
        self,
        returns_a: pd.Series,
        returns_b: pd.Series,
        window: int,
    ) -> float:
        """Calculate the Pearson correlation over the last *window* periods.

        Args:
            returns_a: Percentage returns series for asset A.
            returns_b: Percentage returns series for asset B.
            window: Number of periods (rows) for the rolling window.

        Returns:
            Pearson correlation coefficient in [-1, 1].
            Returns 0.0 if computation fails.
        """
        if len(returns_a) < window or len(returns_b) < window:
            return 0.0

        try:
            tail_a = returns_a.iloc[-window:].values.astype(float)
            tail_b = returns_b.iloc[-window:].values.astype(float)

            if np.std(tail_a) == 0 or np.std(tail_b) == 0:
                return 0.0

            corr: float = float(np.corrcoef(tail_a, tail_b)[0, 1])
            return corr if not np.isnan(corr) else 0.0
        except Exception as exc:
            logger.warning("CorrelationShock: correlation calculation error: %s", exc)
            return 0.0

    def _determine_leader(
        self,
        symbol_a: str,
        symbol_b: str,
        df_a: pd.DataFrame,
        df_b: pd.DataFrame,
        window_days: int = 5,
    ) -> tuple[str, str]:
        """Determine which asset moved more recently (i.e. is the "leader").

        The leader is the asset with the larger absolute price return over the
        last *window_days* periods.  The lagging asset is expected to follow.

        Args:
            symbol_a: Label for asset A.
            symbol_b: Label for asset B.
            df_a: Price DataFrame for asset A (must contain ``close``).
            df_b: Price DataFrame for asset B (must contain ``close``).
            window_days: Lookback window in periods.

        Returns:
            Tuple of ``(leading_asset, lagging_asset)`` as symbol strings.
        """
        try:
            tail = window_days + 1
            ret_a = abs(
                df_a["close"].iloc[-1] / df_a["close"].iloc[-min(tail, len(df_a))] - 1
            )
            ret_b = abs(
                df_b["close"].iloc[-1] / df_b["close"].iloc[-min(tail, len(df_b))] - 1
            )
        except (IndexError, ZeroDivisionError):
            # Fall back to alphabetical order
            return symbol_a, symbol_b

        if ret_a >= ret_b:
            return symbol_a, symbol_b
        return symbol_b, symbol_a
