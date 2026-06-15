"""Carry Trade Optimizer — finds highest-yielding delta-neutral carry positions."""

from dataclasses import dataclass
from datetime import datetime, timezone

import asyncio
import httpx
import numpy as np

from app.core.logging import get_logger

logger = get_logger(__name__)

# Binance Futures base URL (production)
_BINANCE_FAPI_BASE = "https://fapi.binance.com"
_PREMIUM_INDEX_URL = f"{_BINANCE_FAPI_BASE}/fapi/v1/premiumIndex"
_KLINES_URL = f"{_BINANCE_FAPI_BASE}/fapi/v1/klines"

# Funding rate is paid / received every 8 hours on Binance perpetuals
_FUNDING_PERIODS_PER_YEAR = 3 * 365  # 3 per day × 365 days


@dataclass
class CarryOpportunity:
    """A single identified carry trade opportunity."""

    symbol: str
    funding_rate_8h: float        # current 8h funding rate (signed, e.g. 0.0005 = 0.05%)
    funding_yield_annual: float   # annualised yield in percent: rate * 3 * 365 * 100
    volatility: float             # annualised historical volatility (fraction)
    risk_adjusted_yield: float    # funding_yield_annual / (volatility * 100 + 1)
    position_recommendation: str  # "LONG_SPOT_SHORT_PERP" or "SHORT_SPOT_LONG_PERP"
    estimated_monthly_pct: float  # monthly income on capital in percent
    entry_spread_cost: float      # estimated bid-ask round-trip cost in percent
    net_yield_after_cost: float   # annual yield minus entry_spread_cost


@dataclass
class CarryPortfolio:
    """Aggregated carry portfolio scan result."""

    opportunities: list[CarryOpportunity]     # all opportunities passing filters
    top_3_by_yield: list[CarryOpportunity]    # highest gross annual yield
    best_risk_adjusted: CarryOpportunity | None  # highest risk-adjusted score
    estimated_portfolio_yield_annual: float   # mean yield of top_3 in percent
    total_capital_needed: float               # placeholder — set by caller
    last_updated: str                         # ISO-8601 UTC timestamp


