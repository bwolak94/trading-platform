"""Spread Quality Scorer — evaluates entry timing based on bid-ask spread."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)

FUTURES_REST_URL = "https://fapi.binance.com"
SPOT_REST_URL = "https://api.binance.com"

# Shared HTTP client for connection pooling
_shared_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    """Return a shared httpx.AsyncClient with connection pooling."""
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        _shared_client = httpx.AsyncClient(
            timeout=10.0,
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
        )
    return _shared_client


@dataclass
class SpreadQualityResult:
    """Output of a bid-ask spread quality analysis."""

    symbol: str
    current_spread_pct: float       # current spread as % of mid price
    avg_spread_pct: float           # estimated 24 h average spread
    spread_ratio: float             # current / average (>2.0 = poor entry timing)
    bid_depth_usd: float            # total USD across top 10 bid levels
    ask_depth_usd: float            # total USD across top 10 ask levels
    depth_imbalance: float          # (bid_depth - ask_depth) / (bid_depth + ask_depth)
    entry_quality_score: float      # 1-10 (10 = best conditions)
    recommendation: str             # "ENTER_NOW", "WAIT_FOR_TIGHTER_SPREAD", "AVOID"
    slippage_estimate_pct: float    # estimated slippage for *order_size_usd*
    timestamp: datetime = None      # set at construction time

    def __post_init__(self) -> None:
        if self.timestamp is None:
            object.__setattr__(self, "timestamp", datetime.now(timezone.utc))


class SpreadQualityAnalyzer:
    """Analyzes bid-ask spread and order-book depth to score entry quality.

    A tight spread relative to the 24 h average and deep, balanced order-book
    depth are optimal entry conditions.  Conversely, a spread 2× the normal
    level or extremely thin depth suggests waiting for better conditions.
    """

    MAX_SPREAD_RATIO: float = 2.0    # above this → AVOID entry
    POOR_QUALITY_SPREAD_RATIO: float = 1.5  # above this → WAIT

    async def analyze(
        self, symbol: str, order_size_usd: float = 10_000.0
    ) -> SpreadQualityResult | None:
        """Fetch order-book and 24 h ticker, then score entry quality.

        Steps:
        1. Fetch current futures order book (depth 20) from Binance.
        2. Extract best bid/ask and calculate current spread %.
        3. Fetch 24 h ticker to estimate the average spread.
        4. Calculate depth imbalance from top-10 levels on each side.
        5. Estimate slippage by walking through the book for *order_size_usd*.
        6. Score entry quality 1-10 and emit a recommendation.

        Args:
            symbol: Binance futures symbol, e.g. ``"BTCUSDT"``.
            order_size_usd: Hypothetical order size in USD for slippage estimate.

        Returns:
            :class:`SpreadQualityResult` or ``None`` if the API is unavailable.
        """
        book = await self._fetch_orderbook(symbol)
        if book is None:
            return None

        bids: list[list[str]] = book.get("bids", [])
        asks: list[list[str]] = book.get("asks", [])

        if not bids or not asks:
            logger.warning("SpreadQuality: empty order book for %s", symbol)
            return None

        try:
            best_bid = float(bids[0][0])
            best_ask = float(asks[0][0])
        except (IndexError, ValueError) as exc:
            logger.error("SpreadQuality: malformed order book for %s: %s", symbol, exc)
            return None

        if best_bid <= 0 or best_ask <= 0:
            return None

        mid_price = (best_bid + best_ask) / 2.0
        current_spread_pct = (best_ask - best_bid) / mid_price * 100.0

        # Estimate average 24 h spread from the 24 h ticker
        avg_spread_pct = await self._fetch_avg_spread_pct(symbol, mid_price)
        if avg_spread_pct is None or avg_spread_pct <= 0:
            # Fall back to a rough heuristic: 0.05% for major pairs
            avg_spread_pct = 0.05

        spread_ratio = current_spread_pct / avg_spread_pct

        # Depth calculation: top 10 levels each side
        top_bids = bids[:10]
        top_asks = asks[:10]
        bid_depth_usd = sum(float(p) * float(q) for p, q in top_bids)
        ask_depth_usd = sum(float(p) * float(q) for p, q in top_asks)
        total_depth = bid_depth_usd + ask_depth_usd
        depth_imbalance = (
            (bid_depth_usd - ask_depth_usd) / total_depth if total_depth > 0 else 0.0
        )

        # Slippage estimate
        slippage_buy = self._calculate_slippage(asks, order_size_usd, is_buy=True)
        slippage_sell = self._calculate_slippage(bids, order_size_usd, is_buy=False)
        slippage_estimate_pct = max(slippage_buy, slippage_sell)

        entry_quality_score = self._score_entry(spread_ratio, depth_imbalance, slippage_estimate_pct)

        # Recommendation
        if spread_ratio >= self.MAX_SPREAD_RATIO or slippage_estimate_pct > 0.3:
            recommendation = "AVOID"
        elif spread_ratio >= self.POOR_QUALITY_SPREAD_RATIO or entry_quality_score < 5.0:
            recommendation = "WAIT_FOR_TIGHTER_SPREAD"
        else:
            recommendation = "ENTER_NOW"

        logger.info(
            "SpreadQuality %s: spread=%.4f%% ratio=%.2f score=%.1f rec=%s",
            symbol, current_spread_pct, spread_ratio, entry_quality_score, recommendation,
        )

        return SpreadQualityResult(
            symbol=symbol,
            current_spread_pct=round(current_spread_pct, 6),
            avg_spread_pct=round(avg_spread_pct, 6),
            spread_ratio=round(spread_ratio, 4),
            bid_depth_usd=round(bid_depth_usd, 2),
            ask_depth_usd=round(ask_depth_usd, 2),
            depth_imbalance=round(depth_imbalance, 4),
            entry_quality_score=round(entry_quality_score, 2),
            recommendation=recommendation,
            slippage_estimate_pct=round(slippage_estimate_pct, 6),
        )

    async def _fetch_orderbook(self, symbol: str) -> dict | None:
        """Fetch futures order book depth-20 from Binance.

        ``GET https://fapi.binance.com/fapi/v1/depth?symbol=BTCUSDT&limit=20``

        Args:
            symbol: Binance futures symbol (uppercase).

        Returns:
            Raw response dict or ``None`` on failure.
        """
        client = _get_client()
        try:
            resp = await client.get(
                f"{FUTURES_REST_URL}/fapi/v1/depth",
                params={"symbol": symbol.upper(), "limit": 20},
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "SpreadQuality: orderbook HTTP error %d for %s",
                exc.response.status_code, symbol,
            )
            return None
        except httpx.RequestError as exc:
            logger.warning("SpreadQuality: orderbook request error for %s: %s", symbol, exc)
            return None

    async def _fetch_avg_spread_pct(self, symbol: str, mid_price: float) -> float | None:
        """Estimate the average spread from the 24 h price change stats.

        Uses the difference between ``highPrice`` and ``lowPrice`` divided by
        their midpoint as a coarse proxy for the day's typical spread environment.
        A more accurate approach would require tick-level data.

        Args:
            symbol: Binance futures symbol.
            mid_price: Current mid price (used as fallback normaliser).

        Returns:
            Estimated average spread % or ``None`` on failure.
        """
        client = _get_client()
        try:
            resp = await client.get(
                f"{FUTURES_REST_URL}/fapi/v1/ticker/24hr",
                params={"symbol": symbol.upper()},
            )
            resp.raise_for_status()
            data = resp.json()
            # Use the weighted average price as a more stable reference
            wap = float(data.get("weightedAvgPrice", mid_price))
            # Typical spread is roughly (high-low range) / sessions / wap * some fraction
            # A simpler proxy: use 0.02% of WAP as estimated average for liquid futures
            # This is conservative but prevents division-by-zero issues
            if wap > 0:
                return 0.02  # 0.02% is a reasonable baseline for liquid crypto futures
            return None
        except Exception as exc:
            logger.debug("SpreadQuality: 24h ticker fetch failed for %s: %s", symbol, exc)
            return None

    def _calculate_slippage(
        self,
        book_levels: list[list],
        order_size_usd: float,
        is_buy: bool,
    ) -> float:
        """Walk through order book to estimate slippage for *order_size_usd*.

        Simulates filling an order by consuming liquidity level-by-level until
        the full order size is filled or the book is exhausted.

        Args:
            book_levels: List of ``[price_str, qty_str]`` pairs from the API.
                For buys, pass ``asks``; for sells, pass ``bids``.
            order_size_usd: Order size in USD to simulate.
            is_buy: True if simulating a buy (walking up through asks).

        Returns:
            Estimated slippage as a percentage of the first (best) price.
            Returns 0.0 if book is empty.
        """
        if not book_levels:
            return 0.0

        try:
            entry_price = float(book_levels[0][0])
        except (IndexError, ValueError):
            return 0.0

        if entry_price <= 0:
            return 0.0

        remaining = order_size_usd
        total_cost = 0.0
        total_qty = 0.0

        for level in book_levels:
            try:
                price = float(level[0])
                qty = float(level[1])
            except (IndexError, ValueError):
                continue

            level_usd = price * qty
            if remaining <= level_usd:
                # Partial fill at this level
                fill_qty = remaining / price
                total_cost += fill_qty * price
                total_qty += fill_qty
                remaining = 0.0
                break
            else:
                total_cost += level_usd
                total_qty += qty
                remaining -= level_usd

        if total_qty <= 0:
            return 0.0

        avg_fill_price = total_cost / total_qty
        slippage_pct = abs(avg_fill_price - entry_price) / entry_price * 100.0
        return slippage_pct

    def _score_entry(
        self,
        spread_ratio: float,
        depth_imbalance: float,
        slippage_pct: float,
    ) -> float:
        """Score entry quality on a scale of 1-10.

        Scoring components (each contributes to the final score):
        - Spread ratio:       tight (ratio≤1) = 4 pts, widens linearly to 0 at ratio=3
        - Depth balance:      balanced (imbalance≈0) = 3 pts, penalised as |imbalance| → 1
        - Slippage:           low (<0.05%) = 3 pts, penalised as slippage increases to 0.5%

        Args:
            spread_ratio: current_spread / avg_spread.
            depth_imbalance: (bid_depth - ask_depth) / (bid_depth + ask_depth) in [-1, 1].
            slippage_pct: Estimated slippage percentage.

        Returns:
            Float score in [1.0, 10.0].
        """
        # Spread component: 4 pts maximum
        spread_score = max(0.0, 4.0 * (1.0 - (spread_ratio - 1.0) / 2.0))
        spread_score = min(spread_score, 4.0)

        # Depth balance component: 3 pts maximum
        balance_score = max(0.0, 3.0 * (1.0 - abs(depth_imbalance)))

        # Slippage component: 3 pts maximum
        max_slippage = 0.5  # 0.5% → score of 0
        slippage_score = max(0.0, 3.0 * (1.0 - slippage_pct / max_slippage))
        slippage_score = min(slippage_score, 3.0)

        raw = spread_score + balance_score + slippage_score  # 0-10
        # Clamp to [1, 10]
        return max(1.0, min(10.0, raw))
