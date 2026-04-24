/**
 * Benchmark Comparison Panel
 * Compares paper trading vs BTC hold, ETH hold, equal-weight portfolio
 */

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
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
import axios from "axios";

type LookbackDays = 7 | 30 | 90;

interface BenchmarkEntry {
  name: string;
  return_pct: number;
  sharpe_ratio: number | null;
  max_drawdown_pct: number | null;
}

interface BenchmarkComparisonData {
  lookback_days: number;
  entries: BenchmarkEntry[];
  alpha_vs_btc: number;
}

interface BenchmarkRaw {
  period_days: number;
  alpha: number;
  paper_trading: { total_return_pct: number; sharpe: number; max_drawdown_pct: number };
  benchmarks: {
    btc_hold: { total_return_pct: number; sharpe: number; max_drawdown_pct: number };
    eth_hold: { total_return_pct: number; sharpe: number; max_drawdown_pct: number };
    equal_weight: { total_return_pct: number; sharpe: number; max_drawdown_pct: number };
  };
}

async function fetchBenchmarkComparison(lookbackDays: LookbackDays): Promise<BenchmarkComparisonData> {
  const { data: raw } = await axios.get<BenchmarkRaw>("/api/v1/benchmark/comparison", {
    params: { lookback_days: lookbackDays },
  });
  return {
    lookback_days: raw.period_days,
    alpha_vs_btc: raw.alpha,
    entries: [
      { name: "AI System", return_pct: raw.paper_trading.total_return_pct, sharpe_ratio: raw.paper_trading.sharpe, max_drawdown_pct: raw.paper_trading.max_drawdown_pct },
      { name: "BTC Hold", return_pct: raw.benchmarks.btc_hold.total_return_pct, sharpe_ratio: raw.benchmarks.btc_hold.sharpe, max_drawdown_pct: raw.benchmarks.btc_hold.max_drawdown_pct },
      { name: "ETH Hold", return_pct: raw.benchmarks.eth_hold.total_return_pct, sharpe_ratio: raw.benchmarks.eth_hold.sharpe, max_drawdown_pct: raw.benchmarks.eth_hold.max_drawdown_pct },
      { name: "Equal Weight", return_pct: raw.benchmarks.equal_weight.total_return_pct, sharpe_ratio: raw.benchmarks.equal_weight.sharpe, max_drawdown_pct: raw.benchmarks.equal_weight.max_drawdown_pct },
    ],
  };
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: { value: number; name: string }[];
  label?: string;
}

function CustomBarTooltip({ active, payload, label }: CustomTooltipProps) {
  if (!active || !payload?.length) return null;
  const value = payload[0]?.value ?? 0;
  return (
    <div className="rounded border border-border bg-surface px-3 py-2 text-xs shadow-xl">
      <p className="font-medium text-white">{label}</p>
      <p className={value >= 0 ? "text-bullish" : "text-bearish"}>
        Return: {value >= 0 ? "+" : ""}
        {value.toFixed(2)}%
      </p>
    </div>
  );
}

function SkeletonRow() {
  return (
    <div className="flex items-center gap-3 py-2">
      <div className="h-3 w-24 animate-pulse rounded bg-white/5" />
      <div className="h-3 flex-1 animate-pulse rounded bg-white/5" />
      <div className="h-3 w-16 animate-pulse rounded bg-white/5" />
    </div>
  );
}

const LOOKBACK_OPTIONS: { label: string; value: LookbackDays }[] = [
  { label: "7d", value: 7 },
  { label: "30d", value: 30 },
  { label: "90d", value: 90 },
];

export function BenchmarkPanel() {
  const [lookback, setLookback] = useState<LookbackDays>(30);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["benchmark-comparison", lookback],
    queryFn: () => fetchBenchmarkComparison(lookback),
    retry: false,
  });

  const chartData =
    data?.entries.map((e) => ({
      name: e.name,
      return: parseFloat(e.return_pct.toFixed(2)),
    })) ?? [];

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-white">Benchmark Comparison</h2>
        <div className="flex gap-1">
          {LOOKBACK_OPTIONS.map(({ label, value }) => (
            <button
              key={value}
              type="button"
              onClick={() => setLookback(value)}
              className={`rounded px-2 py-0.5 text-xs font-medium transition-colors ${
                lookback === value
                  ? "bg-accent text-white"
                  : "border border-border text-gray-400 hover:text-white"
              }`}
              aria-pressed={lookback === value}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {isError && (
        <div className="mb-3 rounded bg-bearish/10 px-3 py-2 text-xs text-bearish">
          Unable to load benchmark data
        </div>
      )}

      {isLoading ? (
        <div className="space-y-2">
          <div className="h-48 animate-pulse rounded bg-white/5" />
          {[...Array(4)].map((_, i) => (
            <SkeletonRow key={i} />
          ))}
        </div>
      ) : (
        <>
          {data?.alpha_vs_btc !== undefined && (
            <div className="mb-4 flex items-center gap-2 rounded bg-accent/10 px-3 py-2">
              <span className="text-xs text-gray-400">Alpha vs BTC Hold:</span>
              <span
                className={`text-sm font-bold ${
                  data.alpha_vs_btc >= 0 ? "text-bullish" : "text-bearish"
                }`}
              >
                {data.alpha_vs_btc >= 0 ? "+" : ""}
                {data.alpha_vs_btc.toFixed(2)}%
              </span>
            </div>
          )}

          <div className="mb-4 h-48">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} margin={{ top: 4, right: 4, left: -8, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                <XAxis dataKey="name" tick={{ fill: "#9ca3af", fontSize: 10 }} />
                <YAxis tick={{ fill: "#9ca3af", fontSize: 10 }} tickFormatter={(v) => `${v}%`} />
                <Tooltip content={<CustomBarTooltip />} />
                <Bar dataKey="return" radius={[3, 3, 0, 0]}>
                  {chartData.map((entry, index) => (
                    <Cell
                      key={`cell-${index}`}
                      fill={entry.return >= 0 ? "rgb(var(--color-bullish, 34 197 94))" : "rgb(var(--color-bearish, 239 68 68))"}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Summary table */}
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border/50">
                  <th className="pb-1.5 text-left font-medium text-gray-500">Strategy</th>
                  <th className="pb-1.5 text-right font-medium text-gray-500">Return</th>
                  <th className="pb-1.5 text-right font-medium text-gray-500">Sharpe</th>
                  <th className="pb-1.5 text-right font-medium text-gray-500">Max DD</th>
                </tr>
              </thead>
              <tbody>
                {data?.entries.map((entry) => (
                  <tr key={entry.name} className="border-b border-border/20">
                    <td className="py-1.5 pr-2 font-medium text-gray-300">{entry.name}</td>
                    <td
                      className={`py-1.5 text-right ${
                        entry.return_pct >= 0 ? "text-bullish" : "text-bearish"
                      }`}
                    >
                      {entry.return_pct >= 0 ? "+" : ""}
                      {entry.return_pct.toFixed(2)}%
                    </td>
                    <td className="py-1.5 text-right text-gray-300">
                      {entry.sharpe_ratio != null ? entry.sharpe_ratio.toFixed(2) : "—"}
                    </td>
                    <td className="py-1.5 text-right text-bearish">
                      {entry.max_drawdown_pct != null
                        ? `${entry.max_drawdown_pct.toFixed(1)}%`
                        : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
