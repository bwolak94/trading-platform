"""Pre-Entry Checklist Scorer — auto-scores signals against 10 criteria before emission."""

from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from app.ai.strategies.base import MarketContext, SignalResult
from app.core.logging import get_logger

logger = get_logger(__name__)

CRITERIA = [
    "regime_aligned",         # strategy supports current regime
    "htf_aligned",            # higher timeframe trend agrees
    "volume_confirmed",       # volume > 1.2x 20-period average
    "news_clear",             # no HIGH impact event within 2 hours
    "active_session",         # London (7-16 UTC) or NY (13-21 UTC)
    "funding_aligned",        # funding rate supports direction
    "no_duplicate_position",  # no same asset/direction active
    "confidence_threshold",   # raw confidence > 65%
    "rr_minimum",             # risk/reward >= 2.0
    "not_overextended",       # price not > 2 ATR from nearest EMA20
]

# Strategy → compatible regimes mapping
_STRATEGY_REGIME_MAP: dict[str, set[str]] = {
    "trend_following":        {"TRENDING_UP", "TRENDING_DOWN", "TRENDING"},
    "trend_trader":           {"TRENDING_UP", "TRENDING_DOWN", "TRENDING"},
    "dual_momentum":          {"TRENDING_UP", "TRENDING_DOWN", "TRENDING"},
    "volume_breakout":        {"TRENDING_UP", "TRENDING_DOWN", "TRENDING", "BREAKOUT"},
    "mean_reversion":         {"CONSOLIDATION", "RANGING", "HIGH_VOLATILITY"},
    "rsi_scalping":           {"CONSOLIDATION", "RANGING"},
    "breakout_failure":       {"CONSOLIDATION", "RANGING"},
    "basis_arbitrage":        {"CONSOLIDATION", "RANGING", "HIGH_VOLATILITY"},
    "funding_mean_reversion": {"HIGH_VOLATILITY", "CONSOLIDATION"},
    "flash_crash_sniper":     {"HIGH_VOLATILITY"},
    "wyckoff_phases":         {"CONSOLIDATION", "ACCUMULATION"},
    "supply_demand":          {"CONSOLIDATION", "ACCUMULATION", "TRENDING_UP", "TRENDING_DOWN"},
    "carry_optimizer":        {"CONSOLIDATION", "RANGING"},
    "smc_strategy":           {"TRENDING_UP", "TRENDING_DOWN", "TRENDING", "BREAKOUT"},
}


@dataclass
class PreEntryScore:
    """Complete pre-entry evaluation result for a signal."""

    signal: SignalResult
    total_score: int                # 0-10
    grade: str                      # "A+" (9-10), "A" (8), "B" (6-7), "C" (4-5), "F" (<4)
    criteria_passed: list[str]
    criteria_failed: list[str]
    should_emit: bool               # True if score >= 6
    confidence_adjustment: float    # +0 to +10 for high scores
    checklist_text: str             # formatted checklist for display


