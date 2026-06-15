import { useQuery } from "@tanstack/react-query";
import { fetchLearningData } from "../../api/client";

export function StrategyStats() {
  const { data: learning } = useQuery({
    queryKey: ["learning-data"],
    queryFn: fetchLearningData,
    refetchInterval: 15_000,
  });

  if (!learning || learning.strategy_performance.length === 0) {
    return (
      <div className="rounded-lg border border-border bg-surface p-6 text-center text-sm text-gray-500">
        No strategy performance data yet -- stats will appear after trades are recorded.
      </div>
    );
  }

  const perf = learning.strategy_performance;

  // Find best and worst by total_pnl
  const bestPnl = Math.max(...perf.map((p) => p.total_pnl));
  const worstPnl = Math.min(...perf.map((p) => p.total_pnl));

  return (
    <div
      className="rounded-lg border border-border bg-surface p-4"
      aria-label="Strategy performance statistics"
    >
      <h3 className="mb-4 text-sm font-semibold text-white">Strategy Performance Breakdown</h3>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs" aria-label="Strategy statistics table">
          <thead className="border-b border-border text-gray-500">
            <tr>
              <th className="px-3 py-2">Strategy</th>
              <th className="px-3 py-2">Regime</th>
              <th className="px-3 py-2 text-right">Trades</th>
              <th className="px-3 py-2 text-right">Win%</th>
              <th className="px-3 py-2 text-right">PnL%</th>
              <th className="px-3 py-2 text-right">Avg Reward</th>
              <th className="px-3 py-2 text-right">Multiplier</th>
              <th className="px-3 py-2">Status</th>
            </tr>
          </thead>
          <tbody>
            {perf.map((p, i) => {
              const totalTrades = p.wins + p.losses;
              const isBest = p.total_pnl === bestPnl && bestPnl > 0;
              const isWorst = p.total_pnl === worstPnl && worstPnl < 0;
              const rowHighlight = isBest
                ? "bg-green-900/10"
                : isWorst
                  ? "bg-red-900/10"
                  : "";

              return (
                <tr
                  key={`${p.strategy}-${p.regime}-${i}`}
                  className={`border-b border-border transition-colors hover:bg-background/50 ${rowHighlight}`}
                >
                  <td className="px-3 py-2 font-medium text-white">
                    {p.strategy}
                    {isBest && (
                      <span className="ml-1 text-[10px] text-green-400">(best)</span>
                    )}
                    {isWorst && (
                      <span className="ml-1 text-[10px] text-red-400">(worst)</span>
                    )}
                  </td>
                  <td className="px-3 py-2">
                    <span className="rounded bg-purple-900/50 px-2 py-0.5 text-[10px] text-purple-300">
                      {p.regime}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-white">{totalTrades}</td>
                  <td className="px-3 py-2 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-gray-700">
                        <div
                          className={`h-full rounded-full ${
                            p.win_rate >= 50 ? "bg-green-500" : "bg-red-500"
                          }`}
                          style={{ width: `${Math.min(100, p.win_rate)}%` }}
                        />
                      </div>
                      <span
                        className={`font-mono ${
                          p.win_rate >= 50 ? "text-green-400" : "text-red-400"
                        }`}
                      >
                        {p.win_rate.toFixed(0)}%
                      </span>
                    </div>
                  </td>
                  <td
                    className={`px-3 py-2 text-right font-mono font-semibold ${
                      p.total_pnl >= 0 ? "text-green-400" : "text-red-400"
                    }`}
                  >
                    {p.total_pnl > 0 ? "+" : ""}
                    {p.total_pnl.toFixed(2)}%
                  </td>
                  <td
                    className={`px-3 py-2 text-right font-mono ${
                      p.avg_reward >= 0 ? "text-green-400" : "text-red-400"
                    }`}
                  >
                    {p.avg_reward >= 0 ? "+" : ""}
                    {p.avg_reward.toFixed(2)}R
                  </td>
                  <td
                    className={`px-3 py-2 text-right font-mono ${
                      p.confidence_multiplier > 1
                        ? "text-green-400"
                        : p.confidence_multiplier < 0.8
                          ? "text-red-400"
                          : "text-gray-400"
                    }`}
                  >
                    {p.confidence_multiplier.toFixed(2)}x
                  </td>
                  <td className="px-3 py-2">
                    {p.blocked ? (
                      <span className="rounded bg-red-900/30 px-2 py-0.5 text-[10px] font-medium text-red-400">
                        BLOCKED
                      </span>
                    ) : (
                      <span className="rounded bg-green-900/30 px-2 py-0.5 text-[10px] font-medium text-green-400">
                        ACTIVE
                      </span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
