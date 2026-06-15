/**
 * AnnotatedBenchmarkPanel
 * Performance vs BTC buy-hold benchmark with regime shading overlay.
 * Uses recharts for the chart. Fetches equity and regime history.
 */

import { useQuery } from "@tanstack/react-query";
import { useCallback, useMemo } from "react";
import axios from "axios";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

// --------------- Types ---------------

interface EquityPoint {
  timestamp: string;
  equity_pct: number;
  btc_pct: number;
}

interface RegimePeriod {
  start: string;
  end: string;
  regime: string;
}

interface PerformanceData {
  equity_curve: EquityPoint[];
  regime_history: RegimePeriod[];
  alpha_by_regime: AlphaRecord[];
}

interface AlphaRecord {
  regime: string;
  your_return_pct: number;
  btc_return_pct: number;
  alpha_pct: number;
}

// --------------- Constants ---------------

const REGIME_COLORS: Record<string, string> = {
  TREND_BULL: "rgba(34,197,94,0.15)",
  TREND_BEAR: "rgba(239,68,68,0.15)",
  CONSOLIDATION: "rgba(107,114,128,0.15)",
  HIGH_VOL_CHOPPY: "rgba(245,158,11,0.15)",
};

const REGIME_LABELS: Record<string, string> = {
  TREND_BULL: "Bull Trend",
  TREND_BEAR: "Bear Trend",
  CONSOLIDATION: "Consolidation",
  HIGH_VOL_CHOPPY: "High Vol",
};

// --------------- Fetch helpers ---------------

async function fetchPerformance(): Promise<PerformanceData> {
  const { data } = await axios.get<PerformanceData>(
    "/api/v1/simulation/performance",
  );
  return data;
}

// --------------- Helpers ---------------

function formatDate(ts: string): string {
  return new Date(ts).toLocaleDateString([], {
    month: "short",
    day: "numeric",
  });
}

function alphaColor(alpha: number): string {
  if (alpha > 0) return "text-green-400";
  if (alpha < 0) return "text-red-400";
  return "text-gray-400";
}

// --------------- Skeleton ---------------

function BenchmarkSkeleton() {
  return (
    <div className="space-y-3" aria-busy="true" aria-label="Loading benchmark data">
      <div className="h-48 w-full animate-pulse rounded bg-white/5" />
      <div className="grid grid-cols-2 gap-2">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="h-10 animate-pulse rounded bg-white/5" />
        ))}
      </div>
    </div>
  );
}

// --------------- Custom tooltip ---------------

interface TooltipPayloadEntry {
  name: string;
  value: number;
  color: string;
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: TooltipPayloadEntry[];
  label?: string;
}

function CustomTooltip({ active, payload, label }: CustomTooltipProps) {
  if (!active || !payload || payload.length === 0) return null;
  return (
    <div className="rounded border border-border bg-gray-900 px-3 py-2 text-xs shadow-lg">
      <p className="mb-1 text-gray-400">{label}</p>
      {payload.map((entry) => (
        <p key={entry.name} style={{ color: entry.color }}>
          {entry.name}:{" "}
          <span className="font-mono font-bold">
            {entry.value >= 0 ? "+" : ""}
            {entry.value.toFixed(2)}%
          </span>
        </p>
      ))}
    </div>
  );
}

// --------------- Main Component ---------------

