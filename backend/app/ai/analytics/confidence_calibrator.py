"""Confidence Calibrator — self-recalibrates signal confidence scores from outcomes."""

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class CalibrationBand:
    """Calibration statistics for a single confidence band."""

    stated_range: tuple[float, float]  # e.g. (60.0, 70.0) = 60-70% confidence bucket
    actual_win_rate: float             # observed win rate in this band
    sample_size: int
    calibration_error: float           # abs(stated_midpoint - actual_win_rate)
    is_well_calibrated: bool           # calibration_error < 10%
    adjustment_factor: float           # multiply stated confidence by this factor


@dataclass
class CalibrationReport:
    """Full calibration analysis for a strategy or all strategies."""

    strategy: str
    bands: list[CalibrationBand]
    overall_calibration_error: float   # mean absolute calibration error across bands
    is_overconfident: bool             # system claims higher confidence than actual WR
    is_underconfident: bool
    recommended_adjustment: str        # human-readable recommendation string
    calibration_curve: list[tuple[float, float]]  # (stated_midpoint, actual_wr) pairs


class ConfidenceCalibrator:
    """Measures and corrects confidence score calibration from historical signal outcomes.

    A well-calibrated system
    ------------------------
    - 70% confidence signals win 70 % of the time.
    - 80% confidence signals win 80 % of the time.

    An overconfident system
    -----------------------
    - 70% confidence signals actually win only 55 % of the time.
    - Requires a downward adjustment factor.

    Method
    ------
    1. Primary  : Platt scaling (logistic regression on binary outcomes) when
       sufficient data is available (≥ 100 signals total).
    2. Fallback : Simple per-band adjustment when data is sparse.

    Both paths produce a ``CalibrationReport`` with per-band ``adjustment_factor``
    values.  Apply them via ``apply_calibration()``.
    """

    BAND_WIDTH: float = 10.0    # bin width in confidence percentage points
    BAND_STARTS: list[float] = field(default_factory=list)  # not used as instance attr
    MIN_TOTAL_FOR_PLATT: int = 100  # minimum signals for logistic regression
    MIN_SAMPLES_PER_BAND: int = 10  # minimum for a reliable band estimate

    # Static band boundaries: [50-60), [60-70), [70-80), [80-90), [90-100]
    _BANDS: list[tuple[float, float]] = [
        (50.0, 60.0),
        (60.0, 70.0),
        (70.0, 80.0),
        (80.0, 90.0),
        (90.0, 100.0),
    ]

    def calibrate(
        self,
        signal_history: list[dict],
        strategy: str = "ALL",
        min_per_band: int = 10,
    ) -> CalibrationReport:
        """Analyse a list of historical signals and produce a calibration report.

        Each item in ``signal_history`` must have:
            - ``"confidence"`` : float (0-100)
            - ``"result"``     : ``"WIN"`` or ``"LOSS"``

        Steps
        -----
        1. Bin signals by confidence into 10-point bands (50-60, 60-70, …, 90+).
        2. Calculate the actual win rate per band.
        3. Measure calibration error (``|midpoint - actual_wr|``).
        4. If ≥ 100 signals: fit Platt scaling to derive band adjustments.
           Otherwise: use simple mean adjustment per band.
        5. Build and return the CalibrationReport.

        Args:
            signal_history: List of ``{"confidence": float, "result": str}`` dicts.
            strategy: Strategy label for the report (default ``"ALL"``).
            min_per_band: Minimum signals per band for a reliable estimate.

        Returns:
            CalibrationReport with per-band adjustments and overall stats.
        """
        if not signal_history:
            logger.warning("ConfidenceCalibrator.calibrate: empty signal history")
            return self._empty_report(strategy)

        confidences = [float(s["confidence"]) for s in signal_history]
        outcomes = [1 if s["result"].upper() == "WIN" else 0 for s in signal_history]

        bands: list[CalibrationBand] = []
        calibration_curve: list[tuple[float, float]] = []

        # Platt scaling if enough data
        use_platt = len(signal_history) >= self.MIN_TOTAL_FOR_PLATT
        platt_a: float = 1.0
        platt_b: float = 0.0
        if use_platt:
            try:
                platt_a, platt_b = self._platt_scale(confidences, outcomes)
                logger.info(
                    "ConfidenceCalibrator: Platt scaling fitted a=%.4f b=%.4f (strategy=%s)",
                    platt_a,
                    platt_b,
                    strategy,
                )
            except Exception as exc:
                logger.warning("ConfidenceCalibrator: Platt scaling failed: %s", exc)
                use_platt = False

        for band_lo, band_hi in self._BANDS:
            band_conf = [
                c for c in confidences if band_lo <= c < band_hi
            ]
            band_outcomes = [
                o
                for c, o in zip(confidences, outcomes)
                if band_lo <= c < band_hi
            ]

            # Include 100% in the last band
            if band_hi == 100.0:
                band_conf = [c for c in confidences if band_lo <= c <= 100.0]
                band_outcomes = [
                    o
                    for c, o in zip(confidences, outcomes)
                    if band_lo <= c <= 100.0
                ]

            n = len(band_conf)
            midpoint = (band_lo + band_hi) / 2.0

            if n < min_per_band:
                # Not enough data — neutral adjustment
                bands.append(
                    CalibrationBand(
                        stated_range=(band_lo, band_hi),
                        actual_win_rate=midpoint / 100.0,
                        sample_size=n,
                        calibration_error=0.0,
                        is_well_calibrated=True,
                        adjustment_factor=1.0,
                    )
                )
                calibration_curve.append((midpoint, midpoint / 100.0))
                continue

            actual_wr = float(np.mean(band_outcomes))
            stated_wr = midpoint / 100.0
            error = abs(stated_wr - actual_wr)

            if use_platt:
                # Platt-adjusted expected WR for the midpoint confidence
                calibrated_prob = self._sigmoid(platt_a * stated_wr + platt_b)
                adjustment_factor = (
                    calibrated_prob / stated_wr if stated_wr > 0 else 1.0
                )
            else:
                adjustment_factor = (
                    actual_wr / stated_wr if stated_wr > 0 else 1.0
                )

            # Clamp to [0.3, 1.5] to avoid extreme corrections
            adjustment_factor = float(np.clip(adjustment_factor, 0.3, 1.5))

            bands.append(
                CalibrationBand(
                    stated_range=(band_lo, band_hi),
                    actual_win_rate=round(actual_wr, 4),
                    sample_size=n,
                    calibration_error=round(error, 4),
                    is_well_calibrated=error < 0.10,
                    adjustment_factor=round(adjustment_factor, 4),
                )
            )
            calibration_curve.append((midpoint, round(actual_wr, 4)))

        # Overall stats
        errors = [b.calibration_error for b in bands if b.sample_size >= min_per_band]
        overall_error = float(np.mean(errors)) if errors else 0.0

        # Direction of bias
        avg_stated = float(np.mean(confidences)) / 100.0
        avg_actual = float(np.mean(outcomes))
        is_overconfident = avg_stated > avg_actual + 0.05
        is_underconfident = avg_actual > avg_stated + 0.05

        if is_overconfident:
            pct = round((avg_stated - avg_actual) * 100, 1)
            recommended_adjustment = f"REDUCE_BY_{pct}%"
        elif is_underconfident:
            pct = round((avg_actual - avg_stated) * 100, 1)
            recommended_adjustment = f"INCREASE_BY_{pct}%"
        else:
            recommended_adjustment = "WELL_CALIBRATED"

        logger.info(
            "ConfidenceCalibrator: strategy=%s overall_error=%.3f overconfident=%s adj=%s",
            strategy,
            overall_error,
            is_overconfident,
            recommended_adjustment,
        )

        return CalibrationReport(
            strategy=strategy,
            bands=bands,
            overall_calibration_error=round(overall_error, 4),
            is_overconfident=is_overconfident,
            is_underconfident=is_underconfident,
            recommended_adjustment=recommended_adjustment,
            calibration_curve=calibration_curve,
        )

    def apply_calibration(
        self,
        stated_confidence: float,
        report: CalibrationReport,
    ) -> float:
        """Adjust a stated confidence value using a pre-computed CalibrationReport.

        Applies the per-band adjustment factor for the band that contains the
        stated confidence, then clamps the result to [0.0, 100.0].

        Args:
            stated_confidence: The raw confidence value (0-100) from a strategy.
            report: Previously computed CalibrationReport.

        Returns:
            Calibrated confidence value (0-100).
        """
        adjusted = self._simple_band_adjustment(stated_confidence, report.bands)
        calibrated = float(np.clip(adjusted, 0.0, 100.0))
        logger.debug(
            "ConfidenceCalibrator.apply: %.1f → %.1f (strategy=%s)",
            stated_confidence,
            calibrated,
            report.strategy,
        )
        return round(calibrated, 2)

    def _platt_scale(
        self,
        confidences: list[float],
        outcomes: list[int],
    ) -> tuple[float, float]:
        """Fit a Platt scaling logistic regression to binary outcomes.

        Model: P(win) = sigmoid(a * x + b)  where x = confidence / 100.

        Uses gradient descent with a small fixed learning rate.

        Args:
            confidences: List of confidence values (0-100).
            outcomes: List of binary outcomes (1 = WIN, 0 = LOSS).

        Returns:
            Tuple (a, b) — the logistic regression coefficients.

        Raises:
            ValueError: If insufficient data is provided.
        """
        if len(confidences) < 10:
            raise ValueError("Insufficient data for Platt scaling")

        x = np.array(confidences, dtype=float) / 100.0
        y = np.array(outcomes, dtype=float)

        # Initialise: a=1, b=0 (identity mapping)
        a = 1.0
        b = 0.0
        lr = 0.1
        n = len(x)

        for _ in range(1000):
            pred = self._sigmoid_array(a * x + b)
            error = pred - y
            grad_a = float(np.dot(error, x)) / n
            grad_b = float(np.mean(error))
            a -= lr * grad_a
            b -= lr * grad_b

        return float(a), float(b)

    def _simple_band_adjustment(
        self,
        stated: float,
        bands: list[CalibrationBand],
    ) -> float:
        """Apply the adjustment factor from the matching confidence band.

        Args:
            stated: Stated confidence value (0-100).
            bands: List of CalibrationBand from a CalibrationReport.

        Returns:
            Adjusted confidence value (0-100).
        """
        for band in bands:
            lo, hi = band.stated_range
            if lo <= stated <= hi:
                return stated * band.adjustment_factor
        # Fallback: no matching band → return unchanged
        return stated

    @staticmethod
    def _sigmoid(x: float) -> float:
        """Numerically stable sigmoid function."""
        if x >= 0:
            return 1.0 / (1.0 + np.exp(-x))
        exp_x = np.exp(x)
        return exp_x / (1.0 + exp_x)

    @staticmethod
    def _sigmoid_array(x: np.ndarray) -> np.ndarray:
        """Vectorised numerically stable sigmoid."""
        return np.where(
            x >= 0,
            1.0 / (1.0 + np.exp(-x)),
            np.exp(x) / (1.0 + np.exp(x)),
        )

    def _empty_report(self, strategy: str) -> CalibrationReport:
        """Return a neutral CalibrationReport when no history is available."""
        neutral_bands = [
            CalibrationBand(
                stated_range=band,
                actual_win_rate=(band[0] + band[1]) / 2.0 / 100.0,
                sample_size=0,
                calibration_error=0.0,
                is_well_calibrated=True,
                adjustment_factor=1.0,
            )
            for band in self._BANDS
        ]
        return CalibrationReport(
            strategy=strategy,
            bands=neutral_bands,
            overall_calibration_error=0.0,
            is_overconfident=False,
            is_underconfident=False,
            recommended_adjustment="WELL_CALIBRATED",
            calibration_curve=[(b[0] + b[1]) / 2.0 for b in self._BANDS],  # type: ignore[misc]
        )
