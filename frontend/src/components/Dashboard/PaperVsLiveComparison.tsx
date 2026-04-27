/**
 * B9: Paper vs Live Comparison
 *
 * Side-by-side metrics: paper trading P&L vs live P&L for same period.
 * Highlights slippage and execution divergence.
 */

import { useQuery } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

interface ComparisonData {
  period: string;
  paper_pnl_pct: number;
  live_pnl_pct: number;
  slippage_pct: number;
  paper_win_rate: number;
  live_win_rate: number;
  paper_trades: number;
  live_trades: number;
}

async function fetchComparison(): Promise<ComparisonData> {
  const resp = await fetch("/api/v1/simulation/paper-vs-live");
  if (!resp.ok) throw new Error("Failed to fetch comparison data");
  return resp.json();
}

export function PaperVsLiveComparison() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["paper-vs-live"],
    queryFn: fetchComparison,
    staleTime: 5 * 60 * 1000,
  });

  const chartData = data
    ? [
        { name: "P&L%", paper: data.paper_pnl_pct, live: data.live_pnl_pct },
        { name: "Win%", paper: data.paper_win_rate * 100, live: data.live_win_rate * 100 },
      ]
    : [];

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h3 className="mb-3 text-sm font-semibold text-gray-200">Paper vs Live Comparison</h3>
      <p className="mb-3 text-xs text-gray-400">
        Same period — divergence reveals slippage and execution risk
      </p>

      {isLoading && <div className="flex h-40 items-center justify-center text-xs text-gray-500">Loading…</div>}
      {isError && <div className="flex h-40 items-center justify-center text-xs text-bearish">Failed to load</div>}

      {!isLoading && !isError && data && (
        <div>
          <div className="mb-3 grid grid-cols-2 gap-3 text-xs">
            <div className="rounded border border-border bg-background/50 p-2 text-center">
              <div className="text-gray-500 mb-1">Slippage Drag</div>
              <div className={`font-bold text-base ${data.slippage_pct > 0.3 ? "text-bearish" : "text-amber-400"}`}>
                -{data.slippage_pct.toFixed(2)}%
              </div>
            </div>
            <div className="rounded border border-border bg-background/50 p-2 text-center">
              <div className="text-gray-500 mb-1">Period</div>
              <div className="font-semibold text-gray-300">{data.period}</div>
            </div>
          </div>

          <ResponsiveContainer width="100%" height={160}>
            <BarChart data={chartData} margin={{ top: 4, right: 8, bottom: 4, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="name" tick={{ fontSize: 10, fill: "#94a3b8" }} />
              <YAxis tick={{ fontSize: 10, fill: "#94a3b8" }} tickFormatter={(v) => `${v.toFixed(1)}%`} />
              <Tooltip
                contentStyle={{ background: "#1e293b", border: "1px solid #334155", fontSize: 11 }}
                formatter={(v: number) => [`${v.toFixed(2)}%`, ""]}
              />
              <Legend wrapperStyle={{ fontSize: 10 }} />
              <Bar dataKey="paper" name="Paper" fill="#22d3ee" radius={[3, 3, 0, 0]} />
              <Bar dataKey="live" name="Live" fill="#f59e0b" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
