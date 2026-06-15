import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchSimulationPerformance, fetchSessionHistory, fetchClosedPositions } from "../../api/client";
import type { SimulationPerformance, BotSession } from "../../api/client";

function exportToCSV(data: Record<string, unknown>[], filename: string): void {
  if (data.length === 0) return;
  const headers = Object.keys(data[0] ?? {});
  const rows = data.map((row) =>
    headers.map((h) => {
      const val = row[h];
      if (val === null || val === undefined) return "";
      const str = String(val);
      return str.includes(",") || str.includes('"') ? `"${str.replace(/"/g, '""')}"` : str;
    }).join(",")
  );
  const csv = [headers.join(","), ...rows].join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function MetricCard({
  label,
  value,
  sub,
  positive,
}: {
  label: string;
  value: string;
  sub?: string;
  positive?: boolean;
}) {
  const valueColor =
    positive === undefined
      ? "text-foreground"
      : positive
        ? "text-green-400"
        : "text-red-400";

  return (
    <div className="flex flex-col gap-0.5 rounded-lg border border-border/50 bg-surface/50 p-3">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className={`text-lg font-semibold ${valueColor}`}>{value}</span>
      {sub && <span className="text-xs text-muted-foreground">{sub}</span>}
    </div>
  );
}

function PerformanceGrid({ perf }: { perf: SimulationPerformance }) {
  const winRatePct = (perf.win_rate * 100).toFixed(1);
  const isProfit = perf.total_pnl_pct >= 0;

  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
      <MetricCard
        label="Win Rate"
        value={`${winRatePct}%`}
        sub={`${perf.winning_trades}W / ${perf.losing_trades}L`}
        positive={perf.win_rate >= 0.5}
      />
      <MetricCard
        label="Total PnL"
        value={`${perf.total_pnl_pct >= 0 ? "+" : ""}${perf.total_pnl_pct.toFixed(2)}%`}
        sub={`Running: ${perf.running_pnl >= 0 ? "+" : ""}${perf.running_pnl.toFixed(2)}%`}
        positive={isProfit}
      />
      <MetricCard
        label="Sharpe Ratio"
        value={perf.sharpe_ratio.toFixed(2)}
        sub="annualised"
        positive={perf.sharpe_ratio > 1}
      />
      <MetricCard
        label="Max Drawdown"
        value={`${perf.max_drawdown_pct.toFixed(2)}%`}
        sub="from peak"
        positive={perf.max_drawdown_pct < 10}
      />
      <MetricCard
        label="Profit Factor"
        value={perf.profit_factor.toFixed(2)}
        positive={perf.profit_factor > 1}
      />
      <MetricCard
        label="Avg Win"
        value={`+${perf.avg_win_pct.toFixed(2)}%`}
        positive={true}
      />
      <MetricCard
        label="Avg Loss"
        value={`${perf.avg_loss_pct.toFixed(2)}%`}
        positive={false}
      />
      <MetricCard
        label="Total Trades"
        value={String(perf.total_trades)}
        sub={`${perf.open_positions} open`}
      />
    </div>
  );
}

function SessionRow({ session }: { session: BotSession }) {
  const startStr = session.started_at
    ? new Date(session.started_at).toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "—";

  const winPct = (session.win_rate * 100).toFixed(0);
  const pnl = session.total_pnl_pct;

  return (
    <div className="grid grid-cols-[1fr_auto_auto_auto_auto] items-center gap-3 rounded-md border border-border/50 bg-surface/50 px-3 py-2 text-sm">
      <div>
        <span className="text-xs text-muted-foreground">{startStr}</span>
        {session.is_active && (
          <span className="ml-2 rounded-full bg-green-500/15 px-1.5 py-0.5 text-xs text-green-400">
            LIVE
          </span>
        )}
      </div>
      <span className="text-muted-foreground">{session.total_trades} trades</span>
      <span
        className={`font-medium ${session.win_rate >= 0.5 ? "text-green-400" : "text-red-400"}`}
      >
        {winPct}% WR
      </span>
      <span className={`font-mono font-semibold ${pnl >= 0 ? "text-green-400" : "text-red-400"}`}>
        {pnl >= 0 ? "+" : ""}
        {pnl.toFixed(2)}%
      </span>
      <span className="text-xs text-muted-foreground">
        {session.sharpe_ratio !== null ? `S: ${session.sharpe_ratio.toFixed(2)}` : ""}
      </span>
    </div>
  );
}

export function BotPerformancePanel() {
  const [isExporting, setIsExporting] = useState(false);

  const { data: perf, isLoading: perfLoading } = useQuery({
    queryKey: ["sim-performance"],
    queryFn: fetchSimulationPerformance,
    refetchInterval: 15_000,
  });

  const { data: historyData } = useQuery({
    queryKey: ["sim-session-history"],
    queryFn: () => fetchSessionHistory(5),
    refetchInterval: 60_000,
  });

  const sessions = historyData?.sessions ?? [];

  async function handleExportCSV(): Promise<void> {
    setIsExporting(true);
    try {
      const result = await fetchClosedPositions({ limit: 200, offset: 0 });
      exportToCSV(
        result.positions as unknown as Record<string, unknown>[],
        "bot-performance.csv",
      );
    } finally {
      setIsExporting(false);
    }
  }

  return (
    <div className="flex flex-col gap-4 rounded-xl border border-border bg-background p-5">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h2 className="text-base font-semibold text-foreground">Bot Performance</h2>
          <p className="text-xs text-muted-foreground">
            Live metrics from the paper trading simulation engine
          </p>
        </div>
        <button
          onClick={handleExportCSV}
          disabled={isExporting}
          aria-label="Export closed positions to CSV"
          className="shrink-0 rounded-md border border-border/60 bg-surface/50 px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:border-border hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isExporting ? "Exporting..." : "Export CSV"}
        </button>
      </div>

      {perfLoading || !perf ? (
        <div className="flex h-24 items-center justify-center text-sm text-muted-foreground">
          Loading performance data...
        </div>
      ) : (
        <PerformanceGrid perf={perf} />
      )}

      {sessions.length > 0 && (
        <section aria-labelledby="session-hist-heading">
          <h3
            id="session-hist-heading"
            className="mb-2 text-sm font-medium text-muted-foreground"
          >
            Session History
          </h3>
          <div className="flex flex-col gap-1.5">
            {sessions.map((s) => (
              <SessionRow key={s.id} session={s} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
