"""Options Skew Monitor — 25-delta put/call skew analysis from Deribit."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)

# Deribit public API base URL (no auth required for market data)
_DERIBIT_API = "https://www.deribit.com/api/v2/public"

# Tolerance for selecting the "25-delta" option (accept 0.20–0.30 delta range)
_DELTA_TARGET = 0.25
_DELTA_TOLERANCE = 0.07


@dataclass
class OptionsSkewResult:
    """Result of the options skew analysis."""

    symbol: str
    skew_25delta: float              # put IV - call IV for 25-delta options
    skew_classification: str         # "FEAR" (>10%), "GREED" (<-5%), "NEUTRAL"
    term_structure_inverted: bool    # True if near-term IV > long-term IV
    iv_30d: float                    # 30-day ATM implied volatility
    iv_7d: float                     # 7-day ATM implied volatility
    contrarian_signal: str           # "CONTRARIAN_LONG", "CONTRARIAN_SHORT", "NEUTRAL"
    confidence: float
    description: str


class OptionsSkewMonitor:
    """Monitor 25-delta options skew — the professional fear/greed gauge.

    25-delta skew = IV of 25-delta put - IV of 25-delta call (same expiry).

    Interpretation:
    - Positive skew (puts > calls): market is buying downside protection → fear
      → contrarian bullish (extreme fear = capitulation opportunity).
    - Negative skew (calls > puts): market is buying upside calls → greed
      → contrarian bearish (extreme greed = distribution opportunity).
    - Term structure inversion (7d IV > 30d IV): acute near-term fear
      → contrarian LONG (short-term panic, longer-term stable).
    """

    FEAR_SKEW_THRESHOLD: float = 8.0     # >8 pp skew = contrarian LONG
    GREED_SKEW_THRESHOLD: float = -5.0   # <-5 pp skew = contrarian SHORT

    async def analyze(self, currency: str = "BTC") -> OptionsSkewResult | None:
        """Fetch Deribit options data and compute 25-delta skew.

        Steps:
        1. Fetch all options for the nearest 7-day and 30-day expiry.
        2. Find the 25-delta put and call for each expiry.
        3. Compute skew = put_iv_25d - call_iv_25d.
        4. Compare 7d vs 30d implied volatility for term structure.
        5. Generate contrarian signal for extreme readings.

        Args:
            currency: "BTC" or "ETH" (Deribit convention).

        Returns:
            OptionsSkewResult or None if data is unavailable.
        """
        currency = currency.upper()

        try:
            options_7d = await self._fetch_options_chain(currency, days_to_expiry=7)
            options_30d = await self._fetch_options_chain(currency, days_to_expiry=30)
        except Exception as exc:
            logger.warning("options_skew: failed to fetch Deribit data: %s", exc)
            return None

        if not options_7d or not options_30d:
            logger.debug("options_skew: no options data for %s", currency)
            return None

        # 25-delta skew for 7-day expiry
        put_7d, call_7d = self._find_25delta_options(options_7d)
        put_30d, call_30d = self._find_25delta_options(options_30d)

        if not all([put_7d, call_7d, put_30d, call_30d]):
            logger.debug("options_skew: could not find 25-delta options for %s", currency)
            return None

        # Implied volatility values (Deribit returns IV as a decimal, e.g. 0.80 = 80%)
        iv_put_7d = float(put_7d.get("mark_iv", 0)) * 100  # convert to percentage
        iv_call_7d = float(call_7d.get("mark_iv", 0)) * 100
        iv_put_30d = float(put_30d.get("mark_iv", 0)) * 100
        iv_call_30d = float(call_30d.get("mark_iv", 0)) * 100

        if iv_put_7d == 0 or iv_call_7d == 0:
            return None

        skew_7d = iv_put_7d - iv_call_7d
        skew_30d = iv_put_30d - iv_call_30d

        # Use 7d skew as primary (more reactive) — average with 30d for smoothing
        skew_25delta = round((skew_7d * 0.6 + skew_30d * 0.4), 2)

        # ATM IV proxies (average of put + call at the 25-delta level)
        iv_7d = round((iv_put_7d + iv_call_7d) / 2, 2)
        iv_30d = round((iv_put_30d + iv_call_30d) / 2, 2)

        # Term structure: near-term IV higher than long-term = inverted (fear)
        term_structure_inverted = iv_7d > iv_30d

        classification, contrarian_signal, confidence = self._classify_skew(skew_25delta)

        # Extra confidence boost for term structure inversion aligned with signal
        if term_structure_inverted and contrarian_signal == "CONTRARIAN_LONG":
            confidence = min(confidence + 8.0, 90.0)
        elif not term_structure_inverted and contrarian_signal == "CONTRARIAN_SHORT":
            confidence = min(confidence + 5.0, 90.0)

        description = (
            f"{currency} 25Δ skew: {skew_25delta:+.1f}pp "
            f"(7d={skew_7d:+.1f}pp / 30d={skew_30d:+.1f}pp). "
            f"IV 7d={iv_7d:.0f}% / 30d={iv_30d:.0f}%. "
            f"Term structure {'INVERTED' if term_structure_inverted else 'NORMAL'}."
        )

        logger.info(
            "options_skew: %s skew=%.1f classification=%s signal=%s conf=%.1f",
            currency,
            skew_25delta,
            classification,
            contrarian_signal,
            confidence,
        )

        return OptionsSkewResult(
            symbol=currency,
            skew_25delta=skew_25delta,
            skew_classification=classification,
            term_structure_inverted=term_structure_inverted,
            iv_30d=iv_30d,
            iv_7d=iv_7d,
            contrarian_signal=contrarian_signal,
            confidence=round(confidence, 1),
            description=description,
        )

    async def _fetch_options_chain(
        self, currency: str, days_to_expiry: int
    ) -> list[dict]:
        """Fetch all active options for the expiry closest to `days_to_expiry`.

        Uses Deribit public endpoints:
        - /get_instruments to list all options and their expiry dates.
        - /get_order_book_by_instrument_id to retrieve mark IV per instrument.

        Args:
            currency: "BTC" or "ETH".
            days_to_expiry: Target expiry in days from now.

        Returns:
            List of option instrument dicts enriched with mark_iv and greeks.
        """
        import time

        now_ms = int(time.time() * 1000)
        target_ms = now_ms + days_to_expiry * 86_400_000

        # Step 1: fetch instrument list
        instruments_url = f"{_DERIBIT_API}/get_instruments"
        params = {
            "currency": currency,
            "kind": "option",
            "expired": False,
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.get(instruments_url, params=params)
                resp.raise_for_status()
                instruments_data = resp.json().get("result", [])
            except httpx.HTTPError as exc:
                logger.warning("options_skew: instrument fetch failed: %s", exc)
                return []

        if not instruments_data:
            return []

        # Find the expiry closest to our target
        expiries = sorted(
            {int(inst["expiration_timestamp"]) for inst in instruments_data}
        )
        if not expiries:
            return []

        best_expiry = min(expiries, key=lambda e: abs(e - target_ms))

        # Step 2: filter instruments for this expiry
        chain_instruments = [
            inst
            for inst in instruments_data
            if int(inst["expiration_timestamp"]) == best_expiry
        ]

        # Step 3: enrich with ticker data (mark IV and greeks) in bulk
        enriched: list[dict] = []
        ticker_url = f"{_DERIBIT_API}/ticker"

        async with httpx.AsyncClient(timeout=10.0) as client:
            for inst in chain_instruments:
                name = inst.get("instrument_name", "")
                if not name:
                    continue
                try:
                    ticker_resp = await client.get(
                        ticker_url, params={"instrument_name": name}
                    )
                    ticker_resp.raise_for_status()
                    ticker = ticker_resp.json().get("result", {})

                    greeks = ticker.get("greeks", {})
                    enriched.append(
                        {
                            "instrument_name": name,
                            "option_type": inst.get("option_type", ""),  # "call" or "put"
                            "strike": float(inst.get("strike", 0)),
                            "mark_iv": float(ticker.get("mark_iv", 0)) / 100,  # normalise to 0-1
                            "delta": float(greeks.get("delta", 0)),
                            "gamma": float(greeks.get("gamma", 0)),
                            "vega": float(greeks.get("vega", 0)),
                            "mark_price": float(ticker.get("mark_price", 0)),
                        }
                    )
                except httpx.HTTPError:
                    continue

        return enriched

    def _find_25delta_options(
        self, options: list[dict]
    ) -> tuple[dict | None, dict | None]:
        """Find the put and call closest to 25-delta from an options chain.

        For puts: look for delta ≈ -0.25 (Deribit reports put delta as negative).
        For calls: look for delta ≈ +0.25.

        Args:
            options: List of enriched option dicts (must have 'delta' and 'option_type').

        Returns:
            Tuple (put_dict, call_dict), either may be None if not found.
        """
        puts = [o for o in options if str(o.get("option_type", "")).lower() == "put"]
        calls = [o for o in options if str(o.get("option_type", "")).lower() == "call"]

        def closest_to_target(
            instruments: list[dict], target_delta: float
        ) -> dict | None:
            """Find the instrument with delta closest to target within tolerance."""
            candidates = [
                inst
                for inst in instruments
                if abs(abs(float(inst.get("delta", 0))) - _DELTA_TARGET) <= _DELTA_TOLERANCE
            ]
            if not candidates:
                return None
            return min(candidates, key=lambda o: abs(abs(float(o.get("delta", 0))) - target_delta))

        best_put = closest_to_target(puts, _DELTA_TARGET)
        best_call = closest_to_target(calls, _DELTA_TARGET)

        return best_put, best_call

    def _classify_skew(
        self, skew: float
    ) -> tuple[str, str, float]:
        """Classify skew magnitude and generate contrarian signal.

        Args:
            skew: 25-delta skew in percentage points (put IV - call IV).

        Returns:
            Tuple of (classification, contrarian_signal, confidence).
        """
        if skew >= self.FEAR_SKEW_THRESHOLD:
            classification = "FEAR"
            contrarian_signal = "CONTRARIAN_LONG"
            # Confidence scales from 60% at threshold to 85% at 2× threshold
            conf = 60.0 + min(25.0, (skew - self.FEAR_SKEW_THRESHOLD) / self.FEAR_SKEW_THRESHOLD * 25.0)

        elif skew <= self.GREED_SKEW_THRESHOLD:
            classification = "GREED"
            contrarian_signal = "CONTRARIAN_SHORT"
            abs_skew = abs(skew)
            abs_threshold = abs(self.GREED_SKEW_THRESHOLD)
            conf = 60.0 + min(25.0, (abs_skew - abs_threshold) / abs_threshold * 25.0)

        else:
            classification = "NEUTRAL"
            contrarian_signal = "NEUTRAL"
            # Neutral zone: confidence declines toward 0 as skew nears 0
            conf = max(0.0, 40.0 - abs(skew) * 2.0)

        return classification, contrarian_signal, round(min(conf, 90.0), 1)
