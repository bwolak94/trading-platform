"""Bayesian Signal Updater — updates signal probability as new evidence arrives.

Uses Bayes' theorem to adjust the prior probability of a signal being valid
as new market evidence confirms or denies the setup. Allows dynamic confidence
updates without waiting for the trade to close.

P(signal_valid | evidence) = P(evidence | signal_valid) × P(signal_valid) / P(evidence)
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

# Likelihood ratios: P(evidence | state)
EVIDENCE_LIKELIHOOD: dict[str, dict[str, float]] = {
    "price_moves_in_direction": {"if_valid": 0.75, "if_invalid": 0.25},
    "volume_confirms": {"if_valid": 0.70, "if_invalid": 0.35},
    "regime_aligns": {"if_valid": 0.80, "if_invalid": 0.30},
    "higher_tf_agrees": {"if_valid": 0.72, "if_invalid": 0.28},
    "funding_rate_supports": {"if_valid": 0.68, "if_invalid": 0.35},
    "sentiment_aligns": {"if_valid": 0.65, "if_invalid": 0.40},
    "price_moves_against": {"if_valid": 0.20, "if_invalid": 0.75},
    "volume_diverges": {"if_valid": 0.25, "if_invalid": 0.65},
    "regime_opposes": {"if_valid": 0.15, "if_invalid": 0.70},
    "higher_tf_opposes": {"if_valid": 0.18, "if_invalid": 0.68},
}


class BayesianSignalUpdater:
    """Updates signal confidence using sequential Bayesian inference."""

    def update_probability(
        self,
        prior_probability: float,
        evidence_list: list[str],
    ) -> dict[str, Any]:
        """Apply Bayesian updates for each piece of evidence.

        Args:
            prior_probability: Initial signal confidence as probability [0, 1]
            evidence_list: List of evidence keys from EVIDENCE_LIKELIHOOD

        Returns:
            {prior, posterior, evidence_applied, confidence_change, recommendation}
        """
        posterior = max(0.001, min(0.999, prior_probability))  # avoid 0/1 extremes
        applied: list[dict[str, Any]] = []

        for evidence_key in evidence_list:
            if evidence_key not in EVIDENCE_LIKELIHOOD:
                logger.debug("Unknown evidence key: %s", evidence_key)
                continue

            likelihoods = EVIDENCE_LIKELIHOOD[evidence_key]
            prev = posterior
            posterior = self.compute_posterior(
                prior=posterior,
                likelihood_valid=likelihoods["if_valid"],
                likelihood_invalid=likelihoods["if_invalid"],
            )
            applied.append({
                "evidence": evidence_key,
                "prior": round(prev, 4),
                "posterior": round(posterior, 4),
                "impact": round(posterior - prev, 4),
                "direction": "STRENGTHENS" if posterior > prev else "WEAKENS",
            })

        confidence_change = round(posterior - prior_probability, 4)
        recommendation = self._build_recommendation(posterior)

        return {
            "prior": round(prior_probability, 4),
            "posterior": round(posterior, 4),
            "confidence_label": self.classify_confidence(posterior),
            "evidence_applied": applied,
            "evidence_count": len(applied),
            "confidence_change": confidence_change,
            "recommendation": recommendation,
        }

    def compute_posterior(
        self,
        prior: float,
        likelihood_valid: float,
        likelihood_invalid: float,
    ) -> float:
        """Apply a single Bayesian update step.

        P(valid | evidence) = P(e | valid) * P(valid) / [P(e|valid)*P(valid) + P(e|invalid)*P(invalid)]

        Args:
            prior: Current probability [0, 1]
            likelihood_valid: P(evidence | signal is valid)
            likelihood_invalid: P(evidence | signal is invalid)

        Returns:
            Updated posterior probability [0, 1]
        """
        numerator = likelihood_valid * prior
        denominator = numerator + likelihood_invalid * (1.0 - prior)
        return numerator / denominator if denominator > 0 else prior

    def classify_confidence(self, probability: float) -> str:
        """Map probability to a human-readable label.

        Args:
            probability: Signal probability [0, 1]

        Returns:
            Confidence label string
        """
        if probability >= 0.70:
            return "HIGH"
        if probability >= 0.50:
            return "MEDIUM"
        return "LOW"

    def get_available_evidence_types(self) -> list[str]:
        """Return list of valid evidence type keys.

        Returns:
            List of evidence key strings
        """
        return list(EVIDENCE_LIKELIHOOD.keys())

    def _build_recommendation(self, posterior: float) -> str:
        """Generate recommendation based on updated probability.

        Args:
            posterior: Updated probability

        Returns:
            Recommendation string
        """
        if posterior >= 0.75:
            return "HIGH confidence — evidence strongly supports the signal. Proceed with full sizing."
        if posterior >= 0.60:
            return "MEDIUM-HIGH confidence — signal is holding up. Standard position sizing appropriate."
        if posterior >= 0.50:
            return "MEDIUM confidence — mixed evidence. Consider half-size entry or wait for more confirmation."
        if posterior >= 0.35:
            return "LOW confidence — evidence weakening signal. Skip or exit if already in."
        return "VERY LOW confidence — evidence contradicts signal. Exit or do not enter."


# Module-level singleton
_updater: BayesianSignalUpdater | None = None


def get_bayesian_updater() -> BayesianSignalUpdater:
    """Return the global BayesianSignalUpdater singleton.

    Returns:
        Shared updater instance
    """
    global _updater
    if _updater is None:
        _updater = BayesianSignalUpdater()
    return _updater
