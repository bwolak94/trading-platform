import { useQuery } from "@tanstack/react-query";
import { fetchStrategyHeatmap } from "../../api/client";

function winRateColor(winRate: number): string {
  if (winRate >= 0.65) return "bg-green-500/80 text-white";
  if (winRate >= 0.55) return "bg-green-400/50 text-green-100";
  if (winRate >= 0.45) return "bg-yellow-400/40 text-yellow-100";
  if (winRate >= 0.35) return "bg-orange-400/40 text-orange-100";
  return "bg-red-400/40 text-red-100";
}

export function StrategyHeatmapPanel() {
  const { data, isLoading } = useQuery({
    queryKey: ["strategy-heatmap"],
    queryFn: fetchStrategyHeatmap,
    refetchInterval: 60_000,
  });

  const strategies = data?.strategies ?? [];
  const regimes = data?.regimes ?? [];
  const heatmap = data?.heatmap ?? [];

  const getCell = (strategy: string, regime: string) =>
    heatmap.find((h) => h.strategy === strategy && h.regime === regime);

  return (
    <div className="flex flex-col gap-4 rounded-xl border border-border bg-background p-5">
      <div>
        <h2 className="text-base font-semibold text-foreground">Strategy × Regime Heatmap</h2>
        <p className="text-xs text-muted-foreground">Win rate for each strategy in each market regime</p>
      </div>

      {isLoading ? (
        <div className="flex h-32 items-center justify-center text-sm text-muted-foreground">
          Loading heatmap...
        </div>
      ) : strategies.length === 0 ? (
        <div className="flex h-32 items-center justify-center rounded-lg border border-border/50 bg-surface/30 text-sm text-muted-foreground">
          No closed trades yet
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs" role="grid" aria-label="Strategy regime win rate heatmap">
            <thead>
              <tr>
                <th className="pb-2 pr-3 text-left text-muted-foreground font-medium">Strategy</th>
                {regimes.map((regime) => (
                  <th key={regime} className="pb-2 px-1 text-center text-muted-foreground font-medium min-w-[72px]">
                    {regime.replace("_", " ")}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {strategies.map((strategy) => (
                <tr key={strategy}>
                  <td className="py-1 pr-3 font-medium text-foreground whitespace-nowrap">
                    {strategy}
                  </td>
                  {regimes.map((regime) => {
                    const cell = getCell(strategy, regime);
                    return (
                      <td key={regime} className="py-1 px-1 text-center">
                        {cell ? (
                          <div
                            className={`rounded px-1.5 py-1 font-mono text-xs ${winRateColor(cell.win_rate)}`}
                            title={`${cell.total_trades} trades, ${cell.wins} wins`}
                          >
                            {(cell.win_rate * 100).toFixed(0)}%
                          </div>
                        ) : (
                          <div className="rounded px-1.5 py-1 text-muted-foreground/30">—</div>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {data && (
        <p className="text-xs text-muted-foreground">
          Based on {data.total_positions} closed positions
        </p>
      )}
    </div>
  );
}
