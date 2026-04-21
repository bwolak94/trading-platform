"""Champion/Challenger Framework — A/B test strategy parameter variants.

Runs two strategy configurations simultaneously (champion = current best,
challenger = new variant) and uses a simple proportion test to determine
statistical significance after sufficient trades.

After the experiment duration or trade count is reached, the winner is
automatically promoted to champion and the loser is retired.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

_MIN_TRADES_FOR_SIGNIFICANCE = 20


class ChampionChallengerManager:
    """Manages champion/challenger strategy experiments."""

    def __init__(self) -> None:
        """Initialize the manager with an empty experiment registry."""
        self._experiments: dict[str, dict[str, Any]] = {}

    def create_experiment(
        self,
        experiment_id: str,
        champion_params: dict[str, Any],
        challenger_params: dict[str, Any],
        strategy_name: str,
        duration_days: int = 30,
        traffic_split: float = 0.5,
    ) -> dict[str, Any]:
        """Create a new champion/challenger experiment.

        Args:
            experiment_id: Unique experiment identifier
            champion_params: Current champion parameter set
            challenger_params: New challenger parameter set to test
            strategy_name: Strategy this experiment applies to
            duration_days: Maximum experiment duration in days
            traffic_split: Fraction of signals routed to challenger [0.1, 0.9]

        Returns:
            Experiment configuration dict
        """
        now = datetime.now(timezone.utc)
        experiment: dict[str, Any] = {
            "experiment_id": experiment_id,
            "strategy_name": strategy_name,
            "status": "RUNNING",
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(days=duration_days)).isoformat(),
            "traffic_split": max(0.1, min(0.9, traffic_split)),
            "champion": {
                "params": champion_params,
                "trades": 0,
                "wins": 0,
                "total_r": 0.0,
            },
            "challenger": {
                "params": challenger_params,
                "trades": 0,
                "wins": 0,
                "total_r": 0.0,
            },
        }
        self._experiments[experiment_id] = experiment
        logger.info("ChampionChallenger | Experiment created: %s for %s", experiment_id, strategy_name)
        return experiment

    def record_result(
        self,
        experiment_id: str,
        variant: str,
        pnl_r: float,
        win: bool,
    ) -> None:
        """Record a trade outcome for an experiment variant.

        Args:
            experiment_id: Experiment identifier
            variant: "champion" or "challenger"
            pnl_r: Trade result in R-multiples
            win: Whether the trade was a winner
        """
        experiment = self._experiments.get(experiment_id)
        if not experiment or experiment["status"] != "RUNNING":
            return

        v = variant.lower()
        if v not in ("champion", "challenger"):
            return

        experiment[v]["trades"] += 1
        experiment[v]["total_r"] += pnl_r
        if win:
            experiment[v]["wins"] += 1

    def evaluate_experiment(self, experiment_id: str) -> dict[str, Any]:
        """Evaluate experiment statistical significance and recommend winner.

        Uses a simple proportion test: if the difference in win rates exceeds
        the standard error by factor > 1.96, the result is significant (95% CI).

        Args:
            experiment_id: Experiment identifier

        Returns:
            {experiment_id, champion_win_rate, challenger_win_rate, winner,
             confidence_pct, should_promote, performance_delta_pct}
        """
        import math

        experiment = self._experiments.get(experiment_id)
        if not experiment:
            return {"error": f"Experiment {experiment_id} not found"}

        champ = experiment["champion"]
        chall = experiment["challenger"]

        n_champ = champ["trades"]
        n_chall = chall["trades"]

        champ_wr = champ["wins"] / n_champ if n_champ > 0 else 0.0
        chall_wr = chall["wins"] / n_chall if n_chall > 0 else 0.0

        champ_avg_r = champ["total_r"] / n_champ if n_champ > 0 else 0.0
        chall_avg_r = chall["total_r"] / n_chall if n_chall > 0 else 0.0

        # Statistical significance (proportion test)
        is_significant = False
        confidence_pct = 0.0

        if n_champ >= _MIN_TRADES_FOR_SIGNIFICANCE and n_chall >= _MIN_TRADES_FOR_SIGNIFICANCE:
            p_pool = (champ["wins"] + chall["wins"]) / (n_champ + n_chall)
            se = math.sqrt(p_pool * (1 - p_pool) * (1 / n_champ + 1 / n_chall))
            if se > 0:
                z = abs(champ_wr - chall_wr) / se
                # Approximate p-value from z-score
                if z >= 2.576:
                    confidence_pct = 99.0
                    is_significant = True
                elif z >= 1.96:
                    confidence_pct = 95.0
                    is_significant = True
                elif z >= 1.645:
                    confidence_pct = 90.0
                else:
                    confidence_pct = round(z / 2.576 * 90, 1)

        if not is_significant:
            winner = "INCONCLUSIVE"
            should_promote = False
        elif chall_wr > champ_wr or chall_avg_r > champ_avg_r:
            winner = "CHALLENGER"
            should_promote = True
        else:
            winner = "CHAMPION"
            should_promote = False

        performance_delta = (chall_avg_r - champ_avg_r) / abs(champ_avg_r) * 100 if champ_avg_r != 0 else 0.0

        return {
            "experiment_id": experiment_id,
            "strategy_name": experiment["strategy_name"],
            "champion_win_rate": round(champ_wr, 3),
            "challenger_win_rate": round(chall_wr, 3),
            "champion_avg_r": round(champ_avg_r, 3),
            "challenger_avg_r": round(chall_avg_r, 3),
            "champion_trades": n_champ,
            "challenger_trades": n_chall,
            "winner": winner,
            "confidence_pct": confidence_pct,
            "is_significant": is_significant,
            "should_promote": should_promote,
            "performance_delta_pct": round(performance_delta, 2),
            "status": experiment["status"],
        }

    def promote_challenger(self, experiment_id: str) -> dict[str, Any]:
        """Promote the challenger to champion, ending the experiment.

        Args:
            experiment_id: Experiment identifier

        Returns:
            Promotion result dict
        """
        experiment = self._experiments.get(experiment_id)
        if not experiment:
            return {"error": f"Experiment {experiment_id} not found"}

        experiment["status"] = "CHALLENGER_PROMOTED"
        experiment["promoted_at"] = datetime.now(timezone.utc).isoformat()
        new_champion_params = experiment["challenger"]["params"]

        logger.info(
            "ChampionChallenger | Challenger promoted for experiment %s (strategy: %s)",
            experiment_id, experiment["strategy_name"],
        )
        return {
            "experiment_id": experiment_id,
            "status": "CHALLENGER_PROMOTED",
            "new_champion_params": new_champion_params,
            "strategy_name": experiment["strategy_name"],
        }

    def get_all_experiments(self) -> list[dict[str, Any]]:
        """Return all experiments with their current evaluation.

        Returns:
            List of experiment dicts with evaluation results
        """
        results = []
        for exp_id, exp in self._experiments.items():
            eval_result = self.evaluate_experiment(exp_id)
            results.append({**exp, "evaluation": eval_result})
        return results


# Module-level singleton
_manager: ChampionChallengerManager | None = None


def get_champion_challenger() -> ChampionChallengerManager:
    """Return the global ChampionChallengerManager singleton.

    Returns:
        Shared ChampionChallengerManager instance
    """
    global _manager
    if _manager is None:
        _manager = ChampionChallengerManager()
    return _manager
