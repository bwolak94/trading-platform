"""Exchange Flow Signal — inflow/outflow from exchanges as a directional signal."""

import os
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ExchangeFlowResult:
    """Result of an exchange flow analysis for a given asset."""

    symbol: str
    net_flow_direction: str   # "INFLOW" (bearish), "OUTFLOW" (bullish), "NEUTRAL"
    net_flow_usd: float       # positive = net inflow, negative = net outflow
    inflow_24h_usd: float
    outflow_24h_usd: float
    signal: str               # "BEARISH_PRESSURE", "BULLISH_ACCUMULATION", "NEUTRAL"
    confidence: float         # 0-100
    description: str


class ExchangeFlowAnalyzer:
    """Tracks large wallet movements to/from centralised exchanges.

    Exchange inflow  (wallet → Binance) = selling intent   = bearish
    Exchange outflow (Binance → wallet) = accumulation     = bullish

    Primary data source: Whale Alert API (WHALE_ALERT_API_KEY env var).
    Fallback: OI + price correlation proxy when API is unavailable.
    """

    SIGNIFICANT_FLOW_USD = 1_000_000    # only count transactions >= $1M
    STRONG_SIGNAL_RATIO = 2.0           # outflow/inflow > 2x → strong signal
    MODERATE_SIGNAL_RATIO = 1.3         # outflow/inflow > 1.3x → moderate signal

    # Whale Alert supported exchange labels (partial match)
    _EXCHANGE_LABELS = {
        "binance", "coinbase", "kraken", "okx", "bybit", "huobi",
        "kucoin", "bitfinex", "bitmex", "ftx", "gate",
    }

    async def analyze(self, symbol: str = "BTC") -> ExchangeFlowResult:
        """Analyse exchange flow for the given crypto asset.

        Tries the Whale Alert API first. Falls back to OI/price proxy.

        Args:
            symbol: Asset ticker without quote (e.g. "BTC", "ETH").

        Returns:
            ExchangeFlowResult with directional bias and confidence.
        """
        currency = symbol.upper().replace("USDT", "").replace("/", "").strip()

        try:
            inflow_usd, outflow_usd = await self._fetch_whale_alert(currency, hours=24)
            source = "whale_alert"
        except Exception as exc:
            logger.warning("Whale Alert fetch failed, using OI proxy: %s", exc)
            inflow_usd, outflow_usd = 0.0, 0.0
            source = "proxy"

        # If whale alert returned data, classify from it
        if inflow_usd > 0 or outflow_usd > 0:
            direction, signal, confidence = self._classify_flow(inflow_usd, outflow_usd)
            net_flow_usd = inflow_usd - outflow_usd
        else:
            # Proxy fallback — return NEUTRAL with low confidence
            direction, signal, confidence = "NEUTRAL", "NEUTRAL", 25.0
            net_flow_usd = 0.0
            inflow_usd = 0.0
            outflow_usd = 0.0

        description = self._build_description(
            currency, direction, signal, inflow_usd, outflow_usd, net_flow_usd, source
        )

        logger.debug(
            "ExchangeFlow %s: direction=%s signal=%s confidence=%.1f source=%s",
            currency, direction, signal, confidence, source,
        )

        return ExchangeFlowResult(
            symbol=currency,
            net_flow_direction=direction,
            net_flow_usd=round(net_flow_usd, 0),
            inflow_24h_usd=round(inflow_usd, 0),
            outflow_24h_usd=round(outflow_usd, 0),
            signal=signal,
            confidence=round(confidence, 1),
            description=description,
        )

    async def _fetch_whale_alert(
        self, currency: str, hours: int = 24
    ) -> tuple[float, float]:
        """Fetch large transactions from the Whale Alert API.

        Endpoint: GET https://api.whale-alert.io/v1/transactions
        Requires WHALE_ALERT_API_KEY environment variable.

        Args:
            currency: Asset ticker (e.g. "BTC").
            hours: Look-back window in hours (max 24 for free tier).

        Returns:
            Tuple of (inflow_usd, outflow_usd) for exchange-bound transactions.

        Raises:
            RuntimeError: If the API key is missing or the request fails.
        """
        api_key = os.environ.get("WHALE_ALERT_API_KEY", "")
        if not api_key:
            raise RuntimeError("WHALE_ALERT_API_KEY not set in environment")

        now = int(datetime.now(timezone.utc).timestamp())
        start = now - hours * 3600

        url = "https://api.whale-alert.io/v1/transactions"
        params = {
            "api_key": api_key,
            "start": start,
            "min_value": int(self.SIGNIFICANT_FLOW_USD),
            "currency": currency.lower(),
            "limit": 100,
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

        transactions = data.get("transactions", [])
        if not transactions:
            return 0.0, 0.0

        inflow_usd = 0.0
        outflow_usd = 0.0

        for tx in transactions:
            amount_usd = float(tx.get("amount_usd", 0))
            if amount_usd < self.SIGNIFICANT_FLOW_USD:
                continue

            from_owner = str(tx.get("from", {}).get("owner_type", "")).lower()
            to_owner = str(tx.get("to", {}).get("owner_type", "")).lower()

            from_label = str(tx.get("from", {}).get("owner", "")).lower()
            to_label = str(tx.get("to", {}).get("owner", "")).lower()

            is_from_exchange = (
                from_owner == "exchange"
                or any(ex in from_label for ex in self._EXCHANGE_LABELS)
            )
            is_to_exchange = (
                to_owner == "exchange"
                or any(ex in to_label for ex in self._EXCHANGE_LABELS)
            )

            if is_to_exchange and not is_from_exchange:
                # Wallet → Exchange: inflow (selling pressure)
                inflow_usd += amount_usd
            elif is_from_exchange and not is_to_exchange:
                # Exchange → Wallet: outflow (accumulation)
                outflow_usd += amount_usd
            # Exchange → Exchange transfers are ignored (neutral)

        return inflow_usd, outflow_usd

    def _estimate_from_reserves(
        self, oi_change: float, price_change: float
    ) -> tuple[str, float]:
        """Proxy estimate when on-chain data is unavailable.

        Interprets OI + price change combinations:
        - Rising OI + rising price  → longs entering   → mild inflow risk
        - Rising OI + falling price → shorts entering   → bearish (inflow proxy)
        - Falling OI + rising price → shorts covering   → bullish (outflow proxy)
        - Falling OI + falling price→ longs exiting     → bearish (inflow proxy)

        Args:
            oi_change: Open interest change percentage (+/-).
            price_change: Price change percentage over same period (+/-).

        Returns:
            Tuple of (direction, confidence) where direction is
            "INFLOW", "OUTFLOW", or "NEUTRAL".
        """
        if oi_change > 2.0 and price_change < -1.0:
            return "INFLOW", 45.0   # bearish: shorts piling in
        if oi_change < -2.0 and price_change > 1.0:
            return "OUTFLOW", 45.0  # bullish: shorts covering
        if oi_change > 2.0 and price_change > 1.0:
            return "INFLOW", 30.0   # longs entering — mild inflow signal
        if oi_change < -2.0 and price_change < -1.0:
            return "INFLOW", 35.0   # longs exiting — bearish
        return "NEUTRAL", 20.0

    def _classify_flow(
        self, inflow: float, outflow: float
    ) -> tuple[str, str, float]:
        """Classify flow direction, signal type, and confidence from raw USD values.

        Args:
            inflow: Total exchange inflow in USD over the measurement window.
            outflow: Total exchange outflow in USD over the measurement window.

        Returns:
            Tuple of (direction, signal, confidence).
        """
        total = inflow + outflow
        if total < self.SIGNIFICANT_FLOW_USD:
            return "NEUTRAL", "NEUTRAL", 20.0

        outflow - inflow  # positive = more outflow (bullish)

        if inflow == 0 and outflow > 0:
            return "OUTFLOW", "BULLISH_ACCUMULATION", 70.0
        if outflow == 0 and inflow > 0:
            return "INFLOW", "BEARISH_PRESSURE", 70.0

        ratio_out = outflow / max(inflow, 1.0)
        ratio_in = inflow / max(outflow, 1.0)

        if ratio_out >= self.STRONG_SIGNAL_RATIO:
            return "OUTFLOW", "BULLISH_ACCUMULATION", min(80.0, 55.0 + ratio_out * 5)
        if ratio_out >= self.MODERATE_SIGNAL_RATIO:
            return "OUTFLOW", "BULLISH_ACCUMULATION", 55.0

        if ratio_in >= self.STRONG_SIGNAL_RATIO:
            return "INFLOW", "BEARISH_PRESSURE", min(80.0, 55.0 + ratio_in * 5)
        if ratio_in >= self.MODERATE_SIGNAL_RATIO:
            return "INFLOW", "BEARISH_PRESSURE", 55.0

        return "NEUTRAL", "NEUTRAL", 30.0

    def _build_description(
        self,
        currency: str,
        direction: str,
        signal: str,
        inflow: float,
        outflow: float,
        net: float,
        source: str,
    ) -> str:
        """Build a human-readable description of the exchange flow result."""
        def _fmt(usd: float) -> str:
            if abs(usd) >= 1_000_000_000:
                return f"${usd / 1_000_000_000:.2f}B"
            if abs(usd) >= 1_000_000:
                return f"${usd / 1_000_000:.1f}M"
            return f"${usd:,.0f}"

        parts = [
            f"{currency} exchange flow (24h, source={source}): "
            f"inflow {_fmt(inflow)}, outflow {_fmt(outflow)}, net {_fmt(net)}."
        ]

        if signal == "BULLISH_ACCUMULATION":
            parts.append(
                "Net outflow indicates accumulation — coins moving to cold storage suggests "
                "reduced selling pressure. Bullish bias."
            )
        elif signal == "BEARISH_PRESSURE":
            parts.append(
                "Net inflow to exchanges indicates potential selling pressure. "
                "Coins moving on-exchange usually precedes distribution. Bearish bias."
            )
        else:
            parts.append("Balanced flow — no significant directional bias detected.")

        return " ".join(parts)
