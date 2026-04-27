/**
 * B10: Dark Pool Cumulative Flow Chart
 *
 * Chart of cumulative dark pool volume over time for selected asset.
 */

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

interface DarkPoolPoint {
  timestamp: string;
  cumulative_volume: number;
  dark_pool_pct: number;
}

async function fetchDarkPoolFlow(symbol: string): Promise<DarkPoolPoint[]> {
  const resp = await fetch(`/api/v1/dark-pool/cumulative-flow?symbol=${encodeURIComponent(symbol)}`);
  if (!resp.ok) throw new Error("Failed to fetch dark pool data");
  return resp.json();
}

export function DarkPoolCumulativeFlowChart() {
  const [symbol, setSymbol] = useState("BTC/USDT");

  const { data, isLoading, isError } = useQuery({
    queryKey: ["dark-pool-flow", symbol],
    queryFn: () => fetchDarkPoolFlow(symbol),
    staleTime: 2 * 60 * 1000,
    refetchInterval: 5 * 60 * 1000,
  });

  const chartData = (data ?? []).map((p) => ({
    t: new Date(p.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    volume: p.cumulative_volume,
    pct: p.dark_pool_pct,
  }));

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-gray-200">Dark Pool Cumulative Flow</h3>
          <p className="text-xs text-gray-400">Institutional off-exchange volume over time</p>
        </div>
        <select
          value={symbol}
          onChange={(e) => setSymbol(e.target.value)}
          className="rounded border border-border bg-background px-2 py-1 text-xs text-gray-300"
          aria-label="Select asset for dark pool data"
        >
          <option value="BTC/USDT">BTC/USDT</option>
          <option value="ETH/USDT">ETH/USDT</option>
          <option value="SOL/USDT">SOL/USDT</option>
        </select>
      </div>

      {isLoading && (
        <div className="flex h-40 items-center justify-center text-xs text-gray-500">Loading…</div>
      )}
      {isError && (
        <div className="flex h-40 items-center justify-center text-xs text-gray-500">
          Dark pool data unavailable
        </div>
      )}

      {!isLoading && !isError && chartData.length > 0 && (
        <ResponsiveContainer width="100%" height={180}>
          <AreaChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
            <XAxis dataKey="t" tick={{ fontSize: 9, fill: "#94a3b8" }} />
            <YAxis tick={{ fontSize: 9, fill: "#94a3b8" }} tickFormatter={(v) => `$${(v / 1e6).toFixed(0)}M`} />
            <Tooltip
              contentStyle={{ background: "#1e293b", border: "1px solid #334155", fontSize: 11 }}
              formatter={(v: number) => [`$${(v / 1e6).toFixed(2)}M`, "Cumulative Volume"]}
            />
            <Area
              type="monotone"
              dataKey="volume"
              stroke="#8b5cf6"
              fill="#8b5cf620"
              strokeWidth={2}
            />
          </AreaChart>
        </ResponsiveContainer>
      )}

      {!isLoading && !isError && chartData.length === 0 && (
        <div className="flex h-40 items-center justify-center text-xs text-gray-500">
          No dark pool data available
        </div>
      )}
    </div>
  );
}
