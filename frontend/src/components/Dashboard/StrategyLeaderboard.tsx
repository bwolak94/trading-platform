import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchLearningData } from "../../api/client";
import type { LearningData } from "../../api/client";

// --- Types ---

interface LeaderboardEntry {
  name: string;
  winRate: number;
  avgConfidence: number;
  signalCount: number;
  performanceScore: number;
  totalPnl: number;
  blocked: boolean;
}

// --- Helpers ---

function buildLeaderboard(
  strategies: LearningData["strategy_performance"],
  multipliers: LearningData["confidence_multipliers"],
): LeaderboardEntry[] {
  // Aggregate by strategy name (across regimes)
  const grouped = new Map<string, LearningData["strategy_performance"]>();

  for (const entry of strategies) {
    const existing = grouped.get(entry.strategy) ?? [];
    existing.push(entry);
    grouped.set(entry.strategy, existing);
  }

  const entries: LeaderboardEntry[] = [];

  for (const [name, items] of grouped) {
    const totalWins = items.reduce((s, i) => s + i.wins, 0);
    const totalLosses = items.reduce((s, i) => s + i.losses, 0);
    const signalCount = totalWins + totalLosses;
    const winRate = signalCount > 0 ? (totalWins / signalCount) * 100 : 0;
    const totalPnl = items.reduce((s, i) => s + i.total_pnl, 0);
    const avgReward = signalCount > 0
      ? items.reduce((s, i) => s + i.avg_reward * (i.wins + i.losses), 0) / signalCount
      : 0;
    const blocked = items.every((i) => i.blocked);

    // Confidence: use multiplier if available, else average from items
    const avgConfidence = multipliers[name] ?? (
      items.length > 0
        ? items.reduce((s, i) => s + i.confidence_multiplier, 0) / items.length
        : 1
    );

    // Performance score: composite of win rate, pnl, and reward
    const performanceScore =
      winRate * 0.35 +
      Math.min(Math.max(totalPnl, -100), 100) * 0.35 +
      Math.min(Math.max(avgReward * 20, -100), 100) * 0.3;

    entries.push({
      name,
      winRate,
      avgConfidence,
      signalCount,
      performanceScore,
      totalPnl,
      blocked,
    });
  }

  return entries.sort((a, b) => b.performanceScore - a.performanceScore);
}

function getScoreColor(score: number): string {
  if (score >= 60) return "text-green-400";
  if (score >= 30) return "text-yellow-400";
  return "text-red-400";
}

function getScoreBg(score: number): string {
  if (score >= 60) return "bg-green-500";
  if (score >= 30) return "bg-yellow-500";
  return "bg-red-500";
}

function getRankBadge(index: number): string | null {
  if (index === 0) return "1st";
  if (index === 1) return "2nd";
  if (index === 2) return "3rd";
  return null;
}

function getRankColor(index: number): string {
  if (index === 0) return "text-yellow-400";
  if (index === 1) return "text-gray-300";
  if (index === 2) return "text-orange-400";
  return "text-gray-500";
}

// --- Component ---

export function StrategyLeaderboard() {
  const { data: learning, isLoading, isError } = useQuery({
    queryKey: ["learning-data"],
    queryFn: fetchLearningData,
    refetchInterval: 15_000,
  });

  const leaderboard = useMemo(() => {
    if (!learning) return [];
    return buildLeaderboard(learning.strategy_performance, learning.confidence_multipliers);
  }, [learning]);

  if (isLoading) {
    return (
      <div className="rounded-lg border border-border bg-surface p-6 text-center text-sm text-gray-500">
        Loading strategy leaderboard...
      </div>
    );
  }

  if (isError) {
    return (
      <div className="rounded-lg border border-border bg-surface p-6 text-center text-sm text-red-400">
        Failed to load strategy data.
      </div>
    );
  }

  if (leaderboard.length === 0) {
    return (
      <div className="rounded-lg border border-border bg-surface p-6 text-center text-sm text-gray-500">
        No strategy data yet -- leaderboard will populate after trades are recorded.
      </div>
    );
  }

  return (
    <div
      className="rounded-lg border border-border bg-surface p-4"
      aria-label="Strategy leaderboard"
    >
      <h3 className="mb-4 text-sm font-semibold text-white">Strategy Leaderboard</h3>

      <div className="space-y-2">
        {leaderboard.map((entry, index) => {
          const badge = getRankBadge(index);
          const normalizedScore = Math.min(Math.max(entry.performanceScore, 0), 100);

          return (
            <div
              key={entry.name}
              className={`rounded-lg border p-3 transition-colors hover:bg-background/50 ${
                entry.blocked
                  ? "border-red-900/40 bg-red-900/5"
                  : "border-border bg-background/30"
              }`}
            >
              <div className="flex items-start justify-between gap-3">
                {/* Left: rank + name + details */}
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    {badge && (
                      <span
                        className={`text-[10px] font-bold ${getRankColor(index)}`}
                      >
                        {badge}
                      </span>
                    )}
                    <span className="text-xs font-semibold text-white">{entry.name}</span>
                    {entry.blocked && (
                      <span className="rounded bg-red-900/30 px-1.5 py-0.5 text-[10px] font-medium text-red-400">
                        BLOCKED
                      </span>
                    )}
                  </div>

                  <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-[10px]">
                    <span className="text-gray-500">
                      Win Rate:{" "}
                      <span
                        className={`font-mono font-medium ${
                          entry.winRate >= 50 ? "text-green-400" : "text-red-400"
                        }`}
                      >
                        {entry.winRate.toFixed(1)}%
                      </span>
                    </span>
                    <span className="text-gray-500">
                      Confidence:{" "}
                      <span
                        className={`font-mono font-medium ${
                          entry.avgConfidence >= 1 ? "text-green-400" : "text-red-400"
                        }`}
                      >
                        {entry.avgConfidence.toFixed(2)}x
                      </span>
                    </span>
                    <span className="text-gray-500">
                      Signals:{" "}
                      <span className="font-mono font-medium text-white">
                        {entry.signalCount}
                      </span>
                    </span>
                    <span className="text-gray-500">
                      PnL:{" "}
                      <span
                        className={`font-mono font-medium ${
                          entry.totalPnl >= 0 ? "text-green-400" : "text-red-400"
                        }`}
                      >
                        {entry.totalPnl >= 0 ? "+" : ""}{entry.totalPnl.toFixed(2)}%
                      </span>
                    </span>
                  </div>
                </div>

                {/* Right: performance score */}
                <div className="flex flex-col items-end gap-1">
                  <span
                    className={`text-sm font-bold font-mono ${getScoreColor(entry.performanceScore)}`}
                  >
                    {entry.performanceScore.toFixed(1)}
                  </span>
                  <span className="text-[10px] text-gray-500">score</span>
                </div>
              </div>

              {/* Score bar */}
              <div className="mt-2 h-1 w-full overflow-hidden rounded-full bg-gray-700">
                <div
                  className={`h-full rounded-full transition-all ${getScoreBg(entry.performanceScore)}`}
                  style={{ width: `${normalizedScore}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
