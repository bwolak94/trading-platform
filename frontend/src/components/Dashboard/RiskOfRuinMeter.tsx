/**
 * Risk-of-Ruin Meter
 * Given current drawdown % + win rate from closed positions,
 * computes the probability of hitting 50% account loss (ruin threshold).
 *
 * Formula: R = ((1 - edge) / (1 + edge)) ^ n
 * where edge = win_rate - 0.5, n = steps to ruin = ruin_pct / avg_loss_pct
 */

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchClosedPositions } from "../../api/client";

function computeRuin(winRate: number, avgWin: number, avgLoss: number, ruinPct: number, currentDD: number): number {
  if (avgLoss <= 0 || winRate <= 0 || winRate >= 1) return 0;
  const edge = winRate * avgWin - (1 - winRate) * avgLoss;
  if (edge <= 0) return 1; // negative edge = certain ruin
  // Kelly fraction intentionally computed for context; ruin formula uses gambler's approximation
  const remainingBuffer = Math.max(0, ruinPct - currentDD);
  if (remainingBuffer <= 0) return 1;
  // Gambler's ruin approximation
  const p = winRate;
  const q = 1 - winRate;
  if (Math.abs(p - q) < 0.001) {
    return 1 - remainingBuffer / (ruinPct + remainingBuffer);
  }
  const ratio = q / p;
  const stepsToRuin = remainingBuffer / (avgLoss * (1 - winRate));
  return Math.min(Math.pow(ratio, stepsToRuin), 1);
}

function ruinColor(prob: number): string {
  if (prob >= 0.5) return "text-bearish";
  if (prob >= 0.2) return "text-amber-400";
  return "text-bullish";
}

function gaugeColor(prob: number): string {
  if (prob >= 0.5) return "bg-bearish";
  if (prob >= 0.2) return "bg-amber-400";
  return "bg-bullish";
}

interface Props {
  currentDrawdownPct?: number;
  ruinThresholdPct?: number;
}

export function RiskOfRuinMeter({ currentDrawdownPct = 0, ruinThresholdPct = 50 }: Props) {
  const { data } = useQuery({
    queryKey: ["closed-positions-ruin"],
    queryFn: () => fetchClosedPositions({ limit: 100 }),
    staleTime: 60_000,
    refetchInterval: 60_000,
    retry: false,
    placeholderData: (prev) => prev,
  });

  const stats = useMemo(() => {
    const positions = data?.positions ?? [];
    if (positions.length < 5) return null;
    const pnls = positions.map((p) => p.pnl_pct ?? 0);
    const wins = pnls.filter((p) => p > 0);
    const losses = pnls.filter((p) => p < 0);
    const winRate = wins.length / pnls.length;
    const avgWin = wins.length ? wins.reduce((s, v) => s + v, 0) / wins.length : 1;
    const avgLoss = losses.length ? Math.abs(losses.reduce((s, v) => s + v, 0) / losses.length) : 1;
    return { winRate, avgWin, avgLoss, totalTrades: pnls.length };
  }, [data]);

  const ruinProb = useMemo(() => {
    if (!stats) return null;
    return computeRuin(stats.winRate, stats.avgWin, stats.avgLoss, ruinThresholdPct, currentDrawdownPct);
  }, [stats, currentDrawdownPct, ruinThresholdPct]);

  if (!stats || ruinProb === null) {
    return (
      <div className="rounded-lg border border-border bg-surface p-4">
        <h2 className="mb-1 text-sm font-semibold text-white">Risk of Ruin</h2>
        <p className="text-xs text-gray-600">Need ≥ 5 closed positions to compute.</p>
      </div>
    );
  }

  const pct = Math.round(ruinProb * 100);
  const barW = Math.min(pct, 100);

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-white">Risk of Ruin</h2>
        <span className={`font-mono text-lg font-bold ${ruinColor(ruinProb)}`}>{pct}%</span>
      </div>
      <p className="mb-3 text-[10px] text-gray-500">
        Probability of hitting {ruinThresholdPct}% account loss given current win rate + drawdown.
      </p>

      {/* Gauge bar */}
      <div className="mb-3 h-3 w-full overflow-hidden rounded-full bg-white/5">
        <div
          className={`h-full rounded-full transition-all duration-500 ${gaugeColor(ruinProb)}`}
          style={{ width: `${barW}%` }}
        />
      </div>

      <div className="grid grid-cols-3 gap-2 text-center text-[10px]">
        <div className="rounded bg-background px-2 py-1.5">
          <p className="text-gray-500">Win Rate</p>
          <p className="font-mono font-bold text-white">{(stats.winRate * 100).toFixed(1)}%</p>
        </div>
        <div className="rounded bg-background px-2 py-1.5">
          <p className="text-gray-500">Avg Win</p>
          <p className="font-mono font-bold text-bullish">+{stats.avgWin.toFixed(1)}%</p>
        </div>
        <div className="rounded bg-background px-2 py-1.5">
          <p className="text-gray-500">Avg Loss</p>
          <p className="font-mono font-bold text-bearish">-{stats.avgLoss.toFixed(1)}%</p>
        </div>
      </div>

      <p className="mt-2 text-[9px] text-gray-600">
        Based on last {stats.totalTrades} trades · Current DD: {currentDrawdownPct.toFixed(1)}%
      </p>
    </div>
  );
}