class CarryTradeOptimizer:
    """Scans Binance perpetual futures for the best delta-neutral carry opportunities.

    Delta-neutral carry
    -------------------
    - Positive funding (longs pay shorts):
      → LONG spot + SHORT perp → earn funding every 8 hours.
    - Negative funding (shorts pay longs):
      → SHORT spot + LONG perp → earn funding every 8 hours.

    Net directional exposure: ~0 (delta-neutral).
    Net income: funding payments.

    Risks
    -----
    - Funding rate can flip — monitor daily and unwind if it does.
    - High volatility can widen the spot/perp spread temporarily (mark-to-market loss).
    - Exchange counterparty risk.
    - Slippage cost to establish and close the position.

    Filters
    -------
    - Minimum annualised yield: ``MIN_ANNUAL_YIELD`` (default 20%).
    - Minimum risk-adjusted score: ``MIN_RISK_ADJ_SCORE`` (default 0.5).
    """

    MIN_ANNUAL_YIELD: float = 20.0   # minimum annualised yield to consider
    MIN_RISK_ADJ_SCORE: float = 0.5  # minimum yield/volatility ratio
    KLINES_LIMIT: int = 30           # number of daily candles for volatility
    EST_SPREAD_COST_PCT: float = 0.06  # estimated round-trip spread cost (%)

    async def scan(
        self, symbols: list[str] | None = None
    ) -> CarryPortfolio:
        """Scan all (or a subset of) Binance perpetual futures for carry opportunities.

        Steps
        -----
        1. Fetch current funding rates for all symbols.
        2. Fetch recent price data to estimate volatility.
        3. Calculate annualised yield and risk-adjusted score.
        4. Filter by ``MIN_ANNUAL_YIELD`` and ``MIN_RISK_ADJ_SCORE``.
        5. Sort by ``risk_adjusted_yield`` descending.
        6. Return portfolio with top opportunities.

        Args:
            symbols: Optional list of specific symbols to scan (e.g. ``["BTCUSDT"]``).
                     If ``None``, scans all symbols returned by the Binance endpoint.

        Returns:
            CarryPortfolio with ranked opportunities.
        """
        # Step 1: fetch funding rates
        try:
            all_funding = await self._fetch_all_funding_rates()
        except Exception as exc:
            logger.error("CarryTradeOptimizer.scan: failed to fetch funding rates: %s", exc)
            return self._empty_portfolio()

        if symbols:
            all_funding = {
                s: r for s, r in all_funding.items() if s in symbols
            }

        if not all_funding:
            logger.warning("CarryTradeOptimizer.scan: no funding rate data — empty portfolio")
            return self._empty_portfolio()

        # Step 2 + 3: compute volatility and build opportunities concurrently
        # Limit concurrency to avoid rate-limiting
        semaphore = asyncio.Semaphore(10)

        async def _build_opportunity(sym: str, rate: float) -> CarryOpportunity | None:
            async with semaphore:
                return await self._build_carry_opportunity(sym, rate)

        tasks = [_build_opportunity(sym, rate) for sym, rate in all_funding.items()]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        opportunities: list[CarryOpportunity] = []
        for res in results:
            if isinstance(res, Exception):
                logger.debug("CarryTradeOptimizer: opportunity build error: %s", res)
                continue
            if res is None:
                continue
            opportunities.append(res)

        # Step 4: apply filters
        filtered = [
            o for o in opportunities
            if o.funding_yield_annual >= self.MIN_ANNUAL_YIELD
            and o.risk_adjusted_yield >= self.MIN_RISK_ADJ_SCORE
        ]

        # Step 5: sort by risk-adjusted yield
        filtered.sort(key=lambda o: o.risk_adjusted_yield, reverse=True)

        top_3 = filtered[:3]
        best_risk_adj = filtered[0] if filtered else None
        est_portfolio_yield = (
            float(np.mean([o.funding_yield_annual for o in top_3])) if top_3 else 0.0
        )

        logger.info(
            "CarryTradeOptimizer.scan: %d symbols scanned, %d opportunities found, top_yield=%.1f%%",
            len(all_funding),
            len(filtered),
            est_portfolio_yield,
        )

        return CarryPortfolio(
            opportunities=filtered,
            top_3_by_yield=top_3,
            best_risk_adjusted=best_risk_adj,
            estimated_portfolio_yield_annual=round(est_portfolio_yield, 2),
            total_capital_needed=0.0,  # caller sets based on their capital
            last_updated=datetime.now(timezone.utc).isoformat(),
        )

    async def _fetch_all_funding_rates(self) -> dict[str, float]:
        """Fetch current funding rates for all Binance perpetual futures.

        Uses ``GET /fapi/v1/premiumIndex`` which returns funding rates for all symbols
        in a single request (no authentication required).

        Returns:
            Dict mapping symbol → current funding rate (float, e.g. 0.0005).
        """
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(_PREMIUM_INDEX_URL)
            response.raise_for_status()
            data = response.json()

        rates: dict[str, float] = {}
        for item in data:
            symbol = item.get("symbol", "")
            rate_str = item.get("lastFundingRate", "0")
            if not symbol or not rate_str:
                continue
            try:
                rates[symbol] = float(rate_str)
            except (ValueError, TypeError):
                pass

        logger.debug("CarryTradeOptimizer: fetched funding rates for %d symbols", len(rates))
        return rates

    async def _fetch_volatility(self, symbol: str) -> float:
        """Fetch recent daily klines and calculate annualised historical volatility.

        Args:
            symbol: Binance perp symbol (e.g. ``"BTCUSDT"``).

        Returns:
            Annualised HV as a fraction (e.g. 0.60 = 60%).  Returns 0.5 on error
            (conservative fallback — not zero, to avoid division by near-zero).
        """
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                response = await client.get(
                    _KLINES_URL,
                    params={
                        "symbol": symbol,
                        "interval": "1d",
                        "limit": self.KLINES_LIMIT,
                    },
                )
                response.raise_for_status()
                klines = response.json()

            if len(klines) < 5:
                return 0.5  # conservative default

            closes = np.array([float(k[4]) for k in klines], dtype=float)
            log_returns = np.diff(np.log(closes))
            std = float(np.std(log_returns, ddof=1))
            annualised = std * np.sqrt(365)
            return float(np.clip(annualised, 0.01, 5.0))  # clamp to [1%, 500%]

        except Exception as exc:
            logger.debug("CarryTradeOptimizer._fetch_volatility %s: %s", symbol, exc)
            return 0.5  # conservative fallback

    async def _build_carry_opportunity(
        self, symbol: str, funding_rate_8h: float
    ) -> CarryOpportunity | None:
        """Build a CarryOpportunity from funding rate and volatility data.

        Args:
            symbol: Binance perpetual symbol.
            funding_rate_8h: Current 8-hour funding rate.

        Returns:
            CarryOpportunity or ``None`` if data is unavailable.
        """
        volatility = await self._fetch_volatility(symbol)
        annual_yield_pct = abs(funding_rate_8h) * _FUNDING_PERIODS_PER_YEAR * 100
        risk_adjusted = self._calc_risk_adjusted_yield(funding_rate_8h, volatility)
        position_rec = self._recommend_position(funding_rate_8h)
        monthly_pct = annual_yield_pct / 12.0
        net_yield = annual_yield_pct - self.EST_SPREAD_COST_PCT

        return CarryOpportunity(
            symbol=symbol,
            funding_rate_8h=round(funding_rate_8h, 8),
            funding_yield_annual=round(annual_yield_pct, 4),
            volatility=round(volatility, 6),
            risk_adjusted_yield=round(risk_adjusted, 4),
            position_recommendation=position_rec,
            estimated_monthly_pct=round(monthly_pct, 4),
            entry_spread_cost=self.EST_SPREAD_COST_PCT,
            net_yield_after_cost=round(net_yield, 4),
        )

    def _calc_risk_adjusted_yield(
        self, funding_8h: float, volatility: float
    ) -> float:
        """Calculate risk-adjusted carry yield (Sharpe-like ratio).

        Formula: ``annual_yield_pct / (volatility * 100 + 1)``

        The ``+ 1`` prevents division by near-zero for very low-volatility assets.

        Args:
            funding_8h: 8-hour funding rate (signed float).
            volatility: Annualised volatility as a fraction.

        Returns:
            Risk-adjusted yield score (higher is better).
        """
        annual_yield_pct = abs(funding_8h) * _FUNDING_PERIODS_PER_YEAR * 100
        denominator = volatility * 100 + 1.0
        return annual_yield_pct / denominator

    def _recommend_position(self, funding_8h: float) -> str:
        """Determine the correct delta-neutral position for a given funding rate.

        When funding is positive (longs pay shorts):
          → LONG spot + SHORT perp — you are the "short" and earn the funding.
        When funding is negative (shorts pay longs):
          → SHORT spot + LONG perp — you are the "long" and earn the funding.

        Args:
            funding_8h: Current 8-hour funding rate (signed).

        Returns:
            Position recommendation string.
        """
        if funding_8h >= 0:
            return "LONG_SPOT_SHORT_PERP"
        return "SHORT_SPOT_LONG_PERP"

    async def monitor_flip(self, opportunity: CarryOpportunity) -> bool:
        """Check whether the funding rate for a held position has flipped direction.

        A flip means the position is now paying funding instead of earning it,
        which is an unwind signal.

        Args:
            opportunity: The CarryOpportunity established when the position was opened.

        Returns:
            ``True`` if the funding rate has flipped sign (unwind recommended).
            ``False`` if direction is unchanged or data is unavailable.
        """
        try:
            current_rates = await self._fetch_all_funding_rates()
        except Exception as exc:
            logger.warning("CarryTradeOptimizer.monitor_flip: fetch failed: %s", exc)
            return False  # assume no flip on error — safer than unwinding blindly

        current_rate = current_rates.get(opportunity.symbol)
        if current_rate is None:
            logger.warning(
                "CarryTradeOptimizer.monitor_flip: symbol %s not found in current rates",
                opportunity.symbol,
            )
            return False

        original_positive = opportunity.funding_rate_8h >= 0
        current_positive = current_rate >= 0

        flipped = original_positive != current_positive
        if flipped:
            logger.warning(
                "CarryTradeOptimizer.monitor_flip: FUNDING FLIP for %s — "
                "original=%.6f current=%.6f — UNWIND POSITION",
                opportunity.symbol,
                opportunity.funding_rate_8h,
                current_rate,
            )
        else:
            logger.debug(
                "CarryTradeOptimizer.monitor_flip: %s no flip (original=%.6f current=%.6f)",
                opportunity.symbol,
                opportunity.funding_rate_8h,
                current_rate,
            )

        return flipped

    @staticmethod
    def _empty_portfolio() -> CarryPortfolio:
        """Return an empty portfolio for error / no-data conditions."""
        return CarryPortfolio(
            opportunities=[],
            top_3_by_yield=[],
            best_risk_adjusted=None,
            estimated_portfolio_yield_annual=0.0,
            total_capital_needed=0.0,
            last_updated=datetime.now(timezone.utc).isoformat(),
        )
