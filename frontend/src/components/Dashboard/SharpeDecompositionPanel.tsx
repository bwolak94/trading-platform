/**
 * B2: Sharpe Decomposition Panel
 *
 * Breaks the Sharpe ratio into three contributions:
 *   - Signal quality (alpha from signal selection)
 *   - Regime contribution (regime timing bonus/penalty)
 *   - Sizing contribution (Kelly / position-size efficiency)
 */

import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

interface SharpeComponents {
  signal_quality: number;
  regime_contribution: number;
  sizing_contribution: number;
  total_sharpe: number;
}

async function fetchSharpeComponents(): Promise<SharpeComponents> {
  const resp = await fetch("/api/v1/analytics/sharpe-decomposition");
  if (!resp.ok) throw new Error("Failed to fetch Sharpe decomposition");
  return resp.json();
}

export function SharpeDecompositionPanel() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["sharpe-decomposition"],
    queryFn: fetchSharpeComponents,
    staleTime: 5 * 60 * 1000,
  });

  const chartData = useMemo(() => {
    if (!data) return [];
    return [
      { name: "Signal Quality", value: data.signal_quality },
      { name: "Regime", value: data.regime_contribution },
      { name: "Sizing", value: data.sizing_contribution },
    ];
  }, [data]);

  const totalSharpe = data?.total_sharpe ?? 0;

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="mb-4 flex items-start justify-between">
        <div>
          <h3 className="text-sm font-semibold text-gray-200">Sharpe Decomposition</h3>
          <p className="text-xs text-gray-400">Signal quality · Regime · Sizing contributions</p>
        </div>
        {!isLoading && !isError && (
          <div className="text-right">
            <div className="text-xs text-gray-500">Total Sharpe</div>
            <div className={`text-lg font-bold ${totalSharpe >= 1 ? "text-bullish" : totalSharpe >= 0 ? "text-amber-400" : "text-bearish"}`}>
              {totalSharpe.toFixed(2)}
            </div>
          </div>
        )}
      </div>

      {isLoading && (
        <div className="flex h-40 items-center justify-center text-xs text-gray-500">
          Loading…
        </div>
      )}

      {isError && (
        <div className="flex h-40 items-center justify-center text-xs text-bearish">
          Failed to load Sharpe decomposition
        </div>
      )}

      {!isLoading && !isError && (
        <ResponsiveContainer width="100%" height={160}>
          <BarChart data={chartData} layout="vertical" margin={{ left: 8, right: 16, top: 4, bottom: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" horizontal={false} />
            <XAxis type="number" tick={{ fontSize: 10, fill: "#94a3b8" }} tickFormatter={(v) => v.toFixed(2)} />
            <YAxis type="category" dataKey="name" tick={{ fontSize: 10, fill: "#94a3b8" }} width={90} />
            <Tooltip
              contentStyle={{ background: "#1e293b", border: "1px solid #334155", fontSize: 11 }}
              formatter={(v: number) => [v.toFixed(3), "Contribution"]}
            />
            <Bar dataKey="value" radius={[0, 4, 4, 0]}>
              {chartData.map((entry, i) => (
                <Cell key={i} fill={entry.value >= 0 ? "#22c55e" : "#ef4444"} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
