"""Signal Aggregator — weighted multi-source scoring and signal emission."""

import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import numpy as np
import pandas as pd

from app.ai.regime.classifier import RegimeClassifier, RegimePrediction
from app.ai.strategies.base import BaseStrategy, MarketContext, SignalResult
from app.ai.strategies.basis_arbitrage import BasisArbitrageStrategy
from app.ai.strategies.breakout_failure import BreakoutFailureStrategy
from app.ai.strategies.dual_momentum import DualMomentumStrategy
from app.ai.strategies.funding_mean_reversion import FundingMeanReversionStrategy
from app.ai.strategies.mean_reversion import MeanReversionStrategy
from app.ai.strategies.oi_trend_strategy import OITrendDivergenceStrategy
from app.ai.strategies.rsi_scalping import RSIScalpingStrategy
from app.ai.strategies.smc_strategy import SMCStrategy
from app.ai.strategies.trend_following import TrendFollowingStrategy
from app.ai.strategies.trend_trader import TrendTraderStrategy
from app.ai.strategies.volume_breakout import VolumeBreakoutStrategy
from app.core.logging import get_logger

# Optional analytics / risk integrations (graceful degradation if not yet created)
try:
    from app.ai.analytics.confidence_percentile import ConfidencePercentileTracker
    _PERCENTILE_TRACKER_AVAILABLE = True
except ImportError:
    _PERCENTILE_TRACKER_AVAILABLE = False

try:
    from app.ai.risk.psychological_governor import PsychologicalGovernor
    _PSYCH_GOVERNOR_AVAILABLE = True
except ImportError:
    _PSYCH_GOVERNOR_AVAILABLE = False

logger = get_logger(__name__)

WEIGHTS = {
    "technical": 0.40,
    "onchain": 0.30,
    "sentiment": 0.20,
    "macro": 0.10,
}

# Duplicate signal cooldown
SIGNAL_COOLDOWN_HOURS = 4

# ---------------------------------------------------------------------------
# Regime-aware strategy weight multipliers.
# Maps market regime -> strategy name -> confidence multiplier (0.0 – 2.0).
# A multiplier of 1.0 is neutral; >1.0 boosts; <1.0 penalises.
# ---------------------------------------------------------------------------
REGIME_STRATEGY_WEIGHTS: dict[str, dict[str, float]] = {
    "TREND_BULL": {
        "trend_following": 1.5,
        "trend_trader": 1.4,
        "volume_breakout": 1.2,
        "mean_reversion": 0.5,
        "rsi_scalping": 0.7,
        "smc": 1.1,
        "mtf_confluence": 1.3,
        "funding_mean_reversion": 1.3,
        "oi_trend_divergence": 1.2,
        "dual_momentum": 1.4,
        "breakout_failure": 0.8,
        "basis_arbitrage": 1.0,
    },
    "TREND_BEAR": {
        "trend_following": 1.5,
        "trend_trader": 1.4,
        "volume_breakout": 1.2,
        "mean_reversion": 0.5,
        "rsi_scalping": 0.7,
        "smc": 1.2,
        "mtf_confluence": 1.3,
        "funding_mean_reversion": 1.3,
        "oi_trend_divergence": 1.2,
        "dual_momentum": 1.4,
        "breakout_failure": 0.8,
        "basis_arbitrage": 1.0,
    },
    "CONSOLIDATION": {
        "mean_reversion": 1.5,
        "rsi_scalping": 1.3,
        "smc": 1.2,
        "trend_following": 0.6,
        "trend_trader": 0.5,
        "volume_breakout": 0.8,
        "mtf_confluence": 1.0,
        "funding_mean_reversion": 1.3,
        "oi_trend_divergence": 1.2,
        "dual_momentum": 0.9,
        "breakout_failure": 1.4,  # range-bound breakout traps are common
        "basis_arbitrage": 1.2,
    },
    "HIGH_VOL_CHOPPY": {
        "mean_reversion": 0.7,
        "rsi_scalping": 0.8,
        "smc": 0.9,
        "trend_following": 0.5,
        "trend_trader": 0.5,
        "volume_breakout": 0.6,
        "mtf_confluence": 0.7,
        # funding_mean_reversion works in HIGH_VOL_CHOPPY — given full weight
        "funding_mean_reversion": 1.3,
        "oi_trend_divergence": 0.8,
        "dual_momentum": 0.6,
        "breakout_failure": 1.1,  # traps frequent in choppy conditions
        "basis_arbitrage": 1.3,   # funding dislocations peak during vol spikes
    },
}


