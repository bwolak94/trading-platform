/**
 * B4: Signal Invalidation Tracker
 *
 * Shows signals that were ACTIVE but expired without hitting TP1 or SL.
 * Displays invalidation rate per regime to reveal which market conditions
 * produce the most noise.
 */

import { useQuery } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

interface InvalidationStats {
  regime: string;
  total: number;
  invalidated: number;
  invalidation_rate: number;
}

async function fetchInvalidationStats(): Promise<InvalidationStats[]> {
  const resp = await fetch("/api/v1/analytics/signal-invalidation");
  if (!resp.ok) throw new Error("Failed to fetch invalidation stats");
  return resp.json();
}

const REGIME_COLORS: Record<string, string> = {
  TREND_BULL: "#22c55e",
  TREND_BEAR: "#ef4444",
  CONSOLIDATION: "#f59e0b",
  HIGH_VOL_CHOPPY: "#8b5cf6",
  UNKNOWN: "#64748b",
};

export function SignalInvalidationTracker() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["signal-invalidation"],
    queryFn: fetchInvalidationStats,
    staleTime: 5 * 60 * 1000,
  });

  const chartData = (data ?? []).map((d) => ({
    name: d.regime.replace("_", " "),
    rate: Math.round(d.invalidation_rate * 100),
    total: d.total,
    fill: REGIME_COLORS[d.regime] ?? "#64748b",
  }));

  const overall =
    data && data.length > 0
      ? data.reduce((s, d) => s + d.invalidated, 0) /
        data.reduce((s, d) => s + d.total, 1)
      : null;

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="mb-3 flex items-start justify-between">
        <div>
          <h3 className="text-sm font-semibold text-gray-200">Signal Invalidation Tracker</h3>
          <p className="text-xs text-gray-400">Signals expired without TP1/SL hit — by regime</p>
        </div>
        {overall !== null && (
          <div className="text-right">
            <div className="text-xs text-gray-500">Overall</div>
            <div className={`text-base font-bold ${overall > 0.4 ? "text-bearish" : "text-amber-400"}`}>
              {(overall * 100).toFixed(1)}%
            </div>
          </div>
        )}
      </div>

      {isLoading && (
        <div className="flex h-40 items-center justify-center text-xs text-gray-500">Loading…</div>
      )}
      {isError && (
        <div className="flex h-40 items-center justify-center text-xs text-bearish">Failed to load</div>
      )}

      {!isLoading && !isError && chartData.length > 0 && (
        <ResponsiveContainer width="100%" height={160}>
          <BarChart data={chartData} margin={{ top: 4, right: 8, bottom: 4, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
            <XAxis dataKey="name" tick={{ fontSize: 10, fill: "#94a3b8" }} />
            <YAxis tickFormatter={(v) => `${v}%`} tick={{ fontSize: 10, fill: "#94a3b8" }} domain={[0, 100]} />
            <Tooltip
              contentStyle={{ background: "#1e293b", border: "1px solid #334155", fontSize: 11 }}
              formatter={(v: number) => [`${v}%`, "Invalidation Rate"]}
            />
            <Bar dataKey="rate" radius={[4, 4, 0, 0]}>
              {chartData.map((entry, i) => (
                <rect key={i} fill={entry.fill} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      )}

      {!isLoading && !isError && chartData.length === 0 && (
        <div className="flex h-40 items-center justify-center text-xs text-gray-500">
          No signal data yet
        </div>
      )}
    </div>
  );
}
