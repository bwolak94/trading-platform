"""Perpetual/Spot Basis Arbitrage — trades convergence of perp vs spot price."""

import pandas as pd

from app.ai.strategies.base import BaseStrategy, MarketContext, SignalResult
from app.core.logging import get_logger

logger = get_logger(__name__)


class BasisArbitrageStrategy(BaseStrategy):
    """Trades the convergence of perpetual futures price vs spot price.

    Entry logic
    -----------
    ``basis = (perp_price - spot_price) / spot_price``

    - basis > +ENTRY_THRESHOLD  → perp is at a premium → SHORT signal
      (sell the overpriced perp / buy the underpriced spot)
    - basis < -ENTRY_THRESHOLD  → perp is at a discount → LONG signal
      (buy the cheap perp / sell the expensive spot)

    Exit targets
    ------------
    - TP1 / TP2  : basis closes to ENTRY_THRESHOLD / 3 (convergence)
    - Stop loss  : basis widens by 2× the entry threshold (momentum break)

    Expected edge
    -------------
    - 0.2–0.5% return per trade when basis closes within 2–8 hours.
    - Additional income from positive funding while holding.

    Fallback
    --------
    When ``spot_price`` is not available in ``market_data`` the latest
    ``close`` column is used as a spot proxy.  If ``funding_rate`` is
    provided it is used to estimate an approximate basis.

    Data requirements
    -----------------
    ``market_data`` should contain (at least one of):
    - Columns ``spot_price`` and ``perp_price`` (explicit basis)
    - Column ``funding_rate`` (funding-based basis estimation)
    - Column ``close`` (fallback proxy for spot price)
    """

    name: str = "basis_arbitrage"
    supported_regimes: list[str] = [
        "TREND_BULL",
        "TREND_BEAR",
        "CONSOLIDATION",
        "HIGH_VOL_CHOPPY",
    ]
    min_confidence: float = 60.0

    ENTRY_THRESHOLD: float = 0.003   # 0.30% basis required to enter
    EXIT_THRESHOLD: float = 0.0005   # 0.05% basis = convergence target
    MAX_HOLD_HOURS: int = 12          # force exit if basis has not closed

    def generate_signal(
        self,
        asset: str,
        timeframe: str,
        market_data: pd.DataFrame,
        context: MarketContext,
    ) -> SignalResult | None:
        """Analyse basis data and return a convergence trade signal if conditions are met.

        Steps
        -----
        1. Extract spot and perp prices (with fallbacks).
        2. Calculate current basis.
        3. If |basis| > ENTRY_THRESHOLD: generate directional signal.
        4. Confidence = min(100, 60 + abs(basis) * 10 000).
        5. Set TP target at basis / 3 convergence, SL at 2× entry threshold widening.

        Args:
            asset: Instrument symbol.
            timeframe: Candle timeframe string (not critical for this strategy).
            market_data: OHLCV DataFrame, optionally with ``spot_price``,
                         ``perp_price``, and / or ``funding_rate`` columns.
            context: Current MarketContext (regime etc.).

        Returns:
            SignalResult if a valid basis arb setup is found, otherwise ``None``.
        """
        if market_data is None or market_data.empty:
            logger.debug("BasisArbitrageStrategy: empty market_data for %s", asset)
            return None

        # --- 1. Extract prices ---
        spot_price, perp_price, basis = self._extract_basis(market_data)
        if spot_price is None or perp_price is None:
            logger.debug(
                "BasisArbitrageStrategy: cannot determine basis for %s — no signal",
                asset,
            )
            return None

        logger.debug(
            "BasisArbitrageStrategy: %s spot=%.6f perp=%.6f basis=%.5f (%.4f%%)",
            asset,
            spot_price,
            perp_price,
            basis,
            basis * 100,
        )

        # --- 2. Check entry threshold ---
        abs_basis = abs(basis)
        if abs_basis < self.ENTRY_THRESHOLD:
            logger.debug(
                "BasisArbitrageStrategy: basis %.4f%% below threshold %.4f%% for %s — no signal",
                abs_basis * 100,
                self.ENTRY_THRESHOLD * 100,
                asset,
            )
            return None

        # --- 3. Determine direction ---
        # Positive basis (perp > spot) → SHORT (sell premium, expect convergence down)
        # Negative basis (perp < spot) → LONG (buy discount, expect convergence up)
        direction = "SHORT" if basis > 0 else "LONG"

        # --- 4. Confidence ---
        confidence = min(100.0, 60.0 + abs_basis * 10_000)

        # --- 5. Price levels ---
        # Entry: current perp price (or spot close as proxy)
        entry_price = float(perp_price)

        # Convergence target: basis shrinks to EXIT_THRESHOLD
        # For SHORT: perp falls → TP is below entry
        # For LONG:  perp rises → TP is above entry
        convergence_distance = (abs_basis - self.EXIT_THRESHOLD) * spot_price

        # TP1 = full convergence (EXIT_THRESHOLD)
        # TP2 = slight over-shoot (partial over-convergence by 50%)
        if direction == "SHORT":
            tp1 = entry_price - convergence_distance
            tp2 = entry_price - convergence_distance * 1.5
            # SL: basis widens by 2× entry threshold
            sl_distance = 2 * self.ENTRY_THRESHOLD * spot_price
            stop_loss = entry_price + sl_distance
        else:  # LONG
            tp1 = entry_price + convergence_distance
            tp2 = entry_price + convergence_distance * 1.5
            sl_distance = 2 * self.ENTRY_THRESHOLD * spot_price
            stop_loss = entry_price - sl_distance

        risk_reward = (
            round(abs(tp1 - entry_price) / abs(stop_loss - entry_price), 2)
            if abs(stop_loss - entry_price) > 0
            else 0.0
        )

        # Require a minimum R:R of 1:1 — basis arb should be low risk
        if risk_reward < 1.0:
            logger.debug(
                "BasisArbitrageStrategy: R:R %.2f < 1.0 for %s — no signal",
                risk_reward,
                asset,
            )
            return None

        factors = [
            {
                "name": "basis_pct",
                "value": round(basis * 100, 4),
                "description": (
                    f"Perp {'premium' if basis > 0 else 'discount'} vs spot: "
                    f"{abs_basis * 100:.3f}%"
                ),
            },
            {
                "name": "entry_threshold_pct",
                "value": self.ENTRY_THRESHOLD * 100,
                "description": f"Entry threshold: {self.ENTRY_THRESHOLD * 100:.2f}%",
            },
            {
                "name": "convergence_target_pct",
                "value": self.EXIT_THRESHOLD * 100,
                "description": f"Target basis at close: {self.EXIT_THRESHOLD * 100:.3f}%",
            },
            {
                "name": "max_hold_hours",
                "value": self.MAX_HOLD_HOURS,
                "description": f"Force exit after {self.MAX_HOLD_HOURS}h if no convergence",
            },
        ]

        signal = SignalResult(
            asset=asset,
            timeframe=timeframe,
            direction=direction,
            confidence=round(confidence, 2),
            entry_price=round(entry_price, 8),
            stop_loss=round(stop_loss, 8),
            take_profit_1=round(tp1, 8),
            take_profit_2=round(tp2, 8),
            risk_reward=risk_reward,
            factors=factors,
            strategy_name=self.name,
        )

        logger.info(
            "BasisArbitrageStrategy: %s %s signal — basis=%.4f%% conf=%.1f R:R=%.2f",
            asset,
            direction,
            basis * 100,
            confidence,
            risk_reward,
        )
        return signal

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _extract_basis(
        self, df: pd.DataFrame
    ) -> tuple[float | None, float | None, float]:
        """Extract spot price, perp price, and basis from the DataFrame.

        Priority order
        --------------
        1. Explicit ``spot_price`` + ``perp_price`` columns.
        2. ``close`` as spot proxy + ``perp_price`` column.
        3. ``close`` as spot proxy + funding-rate-derived basis estimate.
        4. Returns (None, None, 0.0) if none of the above are available.

        Args:
            df: OHLCV DataFrame with optional extra columns.

        Returns:
            Tuple of (spot_price, perp_price, basis).
            ``basis = (perp - spot) / spot``
        """
        latest = df.iloc[-1]
        close = float(latest["close"]) if "close" in df.columns else None

        # Path 1: explicit spot + perp
        if "spot_price" in df.columns and "perp_price" in df.columns:
            spot = float(latest["spot_price"])
            perp = float(latest["perp_price"])
            if spot > 0:
                basis = (perp - spot) / spot
                return (spot, perp, basis)

        # Path 2: close as spot, explicit perp
        if close is not None and "perp_price" in df.columns:
            perp = float(latest["perp_price"])
            if close > 0:
                basis = (perp - close) / close
                return (close, perp, basis)

        # Path 3: estimate basis from funding rate
        # Funding rate per 8h → approximate 8h premium
        # basis ≈ funding_rate (same sign convention)
        if close is not None and "funding_rate" in df.columns:
            funding = float(latest["funding_rate"])
            # Estimate perp price from funding
            estimated_perp = close * (1 + funding)
            return (close, estimated_perp, funding)

        # Path 4: no basis data available
        return (None, None, 0.0)
