/**
 * Drawdown Waterfall Chart
 * Visualises each losing trade's contribution to the current drawdown valley.
 * Uses closed positions sorted by close date.
 */

import { useQuery } from "@tanstack/react-query";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ReferenceLine, ResponsiveContainer, Cell } from "recharts";
import { fetchClosedPositions } from "../../api/client";

interface WaterfallBar {
  label: string;
  pnl: number;
  cumulative: number;
  asset: string;
}

function buildWaterfall(positions: { symbol: string; pnl_pct?: number | null; closed_at?: string | null }[]): WaterfallBar[] {
  const sorted = [...positions]
    .filter((p) => (p.pnl_pct ?? 0) < 0)
    .sort((a, b) => new Date(a.closed_at ?? 0).getTime() - new Date(b.closed_at ?? 0).getTime())
    .slice(-20);

  let cum = 0;
  return sorted.map((p, i) => {
    const pnl = p.pnl_pct ?? 0;
    cum += pnl;
    return { label: `#${i + 1}`, pnl: parseFloat(pnl.toFixed(2)), cumulative: parseFloat(cum.toFixed(2)), asset: p.symbol };
  });
}

export function DrawdownWaterfallChart() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["closed-positions-waterfall"],
    queryFn: () => fetchClosedPositions({ limit: 100 }),
    refetchInterval: 60_000,
    staleTime: 30_000,
    retry: false,
  });

  const bars = buildWaterfall(data?.positions ?? []);
  const maxDD = bars.length ? Math.min(...bars.map((b) => b.cumulative)) : 0;

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-white">Drawdown Waterfall</h2>
        {maxDD < 0 && (
          <span className="rounded bg-bearish/20 px-2 py-0.5 text-xs font-bold text-bearish">
            Peak DD: {maxDD.toFixed(1)}%
          </span>
        )}
      </div>
      <p className="mb-3 text-[10px] text-gray-500">
        Each bar = one losing trade. Curve shows cumulative drawdown path.
      </p>

      {isError && <p className="text-xs text-bearish">Unable to load position data.</p>}

      {isLoading ? (
        <div className="h-40 animate-pulse rounded bg-white/5" />
      ) : bars.length === 0 ? (
        <p className="py-8 text-center text-xs text-gray-600">No losing trades to display.</p>
      ) : (
        <ResponsiveContainer width="100%" height={160}>
          <BarChart data={bars} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
            <XAxis dataKey="label" tick={{ fontSize: 9, fill: "#6b7280" }} />
            <YAxis tick={{ fontSize: 9, fill: "#6b7280" }} tickFormatter={(v) => `${v}%`} />
            <Tooltip
              contentStyle={{ background: "#1a1a2e", border: "1px solid #374151", fontSize: 11 }}
              formatter={(value: number, name: string) => [`${value.toFixed(2)}%`, name === "pnl" ? "Trade P&L" : "Cumulative DD"]}
            />
            <ReferenceLine y={0} stroke="#374151" />
            <Bar dataKey="pnl" name="pnl" radius={[2, 2, 0, 0]}>
              {bars.map((b, i) => (
                <Cell key={i} fill={b.pnl >= 0 ? "#22c55e" : "#ef4444"} />
              ))}
            </Bar>
            <Bar dataKey="cumulative" name="cumulative" fill="#f59e0b" opacity={0.4} radius={[2, 2, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
