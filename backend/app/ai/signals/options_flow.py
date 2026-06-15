"""Options Flow Signal Generator — IV rank, PCR, GEX-based signals.

Combines three orthogonal options-market signals into a single directional bias:

1. Put/Call Ratio (PCR) — contrarian indicator:
   - PCR > PCR_EXTREME_BEARISH → crowd is too bearish → contrarian LONG
   - PCR < PCR_EXTREME_BULLISH → crowd is too bullish → contrarian SHORT

2. IV Rank — volatility regime indicator:
   - IV rank > IV_HIGH_RANK → elevated volatility → sell premium / expect reversion
   - IV rank < IV_LOW_RANK  → depressed volatility → buy options / expect expansion

3. GEX levels — market-maker hedging creates magnetic price attraction:
   - Price above large GEX wall → dealers sell into strength (bearish)
   - Price below large GEX wall → dealers buy weakness (bullish)
   - Price near max pain → gravitational pull toward max pain into expiry
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from app.core.logging import get_logger
from app.data.deribit_fetcher import DeribitFetcher, OptionsData

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# PCR thresholds (contrarian interpretation)
_PCR_EXTREME_BEARISH: Final[float] = 1.3   # > 1.3 → contrarian LONG
_PCR_EXTREME_BULLISH: Final[float] = 0.7   # < 0.7 → contrarian SHORT
_PCR_MODERATE_BEARISH: Final[float] = 1.1
_PCR_MODERATE_BULLISH: Final[float] = 0.85

# IV rank thresholds
_IV_HIGH_RANK: Final[float] = 70.0   # sell premium
_IV_LOW_RANK: Final[float] = 30.0    # buy options (cheap premium)

# GEX proximity: within this % of a GEX level = "AT_GEX_WALL"
_GEX_PROXIMITY_PCT: Final[float] = 0.5

# Max pain proximity: within this % = "AT_MAX_PAIN"
_MAX_PAIN_PROXIMITY_PCT: Final[float] = 1.0

# Bias scoring
_CONFIDENCE_BASE: Final[float] = 30.0
_CONFIDENCE_PER_SIGNAL: Final[float] = 20.0
_CONFIDENCE_STRONG_BONUS: Final[float] = 10.0


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class OptionsFlowSignal:
    """Directional signal derived from options market structure."""

    symbol: str
    bias: str               # "BULLISH", "BEARISH", "NEUTRAL"
    confidence: float       # 0–100
    iv_rank: float
    iv_signal: str          # "HIGH_IV_SELL_PREMIUM", "LOW_IV_BUY_OPTIONS", "NEUTRAL"
    pcr_signal: str         # "CONTRARIAN_LONG", "CONTRARIAN_SHORT", "NEUTRAL"
    gex_nearest_level: float  # closest GEX strike
    gex_signal: str         # "ABOVE_GEX_WALL", "BELOW_GEX_WALL", "AT_MAX_PAIN", "NEUTRAL"
    max_pain: float
    description: str

    def __repr__(self) -> str:
        return (
            f"OptionsFlowSignal(symbol={self.symbol!r}, bias={self.bias}, "
            f"confidence={self.confidence:.1f}, iv_rank={self.iv_rank:.1f}, "
            f"pcr_signal={self.pcr_signal!r})"
        )


# ---------------------------------------------------------------------------
# Analyzer class
# ---------------------------------------------------------------------------


class OptionsFlowAnalyzer:
    """Generates trading signals from Deribit options market data."""

    # Expose thresholds as class attributes for easy overriding in tests
    PCR_EXTREME_BEARISH: float = _PCR_EXTREME_BEARISH
    PCR_EXTREME_BULLISH: float = _PCR_EXTREME_BULLISH
    IV_HIGH_RANK: float = _IV_HIGH_RANK
    IV_LOW_RANK: float = _IV_LOW_RANK

    def __init__(self) -> None:
        self._fetcher = DeribitFetcher()

    async def analyze(self, symbol: str) -> OptionsFlowSignal | None:
        """Run a full options flow analysis for the given symbol.

        Args:
            symbol: Currency symbol, e.g. "BTC" or "ETH".
                    Also accepts "BTCUSDT" format — the currency is extracted.

        Returns:
            OptionsFlowSignal or None if Deribit data is unavailable.
        """
        # Normalise symbol → "BTC" or "ETH"
        currency = _extract_currency(symbol)

        # --- Fetch Deribit data ---
        options_data = await self._fetcher.get_options_summary(currency)
        if options_data is None:
            logger.warning(
                "OptionsFlowAnalyzer: Deribit data unavailable for %s", symbol
            )
            return None

        gamma_levels = await self._fetcher.get_gamma_levels(currency)

        # --- Derive individual signals ---
        pcr_signal, pcr_confidence_boost = self._pcr_signal(options_data.put_call_ratio)
        iv_signal_str = self._iv_signal(options_data.iv_rank)

        # Need current price to evaluate GEX; fall back to max_pain as proxy
        # (In production the caller would pass current_price from market data)
        current_price = options_data.max_pain  # best available proxy without live feed
        gex_signal_str, gex_confidence_boost, nearest_gex = self._gex_signal(
            current_price, gamma_levels, options_data.max_pain
        )

        # --- Aggregate bias and confidence ---
        bias, confidence = self._aggregate_bias(
            pcr_signal=pcr_signal,
            pcr_confidence_boost=pcr_confidence_boost,
            iv_signal=iv_signal_str,
            gex_signal=gex_signal_str,
            gex_confidence_boost=gex_confidence_boost,
        )

        description = self._build_description(
            currency=currency,
            options_data=options_data,
            pcr_signal=pcr_signal,
            iv_signal=iv_signal_str,
            gex_signal=gex_signal_str,
            bias=bias,
            confidence=confidence,
        )

        logger.info(
            "OptionsFlowAnalyzer completed",
            extra={
                "symbol": symbol,
                "bias": bias,
                "confidence": confidence,
                "pcr": options_data.put_call_ratio,
                "iv_rank": options_data.iv_rank,
            },
        )

        return OptionsFlowSignal(
            symbol=symbol.upper(),
            bias=bias,
            confidence=round(confidence, 1),
            iv_rank=options_data.iv_rank,
            iv_signal=iv_signal_str,
            pcr_signal=pcr_signal,
            gex_nearest_level=round(nearest_gex, 2),
            gex_signal=gex_signal_str,
            max_pain=options_data.max_pain,
            description=description,
        )

    # ------------------------------------------------------------------
    # Signal component methods
    # ------------------------------------------------------------------

    def _pcr_signal(self, pcr: float) -> tuple[str, float]:
        """Map PCR to a contrarian signal and confidence boost.

        Args:
            pcr: Put/Call ratio.

        Returns:
            Tuple of (signal_label, confidence_boost_points).
        """
        if pcr > self.PCR_EXTREME_BEARISH:
            boost = _CONFIDENCE_PER_SIGNAL + (
                _CONFIDENCE_STRONG_BONUS if pcr > 1.5 else 0.0
            )
            return "CONTRARIAN_LONG", boost
        if pcr > _PCR_MODERATE_BEARISH:
            return "WEAK_CONTRARIAN_LONG", _CONFIDENCE_PER_SIGNAL * 0.5
        if pcr < self.PCR_EXTREME_BULLISH:
            boost = _CONFIDENCE_PER_SIGNAL + (
                _CONFIDENCE_STRONG_BONUS if pcr < 0.55 else 0.0
            )
            return "CONTRARIAN_SHORT", boost
        if pcr < _PCR_MODERATE_BULLISH:
            return "WEAK_CONTRARIAN_SHORT", _CONFIDENCE_PER_SIGNAL * 0.5
        return "NEUTRAL", 0.0

    def _iv_signal(self, iv_rank: float) -> str:
        """Classify the IV environment.

        Args:
            iv_rank: 0–100 IV percentile rank.

        Returns:
            Signal label string.
        """
        if iv_rank >= self.IV_HIGH_RANK:
            return "HIGH_IV_SELL_PREMIUM"
        if iv_rank <= self.IV_LOW_RANK:
            return "LOW_IV_BUY_OPTIONS"
        return "NEUTRAL"

    def _gex_signal(
        self,
        current_price: float,
        gex_levels: list[dict],
        max_pain: float,
    ) -> tuple[str, float, float]:
        """Determine price position relative to the largest GEX wall.

        Args:
            current_price: Current spot price.
            gex_levels:    List of {'strike', 'gex', 'net_gex'} dicts.
            max_pain:      Max pain strike price.

        Returns:
            Tuple of (signal_label, confidence_boost, nearest_gex_level).
        """
        if not gex_levels:
            return "NEUTRAL", 0.0, current_price

        # Check max pain proximity first
        if current_price > 0:
            mp_proximity_pct = abs(current_price - max_pain) / current_price * 100
            if mp_proximity_pct <= _MAX_PAIN_PROXIMITY_PCT:
                return "AT_MAX_PAIN", _CONFIDENCE_PER_SIGNAL * 0.75, max_pain

        # Find the nearest significant GEX wall
        nearest = min(gex_levels, key=lambda lv: abs(lv["strike"] - current_price))
        nearest_strike = float(nearest["strike"])
        nearest_gex = float(nearest["gex"])

        if current_price <= 0:
            return "NEUTRAL", 0.0, nearest_strike

        proximity_pct = abs(nearest_strike - current_price) / current_price * 100

        if proximity_pct <= _GEX_PROXIMITY_PCT:
            # At GEX wall — dealer hedging creates resistance/support
            if nearest_gex > 0:
                # Positive GEX wall: dealers long gamma → sell into price rise
                signal = "ABOVE_GEX_WALL" if current_price >= nearest_strike else "BELOW_GEX_WALL"
            else:
                # Negative GEX wall: dealers short gamma → amplify moves
                signal = "NEGATIVE_GEX_ZONE"
            return signal, _CONFIDENCE_PER_SIGNAL, nearest_strike

        # Price clearly above or below GEX wall
        if current_price > nearest_strike and nearest_gex > 0:
            return "ABOVE_GEX_WALL", _CONFIDENCE_PER_SIGNAL * 0.5, nearest_strike
        if current_price < nearest_strike and nearest_gex > 0:
            return "BELOW_GEX_WALL", _CONFIDENCE_PER_SIGNAL * 0.5, nearest_strike

        return "NEUTRAL", 0.0, nearest_strike

    # ------------------------------------------------------------------
    # Aggregation
    # ------------------------------------------------------------------

    def _aggregate_bias(
        self,
        pcr_signal: str,
        pcr_confidence_boost: float,
        iv_signal: str,
        gex_signal: str,
        gex_confidence_boost: float,
    ) -> tuple[str, float]:
        """Combine individual signals into a directional bias and confidence.

        Returns:
            Tuple of (bias_label, confidence_0_to_100).
        """
        bullish_score = 0.0
        bearish_score = 0.0
        confidence = _CONFIDENCE_BASE

        # PCR contribution
        if "CONTRARIAN_LONG" in pcr_signal:
            bullish_score += pcr_confidence_boost
            confidence += pcr_confidence_boost
        elif "CONTRARIAN_SHORT" in pcr_signal:
            bearish_score += pcr_confidence_boost
            confidence += pcr_confidence_boost

        # IV contribution — high IV is directionally neutral (just a vol regime)
        # but amplifies confidence in the other signals
        if iv_signal == "HIGH_IV_SELL_PREMIUM":
            confidence += 5.0  # elevated vol = stronger signal environment
        elif iv_signal == "LOW_IV_BUY_OPTIONS":
            confidence -= 5.0  # depressed vol = less reliable signals

        # GEX contribution
        if gex_signal in ("ABOVE_GEX_WALL",):
            bearish_score += gex_confidence_boost   # GEX wall above = resistance = bearish
            confidence += gex_confidence_boost
        elif gex_signal in ("BELOW_GEX_WALL",):
            bullish_score += gex_confidence_boost   # GEX wall above price = support = bullish
            confidence += gex_confidence_boost
        elif gex_signal == "AT_MAX_PAIN":
            confidence += 5.0  # max pain gravity reduces directional conviction slightly

        # Determine final bias
        if bullish_score > bearish_score and bullish_score > 0:
            bias = "BULLISH"
        elif bearish_score > bullish_score and bearish_score > 0:
            bias = "BEARISH"
        else:
            bias = "NEUTRAL"

        return bias, min(100.0, max(0.0, confidence))

    @staticmethod
    def _build_description(
        currency: str,
        options_data: OptionsData,
        pcr_signal: str,
        iv_signal: str,
        gex_signal: str,
        bias: str,
        confidence: float,
    ) -> str:
        """Build a human-readable description of the options flow analysis."""
        lines: list[str] = [
            f"{currency} options flow analysis — bias: {bias} (confidence: {confidence:.0f}%)",
            f"IV rank: {options_data.iv_rank:.1f}% → {iv_signal.replace('_', ' ')}.",
            f"Put/Call ratio: {options_data.put_call_ratio:.2f} → {pcr_signal.replace('_', ' ')}.",
            f"GEX signal: {gex_signal.replace('_', ' ')}. Max pain: {options_data.max_pain:.0f}.",
        ]
        if options_data.term_structure:
            ts_parts = [f"{k}: {v:.1f}%" for k, v in options_data.term_structure.items() if v > 0]
            if ts_parts:
                lines.append("Term structure — " + ", ".join(ts_parts) + ".")
        return " ".join(lines)


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def _extract_currency(symbol: str) -> str:
    """Extract base currency from a symbol string.

    Examples:
        "BTCUSDT" → "BTC"
        "BTC/USDT" → "BTC"
        "ETH"     → "ETH"
        "eth_usd" → "ETH"
    """
    s = symbol.upper().replace("/", "").replace("_", "")
    for ccy in ("BTC", "ETH", "SOL"):
        if s.startswith(ccy):
            return ccy
    # Fall back to first 3 characters
    return s[:3] if len(s) >= 3 else s