def apply_regime_weights(signals: list[SignalResult], regime: str) -> list[SignalResult]:
    """Apply regime-specific strategy weight multipliers to a list of signals.

    Each signal's confidence is scaled by the multiplier defined in
    ``REGIME_STRATEGY_WEIGHTS`` for its ``strategy_name`` under the given regime.
    If no entry exists for a strategy/regime combination the confidence is left
    unchanged (neutral multiplier of 1.0).

    The resulting confidence is clamped to [0.0, 100.0].

    Args:
        signals: List of raw ``SignalResult`` objects produced by strategies.
        regime: Current market regime string (e.g. ``"TREND_BULL"``).

    Returns:
        New list of ``SignalResult`` objects with adjusted confidence values.
        The original objects are not mutated.
    """
    regime_weights = REGIME_STRATEGY_WEIGHTS.get(regime, {})
    if not regime_weights:
        return signals

    adjusted: list[SignalResult] = []
    for sig in signals:
        multiplier = regime_weights.get(sig.strategy_name, 1.0)
        if multiplier == 1.0:
            adjusted.append(sig)
            continue

        new_confidence = round(min(max(sig.confidence * multiplier, 0.0), 100.0), 2)
        # Build an adjusted copy — dataclass replace would require importing copy
        adjusted_sig = SignalResult(
            asset=sig.asset,
            timeframe=sig.timeframe,
            direction=sig.direction,
            confidence=new_confidence,
            entry_price=sig.entry_price,
            stop_loss=sig.stop_loss,
            take_profit_1=sig.take_profit_1,
            take_profit_2=sig.take_profit_2,
            risk_reward=sig.risk_reward,
            factors=sig.factors,
            strategy_name=sig.strategy_name,
            trailing_stop_pct=sig.trailing_stop_pct,
            partial_tp_schedule=sig.partial_tp_schedule,
            pyramid_levels=sig.pyramid_levels,
        )
        logger.debug(
            "Regime weight applied: strategy=%s regime=%s multiplier=%.2f conf %.1f→%.1f",
            sig.strategy_name, regime, multiplier, sig.confidence, new_confidence,
        )
        adjusted.append(adjusted_sig)

    return adjusted


def calculate_final_score(components: dict[str, float]) -> float:
    """Calculate weighted final score from component scores.

    Each component: -1.0 (strongly bearish) to +1.0 (strongly bullish).
    Returns confidence mapped to 0-100.
    """
    weighted = sum(
        components.get(key, 0.0) * weight for key, weight in WEIGHTS.items()
    )
    confidence = (weighted + 1) / 2 * 100
    return round(confidence, 2)


