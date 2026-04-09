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


class BaseStrategy(ABC):
    """Abstract base class for all trading strategies."""

    name: str = "base"
    supported_regimes: list[str] = []
    min_confidence: float = 50.0

    def is_compatible(self, regime: str) -> bool:
        """Check if this strategy supports the given regime."""
        return regime in self.supported_regimes

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
