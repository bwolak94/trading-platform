/**
 * Signal Confidence Trend
 * Shows how confidence evolved for recent signals over time
 */

import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { fetchSignalHistory } from "../../api/client";

const STRATEGY_COLORS = [
  "#3b82f6", // blue
  "#f59e0b", // amber
  "#8b5cf6", // purple
  "#06b6d4", // cyan
  "#ec4899", // pink
  "#84cc16", // lime
];

const ALL_ASSETS = "ALL";

interface ChartDataPoint {
  time: string;
  [strategy: string]: number | string;
}

export function SignalConfidenceTrend() {
  const [selectedAsset, setSelectedAsset] = useState<string>(ALL_ASSETS);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["signal-confidence-trend"],
    queryFn: () => fetchSignalHistory({ limit: 50 }),
    refetchInterval: 60_000,
    retry: false,
  });

  const signals = data?.data ?? [];

  // Collect unique assets for filter
  const assetOptions = useMemo(() => {
    const assetSet = new Set<string>();
    for (const s of signals) assetSet.add(s.asset);
    return [ALL_ASSETS, ...Array.from(assetSet).sort()];
  }, [signals]);

  // Filter signals by selected asset
  const filtered = useMemo(
    () =>
      selectedAsset === ALL_ASSETS
        ? signals
        : signals.filter((s) => s.asset === selectedAsset),
    [signals, selectedAsset],
  );

  // Collect unique strategies
  const strategies = useMemo(() => {
    const set = new Set<string>();
    for (const s of filtered) set.add(s.strategy_name);
    return Array.from(set).slice(0, STRATEGY_COLORS.length);
  }, [filtered]);

  // Build chart data: one point per signal, grouped by time
  const chartData = useMemo((): ChartDataPoint[] => {
    const cutoff = Date.now() - 48 * 60 * 60 * 1000;
    const recent = filtered.filter(
      (s) => new Date(s.created_at).getTime() > cutoff,
    );

    const points: ChartDataPoint[] = recent
      .sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime())
      .map((s) => {
        const point: ChartDataPoint = {
          time: new Date(s.created_at).toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
          }),
          asset: s.asset,
        };
        point[s.strategy_name] = s.confidence;
        return point;
      });

    return points;
  }, [filtered]);

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <h2 className="text-sm font-semibold text-white">Signal Confidence Trend</h2>
        <select
          value={selectedAsset}
          onChange={(e) => { setSelectedAsset(e.target.value); }}
          className="rounded border border-border bg-background px-2 py-1 text-xs text-gray-300 focus:outline-none focus:ring-1 focus:ring-accent"
          aria-label="Filter by asset"
        >
          {assetOptions.map((asset) => (
            <option key={asset} value={asset}>
              {asset === ALL_ASSETS ? "All Assets" : asset}
            </option>
          ))}
        </select>
      </div>

      {isError && (
        <div className="mb-3 rounded bg-bearish/10 px-3 py-2 text-xs text-bearish">
          Unable to load signal data
        </div>
      )}

      {isLoading ? (
        <div className="h-56 animate-pulse rounded bg-white/5" />
      ) : chartData.length === 0 ? (
        <div className="flex h-56 items-center justify-center text-sm text-gray-500">
          No signals in the last 48 hours
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={224}>
          <LineChart data={chartData} margin={{ top: 4, right: 4, left: -8, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
            <XAxis
              dataKey="time"
              tick={{ fill: "#9ca3af", fontSize: 9 }}
              interval="preserveStartEnd"
            />
            <YAxis
              domain={[0, 100]}
              tick={{ fill: "#9ca3af", fontSize: 10 }}
              tickFormatter={(v) => `${v}%`}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "var(--color-surface, #1f2937)",
                border: "1px solid var(--color-border, #374151)",
                borderRadius: "6px",
                fontSize: "11px",
              }}
              formatter={(value: number, name: string) => [`${value}%`, name]}
            />
            <Legend
              wrapperStyle={{ fontSize: "10px", color: "#9ca3af" }}
              iconType="line"
              iconSize={10}
            />
            {strategies.map((strategy, idx) => (
              <Line
                key={strategy}
                type="monotone"
                dataKey={strategy}
                stroke={STRATEGY_COLORS[idx % STRATEGY_COLORS.length]}
                strokeWidth={1.5}
                dot={{ r: 3 }}
                activeDot={{ r: 5 }}
                connectNulls={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      )}

      <p className="mt-2 text-xs text-gray-600">Last 48h — {filtered.length} signals</p>
    </div>
  );
}
