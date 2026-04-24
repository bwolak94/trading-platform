"""Regime Parameter Store — per-regime optimal strategy parameters that auto-switch."""

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from app.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Default optimised parameters per strategy per regime.
# Values are derived from historical backtesting and manual analysis.
# Override at runtime via RegimeParamStore.update_params().
# ---------------------------------------------------------------------------
DEFAULT_REGIME_PARAMS: dict[str, dict[str, dict[str, Any]]] = {
    "trend_following": {
        "TREND_BULL": {
            "adx_threshold": 25.0,
            "rsi_low": 45.0,
            "rsi_high": 70.0,
            "atr_sl_multiplier": 2.0,
            "atr_tp1_multiplier": 2.0,
            "atr_tp2_multiplier": 4.0,
            "volume_threshold": 1.2,
            "ema_fast": 20,
            "ema_slow": 50,
        },
        "TREND_BEAR": {
            "adx_threshold": 25.0,
            "rsi_low": 30.0,
            "rsi_high": 55.0,
            "atr_sl_multiplier": 2.0,
            "atr_tp1_multiplier": 2.0,
            "atr_tp2_multiplier": 4.0,
            "volume_threshold": 1.2,
            "ema_fast": 20,
            "ema_slow": 50,
        },
        "CONSOLIDATION": {
            "adx_threshold": 20.0,
            "rsi_low": 40.0,
            "rsi_high": 60.0,
            "atr_sl_multiplier": 1.5,
            "atr_tp1_multiplier": 1.5,
            "atr_tp2_multiplier": 3.0,
            "volume_threshold": 1.5,
            "ema_fast": 20,
            "ema_slow": 50,
        },
        "HIGH_VOL_CHOPPY": {
            "adx_threshold": 30.0,
            "rsi_low": 35.0,
            "rsi_high": 65.0,
            "atr_sl_multiplier": 2.5,
            "atr_tp1_multiplier": 1.5,
            "atr_tp2_multiplier": 3.0,
            "volume_threshold": 1.8,
            "ema_fast": 20,
            "ema_slow": 50,
        },
    },
    "mean_reversion": {
        "CONSOLIDATION": {
            "bb_window": 20,
            "bb_std": 2.0,
            "rsi_oversold": 30,
            "rsi_overbought": 70,
        },
        "TREND_BULL": {
            "bb_window": 20,
            "bb_std": 2.0,
            "rsi_oversold": 35,
            "rsi_overbought": 65,
        },
        "TREND_BEAR": {
            "bb_window": 20,
            "bb_std": 2.0,
            "rsi_oversold": 25,
            "rsi_overbought": 60,
        },
        "HIGH_VOL_CHOPPY": {
            "bb_window": 15,
            "bb_std": 2.5,
            "rsi_oversold": 25,
            "rsi_overbought": 75,
        },
    },
    "breakout_failure": {
        "CONSOLIDATION": {
            "lookback": 20,
            "breakout_threshold_pct": 0.1,
            "atr_sl_multiplier": 1.5,
        },
        "TREND_BULL": {
            "lookback": 20,
            "breakout_threshold_pct": 0.15,
            "atr_sl_multiplier": 1.5,
        },
        "TREND_BEAR": {
            "lookback": 20,
            "breakout_threshold_pct": 0.15,
            "atr_sl_multiplier": 1.5,
        },
        "HIGH_VOL_CHOPPY": {
            "lookback": 15,
            "breakout_threshold_pct": 0.2,
            "atr_sl_multiplier": 2.0,
        },
    },
}


@dataclass
class ParamUpdate:
    """Audit record for a parameter update."""

    strategy: str
    regime: str
    params: dict[str, Any]
    source: str      # "default", "optimizer", "manual"
    updated_at: str  # ISO-8601 UTC timestamp


