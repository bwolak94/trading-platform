import { useQuery } from "@tanstack/react-query";
import { fetchAttribution } from "../../api/client";
import type { AttributionEntry } from "../../api/client";

interface PnLBarProps {
  value: number;
  maxAbs: number;
}

function PnLBar({ value, maxAbs }: PnLBarProps) {
  const pct = maxAbs > 0 ? Math.min((Math.abs(value) / maxAbs) * 100, 100) : 0;
  return (
    <div className="flex h-1.5 w-20 overflow-hidden rounded-full bg-border/50">
      <div
        className={`h-full rounded-full ${value >= 0 ? "bg-green-400" : "bg-red-400"}`}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

interface AttributionTableProps {
  title: string;
  entries: AttributionEntry[];
}

function AttributionTable({ title, entries }: AttributionTableProps) {
  const maxAbs = Math.max(...entries.map((e) => Math.abs(e.total_pnl)), 0.001);

  return (
    <div className="flex flex-col gap-2">
      <h3 className="text-sm font-medium text-muted-foreground">{title}</h3>
      <div className="space-y-1">
        {entries.slice(0, 8).map((entry) => (
          <div
            key={entry.key}
            className="flex items-center gap-2 rounded px-2 py-1.5 hover:bg-accent/5 transition-colors"
          >
            <span
              className="w-24 truncate text-xs font-medium text-foreground"
              title={entry.key}
            >
              {entry.key}
            </span>
            <PnLBar value={entry.total_pnl} maxAbs={maxAbs} />
            <span
              className={`ml-auto w-16 text-right font-mono text-xs font-semibold ${
                entry.total_pnl >= 0 ? "text-green-400" : "text-red-400"
              }`}
            >
              {entry.total_pnl >= 0 ? "+" : ""}
              {entry.total_pnl.toFixed(2)}%
            </span>
            <span className="w-10 text-right text-xs text-muted-foreground">
              {(entry.win_rate * 100).toFixed(0)}% WR
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function AttributionPanel() {
  const { data, isLoading } = useQuery({
    queryKey: ["attribution"],
    queryFn: fetchAttribution,
    refetchInterval: 60_000,
  });

  return (
    <div className="flex flex-col gap-4 rounded-xl border border-border bg-background p-5">
      <div>
        <h2 className="text-base font-semibold text-foreground">PnL Attribution</h2>
        <p className="text-xs text-muted-foreground">
          {data
            ? `${data.total_closed_trades} closed trades`
            : "Breakdown by strategy, regime & symbol"}
        </p>
      </div>

      {isLoading ? (
        <div className="flex h-40 items-center justify-center text-sm text-muted-foreground">
          Loading attribution data...
        </div>
      ) : !data || data.total_closed_trades === 0 ? (
        <div className="flex h-40 items-center justify-center rounded-lg border border-border/50 bg-surface/30 text-sm text-muted-foreground">
          No closed trades yet
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <AttributionTable title="By Strategy" entries={data.by_strategy} />
          <AttributionTable title="By Regime" entries={data.by_regime} />
          <AttributionTable title="By Symbol" entries={data.by_symbol} />
        </div>
      )}
    </div>
  );
}
