/**
 * Smart Stop Loss Optimizer
 * Queries the backend to find the ATR multiplier that maximises win rate
 * while keeping max drawdown below a user-set threshold.
 */

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import axios from "axios";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ReferenceLine, ResponsiveContainer, Cell } from "recharts";
import { useDebounce } from "../hooks/useDebounce";

interface SLResult {
  multiplier: number;
  win_rate: number;
  max_drawdown_pct: number;
  total_trades: number;
  feasible: boolean;
}

interface SLResponse {
  symbol: string;
  timeframe: string;
  candles_analyzed: number;
  recommendation: SLResult | null;
  all_results: SLResult[];
}

const TIMEFRAMES = ["15m", "1h", "4h", "1d"];

async function fetchOptimizer(symbol: string, tf: string, maxDD: number): Promise<SLResponse> {
  const { data } = await axios.get(
    `/api/v1/analysis/stop-loss-optimizer/${symbol}`,
    { params: { timeframe: tf, max_drawdown_pct: maxDD } },
  );
  return data as SLResponse;
}

export function SmartStopLossOptimizer() {
  const [symbol, setSymbol] = useState("BTCUSDT");
  const [timeframe, setTimeframe] = useState("1h");
  const [maxDD, setMaxDD] = useState("5");

  const debouncedSymbol = useDebounce(symbol, 500);
  const debouncedMaxDD = useDebounce(parseFloat(maxDD) || 5, 500);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["sl-optimizer", debouncedSymbol, timeframe, debouncedMaxDD],
    queryFn: () => fetchOptimizer(debouncedSymbol, timeframe, debouncedMaxDD),
    staleTime: 120_000,
    retry: false,
    enabled: debouncedMaxDD > 0,
    placeholderData: (prev) => prev,
  });

  const rec = data?.recommendation;

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-3 text-sm font-semibold text-white">Smart Stop Loss Optimizer</h2>
      <p className="mb-3 text-[10px] text-gray-500">
        Scans ATR multipliers 0.5–3.0 against historical candles. Recommends the highest-win-rate
        multiplier that keeps max drawdown below your threshold.
      </p>

      {/* Controls */}
      <div className="mb-4 grid grid-cols-3 gap-2">
        <div>
          <label className="mb-0.5 block text-[10px] text-gray-500">Symbol</label>
          <input
            type="text"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value.toUpperCase())}
            className="w-full rounded border border-border bg-background px-2 py-1.5 font-mono text-xs text-gray-300 focus:outline-none focus:ring-1 focus:ring-accent"
            aria-label="Symbol"
          />
        </div>
        <div>
          <label className="mb-0.5 block text-[10px] text-gray-500">Timeframe</label>
          <select
            value={timeframe}
            onChange={(e) => setTimeframe(e.target.value)}
            className="w-full rounded border border-border bg-background px-2 py-1.5 text-xs text-gray-300 focus:outline-none"
            aria-label="Timeframe"
          >
            {TIMEFRAMES.map((tf) => <option key={tf} value={tf}>{tf}</option>)}
          </select>
        </div>
        <div>
          <label className="mb-0.5 block text-[10px] text-gray-500">Max DD %</label>
          <input
            type="number"
            value={maxDD}
            onChange={(e) => setMaxDD(e.target.value)}
            min={1}
            max={50}
            step={0.5}
            className="w-full rounded border border-border bg-background px-2 py-1.5 font-mono text-xs text-gray-300 focus:outline-none focus:ring-1 focus:ring-accent"
            aria-label="Max drawdown %"
          />
        </div>
      </div>

      {/* Recommendation */}
      {rec && (
        <div className="mb-4 rounded border border-bullish/30 bg-bullish/10 px-4 py-3">
          <p className="mb-1 text-[10px] text-gray-400">Recommended ATR Multiplier</p>
          <p className="text-2xl font-bold text-bullish font-mono">{rec.multiplier}×</p>
          <div className="mt-1 flex gap-4 text-[10px] text-gray-400">
            <span>Win rate: <span className="text-white font-mono">{rec.win_rate}%</span></span>
            <span>Max DD: <span className="text-bearish font-mono">{rec.max_drawdown_pct}%</span></span>
            <span>Trades: <span className="text-white font-mono">{rec.total_trades}</span></span>
          </div>
        </div>
      )}

      {isError && <p className="mb-3 text-xs text-bearish">Failed to load optimizer data.</p>}

      {/* Chart */}
      {isLoading ? (
        <div className="h-32 animate-pulse rounded bg-white/5" />
      ) : data?.all_results && data.all_results.length > 0 ? (
        <ResponsiveContainer width="100%" height={130}>
          <BarChart data={data.all_results} margin={{ top: 2, right: 4, left: -20, bottom: 0 }}>
            <XAxis dataKey="multiplier" tick={{ fontSize: 8, fill: "#6b7280" }} tickFormatter={(v) => `${v}×`} />
            <YAxis tick={{ fontSize: 8, fill: "#6b7280" }} tickFormatter={(v) => `${v}%`} />
            <Tooltip
              contentStyle={{ background: "#1a1a2e", border: "1px solid #374151", fontSize: 10 }}
              formatter={(v: number, name: string) => [`${v}%`, name === "win_rate" ? "Win Rate" : "Max DD"]}
            />
            {rec && <ReferenceLine x={rec.multiplier} stroke="#22c55e" strokeDasharray="3 3" />}
            <Bar dataKey="win_rate" name="win_rate" radius={[2, 2, 0, 0]}>
              {data.all_results.map((r, i) => (
                <Cell key={i} fill={r.feasible ? "#22c55e" : "#374151"} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      ) : null}

      {data && (
        <p className="mt-2 text-[9px] text-gray-600">
          {data.candles_analyzed} candles analyzed · {data.symbol} {data.timeframe}
        </p>
      )}
    </div>
  );
}
