/**
 * Kelly Criterion Position Sizer
 * Pulls live win-rate + avg win/loss from simulation performance,
 * then computes Full Kelly, Half Kelly, and Quarter Kelly position sizes.
 */

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { fetchSimulationPerformance } from "../../api/client";
import { fmtPct, colorClass } from "../../lib/format";

interface KellyResult {
  full: number;
  half: number;
  quarter: number;
  expectancy: number;
  edge: number;
}

function calcKelly(winRate: number, avgWinPct: number, avgLossPct: number): KellyResult {
  const w = winRate / 100;
  const b = Math.abs(avgWinPct) / Math.max(Math.abs(avgLossPct), 0.01);
  // Kelly formula: f* = W - (1-W)/b
  const full = Math.max(0, w - (1 - w) / b) * 100;
  const expectancy = w * Math.abs(avgWinPct) - (1 - w) * Math.abs(avgLossPct);
  const edge = full;
  return {
    full: parseFloat(full.toFixed(2)),
    half: parseFloat((full / 2).toFixed(2)),
    quarter: parseFloat((full / 4).toFixed(2)),
    expectancy: parseFloat(expectancy.toFixed(2)),
    edge: parseFloat(edge.toFixed(2)),
  };
}

function KellyBar({ label, pct, color }: { label: string; pct: number; color: string }) {
  return (
    <div>
      <div className="mb-1 flex justify-between text-xs">
        <span className="text-gray-400">{label}</span>
        <span className={`font-mono font-semibold ${color}`}>{pct.toFixed(1)}%</span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-background">
        <div
          className={`h-full rounded-full transition-all duration-500 ${color.replace("text-", "bg-")}`}
          style={{ width: `${Math.min(pct * 4, 100)}%` }}
          role="progressbar"
          aria-valuenow={pct}
          aria-valuemin={0}
          aria-valuemax={25}
        />
      </div>
    </div>
  );
}

export function KellyCriterionPanel() {
  const [capital, setCapital] = useState(10_000);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["sim-performance-kelly"],
    queryFn: fetchSimulationPerformance,
    refetchInterval: 60_000,
    retry: false,
  });

  const winRate = data?.win_rate ?? 50;
  const avgWin = data?.avg_win_pct ?? 2;
  const avgLoss = data?.avg_loss_pct ?? 1;
  const kelly = calcKelly(winRate, avgWin, avgLoss);

  const kellyTiers = [
    { label: "Full Kelly", pct: kelly.full, color: "text-bullish" },
    { label: "Half Kelly (recommended)", pct: kelly.half, color: "text-blue-400" },
    { label: "Quarter Kelly (conservative)", pct: kelly.quarter, color: "text-amber-400" },
  ];

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-4 text-sm font-semibold text-white">Kelly Criterion Position Sizer</h2>

      {isError && (
        <p className="mb-3 rounded bg-bearish/10 px-3 py-2 text-xs text-bearish">
          Using default 50% win-rate — connect simulation for live values.
        </p>
      )}

      {/* Live performance inputs */}
      <div className="mb-4 grid grid-cols-3 gap-3 text-xs">
        {[
          { label: "Win Rate", value: fmtPct(winRate, { decimals: 1 }), color: colorClass(winRate - 50) },
          { label: "Avg Win", value: fmtPct(avgWin, { showSign: true }), color: "text-bullish" },
          { label: "Avg Loss", value: fmtPct(-Math.abs(avgLoss), { showSign: true }), color: "text-bearish" },
        ].map(({ label, value, color }) => (
          <div key={label} className="rounded bg-background px-2 py-2 text-center">
            <p className="text-gray-500">{label}</p>
            <p className={`font-mono font-bold ${color}`}>{isLoading ? "…" : value}</p>
          </div>
        ))}
      </div>

      {/* Capital input */}
      <div className="mb-4">
        <label htmlFor="kelly-capital" className="mb-1 block text-xs text-gray-500">
          Account Capital ($)
        </label>
        <input
          id="kelly-capital"
          type="number"
          value={capital}
          onChange={(e) => { setCapital(Math.max(1, Number(e.target.value))); }}
          className="w-full rounded border border-border bg-background px-2 py-1.5 font-mono text-sm text-white focus:outline-none focus:ring-1 focus:ring-accent"
          min={1}
          step={1000}
          aria-label="Account capital in dollars"
        />
      </div>

      {/* Kelly bars */}
      <div className="mb-4 space-y-3">
        {kellyTiers.map((tier) => (
          <KellyBar key={tier.label} {...tier} />
        ))}
      </div>

      {/* Dollar amounts */}
      <div className="grid grid-cols-3 gap-2 text-xs">
        {kellyTiers.map((tier) => (
          <div key={tier.label} className="rounded bg-background px-2 py-2 text-center">
            <p className="truncate text-gray-500">{tier.label.split(" ")[0]} Kelly</p>
            <p className={`font-mono font-semibold ${tier.color}`}>
              ${((capital * tier.pct) / 100).toLocaleString(undefined, { maximumFractionDigits: 0 })}
            </p>
          </div>
        ))}
      </div>

      {/* Expectancy */}
      <div className="mt-4 flex items-center justify-between rounded bg-background px-3 py-2 text-xs">
        <span className="text-gray-500">Expected R per trade</span>
        <span className={`font-mono font-bold ${colorClass(kelly.expectancy)}`}>
          {kelly.expectancy >= 0 ? "+" : ""}
          {fmtPct(kelly.expectancy, { decimals: 2 })}
        </span>
      </div>

      <p className="mt-3 text-[10px] text-gray-600">
        Values pulled from live paper trading simulation. Half Kelly is recommended to reduce variance.
      </p>
    </div>
  );
}
