"""HMM Regime Detector — smooth regime transitions using Viterbi algorithm.

A Hidden Markov Model provides smoother regime transitions than threshold-based
classifiers, reducing whipsaw and false regime change signals. Uses predefined
transition and emission probabilities (no training required).

States: BULL_TREND, BEAR_TREND, CONSOLIDATION
Observations: Discretized returns (UP_STRONG, UP_WEAK, FLAT, DOWN_WEAK, DOWN_STRONG)
"""

from __future__ import annotations

import math
import time
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

_CACHE: dict[str, dict[str, Any]] = {}
_CACHE_TTL = 600


class SimpleHMM:
    """2-state Hidden Markov Model for market regime detection with Viterbi decoding."""

    STATES = ["BULL_TREND", "BEAR_TREND", "CONSOLIDATION"]

    TRANSITION: dict[str, dict[str, float]] = {
        "BULL_TREND":    {"BULL_TREND": 0.80, "BEAR_TREND": 0.05, "CONSOLIDATION": 0.15},
        "BEAR_TREND":    {"BULL_TREND": 0.05, "BEAR_TREND": 0.80, "CONSOLIDATION": 0.15},
        "CONSOLIDATION": {"BULL_TREND": 0.25, "BEAR_TREND": 0.25, "CONSOLIDATION": 0.50},
    }

    EMISSION: dict[str, dict[str, float]] = {
        "BULL_TREND":    {"UP_STRONG": 0.35, "UP_WEAK": 0.30, "FLAT": 0.15, "DOWN_WEAK": 0.15, "DOWN_STRONG": 0.05},
        "BEAR_TREND":    {"UP_STRONG": 0.05, "UP_WEAK": 0.15, "FLAT": 0.15, "DOWN_WEAK": 0.30, "DOWN_STRONG": 0.35},
        "CONSOLIDATION": {"UP_STRONG": 0.10, "UP_WEAK": 0.20, "FLAT": 0.40, "DOWN_WEAK": 0.20, "DOWN_STRONG": 0.10},
    }

    INITIAL: dict[str, float] = {
        "BULL_TREND": 0.33,
        "BEAR_TREND": 0.33,
        "CONSOLIDATION": 0.34,
    }

    def discretize_return(self, ret: float) -> str:
        """Map a return value to a discrete observation label.

        Args:
            ret: Log return (decimal, e.g. 0.02 = 2%)

        Returns:
            Observation label string
        """
        if ret > 0.015:
            return "UP_STRONG"
        if ret > 0.003:
            return "UP_WEAK"
        if ret > -0.003:
            return "FLAT"
        if ret > -0.015:
            return "DOWN_WEAK"
        return "DOWN_STRONG"

    def viterbi(self, observations: list[str]) -> list[str]:
        """Run Viterbi algorithm to find the most likely state sequence.

        Args:
            observations: List of discrete observation labels

        Returns:
            List of state labels (most likely sequence)
        """
        n = len(observations)
        if n == 0:
            return []

        # viterbi[t][state] = max log-probability of ending in state at time t
        viterbi_table: list[dict[str, float]] = []
        backpointer: list[dict[str, str]] = []

        # Initialize
        obs0 = observations[0]
        v0: dict[str, float] = {}
        for state in self.STATES:
            v0[state] = math.log(self.INITIAL[state] + 1e-10) + math.log(
                self.EMISSION[state].get(obs0, 1e-10)
            )
        viterbi_table.append(v0)
        backpointer.append({state: "" for state in self.STATES})

        # Recursion
        for t in range(1, n):
            obs = observations[t]
            vt: dict[str, float] = {}
            bt: dict[str, str] = {}
            for state in self.STATES:
                max_prob = float("-inf")
                max_prev = self.STATES[0]
                for prev_state in self.STATES:
                    prob = (
                        viterbi_table[t - 1][prev_state]
                        + math.log(self.TRANSITION[prev_state].get(state, 1e-10))
                        + math.log(self.EMISSION[state].get(obs, 1e-10))
                    )
                    if prob > max_prob:
                        max_prob = prob
                        max_prev = prev_state
                vt[state] = max_prob
                bt[state] = max_prev
            viterbi_table.append(vt)
            backpointer.append(bt)

        # Backtrack
        best_last = max(viterbi_table[-1], key=lambda s: viterbi_table[-1][s])
        path = [best_last]
        for t in range(n - 1, 0, -1):
            path.insert(0, backpointer[t][path[0]])

        return path

    def predict_regime(self, closes: list[float]) -> dict[str, Any]:
        """Predict regime from price series using HMM.

        Args:
            closes: List of closing prices

        Returns:
            {current_regime, previous_regime, regime_changed, state_sequence, confidence}
        """
        if len(closes) < 5:
            return {"current_regime": "CONSOLIDATION", "confidence": 0.0, "error": "Insufficient data"}

        # Compute log returns
        returns = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
        observations = [self.discretize_return(r) for r in returns]

        state_sequence = self.viterbi(observations)

        current_regime = state_sequence[-1] if state_sequence else "CONSOLIDATION"
        previous_regime = state_sequence[-2] if len(state_sequence) >= 2 else current_regime
        regime_changed = current_regime != previous_regime

        # Stability: how many of last 5 states match current
        last_5 = state_sequence[-5:] if len(state_sequence) >= 5 else state_sequence
        stability = sum(1 for s in last_5 if s == current_regime) / len(last_5)

        return {
            "current_regime": current_regime,
            "previous_regime": previous_regime,
            "regime_changed": regime_changed,
            "stability_score": round(stability, 2),
            "confidence": round(stability, 2),
            "state_sequence_tail": state_sequence[-10:],
            "observations_analyzed": len(observations),
        }


async def get_hmm_regime(
    symbol: str,
    interval: str = "1d",
    lookback: int = 60,
) -> dict[str, Any]:
    """Fetch price data and run HMM regime detection.

    Args:
        symbol: Binance trading pair (e.g. BTCUSDT)
        interval: Kline interval
        lookback: Number of candles to analyze

    Returns:
        HMM regime prediction dict
    """
    cache_key = f"{symbol}:{interval}"
    now = time.time()
    cached = _CACHE.get(cache_key)
    if cached and now - cached.get("_ts", 0) < _CACHE_TTL:
        return {k: v for k, v in cached.items() if k != "_ts"}

    try:
        from app.data.fetchers.binance_fetcher import BinanceFetcher

        fetcher = BinanceFetcher(symbol=symbol, interval=interval)
        candles = await fetcher.fetch_historical_ohlcv(limit=lookback)
        if not candles:
            return {"symbol": symbol, "error": "No data", "current_regime": "CONSOLIDATION"}

        closes = [float(c["close"]) for c in candles]
        hmm = SimpleHMM()
        result = hmm.predict_regime(closes)
        result["symbol"] = symbol
        result["interval"] = interval
        result["timestamp"] = int(now * 1000)

        _CACHE[cache_key] = {**result, "_ts": now}
        return result

    except Exception as exc:
        logger.warning("HMM regime failed for %s: %s", symbol, exc)
        return {
            "symbol": symbol,
            "current_regime": "CONSOLIDATION",
            "confidence": 0.0,
            "error": str(exc),
            "timestamp": int(time.time() * 1000),
        }
