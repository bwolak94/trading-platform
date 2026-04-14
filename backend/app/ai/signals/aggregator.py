"""Signal Aggregator — weighted multi-source scoring and signal emission."""

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd

from app.ai.regime.classifier import RegimeClassifier, RegimePrediction
from app.ai.strategies.base import BaseStrategy, MarketContext, SignalResult
from app.ai.strategies.mean_reversion import MeanReversionStrategy
from app.ai.strategies.rsi_scalping import RSIScalpingStrategy
from app.ai.strategies.smc_strategy import SMCStrategy
from app.ai.strategies.trend_following import TrendFollowingStrategy
from app.ai.strategies.volume_breakout import VolumeBreakoutStrategy

logger = logging.getLogger(__name__)

WEIGHTS = {
    "technical": 0.40,
    "onchain": 0.30,
    "sentiment": 0.20,
    "macro": 0.10,
}

# Duplicate signal cooldown
SIGNAL_COOLDOWN_HOURS = 4


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

    def __init__(self) -> None:
        self._strategies: list[BaseStrategy] = [
            TrendFollowingStrategy(),
            MeanReversionStrategy(),
            SMCStrategy(),
            VolumeBreakoutStrategy(),
            RSIScalpingStrategy(),
        ]
        self._classifier = RegimeClassifier()
        self._recent_signals: list[dict[str, Any]] = []

    def aggregate(
        self,
        asset: str,
        timeframe: str,
        market_data: pd.DataFrame,
        regime: RegimePrediction | None = None,
        onchain_score: float = 0.0,
        sentiment_score: float = 0.0,
        macro_events: list[dict[str, Any]] | None = None,
    ) -> SignalResult | None:
        """Run all compatible strategies and produce a single aggregated signal.

        Steps:
        1. Classify regime if not provided
        2. Select strategies compatible with current regime
        3. Generate signals from each strategy
        4. Apply weighted multi-source scoring
        5. Apply filters (confidence, regime, cooldown, macro)
        6. Return best signal or None
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
                if elapsed > 10:
                    logger.warning("Strategy %s took %.1fs for %s", strategy.name, elapsed, asset)
                if signal:
                    raw_signals.append(signal)
            except Exception as exc:
                logger.error("Strategy %s failed for %s: %s", strategy.name, asset, exc)

        if not raw_signals:
            return None

        # 4. Pick the best technical signal (highest confidence)
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
            final_confidence = final_confidence * 0.90
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
        """Check if a HIGH impact macro event is within 15 minutes."""
        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(minutes=15)
        for event in events:
            impact = event.get("impact", "").upper()
            event_time = event.get("time")
            if impact == "HIGH" and event_time and event_time <= cutoff:
                return True
        return False

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