class PreEntryScorer:
    """Quality gate for every signal before emission.

    Only signals meeting 6+/10 criteria are forwarded to users.

    High conviction (8+/10): confidence boosted by up to 10%
    Low conviction (<6/10): signal dropped silently.
    """

    MIN_SCORE_TO_EMIT = 6
    CONFIDENCE_BOOST_SCORE = 8    # score threshold for confidence boost
    MAX_CONFIDENCE_BOOST = 10.0   # max % boost

    def score(
        self,
        signal: SignalResult,
        market_data: pd.DataFrame,
        context: MarketContext,
        macro_events: list[dict] | None = None,
        active_signals: list[dict] | None = None,
        funding_rate: float = 0.0,
    ) -> PreEntryScore:
        """Score signal against all 10 criteria. Return PreEntryScore.

        Args:
            signal: The candidate signal to evaluate.
            market_data: OHLCV DataFrame with at least 50 bars (columns: open, high, low, close, volume).
            context: Current market context including regime.
            macro_events: List of upcoming macro event dicts with keys: impact, timestamp.
            active_signals: Currently active signal dicts with keys: asset, direction.
            funding_rate: Current 8h funding rate as decimal (e.g. 0.0003 = 0.03%).

        Returns:
            PreEntryScore with score, grade, and emission decision.
        """
        if macro_events is None:
            macro_events = []
        if active_signals is None:
            active_signals = []

        checks: dict[str, bool] = {
            "regime_aligned":       self._check_regime_aligned(signal, context),
            "htf_aligned":          self._check_htf_aligned(signal, market_data),
            "volume_confirmed":     self._check_volume(market_data),
            "news_clear":           self._check_news_clear(macro_events),
            "active_session":       self._check_active_session(),
            "funding_aligned":      self._check_funding_aligned(signal, funding_rate),
            "no_duplicate_position":self._check_no_duplicate(signal, active_signals),
            "confidence_threshold": self._check_confidence(signal),
            "rr_minimum":           self._check_rr(signal),
            "not_overextended":     self._check_not_overextended(signal, market_data),
        }

        passed = [c for c, ok in checks.items() if ok]
        failed = [c for c, ok in checks.items() if not ok]
        total_score = len(passed)
        grade = self._score_to_grade(total_score)
        should_emit = total_score >= self.MIN_SCORE_TO_EMIT

        # Confidence boost for high-conviction setups
        confidence_adjustment = 0.0
        if total_score >= self.CONFIDENCE_BOOST_SCORE:
            # Linear: score 8 → +5%, score 10 → +10%
            confidence_adjustment = round(
                self.MAX_CONFIDENCE_BOOST * (total_score - self.CONFIDENCE_BOOST_SCORE) / (10 - self.CONFIDENCE_BOOST_SCORE),
                1,
            )

        checklist_text = self._format_checklist(passed, failed)

        logger.info(
            "PreEntryScore %s/%s | asset=%s dir=%s grade=%s emit=%s",
            total_score, len(CRITERIA), signal.asset, signal.direction, grade, should_emit,
        )

        return PreEntryScore(
            signal=signal,
            total_score=total_score,
            grade=grade,
            criteria_passed=passed,
            criteria_failed=failed,
            should_emit=should_emit,
            confidence_adjustment=confidence_adjustment,
            checklist_text=checklist_text,
        )

    # ------------------------------------------------------------------
    # Individual criterion checks
    # ------------------------------------------------------------------

    def _check_regime_aligned(self, signal: SignalResult, context: MarketContext) -> bool:
        """True if signal's strategy supports current regime.

        Falls back to True when the strategy has no explicit mapping (unknown strategies
        are not penalised — they simply pass this gate).
        """
        strategy = signal.strategy_name.lower().replace(" ", "_")
        compatible = _STRATEGY_REGIME_MAP.get(strategy)
        if compatible is None:
            return True  # unknown strategy: do not penalise

        current_regime = context.regime.upper()
        # Normalise common aliases
        regime_aliases = {
            "BULL": "TRENDING_UP",
            "BEAR": "TRENDING_DOWN",
            "TREND": "TRENDING",
            "RANGE": "RANGING",
            "VOLATILE": "HIGH_VOLATILITY",
        }
        normalised = regime_aliases.get(current_regime, current_regime)
        return normalised in compatible

    def _check_htf_aligned(self, signal: SignalResult, market_data: pd.DataFrame) -> bool:
        """EMA20 > EMA50 for LONG (and EMA20 < EMA50 for SHORT) in last bar.

        Uses the provided DataFrame as a higher timeframe alignment proxy.
        Returns True when data is insufficient (cannot penalise lack of data).
        """
        if market_data is None or len(market_data) < 50:
            return True  # not enough data to check — do not penalise

        closes = market_data["close"].values.astype(float)
        ema20 = _ema(closes, 20)
        ema50 = _ema(closes, 50)

        if signal.direction == "LONG":
            return float(ema20[-1]) > float(ema50[-1])
        # SHORT
        return float(ema20[-1]) < float(ema50[-1])

    def _check_volume(self, market_data: pd.DataFrame) -> bool:
        """Latest volume > 1.2x rolling 20-period mean.

        Returns False when volume data is unavailable.
        """
        if market_data is None or len(market_data) < 21 or "volume" not in market_data.columns:
            return False

        volumes = market_data["volume"].values.astype(float)
        avg_20 = float(np.mean(volumes[-21:-1]))  # last 20 bars (excluding current)
        latest_vol = float(volumes[-1])

        if avg_20 <= 0:
            return False

        return latest_vol > avg_20 * 1.2

    def _check_news_clear(self, macro_events: list[dict]) -> bool:
        """No HIGH impact event within 2 hours of now UTC.

        Event dict expected keys: impact (str), timestamp (str ISO or datetime).
        """
        if not macro_events:
            return True  # no events = clear

        now = datetime.now(timezone.utc)
        window_seconds = 2 * 3600  # 2 hours

        for event in macro_events:
            impact = str(event.get("impact", "")).upper()
            if impact != "HIGH":
                continue

            ts = event.get("timestamp") or event.get("event_time")
            if ts is None:
                continue

            # Parse timestamp to datetime if it's a string
            if isinstance(ts, str):
                try:
                    from datetime import datetime as dt
                    if ts.endswith("Z"):
                        ts = ts.replace("Z", "+00:00")
                    event_dt = dt.fromisoformat(ts)
                    if event_dt.tzinfo is None:
                        event_dt = event_dt.replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
            elif isinstance(ts, (int, float)):
                event_dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            else:
                event_dt = ts
                if event_dt.tzinfo is None:
                    event_dt = event_dt.replace(tzinfo=timezone.utc)

            delta = abs((event_dt - now).total_seconds())
            if delta <= window_seconds:
                return False  # HIGH impact event too close

        return True

    def _check_active_session(self) -> bool:
        """True if current UTC time falls in London (7-16 UTC) or NY (13-21 UTC) sessions."""
        hour = datetime.now(timezone.utc).hour
        in_london = 7 <= hour < 16
        in_ny = 13 <= hour < 21
        return in_london or in_ny

    def _check_funding_aligned(self, signal: SignalResult, funding_rate: float) -> bool:
        """Funding alignment check.

        LONG signal + negative funding (shorts paying longs) = aligned.
        SHORT signal + positive funding (longs paying shorts) = aligned.
        Neutral if |funding| < 0.01% (0.0001 as decimal) — pass by default.
        """
        NEUTRAL_THRESHOLD = 0.0001  # 0.01%

        if abs(funding_rate) < NEUTRAL_THRESHOLD:
            return True  # neutral funding: no penalty

        if signal.direction == "LONG":
            # Negative funding favours longs (shorts pay longs)
            return funding_rate < 0

        # SHORT: positive funding favours shorts (longs pay shorts)
        return funding_rate > 0

    def _check_no_duplicate(self, signal: SignalResult, active_signals: list[dict]) -> bool:
        """True if no active signal exists for the same asset AND direction."""
        asset_norm = signal.asset.upper().replace("/", "").replace("-", "")
        direction = signal.direction.upper()

        for active in active_signals:
            active_asset = str(active.get("asset", "")).upper().replace("/", "").replace("-", "")
            active_dir = str(active.get("direction", "")).upper()
            if active_asset == asset_norm and active_dir == direction:
                return False

        return True

    def _check_confidence(self, signal: SignalResult) -> bool:
        """Signal confidence >= 65%."""
        return signal.confidence >= 65.0

    def _check_rr(self, signal: SignalResult) -> bool:
        """Risk/reward >= 2.0."""
        return signal.risk_reward >= 2.0

    def _check_not_overextended(self, signal: SignalResult, market_data: pd.DataFrame) -> bool:
        """Price not more than 2 ATR away from EMA20.

        Over-extended entries have poor win rates due to mean-reversion risk.
        Returns True (pass) if data is insufficient.
        """
        if market_data is None or len(market_data) < 20:
            return True  # not enough data — do not penalise

        closes = market_data["close"].values.astype(float)
        highs = market_data["high"].values.astype(float) if "high" in market_data.columns else closes
        lows = market_data["low"].values.astype(float) if "low" in market_data.columns else closes

        # ATR (14 periods)
        atr = _atr(highs, lows, closes, period=14)
        if atr <= 0:
            return True

        ema20 = _ema(closes, 20)
        entry = signal.entry_price
        distance = abs(entry - float(ema20[-1]))

        return distance <= 2.0 * atr

    # ------------------------------------------------------------------
    # Formatting helpers
    # ------------------------------------------------------------------

    def _format_checklist(self, passed: list[str], failed: list[str]) -> str:
        """Format as a human-readable checklist string. Passed = check mark, failed = X."""
        lines: list[str] = []
        for criterion in CRITERIA:
            label = criterion.replace("_", " ").title()
            if criterion in passed:
                lines.append(f"[OK] {label}")
            else:
                lines.append(f"[FAIL] {label}")
        score_line = f"Score: {len(passed)}/{len(CRITERIA)}"
        return score_line + "\n" + "\n".join(lines)

    def _score_to_grade(self, score: int) -> str:
        """Convert numeric score (0-10) to letter grade."""
        if score >= 9:
            return "A+"
        if score == 8:
            return "A"
        if score >= 6:
            return "B"
        if score >= 4:
            return "C"
        return "F"


# ---------------------------------------------------------------------------
# Internal math helpers (no external TA lib dependency)
# ---------------------------------------------------------------------------

def _ema(values: np.ndarray, period: int) -> np.ndarray:
    """Compute EMA via pandas for accuracy and vectorisation."""
    s = pd.Series(values)
    return s.ewm(span=period, adjust=False).mean().values


def _atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> float:
    """Compute ATR for the most recent bar using simplified Wilder smoothing."""
    n = len(closes)
    if n < 2:
        return 0.0

    tr_values: list[float] = []
    for i in range(1, n):
        high_low = highs[i] - lows[i]
        high_pc = abs(highs[i] - closes[i - 1])
        low_pc = abs(lows[i] - closes[i - 1])
        tr_values.append(max(high_low, high_pc, low_pc))

    if not tr_values:
        return 0.0

    # Wilder ATR (EMA with alpha = 1/period)
    atr_arr = pd.Series(tr_values).ewm(span=period, adjust=False).mean().values
    return float(atr_arr[-1])
