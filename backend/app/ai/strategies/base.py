"""Base strategy interface — all strategies must inherit from this."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import pandas as pd


@dataclass
class MarketContext:
    """Contextual data passed to strategies alongside OHLCV."""

    regime: str = "CONSOLIDATION"
    regime_confidence: float = 50.0
    sentiment_score: float = 0.0
    onchain_score: float = 0.0
    macro_events: list[dict[str, Any]] = field(default_factory=list)
    market_session: str = "UNKNOWN"  # "NYSE", "LONDON", "ASIAN", "OFF_HOURS", "UNKNOWN"


@dataclass
class SignalResult:
    """Output of a strategy's generate_signal method."""

    asset: str
    timeframe: str
    direction: str  # LONG / SHORT
    confidence: float  # 0-100
    entry_price: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    risk_reward: float
    factors: list[dict[str, Any]]
    strategy_name: str
    trailing_stop_pct: float = 0.0  # 0 = disabled, e.g. 0.02 = 2% trail
    partial_tp_schedule: list[dict] = field(default_factory=list)  # [{pct_close: 25, price: X}, ...]
    pyramid_levels: list[dict] = field(default_factory=list)  # [{price: X, size_pct: 25}, ...]


def calculate_atr_based_stops(
    entry_price: float,
    atr: float,
    direction: str,
    atr_multiplier_sl: float = 2.0,
    atr_multiplier_tp1: float = 2.0,
    atr_multiplier_tp2: float = 4.0,
) -> dict[str, float]:
    """Calculate ATR-based dynamic stop loss and take profit levels.

    Uses the Average True Range (ATR) to set volatility-adaptive risk levels that
    widen in high-volatility conditions and tighten in low-volatility conditions.

    For LONG trades:
        stop_loss     = entry - (atr × atr_multiplier_sl)
        take_profit_1 = entry + (atr × atr_multiplier_tp1)
        take_profit_2 = entry + (atr × atr_multiplier_tp2)

    For SHORT trades:
        stop_loss     = entry + (atr × atr_multiplier_sl)
        take_profit_1 = entry - (atr × atr_multiplier_tp1)
        take_profit_2 = entry - (atr × atr_multiplier_tp2)

    Args:
        entry_price: The trade entry price.
        atr: Average True Range value for the current bar/period.
        direction: ``"LONG"`` or ``"SHORT"`` (case-insensitive).
        atr_multiplier_sl: ATR multiplier for the stop loss distance (default 2.0).
        atr_multiplier_tp1: ATR multiplier for the first take-profit target (default 2.0).
        atr_multiplier_tp2: ATR multiplier for the second take-profit target (default 4.0).

    Returns:
        Dict with keys:
        - ``stop_loss`` (float)
        - ``take_profit_1`` (float)
        - ``take_profit_2`` (float)
        - ``risk_reward`` (float) — ratio of TP1 distance to SL distance, 0 if SL distance is 0.
    """
    sl_distance = atr * atr_multiplier_sl
    tp1_distance = atr * atr_multiplier_tp1
    tp2_distance = atr * atr_multiplier_tp2

    is_long = direction.upper() == "LONG"

    if is_long:
        stop_loss = entry_price - sl_distance
        take_profit_1 = entry_price + tp1_distance
        take_profit_2 = entry_price + tp2_distance
    else:
        stop_loss = entry_price + sl_distance
        take_profit_1 = entry_price - tp1_distance
        take_profit_2 = entry_price - tp2_distance

    risk_reward = round(tp1_distance / sl_distance, 2) if sl_distance > 0 else 0.0

    return {
        "stop_loss": round(stop_loss, 8),
        "take_profit_1": round(take_profit_1, 8),
        "take_profit_2": round(take_profit_2, 8),
        "risk_reward": risk_reward,
    }


class BaseStrategy(ABC):
    """Abstract base class for all trading strategies."""

    name: str = "base"
    supported_regimes: list[str] = []
    min_confidence: float = 50.0

    def is_compatible(self, regime: str) -> bool:
        """Check if this strategy supports the given regime."""
        return regime in self.supported_regimes

    @staticmethod
    def calculate_atr_based_stops(
        entry_price: float,
        atr: float,
        direction: str,
        atr_multiplier_sl: float = 2.0,
        atr_multiplier_tp1: float = 2.0,
        atr_multiplier_tp2: float = 4.0,
    ) -> dict[str, float]:
        """Calculate ATR-based dynamic stop loss and take profit levels.

        Delegates to the module-level ``calculate_atr_based_stops`` function.
        Provided as a convenience method so strategies can call
        ``self.calculate_atr_based_stops(...)`` without importing the function directly.

        See ``calculate_atr_based_stops`` for full parameter and return documentation.
        """
        return calculate_atr_based_stops(
            entry_price=entry_price,
            atr=atr,
            direction=direction,
            atr_multiplier_sl=atr_multiplier_sl,
            atr_multiplier_tp1=atr_multiplier_tp1,
            atr_multiplier_tp2=atr_multiplier_tp2,
        )

    @abstractmethod
    def generate_signal(
        self,
        asset: str,
        timeframe: str,
        market_data: pd.DataFrame,
        context: MarketContext,
    ) -> SignalResult | None:
        """Analyze data and return a SignalResult or None if no signal."""
        ...
