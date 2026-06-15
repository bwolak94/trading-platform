"""Conditional alert chains — multi-condition market alerts.

Rules are evaluated each time check_and_fire_alerts() is called with a
market context dict.  All conditions in a rule must be satisfied before
the alert fires.  A per-rule cooldown prevents duplicate notifications.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class AlertCondition:
    """A single condition within an alert rule."""

    field: str       # e.g. "price", "rsi", "regime"
    operator: str    # "gt", "lt", "eq", "gte", "lte"
    value: float | str


@dataclass
class AlertRule:
    """A named alert rule composed of one or more conditions."""

    id: str
    name: str
    symbol: str | None
    conditions: list[AlertCondition]
    message: str
    cooldown_seconds: int = 3600  # Do not fire more than once per hour by default
    last_fired: float = field(default=0.0)
    active: bool = True


# Module-level rule registry
_rules: dict[str, AlertRule] = {}


def add_alert_rule(rule: AlertRule) -> None:
    """Register or replace an alert rule by its ID."""
    _rules[rule.id] = rule


def remove_alert_rule(rule_id: str) -> None:
    """Remove an alert rule by ID.  No-op if the rule does not exist."""
    _rules.pop(rule_id, None)


def get_alert_rules() -> list[AlertRule]:
    """Return all registered alert rules."""
    return list(_rules.values())


def _check_condition(condition: AlertCondition, context: dict[str, Any]) -> bool:
    """Evaluate a single condition against the provided market context.

    Returns False when the field is absent or the operator is unknown.
    """
    val = context.get(condition.field)
    if val is None:
        return False

    ops: dict[str, Any] = {
        "gt":  lambda a, b: a > b,
        "lt":  lambda a, b: a < b,
        "gte": lambda a, b: a >= b,
        "lte": lambda a, b: a <= b,
        "eq":  lambda a, b: str(a) == str(b),
    }

    op_fn = ops.get(condition.operator)
    if not op_fn:
        logger.warning("Unknown alert operator: %s", condition.operator)
        return False

    try:
        # Coerce numeric types for numeric comparisons; fall back to string equality
        a = float(val) if isinstance(val, (int, float)) else val
        b = (
            float(condition.value)
            if isinstance(condition.value, (int, float))
            else condition.value
        )
        return op_fn(a, b)
    except Exception as exc:
        logger.debug("Alert condition evaluation error: %s", exc)
        return False


async def check_and_fire_alerts(symbol: str, context: dict[str, Any]) -> None:
    """Evaluate all active rules against the current market context.

    Fires alerts whose every condition is satisfied and whose cooldown has
    elapsed.  Dispatches notifications via Telegram.

    Args:
        symbol: The trading symbol being evaluated (e.g. "BTCUSDT").
        context: Dict of market values keyed by field name (price, rsi, …).
    """
    now = time.time()

    for rule in _rules.values():
        if not rule.active:
            continue

        # Skip rules that target a different symbol
        if rule.symbol and rule.symbol != symbol:
            continue

        # Enforce cooldown
        if now - rule.last_fired < rule.cooldown_seconds:
            continue

        # All conditions must be satisfied
        if not all(_check_condition(c, context) for c in rule.conditions):
            continue

        # Fire the alert
        rule.last_fired = now
        msg = f"🔔 *Alert: {rule.name}*\n{rule.message}\nSymbol: {symbol}"

        try:
            from app.notifications.telegram_bot import get_telegram_bot

            bot = get_telegram_bot()
            if bot:
                await bot.send_message(msg)
        except Exception as exc:
            logger.warning("Alert rule '%s' fire failed: %s", rule.id, exc)
