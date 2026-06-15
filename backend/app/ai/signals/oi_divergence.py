"""Open Interest Divergence Signal — detects OI/price divergences."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)

FUTURES_REST_URL = "https://fapi.binance.com"

# Shared HTTP client for connection pooling
_shared_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    """Return a shared httpx.AsyncClient with connection pooling."""
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        _shared_client = httpx.AsyncClient(
            timeout=15.0,
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
        )
    return _shared_client


@dataclass
class OIDivergenceSignal:
    """Result of an Open Interest divergence analysis."""

    symbol: str
    signal_type: str        # "DISTRIBUTION" (bearish) | "ACCUMULATION" (bullish) | "NEUTRAL"
    direction: str          # "SHORT" | "LONG" | "NEUTRAL"
    confidence: float       # 0-100
    oi_change_pct: float    # OI change over lookback period (%)
    price_change_pct: float # price change over lookback period (%)
    divergence_strength: str  # "WEAK", "MODERATE", "STRONG"
    description: str


class OIDivergenceAnalyzer:
    """Detects Open Interest / Price divergences.

    Key patterns:
    - DISTRIBUTION: OI rising strongly + price falling → short sellers adding → bearish
    - ACCUMULATION: OI rising strongly + price rising → longs adding → bullish (trend continuation)
    - SHORT_SQUEEZE:  OI falling + price rising fast → shorts covering → LONG momentum
    - LONG_LIQUIDATION: OI falling + price falling fast → longs being liquidated → SHORT momentum
    """

    # >3% OI change in the look-back period is considered significant
    OI_SIGNIFICANT_CHANGE_PCT: float = 3.0

    def analyze(
        self,
        symbol: str,
        oi_history: list[dict],
        price_history: list[dict],
        lookback_periods: int = 24,
    ) -> OIDivergenceSignal:
        """Compare OI change vs price change over *lookback_periods*.

        Expects both lists sorted chronologically (oldest first).

        Pattern matrix:
        - OI UP   + Price UP   → ACCUMULATION   (LONG,  moderate confidence)
        - OI UP   + Price DOWN → DISTRIBUTION   (SHORT, high confidence)
        - OI DOWN + Price UP   → SHORT_SQUEEZE  (LONG,  high confidence)
        - OI DOWN + Price DOWN → LONG_LIQUIDATION (SHORT, moderate confidence)

        Confidence scales with the absolute magnitude of the two moves and is
        further boosted when the divergence between OI and price direction is
        large (i.e. strong divergence = higher predictive value).

        Args:
            symbol: Trading pair symbol, e.g. "BTCUSDT".
            oi_history: List of dicts with keys ``open_interest`` (float) and
                ``timestamp`` (int ms).  Sorted oldest → newest.
            price_history: List of dicts with keys ``close`` (float) and
                ``timestamp`` (int ms).  Sorted oldest → newest.
            lookback_periods: How many periods to examine (default 24 hours).

        Returns:
            :class:`OIDivergenceSignal` describing the detected pattern.
        """
        neutral = OIDivergenceSignal(
            symbol=symbol,
            signal_type="NEUTRAL",
            direction="NEUTRAL",
            confidence=0.0,
            oi_change_pct=0.0,
            price_change_pct=0.0,
            divergence_strength="WEAK",
            description="Insufficient data for OI divergence analysis.",
        )

        if len(oi_history) < 2 or len(price_history) < 2:
            logger.warning("OIDivergenceAnalyzer: insufficient history for %s", symbol)
            return neutral

        # Trim to lookback window
        oi_window = oi_history[-lookback_periods:]
        price_window = price_history[-lookback_periods:]

        try:
            oi_start = float(oi_window[0]["open_interest"])
            oi_end = float(oi_window[-1]["open_interest"])
            price_start = float(price_window[0]["close"])
            price_end = float(price_window[-1]["close"])
        except (KeyError, TypeError, ValueError) as exc:
            logger.error("OIDivergenceAnalyzer: bad data format for %s: %s", symbol, exc)
            return neutral

        if oi_start == 0 or price_start == 0:
            return neutral

        oi_change_pct = (oi_end - oi_start) / oi_start * 100.0
        price_change_pct = (price_end - price_start) / price_start * 100.0

        oi_up = oi_change_pct > 0
        price_up = price_change_pct > 0

        # Magnitude-based base confidence (0-60 range before boost)
        oi_magnitude = min(abs(oi_change_pct) / 10.0, 1.0)      # normalise to 0-1
        price_magnitude = min(abs(price_change_pct) / 5.0, 1.0)  # normalise to 0-1
        base_confidence = (oi_magnitude + price_magnitude) / 2.0 * 60.0

        # Divergence strength classification
        divergence_score = abs(oi_change_pct - price_change_pct)
        if divergence_score < 3.0:
            divergence_strength = "WEAK"
            divergence_boost = 0.0
        elif divergence_score < 8.0:
            divergence_strength = "MODERATE"
            divergence_boost = 15.0
        else:
            divergence_strength = "STRONG"
            divergence_boost = 30.0

        if oi_up and price_up:
            # Both rising: bulls adding, trend continuation
            signal_type = "ACCUMULATION"
            direction = "LONG"
            confidence = round(min(base_confidence + 10.0, 80.0), 2)
            description = (
                f"ACCUMULATION: OI +{oi_change_pct:.1f}% with price "
                f"+{price_change_pct:.1f}% — longs building, trend continuation likely."
            )

        elif oi_up and not price_up:
            # OI rising but price falling: short sellers adding aggressively
            signal_type = "DISTRIBUTION"
            direction = "SHORT"
            confidence = round(min(base_confidence + divergence_boost + 15.0, 90.0), 2)
            description = (
                f"DISTRIBUTION: OI +{oi_change_pct:.1f}% but price "
                f"{price_change_pct:.1f}% — short sellers increasing positions, bearish pressure."
            )

        elif not oi_up and price_up:
            # OI falling while price rising: shorts covering (squeeze)
            signal_type = "SHORT_SQUEEZE"
            direction = "LONG"
            confidence = round(min(base_confidence + divergence_boost + 15.0, 90.0), 2)
            description = (
                f"SHORT_SQUEEZE: OI {oi_change_pct:.1f}% but price "
                f"+{price_change_pct:.1f}% — shorts closing, squeeze momentum upward."
            )

        else:
            # Both falling: longs being liquidated
            signal_type = "LONG_LIQUIDATION"
            direction = "SHORT"
            confidence = round(min(base_confidence + 10.0, 80.0), 2)
            description = (
                f"LONG_LIQUIDATION: OI {oi_change_pct:.1f}% with price "
                f"{price_change_pct:.1f}% — long positions being closed/liquidated."
            )

        logger.info(
            "OI divergence for %s: type=%s direction=%s conf=%.1f oi_chg=%.1f%% price_chg=%.1f%%",
            symbol, signal_type, direction, confidence, oi_change_pct, price_change_pct,
        )

        return OIDivergenceSignal(
            symbol=symbol,
            signal_type=signal_type,
            direction=direction,
            confidence=confidence,
            oi_change_pct=round(oi_change_pct, 3),
            price_change_pct=round(price_change_pct, 3),
            divergence_strength=divergence_strength,
            description=description,
        )

    async def fetch_oi_data(self, symbol: str, limit: int = 48) -> list[dict]:
        """Fetch Open Interest history from Binance Futures.

        Calls ``GET https://fapi.binance.com/futures/data/openInterestHist``
        with ``period=1h``.

        Args:
            symbol: Binance futures symbol, e.g. ``"BTCUSDT"``.
            limit: Number of hourly data points to retrieve (max 500).

        Returns:
            List of dicts with keys ``timestamp`` (int ms), ``open_interest`` (float),
            and ``open_interest_value`` (float).  Returns empty list on failure.
        """
        client = _get_client()
        try:
            resp = await client.get(
                f"{FUTURES_REST_URL}/futures/data/openInterestHist",
                params={"symbol": symbol.upper(), "period": "1h", "limit": limit},
            )
            resp.raise_for_status()
            raw = resp.json()
            data = [
                {
                    "timestamp": int(item["timestamp"]),
                    "open_interest": float(item["sumOpenInterest"]),
                    "open_interest_value": float(item["sumOpenInterestValue"]),
                }
                for item in raw
            ]
            logger.debug("Fetched %d OI data points for %s", len(data), symbol)
            return data
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Binance OI history HTTP error for %s: %d — %s",
                symbol, exc.response.status_code, exc.response.text[:200],
            )
            return []
        except httpx.RequestError as exc:
            logger.warning("Binance OI history request error for %s: %s", symbol, exc)
            return []
        except Exception as exc:
            logger.error("Unexpected error fetching OI data for %s: %s", symbol, exc)
            return []