class RegimeParamStore:
    """Stores and retrieves optimal strategy parameters per market regime.

    Features
    --------
    - Auto-switches parameters when regime changes (call ``get_params``).
    - Persists overrides to a JSON file so settings survive restarts.
    - Falls back to hard-coded ``DEFAULT_REGIME_PARAMS`` when no override exists.
    - All writes to disk are atomic (write to temp file then rename).
    """

    STORAGE_PATH: str = "/app/models/regime_params.json"

    def __init__(self) -> None:
        # Deep-copy defaults so mutations don't affect the module constant
        import copy

        self._params: dict[str, dict[str, dict[str, Any]]] = copy.deepcopy(
            DEFAULT_REGIME_PARAMS
        )
        self._audit_log: list[ParamUpdate] = []
        self._load_from_disk()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_params(self, strategy: str, regime: str) -> dict[str, Any]:
        """Return optimal parameters for a strategy+regime combination.

        Falls back in order:
        1. Persisted / updated override (in ``_params``)
        2. ``DEFAULT_REGIME_PARAMS``
        3. Empty dict (strategy or regime unknown)

        Args:
            strategy: Strategy name key, e.g. ``"trend_following"``.
            regime: Market regime string, e.g. ``"TREND_BULL"``.

        Returns:
            Dict of parameter name → value.
        """
        params = (
            self._params.get(strategy, {}).get(regime)
            or DEFAULT_REGIME_PARAMS.get(strategy, {}).get(regime)
            or {}
        )
        logger.debug(
            "RegimeParamStore.get_params: strategy=%s regime=%s → %d params",
            strategy,
            regime,
            len(params),
        )
        return dict(params)  # return a copy to prevent external mutation

    def update_params(
        self,
        strategy: str,
        regime: str,
        params: dict[str, Any],
        source: str = "optimizer",
    ) -> None:
        """Update parameters for a strategy+regime combination and persist to disk.

        Merges ``params`` into any existing entry (partial updates are allowed).

        Args:
            strategy: Strategy name.
            regime: Market regime.
            params: Dict of parameter overrides to apply.
            source: Origin of the update — ``"optimizer"``, ``"manual"``, etc.
        """
        if strategy not in self._params:
            self._params[strategy] = {}
        if regime not in self._params[strategy]:
            self._params[strategy][regime] = {}

        self._params[strategy][regime].update(params)

        update = ParamUpdate(
            strategy=strategy,
            regime=regime,
            params=dict(params),
            source=source,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        self._audit_log.append(update)
        self._save_to_disk()

        logger.info(
            "RegimeParamStore: updated %s/%s from source=%s — %d params",
            strategy,
            regime,
            source,
            len(params),
        )

    def get_all_for_regime(self, regime: str) -> dict[str, dict[str, Any]]:
        """Return all strategy parameters for a given regime.

        Args:
            regime: Market regime string.

        Returns:
            Dict mapping strategy name → parameter dict.
        """
        result: dict[str, dict[str, Any]] = {}
        for strategy in self.list_strategies():
            p = self.get_params(strategy, regime)
            if p:
                result[strategy] = p
        return result

    def list_strategies(self) -> list[str]:
        """Return a sorted list of all strategy names with stored parameters."""
        all_strategies = set(self._params.keys()) | set(DEFAULT_REGIME_PARAMS.keys())
        return sorted(all_strategies)

    def reset_to_defaults(
        self, strategy: str, regime: Optional[str] = None
    ) -> None:
        """Reset parameters to the compiled-in defaults.

        Args:
            strategy: Strategy name to reset.
            regime: If provided, reset only this regime.  If ``None``, reset
                    all regimes for the strategy.
        """
        import copy

        default_strategy = DEFAULT_REGIME_PARAMS.get(strategy, {})

        if regime is not None:
            default_regime = default_strategy.get(regime, {})
            if strategy in self._params:
                self._params[strategy][regime] = copy.deepcopy(default_regime)
            logger.info(
                "RegimeParamStore: reset %s/%s to defaults", strategy, regime
            )
        else:
            self._params[strategy] = copy.deepcopy(default_strategy)
            logger.info("RegimeParamStore: reset all regimes for %s to defaults", strategy)

        self._save_to_disk()

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _load_from_disk(self) -> None:
        """Load persisted parameter overrides from the JSON storage file.

        Silently skips if the file does not exist or cannot be parsed.
        Persisted values are merged on top of defaults (overrides only).
        """
        path = self.STORAGE_PATH
        if not os.path.exists(path):
            logger.debug("RegimeParamStore: no storage file at %s — using defaults", path)
            return

        try:
            with open(path, "r", encoding="utf-8") as fh:
                data: dict[str, Any] = json.load(fh)

            loaded_params = data.get("params", {})
            for strategy, regimes in loaded_params.items():
                if strategy not in self._params:
                    self._params[strategy] = {}
                for regime, params in regimes.items():
                    if isinstance(params, dict):
                        self._params[strategy][regime] = params

            logger.info(
                "RegimeParamStore: loaded overrides for %d strategies from %s",
                len(loaded_params),
                path,
            )
        except Exception as exc:
            logger.error("RegimeParamStore: failed to load from disk: %s", exc)

    def _save_to_disk(self) -> None:
        """Persist current parameter state to the JSON storage file.

        Uses a write-then-rename pattern for atomic updates.
        Creates parent directories if they do not exist.
        """
        path = self.STORAGE_PATH
        tmp_path = path + ".tmp"
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            payload = {
                "params": self._params,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "version": 1,
            }
            with open(tmp_path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2, default=str)
            os.replace(tmp_path, path)
            logger.debug("RegimeParamStore: persisted to %s", path)
        except Exception as exc:
            logger.error("RegimeParamStore: failed to save to disk: %s", exc)
            # Clean up temp file if it exists
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass


# ---------------------------------------------------------------------------
# Module-level singleton — use get_regime_param_store() throughout the app.
# ---------------------------------------------------------------------------
_store: Optional[RegimeParamStore] = None


def get_regime_param_store() -> RegimeParamStore:
    """Return the module-level RegimeParamStore singleton (lazy init)."""
    global _store
    if _store is None:
        _store = RegimeParamStore()
    return _store
