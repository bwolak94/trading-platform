/**
 * B5: Walk-Forward Optimization UI
 *
 * UI for backend walk-forward endpoint: pick symbol, parameter ranges, IS/OOS split.
 * Display out-of-sample equity curve.
 */

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

interface WFRequest {
  symbol: string;
  strategy: string;
  is_pct: number;
  oos_pct: number;
  timeframe: string;
}

interface WFResult {
  oos_sharpe: number;
  oos_win_rate: number;
  oos_max_drawdown: number;
  equity_curve: { t: number; equity: number }[];
}

async function runWalkForward(req: WFRequest): Promise<WFResult> {
  const resp = await fetch("/api/v1/backtest/walk-forward", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!resp.ok) throw new Error("Walk-forward request failed");
  return resp.json();
}

export function WalkForwardOptimizationUI() {
  const [symbol, setSymbol] = useState("BTC/USDT");
  const [strategy, setStrategy] = useState("trend_following");
  const [timeframe, setTimeframe] = useState("4h");
  const [isPct, setIsPct] = useState(70);

  const mutation = useMutation({
    mutationFn: runWalkForward,
  });

  const handleRun = () => {
    mutation.mutate({ symbol, strategy, timeframe, is_pct: isPct, oos_pct: 100 - isPct });
  };

  const result = mutation.data;

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h3 className="mb-3 text-sm font-semibold text-gray-200">Walk-Forward Optimization</h3>

      <div className="grid grid-cols-2 gap-3 mb-4">
        <div>
          <label className="mb-1 block text-xs text-gray-500" htmlFor="wf-symbol">Symbol</label>
          <select
            id="wf-symbol"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            className="w-full rounded border border-border bg-background px-2 py-1.5 text-xs text-gray-300"
          >
            <option value="BTC/USDT">BTC/USDT</option>
            <option value="ETH/USDT">ETH/USDT</option>
            <option value="SOL/USDT">SOL/USDT</option>
          </select>
        </div>
        <div>
          <label className="mb-1 block text-xs text-gray-500" htmlFor="wf-strategy">Strategy</label>
          <select
            id="wf-strategy"
            value={strategy}
            onChange={(e) => setStrategy(e.target.value)}
            className="w-full rounded border border-border bg-background px-2 py-1.5 text-xs text-gray-300"
          >
            <option value="trend_following">Trend Following</option>
            <option value="mean_reversion">Mean Reversion</option>
            <option value="smc">SMC</option>
            <option value="volume_breakout">Volume Breakout</option>
          </select>
        </div>
        <div>
          <label className="mb-1 block text-xs text-gray-500" htmlFor="wf-tf">Timeframe</label>
          <select
            id="wf-tf"
            value={timeframe}
            onChange={(e) => setTimeframe(e.target.value)}
            className="w-full rounded border border-border bg-background px-2 py-1.5 text-xs text-gray-300"
          >
            <option value="1h">1h</option>
            <option value="4h">4h</option>
            <option value="1D">1D</option>
          </select>
        </div>
        <div>
          <label className="mb-1 block text-xs text-gray-500" htmlFor="wf-is">
            In-Sample: {isPct}% / OOS: {100 - isPct}%
          </label>
          <input
            id="wf-is"
            type="range"
            min={50}
            max={80}
            value={isPct}
            onChange={(e) => setIsPct(Number(e.target.value))}
            className="w-full accent-accent"
          />
        </div>
      </div>

      <button
        type="button"
        onClick={handleRun}
        disabled={mutation.isPending}
        className="w-full rounded border border-accent bg-accent/10 px-3 py-2 text-xs font-semibold text-accent transition-colors hover:bg-accent/20 disabled:opacity-50"
        aria-label="Run walk-forward backtest"
      >
        {mutation.isPending ? "Running…" : "Run Walk-Forward"}
      </button>

      {mutation.isError && (
        <p className="mt-2 text-xs text-bearish">Failed to run backtest. Check server logs.</p>
      )}

      {result && (
        <div className="mt-4">
          <div className="mb-3 grid grid-cols-3 gap-2 text-center text-xs">
            <div className="rounded border border-border bg-background/60 p-2">
              <div className="text-gray-500">OOS Sharpe</div>
              <div className={`font-bold text-sm ${result.oos_sharpe >= 1 ? "text-bullish" : result.oos_sharpe >= 0 ? "text-amber-400" : "text-bearish"}`}>
                {result.oos_sharpe.toFixed(2)}
              </div>
            </div>
            <div className="rounded border border-border bg-background/60 p-2">
              <div className="text-gray-500">OOS Win%</div>
              <div className="font-bold text-sm text-gray-200">{(result.oos_win_rate * 100).toFixed(1)}%</div>
            </div>
            <div className="rounded border border-border bg-background/60 p-2">
              <div className="text-gray-500">OOS MDD</div>
              <div className="font-bold text-sm text-bearish">-{result.oos_max_drawdown.toFixed(1)}%</div>
            </div>
          </div>

          {result.equity_curve.length > 0 && (
            <ResponsiveContainer width="100%" height={140}>
              <AreaChart data={result.equity_curve} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey="t" tick={false} />
                <YAxis tick={{ fontSize: 10, fill: "#94a3b8" }} />
                <Tooltip
                  contentStyle={{ background: "#1e293b", border: "1px solid #334155", fontSize: 11 }}
                  formatter={(v: number) => [`$${v.toFixed(0)}`, "Equity"]}
                />
                <Area type="monotone" dataKey="equity" stroke="#22d3ee" fill="#22d3ee20" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>
      )}
    </div>
  );
}
