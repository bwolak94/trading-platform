/**
 * Paper Trading Leaderboard
 * Compares bot's simulated P&L vs BTC-hold, ETH-hold, equal-weight
 * over rolling 7 / 30 / 90 day windows.
 */

import { useQuery } from "@tanstack/react-query";
import axios from "axios";
import { useState } from "react";
import { fmtPct, colorClass } from "../../lib/format";

interface LeaderboardEntry {
  name: string;
  pnl_pct: number;
  trades?: number;
  win_rate?: number;
}

interface BenchmarkRaw {
  period_days: number;
  paper_trading: { total_return_pct: number; total_trades: number; win_rate: number };
  benchmarks: { btc_hold: number; eth_hold: number; equal_weight: number };
  alpha: number;
}

const WINDOWS = [7, 30, 90] as const;

async function fetchLeaderboard(days: number): Promise<LeaderboardEntry[]> {
  const { data } = await axios.get<BenchmarkRaw>(`/api/v1/benchmark/comparison?days=${days}`);
  const d = (data as { data?: BenchmarkRaw } & BenchmarkRaw).data ?? data;
  return [
    { name: "Bot (paper)", pnl_pct: d.paper_trading.total_return_pct, trades: d.paper_trading.total_trades, win_rate: d.paper_trading.win_rate },
    { name: "BTC Hold",    pnl_pct: d.benchmarks.btc_hold },
    { name: "ETH Hold",    pnl_pct: d.benchmarks.eth_hold },
    { name: "Equal Weight",pnl_pct: d.benchmarks.equal_weight },
  ].sort((a, b) => b.pnl_pct - a.pnl_pct);
}

const RANK_BADGE = ["🥇", "🥈", "🥉", "4th"];

export function PaperLeaderboardPanel() {
  const [days, setDays] = useState<(typeof WINDOWS)[number]>(30);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["paper-leaderboard", days],
    queryFn: () => fetchLeaderboard(days),
    refetchInterval: 120_000,
    staleTime: 60_000,
    retry: false,
  });

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-white">Paper Trading Leaderboard</h2>
        <div className="flex gap-1">
          {WINDOWS.map((w) => (
            <button
              key={w}
              type="button"
              onClick={() => setDays(w)}
              className={`rounded px-2 py-1 text-xs transition-colors ${
                days === w ? "bg-accent text-white" : "bg-background text-gray-400 hover:text-white"
              }`}
              aria-pressed={days === w}
            >
              {w}d
            </button>
          ))}
        </div>
      </div>
      <p className="mb-3 text-[10px] text-gray-500">
        Bot paper P&L vs passive crypto benchmarks over the last {days} days.
      </p>

      {isError && <p className="text-xs text-bearish">Benchmark data unavailable</p>}

      {isLoading ? (
        <div className="space-y-2">
          {[0, 1, 2, 3].map((i) => <div key={i} className="h-10 animate-pulse rounded bg-white/5" />)}
        </div>
      ) : (
        <div className="space-y-2">
          {(data ?? []).map((entry, i) => {
            const isBot = entry.name === "Bot (paper)";
            return (
              <div
                key={entry.name}
                className={`flex items-center gap-3 rounded border px-3 py-2 ${
                  isBot ? "border-accent/40 bg-accent/5" : "border-border bg-background"
                }`}
              >
                <span className="text-base w-6 text-center" aria-hidden="true">{RANK_BADGE[i] ?? `${i + 1}`}</span>
                <div className="flex-1">
                  <p className={`text-xs font-semibold ${isBot ? "text-accent" : "text-gray-300"}`}>{entry.name}</p>
                  {isBot && entry.win_rate != null && (
                    <p className="text-[10px] text-gray-500">
                      {entry.trades} trades · {(entry.win_rate * 100).toFixed(0)}% win
                    </p>
                  )}
                </div>
                <span className={`font-mono text-sm font-bold ${colorClass(entry.pnl_pct)}`}>
                  {fmtPct(entry.pnl_pct, { showSign: true, decimals: 1 })}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
