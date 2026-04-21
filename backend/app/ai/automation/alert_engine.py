"""Alert Rule Engine — evaluates dynamic alert rules against live market data.

Supports conditional alerts across multiple data dimensions:
- Signal confidence thresholds
- Price level breaks
- Regime changes
- Funding rate anomalies

Each rule has a cooldown period to prevent notification spam.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class AlertRule:
    """Represents a single alert rule definition."""

    rule_id: str
    name: str
    condition_type: str   # SIGNAL_CONFIDENCE | PRICE_LEVEL | REGIME_CHANGE | FUNDING_RATE | SENTIMENT
    operator: str         # GT | LT | EQ | GTE | LTE | CHANGE
    threshold: float
    symbol: str
    channels: list[str]   # telegram | discord | email | webhook
    active: bool = True
    triggered_count: int = 0
    description: str = ""


class AlertRuleEngine:
    """Evaluates alert rules against live market snapshots."""

    def __init__(self, cooldown_seconds: int = 3600) -> None:
        """Initialize the alert rule engine.

        Args:
            cooldown_seconds: Minimum seconds between same-rule triggers (default 1h)
        """
        self._rules: list[AlertRule] = []
        self._cooldown_tracker: dict[str, float] = {}  # rule_id -> last_triggered_ts
        self.cooldown_seconds = cooldown_seconds

    def add_rule(self, rule: AlertRule) -> None:
        """Add a new alert rule.

        Args:
            rule: AlertRule instance to register
        """
        # Remove any existing rule with same ID
        self._rules = [r for r in self._rules if r.rule_id != rule.rule_id]
        self._rules.append(rule)
        logger.info("AlertEngine | Rule added: %s (%s)", rule.rule_id, rule.name)

    def remove_rule(self, rule_id: str) -> bool:
        """Remove an alert rule by ID.

        Args:
            rule_id: Rule identifier

        Returns:
            True if rule was found and removed
        """
        before = len(self._rules)
        self._rules = [r for r in self._rules if r.rule_id != rule_id]
        removed = len(self._rules) < before
        if removed:
            logger.info("AlertEngine | Rule removed: %s", rule_id)
        return removed

    def get_rules(self) -> list[dict[str, Any]]:
        """Return all rules as serializable dicts.

        Returns:
            List of rule dicts
        """
        return [
            {
                "rule_id": r.rule_id,
                "name": r.name,
                "condition_type": r.condition_type,
                "operator": r.operator,
                "threshold": r.threshold,
                "symbol": r.symbol,
                "channels": r.channels,
                "active": r.active,
                "triggered_count": r.triggered_count,
                "description": r.description,
                "in_cooldown": self._is_in_cooldown(r.rule_id),
            }
            for r in self._rules
        ]

    async def evaluate_all_rules(self, market_snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        """Evaluate all active rules against current market data.

        Args:
            market_snapshot: Dict with keys like {signal_confidence, price, regime,
                             funding_rate, sentiment_score, symbol}

        Returns:
            List of triggered alert dicts: [{rule_id, name, message, symbol, channels}]
        """
        triggered: list[dict[str, Any]] = []

        for rule in self._rules:
            if not rule.active:
                continue
            if self._is_in_cooldown(rule.rule_id):
                continue

            try:
                fired = self._evaluate_rule(rule, market_snapshot)
            except Exception as exc:
                logger.debug("Rule evaluation error %s: %s", rule.rule_id, exc)
                continue

            if fired:
                self._mark_triggered(rule.rule_id)
                rule.triggered_count += 1
                message = self._build_message(rule, market_snapshot)
                triggered.append({
                    "rule_id": rule.rule_id,
                    "name": rule.name,
                    "message": message,
                    "symbol": rule.symbol,
                    "channels": rule.channels,
                    "condition_type": rule.condition_type,
                    "threshold": rule.threshold,
                })
                logger.info("AlertEngine | Rule fired: %s for %s", rule.rule_id, rule.symbol)

        return triggered

    def _evaluate_rule(self, rule: AlertRule, snapshot: dict[str, Any]) -> bool:
        """Evaluate a single rule condition against the snapshot.

        Args:
            rule: Rule to evaluate
            snapshot: Market snapshot data

        Returns:
            True if the rule condition is satisfied
        """
        # Extract the relevant value based on condition type
        value: float | None = None

        if rule.condition_type == "SIGNAL_CONFIDENCE":
            value = snapshot.get("signal_confidence")
        elif rule.condition_type == "PRICE_LEVEL":
            value = snapshot.get("price") or snapshot.get("current_price")
        elif rule.condition_type == "FUNDING_RATE":
            value = snapshot.get("funding_rate")
        elif rule.condition_type == "SENTIMENT":
            value = snapshot.get("sentiment_score")
        elif rule.condition_type == "REGIME_CHANGE":
            current_regime = snapshot.get("regime", "")
            prev_regime = snapshot.get("prev_regime", current_regime)
            return current_regime != prev_regime
        else:
            return False

        if value is None:
            return False

        return self._apply_operator(value, rule.operator, rule.threshold)

    def _apply_operator(self, value: float, operator: str, threshold: float) -> bool:
        """Apply comparison operator between value and threshold.

        Args:
            value: Actual measured value
            operator: Comparison operator string
            threshold: Threshold to compare against

        Returns:
            True if comparison is satisfied
        """
        if operator == "GT":
            return value > threshold
        if operator == "GTE":
            return value >= threshold
        if operator == "LT":
            return value < threshold
        if operator == "LTE":
            return value <= threshold
        if operator == "EQ":
            return abs(value - threshold) < 1e-6
        if operator == "CHANGE":
            return abs(value) >= threshold
        return False

    def _is_in_cooldown(self, rule_id: str) -> bool:
        """Check if a rule is currently in cooldown.

        Args:
            rule_id: Rule identifier

        Returns:
            True if cooldown period has not expired
        """
        last = self._cooldown_tracker.get(rule_id, 0.0)
        return time.time() - last < self.cooldown_seconds

    def _mark_triggered(self, rule_id: str) -> None:
        """Record that a rule was triggered now.

        Args:
            rule_id: Rule identifier
        """
        self._cooldown_tracker[rule_id] = time.time()

    def _build_message(self, rule: AlertRule, snapshot: dict[str, Any]) -> str:
        """Build a human-readable alert message.

        Args:
            rule: Triggered rule
            snapshot: Market snapshot

        Returns:
            Alert message string
        """
        symbol = rule.symbol or snapshot.get("symbol", "UNKNOWN")
        return (
            f"🔔 Alert: {rule.name} | {symbol} | "
            f"{rule.condition_type} {rule.operator} {rule.threshold} triggered"
        )


# Module-level singleton
_engine: AlertRuleEngine | None = None


def get_alert_engine() -> AlertRuleEngine:
    """Return the global AlertRuleEngine singleton.

    Returns:
        Shared AlertRuleEngine instance
    """
    global _engine
    if _engine is None:
        _engine = AlertRuleEngine()
    return _engine
