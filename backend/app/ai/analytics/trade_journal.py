"""Trade Journal — pattern recognition and learning from historical trades.

Analyzes closed trade history to surface non-obvious performance patterns that
a trader might miss manually. The goal is to generate concrete, actionable
rules the operator can adopt — not just statistics.

Example insights discovered:
- "You lose 70% of trades taken after 20:00 UTC — stop trading after 8 PM"
- "trend_following has 68% WR but you're skipping 80% of its signals"
- "Confidence 75%+ signals return +1.8% avg vs +0.2% for 50–60% band"
- "Your win rate drops 22% in CONSOLIDATION regime vs TREND_BULL"
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional

import numpy as np

from app.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class TradeEntry:
    """A single trade record for journal analysis."""

    trade_id: str
    symbol: str
    direction: str              # "LONG" | "SHORT"
    strategy: str
    entry_time: datetime
    exit_time: Optional[datetime]
    entry_price: float
    exit_price: Optional[float]
    pnl_pct: float
    result: str                 # "WIN" | "LOSS" | "BE" (breakeven)
    confidence_at_entry: float
    regime: str
    session: str                # "LONDON" | "NYSE" | "ASIAN" | "OFF_HOURS"
    notes: str = ""


@dataclass
class PatternInsight:
    """A discovered performance pattern from trade history."""

    pattern_type: str           # "TIME_BASED" | "REGIME_BASED" | "STRATEGY_BASED" | "CONFIDENCE_BASED"
    description: str
    win_rate: float
    sample_size: int
    avg_return_pct: float
    recommendation: str         # actionable advice
    severity: str               # "CRITICAL" | "IMPORTANT" | "INFORMATIONAL"


@dataclass
class JournalReport:
    """Weekly / monthly trade journal analysis report."""

    period_start: datetime
    period_end: datetime
    total_trades: int
    win_rate: float
    avg_return_pct: float
    best_setup: str
    worst_setup: str
    key_insights: list[PatternInsight]
    improvement_actions: list[str]
    performance_trend: str      # "IMPROVING" | "DECLINING" | "STABLE"


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class TradeJournal:
    """Analyzes trade history to discover patterns and generate actionable insights.

    Usage::

        journal = TradeJournal()
        report = journal.analyze(trades, lookback_days=30)
        for action in report.improvement_actions:
            print(action)
    """

    MIN_SAMPLE_SIZE: int = 10   # minimum trades to draw conclusions from a group
    CONFIDENCE_BANDS: list[tuple[float, float, str]] = [
        (50.0,  60.0, "50–60%"),
        (60.0,  70.0, "60–70%"),
        (70.0,  80.0, "70–80%"),
        (80.0, 101.0, "80%+"),
    ]

    # --------------------------------------------------------------------- public

    def analyze(
        self,
        trades: list[TradeEntry],
        lookback_days: int = 30,
    ) -> JournalReport:
        """Generate a full journal report for the specified look-back period.

        Steps:
        1. Filter to look-back window
        2. Compute aggregate statistics
        3. Run all pattern analyses
        4. Generate improvement actions
        5. Assess performance trend (first-half vs second-half)

        Args:
            trades: All available :class:`TradeEntry` records.
            lookback_days: How many calendar days of history to analyze.

        Returns:
            :class:`JournalReport` with insights and improvement actions.
        """
        if not trades:
            logger.warning("TradeJournal.analyze: no trades provided")
            now = datetime.now(timezone.utc)
            return JournalReport(
                period_start=now - timedelta(days=lookback_days),
                period_end=now,
                total_trades=0,
                win_rate=0.0,
                avg_return_pct=0.0,
                best_setup="N/A",
                worst_setup="N/A",
                key_insights=[],
                improvement_actions=["Collect more trade history before analysis."],
                performance_trend="STABLE",
            )

        cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        filtered: list[TradeEntry] = [
            t for t in trades
            if t.entry_time >= cutoff and t.exit_time is not None
        ]

        period_start = min((t.entry_time for t in filtered), default=cutoff)
        period_end = max((t.exit_time for t in filtered if t.exit_time), default=cutoff)  # type: ignore[misc]

        if not filtered:
            logger.info("TradeJournal: no closed trades in lookback window")
            return JournalReport(
                period_start=period_start,
                period_end=period_end,
                total_trades=0,
                win_rate=0.0,
                avg_return_pct=0.0,
                best_setup="N/A",
                worst_setup="N/A",
                key_insights=[],
                improvement_actions=["No closed trades in the analysis window."],
                performance_trend="STABLE",
            )

        total = len(filtered)
        win_rate = len([t for t in filtered if t.result == "WIN"]) / total
        avg_return = float(np.mean([t.pnl_pct for t in filtered]))

        # Discover patterns
        insights = self.find_patterns(filtered)

        # Best and worst setups from insights
        best_setup = self._best_setup(insights)
        worst_setup = self._worst_setup(insights)

        improvement_actions = self._generate_improvement_actions(insights)
        trend = self._performance_trend(filtered)

        logger.info(
            "TradeJournal: period=%s→%s trades=%d wr=%.2f avg_ret=%.2f%% "
            "insights=%d trend=%s",
            period_start.date(),
            period_end.date(),
            total,
            win_rate,
            avg_return,
            len(insights),
            trend,
        )

        return JournalReport(
            period_start=period_start,
            period_end=period_end,
            total_trades=total,
            win_rate=round(win_rate, 4),
            avg_return_pct=round(avg_return, 4),
            best_setup=best_setup,
            worst_setup=worst_setup,
            key_insights=insights,
            improvement_actions=improvement_actions,
            performance_trend=trend,
        )

    def find_patterns(self, trades: list[TradeEntry]) -> list[PatternInsight]:
        """Discover performance patterns across multiple dimensions.

        Args:
            trades: Closed trade list (already filtered to desired window).

        Returns:
            Combined list of :class:`PatternInsight` objects, sorted by severity.
        """
        insights: list[PatternInsight] = []

        try:
            insights.extend(self._analyze_by_hour(trades))
        except Exception as exc:
            logger.exception("TradeJournal._analyze_by_hour failed: %s", exc)

        try:
            insights.extend(self._analyze_by_regime(trades))
        except Exception as exc:
            logger.exception("TradeJournal._analyze_by_regime failed: %s", exc)

        try:
            insights.extend(self._analyze_by_confidence_band(trades))
        except Exception as exc:
            logger.exception("TradeJournal._analyze_by_confidence_band failed: %s", exc)

        try:
            insights.extend(self._analyze_by_strategy(trades))
        except Exception as exc:
            logger.exception("TradeJournal._analyze_by_strategy failed: %s", exc)

        # Sort: CRITICAL first, then IMPORTANT, then INFORMATIONAL
        severity_order = {"CRITICAL": 0, "IMPORTANT": 1, "INFORMATIONAL": 2}
        insights.sort(key=lambda i: severity_order.get(i.severity, 3))
        return insights

    # --------------------------------------------------------------------- private analysis

    def _analyze_by_hour(self, trades: list[TradeEntry]) -> list[PatternInsight]:
        """Find time-of-day performance patterns (UTC hour).

        Groups trades into hourly buckets and flags hours with win rate
        significantly above or below the global average.

        Args:
            trades: Closed trade list.

        Returns:
            List of time-based :class:`PatternInsight` objects.
        """
        insights: list[PatternInsight] = []
        baseline_wr = self._calc_win_rate(trades)

        # Group by 4-hour windows to increase sample sizes
        buckets: dict[str, list[TradeEntry]] = {}
        for trade in trades:
            hour = trade.entry_time.hour
            bucket_start = (hour // 4) * 4
            label = f"{bucket_start:02d}:00–{bucket_start + 4:02d}:00 UTC"
            buckets.setdefault(label, []).append(trade)

        for label, group in buckets.items():
            if len(group) < self.MIN_SAMPLE_SIZE:
                continue

            wr = self._calc_win_rate(group)
            avg_ret = float(np.mean([t.pnl_pct for t in group]))
            deviation = wr - baseline_wr

            if abs(deviation) < 0.10:
                continue  # not significant

            severity = "CRITICAL" if abs(deviation) >= 0.20 else "IMPORTANT"
            if deviation < 0:
                description = (
                    f"Poor performance during {label}: "
                    f"{wr:.0%} WR vs {baseline_wr:.0%} overall "
                    f"({len(group)} trades)"
                )
                recommendation = (
                    f"Consider avoiding entries during {label}. "
                    f"Win rate is {abs(deviation):.0%} below average."
                )
            else:
                description = (
                    f"Strong performance during {label}: "
                    f"{wr:.0%} WR vs {baseline_wr:.0%} overall "
                    f"({len(group)} trades)"
                )
                recommendation = (
                    f"Prioritise signals during {label}. "
                    f"Win rate is {deviation:.0%} above average."
                )
                severity = "INFORMATIONAL"

            insights.append(PatternInsight(
                pattern_type="TIME_BASED",
                description=description,
                win_rate=round(wr, 4),
                sample_size=len(group),
                avg_return_pct=round(avg_ret, 4),
                recommendation=recommendation,
                severity=severity,
            ))

        return insights

    def _analyze_by_regime(self, trades: list[TradeEntry]) -> list[PatternInsight]:
        """Find regime-based performance patterns.

        Args:
            trades: Closed trade list.

        Returns:
            List of regime-based :class:`PatternInsight` objects.
        """
        insights: list[PatternInsight] = []
        baseline_wr = self._calc_win_rate(trades)

        regimes: dict[str, list[TradeEntry]] = {}
        for trade in trades:
            regimes.setdefault(trade.regime, []).append(trade)

        for regime, group in regimes.items():
            if len(group) < self.MIN_SAMPLE_SIZE:
                continue

            wr = self._calc_win_rate(group)
            avg_ret = float(np.mean([t.pnl_pct for t in group]))
            deviation = wr - baseline_wr

            if abs(deviation) < 0.08:
                continue

            severity = "CRITICAL" if abs(deviation) >= 0.20 else "IMPORTANT"
            if deviation < 0:
                description = (
                    f"Underperformance in {regime} regime: "
                    f"{wr:.0%} WR ({len(group)} trades, avg {avg_ret:+.2f}%)"
                )
                recommendation = (
                    f"Reduce position size or skip signals in {regime} regime. "
                    f"Win rate {abs(deviation):.0%} below average."
                )
            else:
                description = (
                    f"Strong edge in {regime} regime: "
                    f"{wr:.0%} WR ({len(group)} trades, avg {avg_ret:+.2f}%)"
                )
                recommendation = (
                    f"Increase confidence threshold slightly in {regime} — "
                    f"you have proven edge here."
                )
                severity = "INFORMATIONAL"

            insights.append(PatternInsight(
                pattern_type="REGIME_BASED",
                description=description,
                win_rate=round(wr, 4),
                sample_size=len(group),
                avg_return_pct=round(avg_ret, 4),
                recommendation=recommendation,
                severity=severity,
            ))

        return insights

    def _analyze_by_confidence_band(
        self, trades: list[TradeEntry]
    ) -> list[PatternInsight]:
        """Find patterns across confidence bands (50–60%, 60–70%, 70–80%, 80%+).

        Flags calibration issues when high-confidence signals don't outperform
        low-confidence ones.

        Args:
            trades: Closed trade list.

        Returns:
            List of confidence-calibration :class:`PatternInsight` objects.
        """
        insights: list[PatternInsight] = []
        band_results: list[tuple[str, float, float, int]] = []  # (label, wr, avg_ret, n)

        for low, high, label in self.CONFIDENCE_BANDS:
            group = [
                t for t in trades
                if low <= t.confidence_at_entry < high
            ]
            if len(group) < self.MIN_SAMPLE_SIZE:
                continue

            wr = self._calc_win_rate(group)
            avg_ret = float(np.mean([t.pnl_pct for t in group]))
            band_results.append((label, wr, avg_ret, len(group)))

        # Check that higher confidence bands outperform lower ones
        if len(band_results) >= 2:
            # Compare highest to lowest band
            lowest_band = band_results[0]
            highest_band = band_results[-1]

            wr_improvement = highest_band[1] - lowest_band[1]

            if wr_improvement < 0.05:
                insights.append(PatternInsight(
                    pattern_type="CONFIDENCE_BASED",
                    description=(
                        f"Confidence calibration issue: {highest_band[0]} band WR "
                        f"({highest_band[1]:.0%}) is not materially better than "
                        f"{lowest_band[0]} band WR ({lowest_band[1]:.0%}). "
                        f"High confidence signals are not outperforming."
                    ),
                    win_rate=highest_band[1],
                    sample_size=sum(b[3] for b in band_results),
                    avg_return_pct=float(np.mean([b[2] for b in band_results])),
                    recommendation=(
                        "Review confidence scoring methodology. "
                        "Either raise the minimum confidence threshold or "
                        "recalibrate the scoring components."
                    ),
                    severity="IMPORTANT",
                ))

        # Report best confidence band
        if band_results:
            best = max(band_results, key=lambda x: x[1])
            if best[1] >= 0.60:
                insights.append(PatternInsight(
                    pattern_type="CONFIDENCE_BASED",
                    description=(
                        f"Best performing confidence band: {best[0]} "
                        f"→ {best[1]:.0%} WR, avg return {best[2]:+.2f}% "
                        f"({best[3]} trades)"
                    ),
                    win_rate=round(best[1], 4),
                    sample_size=best[3],
                    avg_return_pct=round(best[2], 4),
                    recommendation=(
                        f"Consider using {best[0]} as your primary entry filter. "
                        f"Only take signals in this confidence range."
                    ),
                    severity="INFORMATIONAL",
                ))

        return insights

    def _analyze_by_strategy(
        self, trades: list[TradeEntry]
    ) -> list[PatternInsight]:
        """Find best and worst performing strategies by win rate and avg return.

        Args:
            trades: Closed trade list.

        Returns:
            List of strategy-based :class:`PatternInsight` objects.
        """
        insights: list[PatternInsight] = []
        strategies: dict[str, list[TradeEntry]] = {}

        for trade in trades:
            strategies.setdefault(trade.strategy, []).append(trade)

        strategy_stats: list[tuple[str, float, float, int]] = []

        for strat, group in strategies.items():
            if len(group) < self.MIN_SAMPLE_SIZE:
                continue
            wr = self._calc_win_rate(group)
            avg_ret = float(np.mean([t.pnl_pct for t in group]))
            strategy_stats.append((strat, wr, avg_ret, len(group)))

        if not strategy_stats:
            return insights

        strategy_stats.sort(key=lambda x: x[1], reverse=True)
        baseline_wr = self._calc_win_rate(trades)

        for strat, wr, avg_ret, n in strategy_stats:
            deviation = wr - baseline_wr
            severity = "IMPORTANT" if abs(deviation) >= 0.12 else "INFORMATIONAL"

            if deviation >= 0.12:
                description = (
                    f"Top performer: {strat} — {wr:.0%} WR, "
                    f"avg return {avg_ret:+.2f}% ({n} trades)"
                )
                recommendation = (
                    f"Increase signal weight and position size for '{strat}'. "
                    f"It has {deviation:.0%} edge over average."
                )
            elif deviation <= -0.12:
                description = (
                    f"Underperformer: {strat} — {wr:.0%} WR, "
                    f"avg return {avg_ret:+.2f}% ({n} trades)"
                )
                recommendation = (
                    f"Consider raising minimum confidence for '{strat}' signals "
                    f"or temporarily disabling it while in drawdown."
                )
                severity = "CRITICAL" if deviation <= -0.20 else "IMPORTANT"
            else:
                continue

            insights.append(PatternInsight(
                pattern_type="STRATEGY_BASED",
                description=description,
                win_rate=round(wr, 4),
                sample_size=n,
                avg_return_pct=round(avg_ret, 4),
                recommendation=recommendation,
                severity=severity,
            ))

        return insights

    def _generate_improvement_actions(
        self, insights: list[PatternInsight]
    ) -> list[str]:
        """Convert pattern insights into specific, prioritised actionable rules.

        Args:
            insights: List of discovered :class:`PatternInsight` objects.

        Returns:
            Ordered list of action strings (highest severity first).
        """
        actions: list[str] = []
        seen: set[str] = set()

        for insight in insights:
            rec = insight.recommendation
            if rec and rec not in seen:
                prefix = {
                    "CRITICAL": "[CRITICAL] ",
                    "IMPORTANT": "[IMPORTANT] ",
                    "INFORMATIONAL": "[INFO] ",
                }.get(insight.severity, "")
                actions.append(f"{prefix}{rec}")
                seen.add(rec)

        if not actions:
            actions.append(
                "No significant patterns detected — continue current approach "
                "and collect more trade data."
            )

        return actions

    def _performance_trend(self, trades: list[TradeEntry]) -> str:
        """Compare win rate of the first half vs second half of the trade list.

        Trades are sorted chronologically before splitting.

        Args:
            trades: Closed trade list for the period.

        Returns:
            "IMPROVING" | "DECLINING" | "STABLE"
        """
        if len(trades) < self.MIN_SAMPLE_SIZE * 2:
            return "STABLE"

        sorted_trades = sorted(trades, key=lambda t: t.entry_time)
        mid = len(sorted_trades) // 2
        first_half = sorted_trades[:mid]
        second_half = sorted_trades[mid:]

        wr_first = self._calc_win_rate(first_half)
        wr_second = self._calc_win_rate(second_half)
        delta = wr_second - wr_first

        if delta >= 0.07:
            return "IMPROVING"
        if delta <= -0.07:
            return "DECLINING"
        return "STABLE"

    # --------------------------------------------------------------------- helpers

    def _calc_win_rate(self, trades: list[TradeEntry]) -> float:
        """Calculate win rate from a list of trades.

        Args:
            trades: Trade list (may be empty).

        Returns:
            Win rate [0, 1]; returns 0.0 for empty list.
        """
        if not trades:
            return 0.0
        wins = sum(1 for t in trades if t.result == "WIN")
        return wins / len(trades)

    def _best_setup(self, insights: list[PatternInsight]) -> str:
        """Extract the best-performing setup description from insights.

        Args:
            insights: All discovered insights.

        Returns:
            Description string of the top performer, or "N/A".
        """
        positive = [
            i for i in insights
            if i.win_rate > 0.60 and i.severity == "INFORMATIONAL"
        ]
        if not positive:
            return "N/A"
        best = max(positive, key=lambda i: i.win_rate)
        return best.description

    def _worst_setup(self, insights: list[PatternInsight]) -> str:
        """Extract the worst-performing setup description from insights.

        Args:
            insights: All discovered insights.

        Returns:
            Description string of the worst performer, or "N/A".
        """
        negative = [
            i for i in insights
            if i.severity in ("CRITICAL", "IMPORTANT")
            and i.win_rate < 0.50
        ]
        if not negative:
            return "N/A"
        worst = min(negative, key=lambda i: i.win_rate)
        return worst.description
