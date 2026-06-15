"""High-Conviction Setup Filter — only emit signals meeting N+ independent criteria."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from app.ai.strategies.base import MarketContext, SignalResult
from app.core.logging import get_logger

logger = get_logger(__name__)

# UTC hours for the London open (08:00–10:59) and NY session (13:00–21:59)
_LONDON_HOURS = set(range(8, 11))
_NY_HOURS = set(range(13, 22))
_ACTIVE_HOURS = _LONDON_HOURS | _NY_HOURS

# Minimum raw signal confidence before scoring
_MIN_RAW_CONFIDENCE = 65.0

# Minimum risk/reward ratio
_MIN_RR = 2.0

# How many hours back to check for duplicate signals
_DUPLICATE_WINDOW_HOURS = 4

# Number of EMA periods for the overextension check
_EMA_PERIOD = 20


@dataclass
class ConvictionScore:
    """Detailed conviction assessment for a single signal."""

    signal: SignalResult
    total_score: int          # 0-10
    max_score: int = 10
    grade: str = "D"          # "A" (8-10), "B" (6-7), "C" (4-5), "D" (<4)
    criteria_passed: list[str] = field(default_factory=list)
    criteria_failed: list[str] = field(default_factory=list)
    is_high_conviction: bool = False
    confidence_boost: float = 0.0  # +0 to +15% for high conviction signals


class ConvictionFilter:
    """Score signals against 10 independent criteria and gate on minimum score.

    Criteria:
    1.  regime_aligned       — strategy supports current regime.
    2.  htf_aligned          — higher timeframe trend agrees.
    3.  volume_confirmed     — volume > 1.2× 20-period average.
    4.  news_clear           — no HIGH impact event within 2 hours.
    5.  active_session       — London or NY session active.
    6.  funding_aligned      — funding rate supports direction.
    7.  no_duplicate         — no same asset/direction signal in last 4 h.
    8.  confidence_threshold — raw confidence > 65%.
    9.  rr_minimum           — risk/reward >= 2.0.
    10. not_overextended     — price not >2 ATR from nearest EMA20.
    """

    MIN_REQUIRED: int = 6        # minimum criteria to emit signal
    CONVICTION_THRESHOLD: int = 8  # 8+ = high conviction → confidence boost

    def score(
        self,
        signal: SignalResult,
        market_data: pd.DataFrame,
        context: MarketContext,
        macro_events: list[dict] | None = None,
        recent_signals: list[dict] | None = None,
        funding_rate: float = 0.0,
    ) -> ConvictionScore:
        """Score a signal against all 10 criteria.

        Args:
            signal: The SignalResult to evaluate.
            market_data: OHLCV DataFrame (latest candle last).
            context: Current MarketContext (regime, session, etc.).
            macro_events: Optional list of scheduled macro events as dicts with
                          keys: 'impact' (str), 'timestamp' (datetime or ISO str).
            recent_signals: Optional list of recent signal dicts with keys:
                            'asset', 'direction', 'timestamp' (datetime or ISO str).
            funding_rate: Current perpetual funding rate (float).

        Returns:
            ConvictionScore with full breakdown.
        """
        macro_events = macro_events or []
        recent_signals = recent_signals or []

        checks: list[tuple[str, bool]] = [
            ("regime_aligned",       self._check_regime(signal, context)),
            ("htf_aligned",          self._check_htf_aligned(signal, context)),
            ("volume_confirmed",     self._check_volume(market_data)),
            ("news_clear",           self._check_news_clear(macro_events)),
            ("active_session",       self._check_session()),
            ("funding_aligned",      self._check_funding(signal, funding_rate)),
            ("no_duplicate",         self._check_no_duplicate(signal, recent_signals)),
            ("confidence_threshold", self._check_confidence_threshold(signal)),
            ("rr_minimum",           self._check_rr(signal)),
            ("not_overextended",     self._check_overextended(signal, market_data)),
        ]

        passed = [name for name, result in checks if result]
        failed = [name for name, result in checks if not result]
        total = len(passed)

        # Grade
        if total >= 8:
            grade = "A"
        elif total >= 6:
            grade = "B"
        elif total >= 4:
            grade = "C"
        else:
            grade = "D"

        is_high = total >= self.CONVICTION_THRESHOLD

        # Confidence boost: +5% at threshold, scaling to +15% at perfect 10
        boost = 0.0
        if is_high:
            boost = 5.0 + (total - self.CONVICTION_THRESHOLD) * 5.0

        logger.debug(
            "conviction_filter: %s %s score=%d/%d grade=%s",
            signal.asset,
            signal.direction,
            total,
            10,
            grade,
        )

        return ConvictionScore(
            signal=signal,
            total_score=total,
            max_score=10,
            grade=grade,
            criteria_passed=passed,
            criteria_failed=failed,
            is_high_conviction=is_high,
            confidence_boost=round(boost, 1),
        )

    def filter(
        self, signal: SignalResult, score: ConvictionScore
    ) -> SignalResult | None:
        """Gate signal on minimum criteria count and boost confidence if high conviction.

        Args:
            signal: Original signal.
            score: ConvictionScore from self.score().

        Returns:
            Modified SignalResult with boosted confidence, or None if below threshold.
        """
        if score.total_score < self.MIN_REQUIRED:
            logger.info(
                "conviction_filter: rejected %s %s score=%d (min=%d)",
                signal.asset,
                signal.direction,
                score.total_score,
                self.MIN_REQUIRED,
            )
            return None

        if score.confidence_boost > 0:
            new_confidence = round(
                min(signal.confidence + score.confidence_boost, 95.0), 1
            )
            # Return a new SignalResult with the boosted confidence
            return SignalResult(
                asset=signal.asset,
                timeframe=signal.timeframe,
                direction=signal.direction,
                confidence=new_confidence,
                entry_price=signal.entry_price,
                stop_loss=signal.stop_loss,
                take_profit_1=signal.take_profit_1,
                take_profit_2=signal.take_profit_2,
                risk_reward=signal.risk_reward,
                factors=signal.factors + [
                    {
                        "name": f"Conviction Filter Grade {score.grade}",
                        "weight": 0.0,
                        "score": score.total_score / 10.0,
                        "label": "QUALITY",
                    }
                ],
                strategy_name=signal.strategy_name,
                trailing_stop_pct=signal.trailing_stop_pct,
                partial_tp_schedule=signal.partial_tp_schedule,
                pyramid_levels=signal.pyramid_levels,
            )

        return signal

    # ------------------------------------------------------------------
    # Individual criterion checks
    # ------------------------------------------------------------------

    def _check_regime(self, signal: SignalResult, context: MarketContext) -> bool:
        """Criterion 1: strategy name must appear in the strategy registry for the regime.

        We verify via a simple direction-regime alignment heuristic:
        - TREND_BULL regime: LONG signals favored.
        - TREND_BEAR regime: SHORT signals favored.
        - CONSOLIDATION: both directions valid.
        """
        regime = context.regime.upper()
        direction = signal.direction.upper()

        if regime == "TREND_BULL" and direction == "SHORT":
            # Counter-trend short in a bull regime — marginal
            return False
        if regime == "TREND_BEAR" and direction == "LONG":
            # Counter-trend long in a bear regime — marginal
            return False

        # For CONSOLIDATION or HIGH_VOLATILITY both directions are valid
        return True

    def _check_htf_aligned(self, signal: SignalResult, context: MarketContext) -> bool:
        """Criterion 2: higher timeframe trend alignment via regime confidence.

        Uses regime_confidence as a proxy: if regime_confidence > 60 and
        the direction aligns with the regime, HTF is considered aligned.
        """
        regime = context.regime.upper()
        direction = signal.direction.upper()
        regime_conf = context.regime_confidence

        if regime_conf < 55.0:
            # Unclear regime — neither direction is confirmed by HTF
            return False

        if regime == "TREND_BULL" and direction == "LONG":
            return True
        if regime == "TREND_BEAR" and direction == "SHORT":
            return True
        if regime == "CONSOLIDATION":
            # Both directions acceptable in ranging market
            return True

        return False

    def _check_volume(self, market_data: pd.DataFrame) -> bool:
        """Criterion 3: current candle volume > 1.2× the 20-period average."""
        if market_data is None or len(market_data) < 21:
            return False

        avg_vol = float(market_data["volume"].iloc[-21:-1].mean())
        curr_vol = float(market_data["volume"].iloc[-1])

        if avg_vol <= 0:
            return False

        return (curr_vol / avg_vol) >= 1.2

    def _check_news_clear(self, macro_events: list[dict]) -> bool:
        """Criterion 4: no HIGH impact event within 2 hours of now (UTC).

        Event dict expected to have:
          - 'impact': str, one of 'HIGH', 'MEDIUM', 'LOW'
          - 'timestamp': datetime (UTC) or ISO-format string
        """
        now = datetime.now(tz=timezone.utc)
        window_seconds = 2 * 3600  # 2 hours

        for event in macro_events:
            if str(event.get("impact", "")).upper() != "HIGH":
                continue

            ts = event.get("timestamp")
            if ts is None:
                continue

            # Normalise to datetime
            if isinstance(ts, str):
                try:
                    ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except ValueError:
                    continue

            if not isinstance(ts, datetime):
                continue

            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)

            diff = abs((ts - now).total_seconds())
            if diff <= window_seconds:
                return False  # high-impact event too close

        return True

    def _check_session(self) -> bool:
        """Criterion 5: current UTC hour is within London or NY session."""
        current_hour = datetime.now(tz=timezone.utc).hour
        return current_hour in _ACTIVE_HOURS

    def _check_funding(self, signal: SignalResult, funding_rate: float) -> bool:
        """Criterion 6: funding rate supports the signal direction.

        Positive funding → longs pay shorts → bearish pressure → SHORT aligned.
        Negative funding → shorts pay longs → bullish pressure → LONG aligned.
        Neutral funding (|rate| < 0.0003) is considered aligned for both directions.
        """
        direction = signal.direction.upper()
        threshold = 0.0003  # ~0.03% — considered neutral below this

        if abs(funding_rate) < threshold:
            return True  # neutral — acceptable for both

        if direction == "SHORT" and funding_rate > threshold:
            return True  # positive funding supports short

        if direction == "LONG" and funding_rate < -threshold:
            return True  # negative funding supports long

        return False

    def _check_no_duplicate(
        self, signal: SignalResult, recent_signals: list[dict]
    ) -> bool:
        """Criterion 7: no same asset/direction signal in the last 4 hours.

        Recent signal dict expected to have:
          - 'asset': str
          - 'direction': str
          - 'timestamp': datetime (UTC) or ISO-format string
        """
        now = datetime.now(tz=timezone.utc)
        window_seconds = _DUPLICATE_WINDOW_HOURS * 3600

        for prev in recent_signals:
            if prev.get("asset") != signal.asset:
                continue
            if str(prev.get("direction", "")).upper() != signal.direction.upper():
                continue

            ts = prev.get("timestamp")
            if ts is None:
                continue

            if isinstance(ts, str):
                try:
                    ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except ValueError:
                    continue

            if not isinstance(ts, datetime):
                continue

            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)

            age = (now - ts).total_seconds()
            if 0 <= age <= window_seconds:
                return False  # duplicate found

        return True

    def _check_confidence_threshold(self, signal: SignalResult) -> bool:
        """Criterion 8: raw signal confidence must exceed minimum threshold."""
        return signal.confidence >= _MIN_RAW_CONFIDENCE

    def _check_rr(self, signal: SignalResult) -> bool:
        """Criterion 9: risk/reward ratio must be at least 2.0."""
        return signal.risk_reward >= _MIN_RR

    def _check_overextended(
        self, signal: SignalResult, market_data: pd.DataFrame
    ) -> bool:
        """Criterion 10: price must not be more than 2 ATR away from EMA20.

        An overextended entry has lower probability of continuation.
        """
        if market_data is None or len(market_data) < _EMA_PERIOD + 2:
            return True  # insufficient data — don't penalise

        close_series = market_data["close"]
        ema20 = close_series.ewm(span=_EMA_PERIOD, adjust=False).mean()
        current_price = float(close_series.iloc[-1])
        current_ema = float(ema20.iloc[-1])

        # ATR
        if "atr_14" in market_data.columns:
            atr = float(market_data["atr_14"].iloc[-1])
        else:
            atr = _quick_atr(market_data, 14)

        if atr <= 0:
            return True

        distance = abs(current_price - current_ema)
        return distance <= 2.0 * atr


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _quick_atr(df: pd.DataFrame, period: int = 14) -> float:
    """Calculate a single ATR value from the last `period` rows."""
    if len(df) < period + 1:
        return 0.0

    window = df.iloc[-(period + 1):]
    high = window["high"].values
    low = window["low"].values
    prev_close = window["close"].shift(1).values

    tr = np.maximum(
        high - low,
        np.maximum(
            np.abs(high - prev_close),
            np.abs(low - prev_close),
        ),
    )
    return float(np.nanmean(tr[1:]))  # skip the first NaN row
