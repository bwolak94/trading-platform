"""Entry Precision Grader — grades actual entries vs ideal signal price."""

from collections import defaultdict
from dataclasses import dataclass


from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class EntryGrade:
    """Grade for a single trade entry relative to the signal price."""

    trade_id: str
    symbol: str
    signal_price: float         # price when signal was generated
    actual_entry_price: float   # price at which the trade was actually entered
    slippage_pct: float         # absolute slippage as positive percent (bad = large)
    grade: str                  # "A" (<0.1%), "B" (0.1-0.3%), "C" (0.3-0.8%), "D" (>0.8%)
    grade_value: int            # A=4, B=3, C=2, D=1
    is_chased: bool             # True when slippage >= Grade C threshold (>0.3%)
    estimated_pnl_impact: float  # estimated % P&L impact from slippage (negative = drag)
    feedback: str               # actionable feedback message


@dataclass
class EntryPrecisionReport:
    """Summary report across a collection of graded entries."""

    total_trades: int
    grade_distribution: dict[str, int]   # e.g. {"A": 10, "B": 8, "C": 5, "D": 2}
    avg_slippage_pct: float
    avg_grade_value: float
    cost_from_poor_entries: float        # total % P&L lost to Grade C/D slippage
    worst_offenders: list[str]           # symbols where chasing is most common
    improvement_tip: str


