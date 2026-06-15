/**
 * Strategy A/B Backtester
 * Side-by-side comparison of two strategy variants over historical data.
 * Shows equity curves, Sharpe ratio, win rate diff and a winner badge.
 */

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import axios from "axios";
import { LineChart, Line, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer } from "recharts";
import { useDebounce } from "../hooks/useDebounce";

interface VariantResult {
  label: string;
  params: { atr_mult: number; rr_ratio: number; confidence_threshold: number };
  total_trades: number;
  wins: number;
  win_rate_pct: number;
  net_pnl: number;
  net_pnl_pct: number;
  max_drawdown_pct: number;
  sharpe: number;
  equity_curve: { ts: number; equity: number }[];
}

interface ABResponse {
  symbol: string;
  timeframe: string;
  candles_analyzed: number;
  initial_capital: number;
  variant_a: VariantResult;
  variant_b: VariantResult;
  winner: "A" | "B";
  sharpe_diff: number;
}

const TIMEFRAMES = ["15m", "1h", "4h", "1d"];

async function fetchAB(
  symbol: string,
  tf: string,
  multA: number,
  multB: number,
  rrA: number,
  rrB: number,
): Promise<ABResponse> {
  const { data } = await axios.get(`/api/v1/backtest/ab-compare/${symbol}`, {
    params: { timeframe: tf, atr_mult_a: multA, atr_mult_b: multB, rr_ratio_a: rrA, rr_ratio_b: rrB },
  });
  return data as ABResponse;
}

function MetricRow({ label, a, b, winner }: { label: string; a: string; b: string; winner: "A" | "B" | null }) {
  return (
    <div className="flex items-center text-[10px]">
      <span className="w-32 text-gray-500">{label}</span>
      <span className={`flex-1 text-center font-mono ${winner === "A" ? "text-bullish font-bold" : "text-gray-300"}`}>{a}</span>
      <span className={`flex-1 text-center font-mono ${winner === "B" ? "text-bullish font-bold" : "text-gray-300"}`}>{b}</span>
    </div>
  );
}

