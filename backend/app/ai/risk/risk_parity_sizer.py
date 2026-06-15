"""Risk Parity Position Sizer — equal dollar risk per position across assets."""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class RiskParityAllocation:
    """Allocation for a single asset under risk parity sizing."""

    symbol: str
    volatility: float              # annualized historical volatility (fraction, e.g. 0.60)
    risk_weight: float             # inverse-vol weight in [0, 1], sums to 1 across assets
    capital_allocation_pct: float  # percentage of total capital allocated
    position_size_usd: float       # dollar position size
    rationale: str


@dataclass
class RiskParityPortfolio:
    """Full risk-parity portfolio allocation result."""

    allocations: list[RiskParityAllocation]
    total_capital: float
    target_portfolio_vol: float    # target annualized portfolio volatility (fraction)
    current_portfolio_vol: float   # estimated portfolio volatility after weighting
    diversification_ratio: float   # > 1.0 means risk parity adds diversification


class RiskParitySizer:
    """Allocates capital inversely to volatility so each asset contributes
    equal risk to the portfolio.

    Formula (inverse-volatility weighting)
    ----------------------------------------
        raw_weight[i]   = 1 / volatility[i]
        weight[i]       = raw_weight[i] / sum(raw_weights)
        allocation[i]   = weight[i] * total_capital

    Correlation adjustment (optional)
    -----------------------------------
    Each raw weight is further divided by ``(1 + avg_pairwise_corr[i])`` to
    down-weight assets that move together with the rest of the portfolio.

    Target portfolio volatility scaling
    -------------------------------------
    All weights are rescaled so the estimated portfolio volatility ≈ ``target_vol``
    (default 15 % annualised).  This prevents the portfolio from being over- or
    under-leveraged.
    """

    TARGET_PORTFOLIO_VOL: float = 0.15  # 15% annualised
    MIN_HISTORY_CANDLES: int = 30

    def calculate(
        self,
        asset_data: dict[str, pd.DataFrame],
        total_capital: float,
        target_vol: float = 0.15,
        use_correlation_adjustment: bool = True,
    ) -> RiskParityPortfolio:
        """Compute risk-parity allocations for all provided assets.

        Steps
        -----
        1. Calculate annualised historical volatility (HV20) for each asset.
        2. Compute inverse-volatility raw weights.
        3. Optionally adjust for pairwise correlations.
        4. Normalise weights to sum to 1.
        5. Estimate portfolio volatility and scale weights to hit ``target_vol``.
        6. Convert to dollar allocations.

        Args:
            asset_data: Mapping of ``{symbol: OHLCV DataFrame}``.
            total_capital: Total capital in USD available to allocate.
            target_vol: Target annualised portfolio volatility (default 0.15).
            use_correlation_adjustment: Apply correlation penalty to correlated assets.

        Returns:
            RiskParityPortfolio with per-asset allocations and portfolio-level stats.
        """
        if not asset_data or total_capital <= 0:
            logger.warning("RiskParitySizer: empty asset_data or zero capital")
            return RiskParityPortfolio(
                allocations=[],
                total_capital=total_capital,
                target_portfolio_vol=target_vol,
                current_portfolio_vol=0.0,
                diversification_ratio=1.0,
            )

        list(asset_data.keys())
        vols: dict[str, float] = {}

        for sym, df in asset_data.items():
            if len(df) < self.MIN_HISTORY_CANDLES:
                logger.warning(
                    "RiskParitySizer: insufficient history for %s (%d candles) — skipping",
                    sym,
                    len(df),
                )
                continue
            hv = self._calc_hv(df)
            if hv <= 0:
                logger.warning("RiskParitySizer: zero volatility for %s — skipping", sym)
                continue
            vols[sym] = hv

        if not vols:
            logger.error("RiskParitySizer: no valid assets after volatility calculation")
            return RiskParityPortfolio(
                allocations=[],
                total_capital=total_capital,
                target_portfolio_vol=target_vol,
                current_portfolio_vol=0.0,
                diversification_ratio=1.0,
            )

        valid_symbols = list(vols.keys())
        vol_array = np.array([vols[s] for s in valid_symbols], dtype=float)

        # Step 2: inverse-vol weights
        raw_weights = 1.0 / vol_array

        # Step 3: correlation adjustment
        if use_correlation_adjustment and len(valid_symbols) > 1:
            corr_matrix = self._correlation_matrix(
                {s: asset_data[s] for s in valid_symbols}
            )
            for i in range(len(valid_symbols)):
                # Average pairwise correlation of asset i with all others
                others = [corr_matrix[i, j] for j in range(len(valid_symbols)) if j != i]
                avg_corr = float(np.mean(others)) if others else 0.0
                avg_corr = max(avg_corr, 0.0)  # treat negative correlation as 0 benefit
                raw_weights[i] /= (1.0 + avg_corr)

        # Step 4: normalise
        total_raw = raw_weights.sum()
        weights = raw_weights / total_raw if total_raw > 0 else raw_weights

        # Step 5: estimate portfolio volatility and scale to target
        # Simplified: weighted-sum of individual vols (assumes zero correlation baseline)
        portfolio_vol_unscaled = float(np.dot(weights, vol_array))

        # Diversification ratio = (weighted sum of individual vols) / portfolio vol
        # With correlation adjustment already applied, use this as approximation
        diversification_ratio = (
            float(np.mean(vol_array)) / portfolio_vol_unscaled
            if portfolio_vol_unscaled > 0
            else 1.0
        )
        diversification_ratio = max(diversification_ratio, 1.0)

        # Scale weights so portfolio vol ≈ target_vol
        scale_factor = (
            target_vol / portfolio_vol_unscaled if portfolio_vol_unscaled > 0 else 1.0
        )
        # Cap scale to avoid excessive leverage (max 2×, min 0.1×)
        scale_factor = float(np.clip(scale_factor, 0.1, 2.0))
        scaled_weights = weights * scale_factor
        # Re-normalise after scaling so allocations still sum to 100% of capital
        scaled_weights /= scaled_weights.sum()

        current_portfolio_vol = float(np.dot(scaled_weights, vol_array))

        # Step 6: build allocations
        allocations: list[RiskParityAllocation] = []
        for i, sym in enumerate(valid_symbols):
            w = float(scaled_weights[i])
            pos_usd = total_capital * w
            rationale = (
                f"Vol={vols[sym]:.1%} → inv-vol weight={float(weights[i]):.3f} "
                f"→ scaled weight={w:.3f} (target_vol={target_vol:.1%})"
            )
            allocations.append(
                RiskParityAllocation(
                    symbol=sym,
                    volatility=round(vols[sym], 6),
                    risk_weight=round(w, 6),
                    capital_allocation_pct=round(w * 100, 4),
                    position_size_usd=round(pos_usd, 2),
                    rationale=rationale,
                )
            )

        allocations.sort(key=lambda a: a.risk_weight, reverse=True)

        logger.info(
            "RiskParitySizer: allocated %d assets, portfolio_vol=%.2f%% (target=%.2f%%)",
            len(allocations),
            current_portfolio_vol * 100,
            target_vol * 100,
        )

        return RiskParityPortfolio(
            allocations=allocations,
            total_capital=total_capital,
            target_portfolio_vol=target_vol,
            current_portfolio_vol=round(current_portfolio_vol, 6),
            diversification_ratio=round(diversification_ratio, 4),
        )

    def _calc_hv(self, df: pd.DataFrame, window: int = 20) -> float:
        """Calculate annualised historical volatility from log returns.

        HV = std(log_returns, window=20) * sqrt(252 * 24)  for hourly data.
        Falls back to sqrt(365) annualisation when candle count < 252*24.

        Args:
            df: OHLCV DataFrame with a ``close`` column.
            window: Rolling window for standard deviation (default 20).

        Returns:
            Annualised HV as a fraction (e.g. 0.60 = 60 %).  Returns 0.0 on error.
        """
        try:
            close = df["close"].astype(float)
            log_returns = np.log(close / close.shift(1)).dropna()
            if len(log_returns) < window:
                return 0.0
            rolling_std = float(log_returns.rolling(window).std().iloc[-1])
            if np.isnan(rolling_std):
                return 0.0
            # Annualise: detect approximate candle frequency
            # Use 252 trading days; multiply by candles-per-day based on df size hint
            n = len(df)
            if n > 5000:
                periods_per_year = 365 * 24  # roughly hourly
            elif n > 500:
                periods_per_year = 365 * 4   # roughly 6-hourly
            else:
                periods_per_year = 252        # daily
            return float(rolling_std * np.sqrt(periods_per_year))
        except Exception as exc:
            logger.error("RiskParitySizer._calc_hv error: %s", exc)
            return 0.0

    def _correlation_matrix(
        self, asset_data: dict[str, pd.DataFrame]
    ) -> np.ndarray:
        """Calculate pairwise Pearson correlation matrix of log returns.

        Assets with fewer than ``MIN_HISTORY_CANDLES`` rows are treated as
        uncorrelated (row/column filled with 0.0, diagonal with 1.0).

        Args:
            asset_data: Mapping of ``{symbol: OHLCV DataFrame}``.

        Returns:
            Square numpy array of shape (n_assets, n_assets).
        """
        symbols = list(asset_data.keys())
        n = len(symbols)
        corr_matrix = np.eye(n, dtype=float)

        if n < 2:
            return corr_matrix

        returns_dict: dict[str, pd.Series] = {}
        for sym, df in asset_data.items():
            try:
                close = df["close"].astype(float)
                lr = np.log(close / close.shift(1)).dropna()
                returns_dict[sym] = lr
            except Exception as exc:
                logger.debug("Correlation matrix: error for %s: %s", sym, exc)

        for i, sym_i in enumerate(symbols):
            for j, sym_j in enumerate(symbols):
                if i >= j:
                    continue
                if sym_i not in returns_dict or sym_j not in returns_dict:
                    continue
                ri = returns_dict[sym_i]
                rj = returns_dict[sym_j]
                # Align on common index
                common = ri.index.intersection(rj.index)
                if len(common) < 10:
                    continue
                corr = float(ri.loc[common].corr(rj.loc[common]))
                if not np.isnan(corr):
                    corr_matrix[i, j] = corr
                    corr_matrix[j, i] = corr

        return corr_matrix

    def rebalance_required(
        self,
        current_allocations: list[RiskParityAllocation],
        new_portfolio: RiskParityPortfolio,
        threshold_pct: float = 5.0,
    ) -> bool:
        """Check whether rebalancing is needed.

        Compares the current allocation weights against the newly computed
        target weights.  Returns ``True`` if any asset's weight has drifted
        more than ``threshold_pct`` percentage points.

        Args:
            current_allocations: Existing portfolio allocations.
            new_portfolio: Freshly computed target portfolio.
            threshold_pct: Drift threshold in percentage points (default 5.0).

        Returns:
            ``True`` if any weight drift exceeds the threshold, ``False`` otherwise.
        """
        current_map = {a.symbol: a.capital_allocation_pct for a in current_allocations}
        for alloc in new_portfolio.allocations:
            current_pct = current_map.get(alloc.symbol, 0.0)
            drift = abs(alloc.capital_allocation_pct - current_pct)
            if drift > threshold_pct:
                logger.info(
                    "RiskParitySizer: rebalance required — %s drifted %.2f pp (threshold=%.1f pp)",
                    alloc.symbol,
                    drift,
                    threshold_pct,
                )
                return True
        return False
