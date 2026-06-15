"""Deribit Options Data Fetcher — IV, Greeks, GEX for directional bias.

Fetches options market data from Deribit's public REST API to derive:
  - Implied Volatility rank (current IV vs 52-week range)
  - Put/Call Ratio (contrarian sentiment indicator)
  - Gamma Exposure (GEX) by strike — identifies magnetic price levels
  - Max Pain level — strike where most options expire worthless

All endpoints used are public (no authentication required).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DERIBIT_BASE: Final[str] = "https://www.deribit.com/api/v2/public"
_HTTP_TIMEOUT: Final[float] = 10.0
_IV_HISTORY_ENDPOINT: Final[str] = "/get_volatility_index_data"
_BOOK_SUMMARY_ENDPOINT: Final[str] = "/get_book_summary_by_currency"
_INDEX_PRICE_ENDPOINT: Final[str] = "/get_index_price"
_INSTRUMENT_ENDPOINT: Final[str] = "/get_instruments"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class OptionsData:
    """Aggregated options market data for a single underlying asset."""

    underlying: str          # "BTC" or "ETH"
    iv_rank: float           # 0–100: current IV percentile vs 52-week range
    iv_current: float        # current 30-day implied volatility (%)
    put_call_ratio: float    # volume-based PCR (> 1.2 bearish, < 0.8 bullish)
    gamma_exposure: float    # aggregate GEX in dollars (net dealer gamma)
    max_pain: float          # strike where most options expire worthless
    key_levels: list[float]  # strikes with highest open interest
    term_structure: dict[str, float]  # {"7d": iv, "30d": iv, "90d": iv}

    def __repr__(self) -> str:
        pcr_label = "BEARISH" if self.put_call_ratio > 1.2 else ("BULLISH" if self.put_call_ratio < 0.8 else "NEUTRAL")
        return (
            f"OptionsData(underlying={self.underlying}, iv_rank={self.iv_rank:.1f}, "
            f"iv={self.iv_current:.1f}%, pcr={self.put_call_ratio:.2f}[{pcr_label}], "
            f"max_pain={self.max_pain:.0f})"
        )


# ---------------------------------------------------------------------------
# Fetcher class
# ---------------------------------------------------------------------------


class DeribitFetcher:
    """Fetches options market data from Deribit's public API.

    Uses a shared httpx.AsyncClient per instance for connection reuse.
    Returns None (with a logged warning) if the API is unavailable rather
    than raising, so callers can degrade gracefully.
    """

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Return (or create) the shared async HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=DERIBIT_BASE,
                timeout=_HTTP_TIMEOUT,
                headers={"Accept": "application/json"},
            )
        return self._client

    async def _get(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any] | None:
        """Perform a GET request to a Deribit endpoint.

        Args:
            endpoint: Path relative to DERIBIT_BASE.
            params:   Query parameters.

        Returns:
            Parsed JSON result dict, or None on failure.
        """
        client = await self._get_client()
        url = f"{DERIBIT_BASE}{endpoint}"
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            result = data.get("result")
            if result is None:
                logger.warning(
                    "Deribit API returned no result",
                    extra={"endpoint": endpoint, "error": data.get("error")},
                )
                return None
            return result  # type: ignore[return-value]
        except httpx.TimeoutException:
            logger.warning("Deribit API timeout", extra={"endpoint": endpoint})
            return None
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Deribit API HTTP error",
                extra={"endpoint": endpoint, "status_code": exc.response.status_code},
            )
            return None
        except Exception as exc:
            logger.error(
                "Deribit API unexpected error",
                extra={"endpoint": endpoint, "error": str(exc)},
            )
            return None

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def get_options_summary(self, currency: str = "BTC") -> OptionsData | None:
        """Fetch comprehensive options data for the given currency.

        Steps:
        1. Fetch spot price via get_index_price.
        2. Fetch all option book summaries via get_book_summary_by_currency.
        3. Compute PCR from put/call volumes.
        4. Compute GEX and max pain from open interest.
        5. Build a simple term-structure from near-term expirations.

        Args:
            currency: "BTC" or "ETH".

        Returns:
            OptionsData or None if the API is unavailable.
        """
        currency = currency.upper()
        index_name = f"{currency.lower()}_usd"

        # --- Step 1: Spot price ---
        index_result = await self._get(_INDEX_PRICE_ENDPOINT, {"index_name": index_name})
        if index_result is None:
            logger.warning("Deribit: could not fetch spot price for %s", currency)
            return None
        spot_price = float(index_result.get("index_price", 0.0))
        if spot_price <= 0:
            logger.warning("Deribit: invalid spot price for %s", currency)
            return None

        # --- Step 2: All option book summaries ---
        summaries_result = await self._get(
            _BOOK_SUMMARY_ENDPOINT,
            {"currency": currency, "kind": "option"},
        )
        if summaries_result is None or not isinstance(summaries_result, list):
            logger.warning("Deribit: could not fetch book summaries for %s", currency)
            return None

        summaries: list[dict[str, Any]] = summaries_result  # type: ignore[assignment]

        # --- Step 3: PCR from volume ---
        put_volume = 0.0
        call_volume = 0.0
        put_oi = 0.0
        call_oi = 0.0

        # Aggregate data structures for GEX and max pain
        strike_data: dict[float, dict[str, float]] = {}

        for item in summaries:
            instrument_name: str = item.get("instrument_name", "")
            # Instrument naming: BTC-28MAR25-100000-C  (last char = C/P)
            option_type = "C" if instrument_name.endswith("-C") else "P"
            volume = float(item.get("volume", 0.0))
            oi = float(item.get("open_interest", 0.0))
            mid_iv = float(item.get("mark_iv", 0.0))

            # Extract strike from instrument name (4th segment)
            parts = instrument_name.split("-")
            try:
                strike = float(parts[2]) if len(parts) >= 4 else 0.0
            except (ValueError, IndexError):
                strike = 0.0

            if option_type == "P":
                put_volume += volume
                put_oi += oi
            else:
                call_volume += volume
                call_oi += oi

            if strike > 0:
                if strike not in strike_data:
                    strike_data[strike] = {
                        "call_oi": 0.0,
                        "put_oi": 0.0,
                        "call_iv": 0.0,
                        "put_iv": 0.0,
                    }
                if option_type == "C":
                    strike_data[strike]["call_oi"] += oi
                    if mid_iv > 0:
                        strike_data[strike]["call_iv"] = mid_iv
                else:
                    strike_data[strike]["put_oi"] += oi
                    if mid_iv > 0:
                        strike_data[strike]["put_iv"] = mid_iv

        put_volume + call_volume
        pcr = (put_volume / call_volume) if call_volume > 0 else 1.0

        # --- Step 4: GEX and max pain ---
        gamma_exposure = self._compute_gex(strike_data, spot_price)
        max_pain = self._compute_max_pain(strike_data, spot_price)
        key_levels = self._top_oi_strikes(strike_data, n=5)

        # --- Step 5: IV rank and current IV ---
        iv_rank = await self.get_iv_percentile(currency)
        # Current IV: volume-weighted mean of ATM options
        current_iv = self._atm_iv(strike_data, spot_price)

        # --- Step 6: Simple term structure from ATM options ---
        term_structure = await self._build_term_structure(currency, spot_price, summaries)

        logger.info(
            "Deribit options summary fetched",
            extra={
                "currency": currency,
                "spot": spot_price,
                "pcr": round(pcr, 3),
                "iv_rank": round(iv_rank, 1),
                "max_pain": max_pain,
            },
        )

        return OptionsData(
            underlying=currency,
            iv_rank=round(iv_rank, 1),
            iv_current=round(current_iv, 2),
            put_call_ratio=round(pcr, 3),
            gamma_exposure=round(gamma_exposure, 0),
            max_pain=round(max_pain, 0),
            key_levels=[round(lv, 0) for lv in key_levels],
            term_structure={k: round(v, 2) for k, v in term_structure.items()},
        )

    async def get_iv_percentile(self, currency: str = "BTC", lookback_days: int = 252) -> float:
        """Calculate IV rank: (current_iv - 52w_low) / (52w_high - 52w_low) × 100.

        Uses Deribit's volatility index history endpoint.

        Args:
            currency:      "BTC" or "ETH".
            lookback_days: Number of calendar days of history to fetch.

        Returns:
            IV rank 0–100, or 50.0 as a neutral default if data unavailable.
        """
        currency = currency.upper()
        # Deribit volatility index: DVOL for BTC / ETH
        f"{currency.lower()}_dvol"

        # end_timestamp: now (ms), start_timestamp: lookback_days ago
        import time
        end_ms = int(time.time() * 1000)
        start_ms = end_ms - lookback_days * 86_400 * 1000

        result = await self._get(
            _IV_HISTORY_ENDPOINT,
            {
                "currency": currency,
                "start_timestamp": start_ms,
                "end_timestamp": end_ms,
                "resolution": "1D",
            },
        )

        if result is None:
            logger.warning("Deribit: IV history unavailable for %s, returning 50.0", currency)
            return 50.0

        # Deribit DVOL result: {"data": [[timestamp, open, high, low, close], ...]}
        data_points = result.get("data", [])
        if not data_points:
            return 50.0

        closes = [float(row[4]) for row in data_points if len(row) >= 5]
        if not closes:
            return 50.0

        current_iv = closes[-1]
        iv_high = max(closes)
        iv_low = min(closes)
        iv_range = iv_high - iv_low
        if iv_range < 0.01:
            return 50.0

        rank = (current_iv - iv_low) / iv_range * 100.0
        return round(min(100.0, max(0.0, rank)), 1)

    async def get_gamma_levels(self, currency: str = "BTC") -> list[dict[str, float]]:
        """Calculate Gamma Exposure (GEX) by strike.

        GEX per strike = gamma × open_interest × spot² × contract_size
        Net GEX = call GEX − put GEX  (negative = dealers short gamma = amplified moves)

        Args:
            currency: "BTC" or "ETH".

        Returns:
            List of dicts sorted by |gex| descending:
            {'strike': float, 'gex': float, 'net_gex': float}
        """
        currency = currency.upper()
        index_name = f"{currency.lower()}_usd"

        index_result = await self._get(_INDEX_PRICE_ENDPOINT, {"index_name": index_name})
        spot_price = float((index_result or {}).get("index_price", 0.0))
        if spot_price <= 0:
            return []

        summaries_result = await self._get(
            _BOOK_SUMMARY_ENDPOINT,
            {"currency": currency, "kind": "option"},
        )
        if not summaries_result or not isinstance(summaries_result, list):
            return []

        strike_gex: dict[float, dict[str, float]] = {}

        for item in summaries_result:
            instrument_name: str = item.get("instrument_name", "")
            option_type = "C" if instrument_name.endswith("-C") else "P"
            oi = float(item.get("open_interest", 0.0))
            gamma = float(item.get("greeks", {}).get("gamma", 0.0)) if item.get("greeks") else 0.0

            parts = instrument_name.split("-")
            try:
                strike = float(parts[2]) if len(parts) >= 4 else 0.0
            except (ValueError, IndexError):
                strike = 0.0

            if strike <= 0 or oi <= 0:
                continue

            # GEX contribution = gamma × OI × spot² (standard formula)
            gex_contribution = gamma * oi * (spot_price ** 2)

            if strike not in strike_gex:
                strike_gex[strike] = {"call_gex": 0.0, "put_gex": 0.0}

            if option_type == "C":
                strike_gex[strike]["call_gex"] += gex_contribution
            else:
                # Dealers are short puts → negative gamma contribution
                strike_gex[strike]["put_gex"] += gex_contribution

        result_list = []
        for strike, gex_data in strike_gex.items():
            call_gex = gex_data["call_gex"]
            put_gex = gex_data["put_gex"]
            total_gex = call_gex + put_gex
            net_gex = call_gex - put_gex  # net dealer gamma
            result_list.append({
                "strike": strike,
                "gex": round(total_gex, 2),
                "net_gex": round(net_gex, 2),
            })

        # Sort by absolute GEX descending (highest GEX = strongest magnetic level)
        result_list.sort(key=lambda x: abs(x["gex"]), reverse=True)
        return result_list

    # ------------------------------------------------------------------
    # Private computation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_gex(
        strike_data: dict[float, dict[str, float]],
        spot_price: float,
    ) -> float:
        """Compute aggregate net Gamma Exposure.

        Uses simplified GEX = sum(call_oi - put_oi) × spot² / 100 as a proxy
        when per-strike gamma values are not available from book summaries.
        """
        total_gex = 0.0
        for strike, data in strike_data.items():
            net_oi = data["call_oi"] - data["put_oi"]
            # Proxy: assume gamma ≈ 1/strike for rough scaling
            proxy_gamma = 1.0 / max(strike, 1.0) * 0.01
            total_gex += proxy_gamma * net_oi * (spot_price ** 2)
        return total_gex

    @staticmethod
    def _compute_max_pain(
        strike_data: dict[float, dict[str, float]],
        spot_price: float,
    ) -> float:
        """Find the max pain strike (minimises total option value at expiry).

        For each potential expiry price (= each strike), compute the total
        intrinsic value that would be paid out, then return the strike
        where this total is minimised.
        """
        if not strike_data:
            return spot_price

        strikes = sorted(strike_data.keys())
        min_pain = float("inf")
        max_pain_strike = spot_price

        for test_strike in strikes:
            total_pain = 0.0
            for strike, data in strike_data.items():
                # Call value at expiry = max(test_strike - strike, 0) × call_oi
                call_value = max(test_strike - strike, 0.0) * data["call_oi"]
                # Put value at expiry = max(strike - test_strike, 0) × put_oi
                put_value = max(strike - test_strike, 0.0) * data["put_oi"]
                total_pain += call_value + put_value
            if total_pain < min_pain:
                min_pain = total_pain
                max_pain_strike = test_strike

        return max_pain_strike

    @staticmethod
    def _top_oi_strikes(
        strike_data: dict[float, dict[str, float]],
        n: int = 5,
    ) -> list[float]:
        """Return the N strikes with highest total open interest."""
        if not strike_data:
            return []
        sorted_strikes = sorted(
            strike_data.items(),
            key=lambda kv: kv[1]["call_oi"] + kv[1]["put_oi"],
            reverse=True,
        )
        return [strike for strike, _ in sorted_strikes[:n]]

    @staticmethod
    def _atm_iv(
        strike_data: dict[float, dict[str, float]],
        spot_price: float,
    ) -> float:
        """Return the implied volatility of the most at-the-money strike."""
        if not strike_data:
            return 0.0
        atm_strike = min(strike_data.keys(), key=lambda s: abs(s - spot_price))
        data = strike_data[atm_strike]
        ivs = [v for v in (data.get("call_iv", 0.0), data.get("put_iv", 0.0)) if v > 0]
        return float(sum(ivs) / len(ivs)) if ivs else 0.0

    async def _build_term_structure(
        self,
        currency: str,
        spot_price: float,
        summaries: list[dict[str, Any]],
    ) -> dict[str, float]:
        """Build a simplified term structure from book summary data.

        Groups options by days-to-expiry buckets (7d, 30d, 90d) and
        computes the average ATM IV for each bucket.

        Args:
            currency:   "BTC" or "ETH".
            spot_price: Current spot price.
            summaries:  Raw book summary list from Deribit.

        Returns:
            Dict {"7d": iv, "30d": iv, "90d": iv} with floats.
        """
        from datetime import datetime, timezone
        import re

        # Month abbreviation → month number
        month_map = {
            "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
            "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
        }

        now = datetime.now(tz=timezone.utc)
        bucket_ivs: dict[str, list[float]] = {"7d": [], "30d": [], "90d": []}

        for item in summaries:
            instrument_name: str = item.get("instrument_name", "")
            iv = float(item.get("mark_iv", 0.0))
            if iv <= 0:
                continue

            # Parse expiry date from instrument name: e.g. BTC-28MAR25-100000-C
            parts = instrument_name.split("-")
            if len(parts) < 3:
                continue
            expiry_str = parts[1]  # e.g. "28MAR25"
            match = re.fullmatch(r"(\d{1,2})([A-Z]{3})(\d{2})", expiry_str)
            if not match:
                continue

            try:
                day = int(match.group(1))
                month = month_map.get(match.group(2), 0)
                year = 2000 + int(match.group(3))
                expiry_dt = datetime(year, month, day, tzinfo=timezone.utc)
                dte = (expiry_dt - now).days
            except (ValueError, KeyError):
                continue

            # Extract strike to filter near-ATM options
            try:
                strike = float(parts[2])
            except (ValueError, IndexError):
                continue

            atm_tolerance = spot_price * 0.05  # 5% of spot
            if abs(strike - spot_price) > atm_tolerance:
                continue

            if dte <= 7:
                bucket_ivs["7d"].append(iv)
            elif dte <= 30:
                bucket_ivs["30d"].append(iv)
            elif dte <= 90:
                bucket_ivs["90d"].append(iv)

        term_structure: dict[str, float] = {}
        for bucket, ivs in bucket_ivs.items():
            term_structure[bucket] = round(float(sum(ivs) / len(ivs)), 2) if ivs else 0.0

        return term_structure

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