export function StrategyABBacktester() {
  const [symbol, setSymbol] = useState("BTCUSDT");
  const [tf, setTf] = useState("1h");
  const [multA, setMultA] = useState("1.5");
  const [multB, setMultB] = useState("2.5");
  const [rrA, setRrA] = useState("1.5");
  const [rrB, setRrB] = useState("2.0");

  const dSym = useDebounce(symbol, 500);
  const dMultA = useDebounce(parseFloat(multA) || 1.5, 500);
  const dMultB = useDebounce(parseFloat(multB) || 2.5, 500);
  const dRrA = useDebounce(parseFloat(rrA) || 1.5, 500);
  const dRrB = useDebounce(parseFloat(rrB) || 2.0, 500);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["ab-backtest", dSym, tf, dMultA, dMultB, dRrA, dRrB],
    queryFn: () => fetchAB(dSym, tf, dMultA, dMultB, dRrA, dRrB),
    staleTime: 300_000,
    retry: false,
    placeholderData: (prev) => prev,
  });

  // Merge equity curves for comparison chart
  const chartData = data
    ? (() => {
        const curveA = data.variant_a.equity_curve;
        const curveB = data.variant_b.equity_curve;
        const len = Math.min(curveA.length, curveB.length);
        return Array.from({ length: len }, (_, i) => ({
          i,
          A: curveA[i]?.equity ?? data.initial_capital,
          B: curveB[i]?.equity ?? data.initial_capital,
        }));
      })()
    : [];

  const inputCls = "w-full rounded border border-border bg-background px-2 py-1.5 font-mono text-xs text-gray-300 focus:outline-none focus:ring-1 focus:ring-accent";

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-white">Strategy A/B Backtester</h2>
        {data && (
          <span className={`rounded px-2 py-0.5 text-xs font-bold ${data.winner === "A" ? "bg-bullish/20 text-bullish" : "bg-accent/20 text-accent"}`}>
            Variant {data.winner} wins (Δ Sharpe {data.sharpe_diff})
          </span>
        )}
      </div>
      <p className="mb-3 text-[10px] text-gray-500">
        Compare two ATR-based strategy configs head-to-head. Sharpe ratio determines the winner.
      </p>

      {/* Controls */}
      <div className="mb-4 grid grid-cols-2 gap-3">
        <div>
          <p className="mb-1.5 text-[10px] font-semibold text-accent">Variant A</p>
          <div className="space-y-1.5">
            <div><label className="text-[9px] text-gray-500">ATR Mult</label><input type="number" value={multA} onChange={(e) => { setMultA(e.target.value); }} step={0.1} className={inputCls} /></div>
            <div><label className="text-[9px] text-gray-500">R/R Ratio</label><input type="number" value={rrA} onChange={(e) => { setRrA(e.target.value); }} step={0.1} className={inputCls} /></div>
          </div>
        </div>
        <div>
          <p className="mb-1.5 text-[10px] font-semibold text-purple-400">Variant B</p>
          <div className="space-y-1.5">
            <div><label className="text-[9px] text-gray-500">ATR Mult</label><input type="number" value={multB} onChange={(e) => { setMultB(e.target.value); }} step={0.1} className={inputCls} /></div>
            <div><label className="text-[9px] text-gray-500">R/R Ratio</label><input type="number" value={rrB} onChange={(e) => { setRrB(e.target.value); }} step={0.1} className={inputCls} /></div>
          </div>
        </div>
      </div>

      {/* Symbol & TF */}
      <div className="mb-4 flex gap-2">
        <input
          type="text"
          value={symbol}
          onChange={(e) => { setSymbol(e.target.value.toUpperCase()); }}
          placeholder="BTCUSDT"
          className="flex-1 rounded border border-border bg-background px-2 py-1.5 font-mono text-xs text-gray-300 focus:outline-none focus:ring-1 focus:ring-accent"
          aria-label="Symbol"
        />
        <select
          value={tf}
          onChange={(e) => { setTf(e.target.value); }}
          className="rounded border border-border bg-background px-2 py-1 text-xs text-gray-300 focus:outline-none"
          aria-label="Timeframe"
        >
          {TIMEFRAMES.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
      </div>

      {isError && <p className="mb-3 text-xs text-bearish">Backtest failed. Check symbol format.</p>}

      {isLoading ? (
        <div className="h-40 animate-pulse rounded bg-white/5" />
      ) : data ? (
        <>
          {/* Metrics table */}
          <div className="mb-4 space-y-1 rounded border border-border bg-background px-3 py-2">
            <div className="mb-1 flex text-[9px] font-semibold">
              <span className="w-32" />
              <span className="flex-1 text-center text-accent">Variant A</span>
              <span className="flex-1 text-center text-purple-400">Variant B</span>
            </div>
            <MetricRow label="Sharpe" a={data.variant_a.sharpe.toFixed(3)} b={data.variant_b.sharpe.toFixed(3)} winner={data.winner} />
            <MetricRow label="Win Rate" a={`${data.variant_a.win_rate_pct}%`} b={`${data.variant_b.win_rate_pct}%`} winner={data.variant_a.win_rate_pct >= data.variant_b.win_rate_pct ? "A" : "B"} />
            <MetricRow label="Net P&L" a={`${data.variant_a.net_pnl_pct.toFixed(1)}%`} b={`${data.variant_b.net_pnl_pct.toFixed(1)}%`} winner={data.variant_a.net_pnl >= data.variant_b.net_pnl ? "A" : "B"} />
            <MetricRow label="Max DD" a={`${data.variant_a.max_drawdown_pct.toFixed(1)}%`} b={`${data.variant_b.max_drawdown_pct.toFixed(1)}%`} winner={data.variant_a.max_drawdown_pct <= data.variant_b.max_drawdown_pct ? "A" : "B"} />
            <MetricRow label="Trades" a={String(data.variant_a.total_trades)} b={String(data.variant_b.total_trades)} winner={null} />
          </div>

          {/* Equity curve chart */}
          {chartData.length > 2 && (
            <ResponsiveContainer width="100%" height={140}>
              <LineChart data={chartData} margin={{ top: 2, right: 4, left: -20, bottom: 0 }}>
                <XAxis dataKey="i" hide />
                <YAxis tick={{ fontSize: 8, fill: "#6b7280" }} tickFormatter={(v) => `$${(v / 1000).toFixed(0)}K`} />
                <Tooltip
                  contentStyle={{ background: "#1a1a2e", border: "1px solid #374151", fontSize: 10 }}
                  formatter={(v: number) => [`$${v.toLocaleString()}`, ""]}
                />
                <Legend wrapperStyle={{ fontSize: 9 }} />
                <Line type="monotone" dataKey="A" stroke="#6366f1" strokeWidth={1.5} dot={false} name="Variant A" />
                <Line type="monotone" dataKey="B" stroke="#a855f7" strokeWidth={1.5} dot={false} name="Variant B" />
              </LineChart>
            </ResponsiveContainer>
          )}
          <p className="mt-2 text-[9px] text-gray-600">
            {data.candles_analyzed} candles · {data.symbol} {data.timeframe} · $10K initial
          </p>
        </>
      ) : null}
    </div>
  );
}