class SignalAggregator:
    """Aggregates signals from multiple strategies with multi-source weighting."""

    STRATEGY_TIMEOUT_SECONDS = 10
    SESSION_REDUCTION_FACTOR = 0.90
    MACRO_MINUTES_THRESHOLD = 15

    HIGHER_TF_MAP: dict[str, str] = {
        "1m": "15m",
        "5m": "1h",
        "15m": "4h",
        "1h": "4h",
        "4h": "1d",
    }

    HTF_ALIGNED_MULTIPLIER = 1.2
    HTF_NEUTRAL_MULTIPLIER = 1.0
    HTF_OPPOSING_MULTIPLIER = 0.7

    def __init__(self) -> None:
        self._strategies: list[BaseStrategy] = [
            TrendFollowingStrategy(),
            MeanReversionStrategy(),
            SMCStrategy(),
            VolumeBreakoutStrategy(),
            RSIScalpingStrategy(),
            TrendTraderStrategy(),
            FundingMeanReversionStrategy(),
            OITrendDivergenceStrategy(),
            BreakoutFailureStrategy(),
            DualMomentumStrategy(),
            BasisArbitrageStrategy(),
        ]
        self._classifier = RegimeClassifier()
        self._recent_signals: list[dict[str, Any]] = []

        # Optional analytics integrations
        self._percentile_tracker = (
            ConfidencePercentileTracker() if _PERCENTILE_TRACKER_AVAILABLE else None
        )
        self._psych_governor = (
            PsychologicalGovernor() if _PSYCH_GOVERNOR_AVAILABLE else None
        )

    def aggregate(
        self,
        asset: str,
        timeframe: str,
        market_data: pd.DataFrame,
        regime: RegimePrediction | None = None,
        onchain_score: float = 0.0,
        sentiment_score: float = 0.0,
        macro_events: list[dict[str, Any]] | None = None,
        htf_data: Optional[pd.DataFrame] = None,
        percentile_filter_pct: float = 0.0,
        equity_curve_scale: float = 1.0,
    ) -> SignalResult | None:
        """Run all compatible strategies and produce a single aggregated signal.

        Steps:
        1. Classify regime if not provided
        2. Select strategies compatible with current regime
        3. Generate signals from each strategy
        4. Apply weighted multi-source scoring
        5. Apply optional equity curve scaling
        6. Apply psychological governor multiplier
        7. Apply optional percentile filter
        8. Apply filters (confidence, regime, cooldown, macro)
        9. Return best signal or None

        Args:
            asset: Instrument symbol.
            timeframe: Candle timeframe string (e.g. '1h').
            market_data: OHLCV DataFrame with feature columns.
            regime: Pre-computed regime prediction or None to auto-classify.
            onchain_score: On-chain sentiment score in [-1, 1].
            sentiment_score: NLP/social sentiment score in [-1, 1].
            macro_events: List of upcoming macro event dicts.
            htf_data: Optional higher-timeframe OHLCV for confluence check.
            percentile_filter_pct: If > 0, only emit signals in the top N% of
                historical confidence (e.g. 30 = top 30%). Default 0 = disabled.
            equity_curve_scale: Scale factor from EquityCurveScaler that multiplies
                final_confidence. Values < 1 reduce sizing during drawdown. Default 1.0.
        """
        macro_events = macro_events or []

        # 1. Classify regime
        if regime is None:
            regime = self._classifier.predict_df(market_data)

        # Filter: no signals in HIGH_VOL_CHOPPY
        if regime.regime == "HIGH_VOL_CHOPPY":
            logger.info("Regime is HIGH_VOL_CHOPPY for %s — no signals", asset)
            return None

        # Filter: high-impact macro event within 15 minutes
        if self._has_imminent_macro(macro_events):
            logger.info("High-impact macro event imminent for %s — skipping", asset)
            return None

        # Determine market session based on UTC hour
        session = self._determine_market_session()

        # 2. Select compatible strategies
        context = MarketContext(
            regime=regime.regime,
            regime_confidence=regime.confidence,
            sentiment_score=sentiment_score,
            onchain_score=onchain_score,
            macro_events=macro_events,
            market_session=session,
        )

        compatible = [s for s in self._strategies if s.is_compatible(regime.regime)]
        if not compatible:
            logger.debug("No strategies compatible with %s for %s", regime.regime, asset)
            return None

        # 3. Generate signals from each strategy
        raw_signals: list[SignalResult] = []
        for strategy in compatible:
            try:
                start = time.monotonic()
                signal = strategy.generate_signal(asset, timeframe, market_data, context)
                elapsed = time.monotonic() - start
                if elapsed > self.STRATEGY_TIMEOUT_SECONDS:
                    logger.warning("Strategy %s took %.1fs for %s", strategy.name, elapsed, asset)
                if signal:
                    raw_signals.append(signal)
            except Exception as exc:
                logger.error("Strategy %s failed for %s: %s", strategy.name, asset, exc)

        if not raw_signals:
            return None

        # 4a. Apply regime-aware strategy weight multipliers
        raw_signals = apply_regime_weights(raw_signals, regime.regime)

        # 4b. Pick the best technical signal (highest confidence after regime weighting)
        best = max(raw_signals, key=lambda s: s.confidence)

        # 5. Apply multi-source weighting
        technical_score = (best.confidence / 100) * 2 - 1  # map 0-100 -> -1 to +1
        if best.direction == "SHORT":
            technical_score = -abs(technical_score)

        components = {
            "technical": technical_score,
            "onchain": onchain_score,
            "sentiment": sentiment_score,
            "macro": self._macro_score(macro_events),
        }
        final_confidence = calculate_final_score(components)

        # 6. Apply higher-timeframe confluence multiplier
        htf_multiplier = self._check_higher_tf_alignment(
            asset, timeframe, best.direction, htf_data,
        )
        if htf_multiplier != self.HTF_NEUTRAL_MULTIPLIER:
            final_confidence = round(
                min(final_confidence * htf_multiplier, 100.0), 2,
            )
            logger.info(
                "HTF confluence applied for %s: multiplier=%.2f, adjusted_conf=%.1f",
                asset, htf_multiplier, final_confidence,
            )

        # 7. Apply equity curve scale factor (reduces confidence during drawdown)
        if equity_curve_scale != 1.0:
            final_confidence = round(min(final_confidence * equity_curve_scale, 100.0), 2)
            logger.debug(
                "Equity curve scale %.2f applied for %s: conf=%.1f",
                equity_curve_scale, asset, final_confidence,
            )

        # 8. Apply psychological governor multiplier (biases from recent streak)
        if self._psych_governor is not None:
            try:
                final_confidence = self._psych_governor.apply_to_confidence(final_confidence)
                logger.debug(
                    "Psychological governor applied for %s: conf=%.1f", asset, final_confidence
                )
            except Exception as _gov_exc:
                logger.debug("PsychologicalGovernor apply failed: %s", _gov_exc)

        # 9. Track confidence percentile and apply filter if requested
        if self._percentile_tracker is not None:
            try:
                self._percentile_tracker.add_signal(
                    final_confidence, asset, best.strategy_name
                )
                if percentile_filter_pct > 0:
                    percentile = self._percentile_tracker.get_percentile(
                        final_confidence, asset, best.strategy_name
                    )
                    # E.g. filter_pct=30 → only top 30% pass → percentile must be >= 70
                    threshold_percentile = 100.0 - percentile_filter_pct
                    if percentile < threshold_percentile:
                        logger.info(
                            "Signal for %s filtered by percentile (%.1f < %.1f threshold, filter_pct=%.0f)",
                            asset, percentile, threshold_percentile, percentile_filter_pct,
                        )
                        return None
            except Exception as _pct_exc:
                logger.debug("ConfidencePercentileTracker failed: %s", _pct_exc)

        # Adjust direction based on final score
        if final_confidence < 50:
            # Multi-source disagreement — weaken or flip
            if final_confidence < 40:
                logger.info(
                    "Multi-source disagreement for %s (conf=%.1f) — no signal",
                    asset, final_confidence,
                )
                return None

        # Filter: minimum confidence
        if final_confidence < best.min_confidence:
            logger.info(
                "Signal for %s below min confidence (%.1f < %.1f)",
                asset, final_confidence, best.min_confidence,
            )
            return None

        # Filter: duplicate signal cooldown
        if self._is_duplicate(asset, best.direction):
            logger.info("Duplicate signal suppressed for %s %s", asset, best.direction)
            return None

        # Reduce confidence by 10% during off-hours or Asian session
        if session in ("OFF_HOURS", "ASIAN"):
            final_confidence = final_confidence * self.SESSION_REDUCTION_FACTOR
            logger.info(
                "Off-hours/Asian session confidence reduction applied for %s: %.1f",
                asset, final_confidence,
            )

        # Re-check minimum confidence after session adjustment
        if final_confidence < best.min_confidence:
            logger.info(
                "Signal for %s below min confidence after session adj (%.1f < %.1f)",
                asset, final_confidence, best.min_confidence,
            )
            return None

        # Build final signal with adjusted confidence
        final_signal = SignalResult(
            asset=best.asset,
            timeframe=best.timeframe,
            direction=best.direction,
            confidence=final_confidence,
            entry_price=best.entry_price,
            stop_loss=best.stop_loss,
            take_profit_1=best.take_profit_1,
            take_profit_2=best.take_profit_2,
            risk_reward=best.risk_reward,
            factors=best.factors,
            strategy_name=best.strategy_name,
        )

        # Record for cooldown tracking
        self._recent_signals.append({
            "asset": asset,
            "direction": best.direction,
            "timestamp": datetime.now(timezone.utc),
        })
        self._prune_old_signals()

        logger.info(
            "Signal emitted: %s %s %s conf=%.1f (strategy=%s)",
            asset, best.direction, timeframe, final_confidence, best.strategy_name,
        )
        return final_signal

    def _check_higher_tf_alignment(
        self,
        asset: str,
        timeframe: str,
        direction: str,
        htf_data: Optional[pd.DataFrame] = None,
    ) -> float:
        """Check if the higher-timeframe trend aligns with the signal direction.

        Uses EMA20 vs EMA50 crossover on the higher timeframe to determine trend.

        Args:
            asset: The asset symbol (used for logging).
            timeframe: The signal's timeframe (e.g. '5m', '1h').
            direction: Signal direction — 'LONG' or 'SHORT'.
            htf_data: Optional OHLCV DataFrame for the higher timeframe.
                      Must contain a 'close' column with enough rows for EMA50.

        Returns:
            Multiplier: 1.2 if aligned, 1.0 if neutral/no data, 0.7 if opposing.
        """
        higher_tf = self.HIGHER_TF_MAP.get(timeframe)
        if higher_tf is None:
            logger.debug("No higher TF mapping for %s — neutral multiplier", timeframe)
            return self.HTF_NEUTRAL_MULTIPLIER

        if htf_data is None or htf_data.empty or len(htf_data) < 50:
            logger.debug(
                "No sufficient HTF data for %s %s→%s — neutral multiplier",
                asset, timeframe, higher_tf,
            )
            return self.HTF_NEUTRAL_MULTIPLIER

        close = htf_data["close"].astype(float)
        ema20 = close.ewm(span=20, adjust=False).mean()
        ema50 = close.ewm(span=50, adjust=False).mean()

        latest_ema20 = ema20.iloc[-1]
        latest_ema50 = ema50.iloc[-1]

        if np.isnan(latest_ema20) or np.isnan(latest_ema50):
            return self.HTF_NEUTRAL_MULTIPLIER

        htf_bullish = latest_ema20 > latest_ema50
        signal_bullish = direction.upper() == "LONG"

        if htf_bullish == signal_bullish:
            logger.debug(
                "HTF %s aligned with %s for %s — boost multiplier",
                higher_tf, direction, asset,
            )
            return self.HTF_ALIGNED_MULTIPLIER

        logger.debug(
            "HTF %s opposes %s for %s — reduction multiplier",
            higher_tf, direction, asset,
        )
        return self.HTF_OPPOSING_MULTIPLIER

    @staticmethod
    def _determine_market_session() -> str:
        """Determine the current market session based on UTC hour.

        NYSE:    13:00-21:00 UTC
        LONDON:  07:00-16:00 UTC
        ASIAN:   00:00-09:00 UTC
        OFF_HOURS: everything else (gaps between sessions)
        """
        hour = datetime.now(timezone.utc).hour
        if 13 <= hour <= 21:
            return "NYSE"
        elif 7 <= hour <= 16:
            return "LONDON"
        elif 0 <= hour <= 9:
            return "ASIAN"
        else:
            return "OFF_HOURS"

    def _has_imminent_macro(self, events: list[dict[str, Any]]) -> bool:
        """Check if a HIGH impact macro event is within the blackout window.

        Window rules per event type:
        - FOMC / CPI: 4 hours before event + 2 hours after event
        - Other HIGH impact: 2 hours before + 1 hour after
        """
        now = datetime.now(timezone.utc)

        _FOMC_CPI_NAMES = {"fomc", "cpi", "federal open market", "consumer price"}

        for event in events:
            impact = event.get("impact", "").upper()
            if impact != "HIGH":
                continue

            event_time = event.get("time")
            if not event_time:
                continue

            event_name_lower = str(event.get("name", "")).lower()
            is_fomc_cpi = any(kw in event_name_lower for kw in _FOMC_CPI_NAMES)

            if is_fomc_cpi:
                window_before = timedelta(hours=4)
                window_after = timedelta(hours=2)
            else:
                window_before = timedelta(hours=2)
                window_after = timedelta(hours=1)

            # Block if we are within [event_time - window_before, event_time + window_after]
            if (event_time - window_before) <= now <= (event_time + window_after):
                logger.info(
                    "Macro blackout active for event '%s' (FOMC/CPI=%s)",
                    event.get("name", "unknown"), is_fomc_cpi,
                )
                return True

        return False

    def get_next_event_countdown(
        self, macro_events: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        """Return countdown info for the next upcoming HIGH-impact macro event.

        Returns a dict with keys:
            - minutes (float): minutes until the event
            - event_name (str): name of the event
            - event_time (datetime): UTC datetime of the event
            - impact (str): impact level

        Returns None if no future HIGH-impact events are in the list.
        """
        now = datetime.now(timezone.utc)
        future_high = [
            e for e in macro_events
            if e.get("impact", "").upper() == "HIGH"
            and e.get("time") is not None
            and e["time"] > now
        ]
        if not future_high:
            return None

        next_event = min(future_high, key=lambda e: e["time"])
        minutes_until = (next_event["time"] - now).total_seconds() / 60
        return {
            "minutes": round(minutes_until, 1),
            "event_name": next_event.get("name", "Unknown"),
            "event_time": next_event["time"],
            "impact": next_event.get("impact", "HIGH"),
        }

    def _macro_score(self, events: list[dict[str, Any]]) -> float:
        """Derive a macro score from upcoming events.

        No events = neutral (0). High impact near = slightly negative (caution).
        """
        if not events:
            return 0.0

        now = datetime.now(timezone.utc)
        score = 0.0
        for event in events:
            event_time = event.get("time")
            if not event_time:
                continue
            hours_until = (event_time - now).total_seconds() / 3600
            impact = event.get("impact", "").upper()
            if impact == "HIGH" and 0 < hours_until < 1:
                score -= 0.3
            elif impact == "HIGH" and 1 <= hours_until < 4:
                score -= 0.1

        return max(-1.0, min(1.0, score))

    def _is_duplicate(self, asset: str, direction: str) -> bool:
        """Check if an identical signal was emitted within the cooldown period."""
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=SIGNAL_COOLDOWN_HOURS)
        return any(
            s["asset"] == asset
            and s["direction"] == direction
            and s["timestamp"] >= cutoff
            for s in self._recent_signals
        )

    def _prune_old_signals(self) -> None:
        """Remove signals older than the cooldown period."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=SIGNAL_COOLDOWN_HOURS)
        self._recent_signals = [
            s for s in self._recent_signals if s["timestamp"] >= cutoff
        ]
