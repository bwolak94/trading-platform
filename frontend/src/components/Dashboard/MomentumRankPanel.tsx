import { useQuery } from "@tanstack/react-query";
import { fetchMomentumRank } from "../../api/client";
import type { MomentumEntry } from "../../api/client";

function ScoreBar({ score }: { score: number }) {
  const pct = Math.min(Math.abs(score) * 100, 100);
  const isLong = score > 0;
  return (
    <div className="flex h-1.5 w-16 overflow-hidden rounded-full bg-border/50">
      <div
        className={`h-full rounded-full transition-all ${isLong ? "bg-green-400" : "bg-red-400"}`}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

function MomentumRow({ entry, rank }: { entry: MomentumEntry; rank: number }) {
  const dirColor =
    entry.direction === "LONG" ? "text-green-400 bg-green-400/10" :
    entry.direction === "SHORT" ? "text-red-400 bg-red-400/10" :
    "text-muted-foreground bg-border/20";

  return (
    <div className="flex items-center gap-3 rounded-md px-2 py-1.5 hover:bg-accent/5 transition-colors">
      <span className="w-5 text-center text-xs text-muted-foreground">{rank}</span>
      <span className="w-24 truncate text-sm font-medium text-foreground">{entry.symbol.replace("USDT", "")}</span>
      <span className={`rounded px-1.5 py-0.5 text-xs font-semibold ${dirColor}`}>
        {entry.direction}
      </span>
      <ScoreBar score={entry.score} />
      <span className={`ml-auto font-mono text-xs ${entry.score > 0 ? "text-green-400" : entry.score < 0 ? "text-red-400" : "text-muted-foreground"}`}>
        {entry.score > 0 ? "+" : ""}{entry.score.toFixed(3)}
      </span>
    </div>
  );
}

export function MomentumRankPanel() {
  const { data, isLoading } = useQuery({
    queryKey: ["momentum-rank"],
    queryFn: () => fetchMomentumRank(15),
    refetchInterval: 15 * 60_000, // 15 min (matches server cache)
  });

  const rankings = data?.rankings ?? [];

  return (
    <div className="flex flex-col gap-4 rounded-xl border border-border bg-background p-5">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-base font-semibold text-foreground">Momentum Rankings</h2>
          <p className="text-xs text-muted-foreground">Multi-timeframe score (1h + 4h + 1d)</p>
        </div>
        <span className="text-xs text-muted-foreground">Updated every 15 min</span>
      </div>

      {isLoading ? (
        <div className="flex h-40 items-center justify-center text-sm text-muted-foreground">
          Calculating momentum scores...
        </div>
      ) : rankings.length === 0 ? (
        <div className="flex h-40 items-center justify-center text-sm text-muted-foreground">
          No data available
        </div>
      ) : (
        <div className="flex flex-col divide-y divide-border/30">
          {rankings.map((entry, i) => (
            <MomentumRow key={entry.symbol} entry={entry} rank={i + 1} />
          ))}
        </div>
      )}
    </div>
  );
}