export default function AnnotatedBenchmarkPanel() {
  const { data, isLoading, isError, refetch } = useQuery<PerformanceData>({
    queryKey: ["annotated-benchmark"],
    queryFn: fetchPerformance,
    refetchInterval: 5 * 60_000,
    retry: 2,
  });

  const handleRetry = useCallback(() => {
    void refetch();
  }, [refetch]);

  // Build regime reference areas mapped to chart x-domain (timestamps as strings)
  const regimeAreas = useMemo(() => {
    if (!data?.regime_history) return [];
    return data.regime_history.map((rp, i) => ({
      key: `${rp.regime}-${i}`,
      x1: formatDate(rp.start),
      x2: formatDate(rp.end),
      fill: REGIME_COLORS[rp.regime] ?? "rgba(107,114,128,0.1)",
      label: REGIME_LABELS[rp.regime] ?? rp.regime,
    }));
  }, [data]);

  const chartData = useMemo(
    () =>
      data?.equity_curve.map((pt) => ({
        ...pt,
        date: formatDate(pt.timestamp),
      })) ?? [],
    [data],
  );

  return (
    <div className="rounded-lg border border-border bg-gray-900 p-4">
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-white">
            Performance vs Benchmark
          </h2>
          <p className="text-[10px] text-gray-500">
            Your equity (blue) vs BTC buy-hold (orange) · regime shading
          </p>
        </div>
      </div>

      {/* Error */}
      {isError && (
        <div className="mb-3 flex items-center justify-between rounded bg-red-500/10 px-3 py-2">
          <span className="text-xs text-red-400">
            Failed to load performance data
          </span>
          <button
            type="button"
            onClick={handleRetry}
            className="text-xs text-red-400 underline hover:text-red-300"
            aria-label="Retry loading performance data"
          >
            Retry
          </button>
        </div>
      )}

      {isLoading && <BenchmarkSkeleton />}

      {data && (
        <div className="space-y-4">
          {/* Legend for regimes */}
          <div className="flex flex-wrap gap-2">
            {Object.entries(REGIME_LABELS).map(([key, label]) => (
              <div key={key} className="flex items-center gap-1">
                <div
                  className="h-3 w-6 rounded-sm"
                  style={{ background: REGIME_COLORS[key] ?? "transparent", border: "1px solid rgba(255,255,255,0.1)" }}
                  aria-hidden="true"
                />
                <span className="text-[10px] text-gray-500">{label}</span>
              </div>
            ))}
          </div>

          {/* Chart */}
          {chartData.length > 0 ? (
            <div className="h-48">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData} margin={{ top: 4, right: 8, left: 0, bottom: 4 }}>
                  <CartesianGrid
                    strokeDasharray="3 3"
                    stroke="rgba(255,255,255,0.05)"
                  />
                  {/* Regime shading */}
                  {regimeAreas.map((area) => (
                    <ReferenceArea
                      key={area.key}
                      x1={area.x1}
                      x2={area.x2}
                      fill={area.fill}
                      strokeOpacity={0}
                    />
                  ))}
                  <XAxis
                    dataKey="date"
                    tick={{ fill: "#6b7280", fontSize: 10 }}
                    tickLine={false}
                    axisLine={false}
                    interval="preserveStartEnd"
                  />
                  <YAxis
                    tick={{ fill: "#6b7280", fontSize: 10 }}
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={(v: number) => `${v > 0 ? "+" : ""}${v.toFixed(0)}%`}
                    width={46}
                  />
                  <Tooltip content={<CustomTooltip />} />
                  <Legend
                    wrapperStyle={{ fontSize: "11px", color: "#9ca3af" }}
                  />
                  <Line
                    type="monotone"
                    dataKey="equity_pct"
                    name="Your Equity"
                    stroke="#3b82f6"
                    strokeWidth={2}
                    dot={false}
                    activeDot={{ r: 3 }}
                  />
                  <Line
                    type="monotone"
                    dataKey="btc_pct"
                    name="BTC Buy-Hold"
                    stroke="#f97316"
                    strokeWidth={2}
                    dot={false}
                    activeDot={{ r: 3 }}
                    strokeDasharray="4 2"
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="flex h-48 items-center justify-center rounded border border-gray-800 text-xs text-gray-500">
              No equity data available
            </div>
          )}

          {/* Alpha by regime table */}
          {data.alpha_by_regime && data.alpha_by_regime.length > 0 && (
            <div>
              <p className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-gray-500">
                Alpha by Regime
              </p>
              <div className="space-y-1.5">
                {data.alpha_by_regime.map((row) => (
                  <div
                    key={row.regime}
                    className="flex items-center justify-between rounded bg-gray-800/60 px-3 py-1.5 text-xs"
                  >
                    <div className="flex items-center gap-2">
                      <div
                        className="h-2 w-2 rounded-full"
                        style={{
                          background:
                            REGIME_COLORS[row.regime]?.replace("0.15", "1") ??
                            "#6b7280",
                        }}
                        aria-hidden="true"
                      />
                      <span className="text-gray-300">
                        {REGIME_LABELS[row.regime] ?? row.regime}
                      </span>
                    </div>
                    <div className="flex items-center gap-3 font-mono">
                      <span className="text-blue-400">
                        You:{" "}
                        {row.your_return_pct >= 0 ? "+" : ""}
                        {row.your_return_pct.toFixed(1)}%
                      </span>
                      <span className="text-orange-400">
                        BTC:{" "}
                        {row.btc_return_pct >= 0 ? "+" : ""}
                        {row.btc_return_pct.toFixed(1)}%
                      </span>
                      <span
                        className={`font-bold ${alphaColor(row.alpha_pct)}`}
                      >
                        α{row.alpha_pct >= 0 ? "+" : ""}
                        {row.alpha_pct.toFixed(1)}%
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
