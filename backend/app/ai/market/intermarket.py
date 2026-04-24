"""Intermarket Analysis — cross-asset correlations and divergence signals."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd

from app.core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Key intermarket relationships for crypto macro context
# ---------------------------------------------------------------------------
INTERMARKET_PAIRS: dict[str, dict] = {
    "BTC_DXY": {
        "asset_a": "BTC/USDT",
        "asset_b": "DXY",
        "typical_correlation": -0.6,   # inverse: DXY rising = BTC typically falls
        "description": "Dollar strength vs BTC (inverse relationship)",
    },
    "BTC_SPX": {
        "asset_a": "BTC/USDT",
        "asset_b": "SPX",
        "typical_correlation": 0.5,    # positive: risk-on / risk-off
        "description": "Risk appetite (BTC follows equities during risk-on/off)",
    },
    "BTC_GOLD": {
        "asset_a": "BTC/USDT",
        "asset_b": "GOLD",
        "typical_correlation": 0.3,    # mild positive: inflation/hedge narrative
        "description": "Inflation hedge narrative (BTC as digital gold)",
    },
}

# yfinance tickers for traditional market assets
YFINANCE_TICKERS: dict[str, str] = {
    "DXY": "DX-Y.NYB",
    "SPX": "^GSPC",
    "GOLD": "GC=F",
}


@dataclass
class IntermarketSignal:
    """Signal derived from a single cross-asset correlation relationship."""

    symbol: str                  # crypto symbol being analyzed (e.g. "BTC/USDT")
    relationship: str            # key from INTERMARKET_PAIRS (e.g. "BTC_DXY")
    correlation_current: float   # rolling 20-day correlation
    correlation_baseline: float  # typical correlation from INTERMARKET_PAIRS
    driver_asset: str            # traditional market asset acting as driver
    driver_trend: str            # "UP" or "DOWN" (recent move in the driver)
    expected_impact: str         # "BULLISH" or "BEARISH" for the crypto side
    confidence: float            # 0-100
    description: str


@dataclass
class IntermarketSummary:
    """Aggregated intermarket analysis across all relationships."""

    symbol: str
    net_bias: str                # "BULLISH", "BEARISH", "NEUTRAL"
    net_confidence: float        # 0-100
    signals: list[IntermarketSignal] = field(default_factory=list)
    dominant_driver: str = "UNKNOWN"   # which traditional asset is most influential now
    risk_regime: str = "MIXED"         # "RISK_ON", "RISK_OFF", "MIXED"


class IntermarketAnalyzer:
    """Analyzes cross-asset correlations to determine the macro trading context.

    Correlates BTC/ETH price movements against DXY, S&P 500, and Gold to
    identify whether macro conditions are supportive or hostile for crypto.

    Usage::

        analyzer = IntermarketAnalyzer()
        summary = await analyzer.analyze("BTC/USDT")
        print(summary.net_bias, summary.risk_regime)
    """

    CORRELATION_WINDOW: int = 20   # days for rolling correlation

    async def analyze(self, crypto_symbol: str = "BTC/USDT") -> IntermarketSummary:
        """Run full intermarket analysis for *crypto_symbol*.

        Steps:
        1. Fetch DXY, SPX, Gold price data via yfinance.
        2. Fetch BTC price data from Binance (via the existing fetcher).
        3. Calculate rolling 20-day correlations.
        4. Detect when active correlations diverge from their baseline.
        5. Aggregate into a net macro bias.

        Args:
            crypto_symbol: The crypto pair to analyze (default ``"BTC/USDT"``).

        Returns:
            :class:`IntermarketSummary` with net bias, confidence, and individual signals.
        """
        traditional_data = await self._fetch_traditional_markets()
        crypto_data = await self._fetch_crypto_data(crypto_symbol)

        signals: list[IntermarketSignal] = []

        if crypto_data is None or crypto_data.empty:
            logger.warning("IntermarketAnalyzer: no crypto data for %s", crypto_symbol)
            return IntermarketSummary(
                symbol=crypto_symbol,
                net_bias="NEUTRAL",
                net_confidence=0.0,
            )

        crypto_returns = crypto_data["close"].pct_change().dropna()

        for rel_key, rel_config in INTERMARKET_PAIRS.items():
            trad_asset = rel_config["asset_b"]
            trad_df = traditional_data.get(trad_asset)

            if trad_df is None or trad_df.empty:
                logger.debug("IntermarketAnalyzer: no data for %s — skipping %s", trad_asset, rel_key)
                continue

            trad_returns = trad_df["close"].pct_change().dropna()

            # Align on common index
            aligned = pd.concat(
                [crypto_returns.rename("crypto"), trad_returns.rename("trad")],
                axis=1,
            ).dropna()

            if len(aligned) < self.CORRELATION_WINDOW + 2:
                logger.debug(
                    "IntermarketAnalyzer: insufficient aligned rows for %s (%d)",
                    rel_key, len(aligned),
                )
                continue

            # Current rolling correlation (last CORRELATION_WINDOW days)
            tail = aligned.tail(self.CORRELATION_WINDOW)
            try:
                current_corr = float(tail["crypto"].corr(tail["trad"]))
                if np.isnan(current_corr):
                    current_corr = 0.0
            except Exception:
                current_corr = 0.0

            baseline_corr: float = rel_config["typical_correlation"]

            # Determine driver trend (last 5 periods)
            recent_trad_return = (
                float(trad_df["close"].iloc[-1]) / float(trad_df["close"].iloc[-6]) - 1.0
                if len(trad_df) >= 6
                else 0.0
            )
            driver_trend = "UP" if recent_trad_return > 0 else "DOWN"

            # Expected impact on crypto based on typical correlation and driver direction
            # If current_corr is close to baseline, relationship is active
            correlation_active = abs(current_corr - baseline_corr) < 0.3

            if correlation_active:
                if baseline_corr < 0:
                    # Inverse relationship (e.g. DXY): DXY UP → BTC bearish
                    expected_impact = "BEARISH" if driver_trend == "UP" else "BULLISH"
                else:
                    # Positive relationship (e.g. SPX): SPX UP → BTC bullish
                    expected_impact = "BULLISH" if driver_trend == "UP" else "BEARISH"
            else:
                # Correlation has broken down — reduced confidence, unclear impact
                expected_impact = "NEUTRAL"
                logger.debug(
                    "IntermarketAnalyzer: correlation decoupled for %s "
                    "(current=%.2f, baseline=%.2f)",
                    rel_key, current_corr, baseline_corr,
                )

            # Confidence: higher when correlation is strong and active
            corr_strength = abs(current_corr)
            magnitude_boost = min(abs(recent_trad_return) / 0.05, 1.0) * 20.0  # up to +20
            confidence = round(
                min(corr_strength * 60.0 + magnitude_boost, 90.0),
                2,
            ) if expected_impact != "NEUTRAL" else 20.0

            description = (
                f"{rel_config['description']}. {trad_asset} moved {driver_trend} "
                f"({recent_trad_return:+.2%}). Active correlation={current_corr:.2f} "
                f"(baseline={baseline_corr:.2f}). Expected impact: {expected_impact}."
            )

            signals.append(
                IntermarketSignal(
                    symbol=crypto_symbol,
                    relationship=rel_key,
                    correlation_current=round(current_corr, 4),
                    correlation_baseline=baseline_corr,
                    driver_asset=trad_asset,
                    driver_trend=driver_trend,
                    expected_impact=expected_impact,
                    confidence=confidence,
                    description=description,
                )
            )

        net_bias, net_confidence = self._net_bias(signals)
        risk_regime = self._calculate_risk_regime(signals)
        dominant_driver = self._dominant_driver(signals)

        logger.info(
            "IntermarketAnalyzer: %s net_bias=%s conf=%.1f risk_regime=%s",
            crypto_symbol, net_bias, net_confidence, risk_regime,
        )

        return IntermarketSummary(
            symbol=crypto_symbol,
            net_bias=net_bias,
            net_confidence=net_confidence,
            signals=signals,
            dominant_driver=dominant_driver,
            risk_regime=risk_regime,
        )

    async def _fetch_traditional_markets(self) -> dict[str, pd.DataFrame]:
        """Fetch DXY, SPX, Gold daily OHLCV data via yfinance.

        Uses the ``yfinance`` library (``pip install yfinance``).
        Returns an empty dict for each asset if yfinance is unavailable or the
        download fails — the caller handles missing assets gracefully.

        Returns:
            Dict mapping asset name → DataFrame with ``close`` column indexed by date.
        """
        result: dict[str, pd.DataFrame] = {}

        try:
            import yfinance as yf  # noqa: PLC0415 — optional dependency
        except ImportError:
            logger.warning(
                "IntermarketAnalyzer: yfinance not installed — "
                "traditional market data unavailable. Install with: pip install yfinance"
            )
            return result

        lookback_days = self.CORRELATION_WINDOW + 30  # extra buffer
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=lookback_days)

        for asset_name, ticker_symbol in YFINANCE_TICKERS.items():
            try:
                raw = yf.download(
                    ticker_symbol,
                    start=start.strftime("%Y-%m-%d"),
                    end=end.strftime("%Y-%m-%d"),
                    progress=False,
                    auto_adjust=True,
                )
                if raw.empty:
                    logger.warning("IntermarketAnalyzer: empty data for %s (%s)", asset_name, ticker_symbol)
                    continue

                df = raw[["Close"]].rename(columns={"Close": "close"})
                df.index = pd.to_datetime(df.index, utc=True)
                result[asset_name] = df
                logger.debug(
                    "IntermarketAnalyzer: loaded %d rows for %s", len(df), asset_name
                )
            except Exception as exc:
                logger.warning(
                    "IntermarketAnalyzer: failed to fetch %s (%s): %s",
                    asset_name, ticker_symbol, exc,
                )

        return result

    async def _fetch_crypto_data(self, symbol: str) -> pd.DataFrame | None:
        """Fetch recent daily OHLCV data for the crypto symbol via Binance REST.

        Args:
            symbol: Trading pair, e.g. ``"BTC/USDT"``.

        Returns:
            DataFrame with ``close`` column or ``None`` on failure.
        """
        import httpx as _httpx  # noqa: PLC0415

        binance_symbol = symbol.replace("/", "")
        url = "https://fapi.binance.com/fapi/v1/klines"
        lookback = self.CORRELATION_WINDOW + 30

        try:
            async with _httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    url,
                    params={
                        "symbol": binance_symbol,
                        "interval": "1d",
                        "limit": lookback,
                    },
                )
                resp.raise_for_status()
                raw = resp.json()

            if not raw:
                return None

            df = pd.DataFrame(
                [
                    {
                        "timestamp": pd.Timestamp(int(k[0]), unit="ms", tz="UTC"),
                        "close": float(k[4]),
                    }
                    for k in raw
                ]
            ).set_index("timestamp")
            return df

        except Exception as exc:
            logger.warning("IntermarketAnalyzer: Binance fetch failed for %s: %s", symbol, exc)
            return None

    def _calculate_risk_regime(self, signals: list[IntermarketSignal]) -> str:
        """Determine whether markets are in risk-on or risk-off mode.

        Logic:
        - SPX trending UP = risk-on indicator.
        - DXY trending DOWN = risk-on (dollar weakening, assets bid).
        - Both indicators aligned = strong regime; otherwise MIXED.

        Args:
            signals: List of :class:`IntermarketSignal` objects.

        Returns:
            ``"RISK_ON"``, ``"RISK_OFF"``, or ``"MIXED"``.
        """
        regime_votes: dict[str, int] = {"RISK_ON": 0, "RISK_OFF": 0}

        for sig in signals:
            if sig.relationship == "BTC_SPX":
                if sig.driver_trend == "UP":
                    regime_votes["RISK_ON"] += 2  # SPX up is strongest risk-on signal
                else:
                    regime_votes["RISK_OFF"] += 2
            elif sig.relationship == "BTC_DXY":
                if sig.driver_trend == "DOWN":
                    regime_votes["RISK_ON"] += 1  # DXY down = weaker dollar = risk-on
                else:
                    regime_votes["RISK_OFF"] += 1
            elif sig.relationship == "BTC_GOLD":
                if sig.driver_trend == "UP":
                    regime_votes["RISK_OFF"] += 1  # gold up = fear / inflation hedge
                else:
                    regime_votes["RISK_ON"] += 1

        risk_on = regime_votes["RISK_ON"]
        risk_off = regime_votes["RISK_OFF"]

        if risk_on > risk_off + 1:
            return "RISK_ON"
        if risk_off > risk_on + 1:
            return "RISK_OFF"
        return "MIXED"

    def _net_bias(
        self, signals: list[IntermarketSignal]
    ) -> tuple[str, float]:
        """Aggregate all intermarket signals into a net directional bias.

        Bullish signals add confidence; bearish signals subtract it.
        Neutral signals are ignored.

        Args:
            signals: List of :class:`IntermarketSignal` objects.

        Returns:
            Tuple of ``(bias_string, net_confidence)`` where bias is
            ``"BULLISH"``, ``"BEARISH"``, or ``"NEUTRAL"``.
        """
        if not signals:
            return "NEUTRAL", 0.0

        bullish_score = 0.0
        bearish_score = 0.0

        for sig in signals:
            weight = sig.confidence / 100.0
            if sig.expected_impact == "BULLISH":
                bullish_score += weight
            elif sig.expected_impact == "BEARISH":
                bearish_score += weight

        total = bullish_score + bearish_score
        if total == 0:
            return "NEUTRAL", 0.0

        if bullish_score > bearish_score:
            net_confidence = round((bullish_score / total) * 80.0, 2)
            return "BULLISH", net_confidence
        if bearish_score > bullish_score:
            net_confidence = round((bearish_score / total) * 80.0, 2)
            return "BEARISH", net_confidence

        return "NEUTRAL", 30.0

    def _dominant_driver(self, signals: list[IntermarketSignal]) -> str:
        """Return the traditional asset with the highest individual signal confidence.

        Args:
            signals: List of :class:`IntermarketSignal` objects.

        Returns:
            Name of the most influential traditional market asset (e.g. ``"SPX"``).
        """
        if not signals:
            return "UNKNOWN"
        return max(signals, key=lambda s: s.confidence).driver_asset
