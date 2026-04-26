/**
 * Session P&L Breakdown
 * Segments closed positions into Asia / London / New York sessions
 * and shows P&L, win rate, and avg return per session.
 */

import { useQuery } from "@tanstack/react-query";
import { fetchClosedPositions } from "../../api/client";
import { fmtPct, colorClass } from "../../lib/format";

interface SessionStats {
  name: string;
  range: string;
  pnl: number;
  trades: number;
  wins: number;
  avgPnl: number;
}

const SESSIONS: { name: string; range: string; startHour: number; endHour: number }[] = [
  { name: "Asia",   range: "00–08 UTC", startHour: 0,  endHour: 8  },
  { name: "London", range: "08–16 UTC", startHour: 8,  endHour: 16 },
  { name: "NY",     range: "16–24 UTC", startHour: 16, endHour: 24 },
];

function buildSessionStats(positions: { pnl_pct?: number | null; closed_at?: string | null }[]): SessionStats[] {
  return SESSIONS.map((sess) => {
    const inSession = positions.filter((p) => {
      if (!p.closed_at) return false;
      const h = new Date(p.closed_at).getUTCHours();
      return h >= sess.startHour && h < sess.endHour;
    });
    const pnl = inSession.reduce((s, p) => s + (p.pnl_pct ?? 0), 0);
    const wins = inSession.filter((p) => (p.pnl_pct ?? 0) > 0).length;
    return {
      ...sess,
      pnl: parseFloat(pnl.toFixed(2)),
      trades: inSession.length,
      wins,
      avgPnl: inSession.length ? parseFloat((pnl / inSession.length).toFixed(2)) : 0,
    };
  });
}

const SESSION_COLOR: Record<string, string> = {
  Asia:   "bg-blue-500/20 border-blue-500/30",
  London: "bg-amber-500/20 border-amber-500/30",
  NY:     "bg-purple-500/20 border-purple-500/30",
};

export function SessionPnLPanel() {
  const { data, isLoading } = useQuery({
    queryKey: ["closed-positions-session"],
    queryFn: () => fetchClosedPositions({ limit: 200 }),
    refetchInterval: 60_000,
    staleTime: 30_000,
    retry: false,
  });

  const stats = buildSessionStats(data?.positions ?? []);
  const best = [...stats].sort((a, b) => b.pnl - a.pnl)[0];

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-white">Session P&L</h2>
        {best && best.trades > 0 && (
          <span className="text-[10px] text-gray-500">Best: <span className="text-white">{best.name}</span></span>
        )}
      </div>
      <p className="mb-3 text-[10px] text-gray-500">
        P&L breakdown by trading session (UTC). Identifies which session generates alpha.
      </p>

      {isLoading ? (
        <div className="space-y-2">
          {[0, 1, 2].map((i) => <div key={i} className="h-16 animate-pulse rounded bg-white/5" />)}
        </div>
      ) : (
        <div className="space-y-2">
          {stats.map((s) => {
            const winRate = s.trades ? Math.round((s.wins / s.trades) * 100) : 0;
            const barW = s.trades > 0 ? Math.min(Math.abs(s.pnl) * 10, 100) : 0;
            return (
              <div key={s.name} className={`rounded border p-3 ${SESSION_COLOR[s.name] ?? "border-border bg-background"}`}>
                <div className="mb-2 flex items-center justify-between text-xs">
                  <span className="font-semibold text-white">{s.name} <span className="text-[10px] font-normal text-gray-500">{s.range}</span></span>
                  <span className={`font-mono font-bold text-sm ${colorClass(s.pnl)}`}>
                    {s.pnl >= 0 ? "+" : ""}{s.pnl.toFixed(1)}%
                  </span>
                </div>
                <div className="h-1 w-full overflow-hidden rounded-full bg-white/5 mb-2">
                  <div
                    className={`h-full rounded-full ${s.pnl >= 0 ? "bg-bullish" : "bg-bearish"}`}
                    style={{ width: `${barW}%` }}
                  />
                </div>
                <div className="flex justify-between text-[10px] text-gray-500">
                  <span>{s.trades} trades</span>
                  <span>{winRate}% win</span>
                  <span>avg {fmtPct(s.avgPnl, { showSign: true, decimals: 1 })}</span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
