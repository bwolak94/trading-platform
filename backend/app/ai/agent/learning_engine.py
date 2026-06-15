"""Adaptive Learning Engine — adjusts strategy parameters based on trade outcomes.

Uses a simple online learning approach:
1. Tracks win/loss rates per strategy + market condition combo
2. Adjusts confidence multipliers based on performance
3. Learns which strategies work in which regimes
4. Penalizes strategies that lose in specific conditions
5. Maintains a "memory" of market patterns that preceded wins/losses

Persistence: learning state is stored in Redis (key ``learning:memory``) so it
survives restarts without polluting git history with a mutable JSON file.
Falls back to the legacy ``learning_memory.json`` file if Redis is unavailable.
"""

import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Legacy file — used as fallback when Redis is unavailable
_LEGACY_MEMORY_FILE = Path(__file__).parent / "learning_memory.json"
_REDIS_KEY = "learning:memory"

# Strategy + condition combos
StrategyKey = str  # e.g. "trend_following:TREND_BULL"


class LearningEngine:
    """Online learning engine that adapts from trade outcomes."""

    def __init__(self) -> None:
        # Performance tracking per strategy+regime combo
        self._stats: dict[StrategyKey, dict[str, float]] = defaultdict(
            lambda: {"wins": 0, "losses": 0, "total_pnl": 0.0, "avg_reward": 0.0, "confidence_adj": 1.0}
        )

        # Pattern memory: market conditions that preceded wins/losses
        self._win_patterns: list[dict[str, Any]] = []
        self._loss_patterns: list[dict[str, Any]] = []

        # Strategy confidence multipliers (learned)
        self._confidence_multipliers: dict[str, float] = {
            "trend_following": 1.0,
            "mean_reversion": 1.0,
            "smc": 1.0,
            "volume_breakout": 1.0,
            "liquidity_sweep": 1.0,
            "ob_bounce": 1.0,
            "vwap_reversion": 1.0,
            "delta_divergence": 1.0,
        }

        # Blocked conditions: strategy+regime combos that have lost too much
        self._blocked: dict[StrategyKey, datetime] = {}

        # Load saved memory
        self._load_memory()

    def record_outcome(
        self,
        strategy: str,
        regime: str,
        pnl_pct: float,
        reward: float,
        hit_level: str,
        market_snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        """Record a trade outcome and update the learning model.

        Returns a dict with the adjustments made.
        """
        key = f"{strategy}:{regime}"
        stats = self._stats[key]

        if pnl_pct > 0:
            stats["wins"] += 1
            self._win_patterns.append({
                "strategy": strategy, "regime": regime,
                "pnl": pnl_pct, "hit": hit_level,
                "snapshot": _slim_snapshot(market_snapshot),
                "time": datetime.now(timezone.utc).isoformat(),
            })
            if len(self._win_patterns) > 200:
                self._win_patterns = self._win_patterns[-200:]
        else:
            stats["losses"] += 1
            self._loss_patterns.append({
                "strategy": strategy, "regime": regime,
                "pnl": pnl_pct, "hit": hit_level,
                "snapshot": _slim_snapshot(market_snapshot),
                "time": datetime.now(timezone.utc).isoformat(),
            })
            if len(self._loss_patterns) > 200:
                self._loss_patterns = self._loss_patterns[-200:]

        total = stats["wins"] + stats["losses"]
        stats["total_pnl"] += pnl_pct
        stats["avg_reward"] = round((stats["avg_reward"] * (total - 1) + reward) / total, 3)

        # --- Adaptive adjustments ---
        adjustments: dict[str, Any] = {"key": key, "total_trades": total}

        # 1. Update confidence multiplier based on win rate
        if total >= 3:
            win_rate = stats["wins"] / total
            # Good performance → boost confidence, bad → reduce
            if win_rate >= 0.6:
                new_mult = min(1.5, 1.0 + (win_rate - 0.5) * 2)
                adjustments["confidence_boost"] = round(new_mult, 2)
            elif win_rate <= 0.35:
                new_mult = max(0.3, win_rate * 2)
                adjustments["confidence_penalty"] = round(new_mult, 2)
            else:
                new_mult = 1.0

            self._confidence_multipliers[strategy] = round(new_mult, 2)
            stats["confidence_adj"] = round(new_mult, 2)
            adjustments["new_multiplier"] = round(new_mult, 2)

        # 2. Block strategy+regime if 3+ consecutive losses
        recent_losses = sum(
            1 for p in self._loss_patterns[-5:]
            if p["strategy"] == strategy and p["regime"] == regime
        )
        if recent_losses >= 3:
            from datetime import timedelta
            block_hours = min(12, recent_losses * 2)
            self._blocked[key] = datetime.now(timezone.utc) + timedelta(hours=block_hours)
            adjustments["blocked_until"] = self._blocked[key].isoformat()
            adjustments["block_reason"] = f"{recent_losses} consecutive losses in {regime}"
            logger.warning("LEARNING: Blocked %s for %dh after %d losses", key, block_hours, recent_losses)

        # 3. Learn market patterns
        if total >= 5:
            win_rate = stats["wins"] / total
            adjustments["learned_win_rate"] = round(win_rate * 100, 1)
            adjustments["learned_avg_pnl"] = round(stats["total_pnl"] / total, 3)

        # Save to disk
        self._save_memory()

        logger.info(
            "LEARNING: %s | %s | PnL=%.2f%% | WinRate=%.1f%% | Mult=%.2f | %s",
            strategy, regime, pnl_pct,
            stats["wins"] / max(total, 1) * 100,
            self._confidence_multipliers.get(strategy, 1.0),
            "BLOCKED" if key in self._blocked else "OK",
        )

        return adjustments

    def get_confidence_multiplier(self, strategy: str) -> float:
        """Get the learned confidence multiplier for a strategy."""
        return self._confidence_multipliers.get(strategy, 1.0)

    def is_blocked(self, strategy: str, regime: str) -> bool:
        """Check if a strategy+regime combo is currently blocked."""
        key = f"{strategy}:{regime}"
        blocked_until = self._blocked.get(key)
        if blocked_until and datetime.now(timezone.utc) < blocked_until:
            return True
        # Clean up expired blocks
        if blocked_until:
            del self._blocked[key]
        return False

    def adjust_confidence(self, strategy: str, base_confidence: float) -> float:
        """Apply learned multiplier to a base confidence score."""
        mult = self._confidence_multipliers.get(strategy, 1.0)
        adjusted = base_confidence * mult
        return round(min(95, max(10, adjusted)), 1)

    def get_best_strategy(self, regime: str) -> str | None:
        """Return the best-performing strategy for a given regime."""
        best_strategy = None
        best_score = -999.0

        for key, stats in self._stats.items():
            strat, reg = key.split(":", 1) if ":" in key else (key, "")
            if reg != regime:
                continue
            total = stats["wins"] + stats["losses"]
            if total < 3:
                continue
            win_rate = stats["wins"] / total
            score = win_rate * 100 + stats["avg_reward"] * 10
            if score > best_score:
                best_score = score
                best_strategy = strat

        return best_strategy

    def get_learning_summary(self) -> dict[str, Any]:
        """Return full learning state for display."""
        strategy_performance: list[dict[str, Any]] = []

        for key, stats in sorted(self._stats.items()):
            total = stats["wins"] + stats["losses"]
            if total == 0:
                continue
            parts = key.split(":", 1)
            strategy_performance.append({
                "strategy": parts[0],
                "regime": parts[1] if len(parts) > 1 else "UNKNOWN",
                "wins": int(stats["wins"]),
                "losses": int(stats["losses"]),
                "win_rate": round(stats["wins"] / total * 100, 1),
                "total_pnl": round(stats["total_pnl"], 2),
                "avg_reward": stats["avg_reward"],
                "confidence_multiplier": stats["confidence_adj"],
                "blocked": self.is_blocked(parts[0], parts[1] if len(parts) > 1 else ""),
            })

        # Sort by total trades descending
        strategy_performance.sort(key=lambda x: x["wins"] + x["losses"], reverse=True)

        blocked_combos = {
            k: v.isoformat()
            for k, v in self._blocked.items()
            if v > datetime.now(timezone.utc)
        }

        return {
            "strategy_performance": strategy_performance,
            "confidence_multipliers": self._confidence_multipliers,
            "blocked_combos": blocked_combos,
            "total_win_patterns": len(self._win_patterns),
            "total_loss_patterns": len(self._loss_patterns),
            "best_by_regime": {
                regime: self.get_best_strategy(regime)
                for regime in ["TREND_BULL", "TREND_BEAR", "CONSOLIDATION", "HIGH_VOL_CHOPPY", "INTRADAY"]
            },
        }

    def _save_memory(self) -> None:
        """Persist learning state — Redis primary, legacy JSON file as fallback."""
        data = {
            "stats": {k: dict(v) for k, v in self._stats.items()},
            "multipliers": self._confidence_multipliers,
            "blocked": {k: v.isoformat() for k, v in self._blocked.items()},
            "win_patterns": self._win_patterns[-50:],
            "loss_patterns": self._loss_patterns[-50:],
        }
        payload = json.dumps(data)

        # Try Redis first (30-day TTL — long enough to survive restarts)
        try:
            import redis as _redis
            from app.core.config import settings
            r = _redis.from_url(settings.REDIS_URL, decode_responses=True)
            r.set(_REDIS_KEY, payload, ex=60 * 60 * 24 * 30)
            return
        except Exception as exc:
            logger.debug("Redis save failed, falling back to JSON file: %s", exc)

        # Fallback: write to local file
        try:
            _LEGACY_MEMORY_FILE.write_text(payload)
        except Exception as exc:
            logger.debug("Failed to save learning memory: %s", exc)

    def _load_memory(self) -> None:
        """Load learning state — Redis primary, legacy JSON file as fallback."""
        payload: str | None = None

        # Try Redis first
        try:
            import redis as _redis
            from app.core.config import settings
            r = _redis.from_url(settings.REDIS_URL, decode_responses=True)
            payload = r.get(_REDIS_KEY)
        except Exception as exc:
            logger.debug("Redis load failed, trying JSON file: %s", exc)

        # Fallback: read from legacy file
        if payload is None and _LEGACY_MEMORY_FILE.exists():
            try:
                payload = _LEGACY_MEMORY_FILE.read_text()
            except Exception as exc:
                logger.debug("Failed to read legacy memory file: %s", exc)

        if payload is None:
            return

        try:
            data = json.loads(payload)
            for k, v in data.get("stats", {}).items():
                self._stats[k] = v
            self._confidence_multipliers.update(data.get("multipliers", {}))
            for k, v in data.get("blocked", {}).items():
                self._blocked[k] = datetime.fromisoformat(v)
            self._win_patterns = data.get("win_patterns", [])
            self._loss_patterns = data.get("loss_patterns", [])
            logger.info("Loaded learning memory: %d strategy combos", len(self._stats))
        except Exception as exc:
            logger.debug("Failed to parse learning memory: %s", exc)


def _slim_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Keep only key fields from market snapshot to save memory."""
    return {
        k: snapshot[k]
        for k in ["rsi", "adx", "atr_pct", "volume_vs_avg", "ema_cross", "bb_position"]
        if k in snapshot
    }


# Singleton
_engine: LearningEngine | None = None


def get_learning_engine() -> LearningEngine:
    global _engine
    if _engine is None:
        _engine = LearningEngine()
    return _engine