class EntryPrecisionGrader:
    """Grades trade entries: were you entering at signal price or chasing?

    Grading scale
    -------------
    Grade A : ≤ 0.10% slippage — professional execution
    Grade B : 0.10–0.30% — acceptable
    Grade C : 0.30–0.80% — chasing; needs improvement
    Grade D : > 0.80% — significantly chasing; major P&L drag

    Key insight
    -----------
    If 30% of trades are Grade C/D, you are losing 0.5–1% per trade from execution
    alone — before any consideration of signal quality.

    Slippage direction
    ------------------
    For LONG  : positive slippage = paid more than signal price (bad).
    For SHORT : negative slippage = sold lower than signal price (bad).
    In both cases ``slippage_pct`` is returned as a positive absolute value so that
    larger numbers always mean worse execution.
    """

    GRADE_THRESHOLDS: dict[str, float] = {"A": 0.1, "B": 0.3, "C": 0.8}
    # slippage < 0.1  → A
    # 0.1 <= slip < 0.3 → B
    # 0.3 <= slip < 0.8 → C
    # slip >= 0.8      → D

    def grade_entry(
        self,
        trade_id: str,
        symbol: str,
        signal_price: float,
        actual_entry_price: float,
        direction: str,
    ) -> EntryGrade:
        """Grade a single trade entry against the signal price.

        Args:
            trade_id: Unique identifier for the trade (for tracking).
            symbol: Instrument symbol.
            signal_price: Price at which the signal was generated.
            actual_entry_price: Price at which the trader actually entered.
            direction: ``"LONG"`` or ``"SHORT"``.

        Returns:
            EntryGrade dataclass with full analysis.
        """
        direction = direction.upper()
        slippage_pct = self._calc_slippage(signal_price, actual_entry_price, direction)
        grade_letter, grade_value = self._to_grade(slippage_pct)
        is_chased = slippage_pct >= self.GRADE_THRESHOLDS["B"]  # >= Grade C onset

        # Estimated P&L impact: the slippage is a direct cost against returns
        estimated_pnl_impact = -slippage_pct  # negative means it reduces profits

        feedback = self._build_feedback(
            grade_letter, slippage_pct, signal_price, actual_entry_price, direction
        )

        grade = EntryGrade(
            trade_id=trade_id,
            symbol=symbol,
            signal_price=round(signal_price, 8),
            actual_entry_price=round(actual_entry_price, 8),
            slippage_pct=round(slippage_pct, 4),
            grade=grade_letter,
            grade_value=grade_value,
            is_chased=is_chased,
            estimated_pnl_impact=round(estimated_pnl_impact, 4),
            feedback=feedback,
        )

        logger.debug(
            "EntryGrade: %s %s grade=%s slippage=%.3f%% chased=%s",
            symbol,
            direction,
            grade_letter,
            slippage_pct,
            is_chased,
        )
        return grade

    def generate_report(self, grades: list[EntryGrade]) -> EntryPrecisionReport:
        """Generate a summary precision report from a list of EntryGrade objects.

        Args:
            grades: List of ``EntryGrade`` instances to analyse.

        Returns:
            EntryPrecisionReport with aggregate statistics.
        """
        if not grades:
            return EntryPrecisionReport(
                total_trades=0,
                grade_distribution={"A": 0, "B": 0, "C": 0, "D": 0},
                avg_slippage_pct=0.0,
                avg_grade_value=0.0,
                cost_from_poor_entries=0.0,
                worst_offenders=[],
                improvement_tip="No trades to analyse.",
            )

        grade_distribution: dict[str, int] = {"A": 0, "B": 0, "C": 0, "D": 0}
        total_slippage = 0.0
        total_grade_value = 0.0
        cost_poor = 0.0

        # Track chase rate per symbol
        symbol_chase_count: dict[str, int] = defaultdict(int)
        symbol_total_count: dict[str, int] = defaultdict(int)

        for g in grades:
            grade_distribution[g.grade] = grade_distribution.get(g.grade, 0) + 1
            total_slippage += g.slippage_pct
            total_grade_value += g.grade_value
            symbol_total_count[g.symbol] += 1
            if g.is_chased:
                cost_poor += g.slippage_pct
                symbol_chase_count[g.symbol] += 1

        n = len(grades)
        avg_slippage = total_slippage / n
        avg_grade_value = total_grade_value / n

        # Worst offenders: symbols with highest chase rate (min 3 trades)
        chase_rates = {
            sym: symbol_chase_count[sym] / symbol_total_count[sym]
            for sym in symbol_total_count
            if symbol_total_count[sym] >= 3
        }
        worst_offenders = sorted(chase_rates, key=lambda s: chase_rates[s], reverse=True)[
            :5
        ]

        # Build improvement tip
        pct_poor = (
            (grade_distribution.get("C", 0) + grade_distribution.get("D", 0)) / n * 100
        )
        if pct_poor >= 40:
            tip = (
                f"{pct_poor:.0f}% of entries are Grade C/D. Use limit orders at or "
                "below signal price instead of market orders to reduce chasing."
            )
        elif pct_poor >= 20:
            tip = (
                f"{pct_poor:.0f}% of entries are Grade C/D. Consider setting a "
                "maximum slippage tolerance of 0.3% per trade."
            )
        elif avg_grade_value >= 3.5:
            tip = "Entry execution is excellent (avg grade ≥ A/B). Maintain discipline."
        else:
            tip = (
                "Entry execution is acceptable. Focus on signal quality improvements "
                "for greater P&L impact."
            )

        logger.info(
            "EntryPrecisionReport: n=%d avg_slip=%.3f%% grade_dist=%s cost_poor=%.2f%%",
            n,
            avg_slippage,
            grade_distribution,
            cost_poor,
        )

        return EntryPrecisionReport(
            total_trades=n,
            grade_distribution=grade_distribution,
            avg_slippage_pct=round(avg_slippage, 4),
            avg_grade_value=round(avg_grade_value, 3),
            cost_from_poor_entries=round(cost_poor, 4),
            worst_offenders=worst_offenders,
            improvement_tip=tip,
        )

    def _calc_slippage(
        self,
        signal_price: float,
        actual_price: float,
        direction: str,
    ) -> float:
        """Calculate absolute slippage percentage (higher = worse execution).

        For LONG  : slippage = (actual - signal) / signal * 100
                    Positive if you paid more than the signal price (bad).
                    Negative if you got a better fill (good → returned as 0.0).
        For SHORT : slippage = (signal - actual) / signal * 100
                    Positive if you sold lower than the signal price (bad).

        Args:
            signal_price: Price at signal generation time.
            actual_price: Actual fill price.
            direction: ``"LONG"`` or ``"SHORT"``.

        Returns:
            Absolute slippage in percent (≥ 0). Zero or better fills return 0.0.
        """
        if signal_price <= 0:
            return 0.0

        if direction == "LONG":
            raw = (actual_price - signal_price) / signal_price * 100
        else:  # SHORT
            raw = (signal_price - actual_price) / signal_price * 100

        # Better-than-signal fills are a bonus, not slippage → clamp to 0
        return max(0.0, float(raw))

    def _to_grade(self, slippage_pct: float) -> tuple[str, int]:
        """Convert a slippage percentage into a letter grade and numeric value.

        Args:
            slippage_pct: Absolute slippage in percent (≥ 0).

        Returns:
            Tuple of (letter_grade: str, grade_value: int).
            A=4, B=3, C=2, D=1.
        """
        if slippage_pct < self.GRADE_THRESHOLDS["A"]:
            return ("A", 4)
        if slippage_pct < self.GRADE_THRESHOLDS["B"]:
            return ("B", 3)
        if slippage_pct < self.GRADE_THRESHOLDS["C"]:
            return ("C", 2)
        return ("D", 1)

    @staticmethod
    def _build_feedback(
        grade: str,
        slippage_pct: float,
        signal_price: float,
        actual_price: float,
        direction: str,
    ) -> str:
        """Build a human-readable, actionable feedback string for an entry.

        Args:
            grade: Letter grade (A–D).
            slippage_pct: Absolute slippage percent.
            signal_price: Price at signal time.
            actual_price: Actual fill price.
            direction: ``"LONG"`` or ``"SHORT"``.

        Returns:
            Feedback string.
        """
        diff = actual_price - signal_price if direction == "LONG" else signal_price - actual_price

        if grade == "A":
            return (
                f"Excellent execution: slippage {slippage_pct:.3f}% "
                f"(signal={signal_price:.6f}, fill={actual_price:.6f})."
            )
        if grade == "B":
            return (
                f"Acceptable execution: {slippage_pct:.3f}% slippage "
                f"({'paid' if direction == 'LONG' else 'sold'} {abs(diff):.6f} "
                f"{'above' if diff > 0 else 'below'} signal). "
                "Use limit orders to improve."
            )
        if grade == "C":
            return (
                f"Chasing detected: {slippage_pct:.3f}% slippage on {direction}. "
                f"Signal was {signal_price:.6f}, entered at {actual_price:.6f}. "
                "Wait for price to return to signal level or skip the trade."
            )
        # Grade D
        return (
            f"Significant chase: {slippage_pct:.3f}% slippage on {direction}. "
            f"Signal={signal_price:.6f}, fill={actual_price:.6f}. "
            f"This {slippage_pct:.2f}% drag must be recovered before any profit. "
            "Only enter at or better than signal price."
        )
