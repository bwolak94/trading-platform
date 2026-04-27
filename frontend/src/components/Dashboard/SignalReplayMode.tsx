/**
 * Signal Replay Mode
 * Scrub back through historical signals day by day with a date picker.
 * Shows signals as they would have appeared at that point in time.
 */

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import axios from "axios";

interface HistoricalSignal {
  id: string;
  asset: string;
  direction: "LONG" | "SHORT" | "NEUTRAL";
  confidence: number;
  entry_price: number | null;
  stop_loss: number | null;
  take_profit_1: number | null;
  risk_reward: number | null;
  status: string;
  regime: string;
  created_at: string;
}

async function fetchSignalsByDate(date: string): Promise<HistoricalSignal[]> {
  const from = `${date}T00:00:00Z`;
  const to = `${date}T23:59:59Z`;
  const { data } = await axios.get("/api/v1/signals", {
    params: { from, to, limit: 50 },
  });
  return (data?.data ?? []) as HistoricalSignal[];
}

const DIR_COLOR: Record<string, string> = {
  LONG: "text-bullish",
  SHORT: "text-bearish",
  NEUTRAL: "text-gray-400",
};

const STATUS_BADGE: Record<string, string> = {
  TP1_HIT: "bg-bullish/20 text-bullish",
  TP2_HIT: "bg-bullish/30 text-bullish",
  SL_HIT: "bg-bearish/20 text-bearish",
  EXPIRED: "bg-gray-700 text-gray-400",
  ACTIVE: "bg-accent/20 text-accent",
};

export function SignalReplayMode() {
  const today = new Date().toISOString().slice(0, 10);
  const [selectedDate, setSelectedDate] = useState(() => {
    const d = new Date();
    d.setDate(d.getDate() - 1);
    return d.toISOString().slice(0, 10);
  });

  const { data, isLoading, isError } = useQuery({
    queryKey: ["signal-replay", selectedDate],
    queryFn: () => fetchSignalsByDate(selectedDate),
    staleTime: 300_000,
    retry: false,
    placeholderData: (prev) => prev,
  });

  const signals = data ?? [];

  const summary = {
    total: signals.length,
    longs: signals.filter((s) => s.direction === "LONG").length,
    shorts: signals.filter((s) => s.direction === "SHORT").length,
    avgConf: signals.length
      ? Math.round(signals.reduce((s, sig) => s + sig.confidence, 0) / signals.length)
      : 0,
    winners: signals.filter((s) => s.status === "TP1_HIT" || s.status === "TP2_HIT").length,
  };

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-white">Signal Replay</h2>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => {
              const d = new Date(selectedDate);
              d.setDate(d.getDate() - 1);
              setSelectedDate(d.toISOString().slice(0, 10));
            }}
            className="rounded border border-border px-2 py-0.5 text-xs text-gray-400 hover:text-white transition-colors"
            aria-label="Previous day"
          >
            ←
          </button>
          <input
            type="date"
            value={selectedDate}
            max={today}
            onChange={(e) => setSelectedDate(e.target.value)}
            className="rounded border border-border bg-background px-2 py-1 text-xs text-gray-300 focus:outline-none focus:ring-1 focus:ring-accent"
            aria-label="Replay date"
          />
          <button
            type="button"
            onClick={() => {
              const d = new Date(selectedDate);
              d.setDate(d.getDate() + 1);
              if (d.toISOString().slice(0, 10) <= today) {
                setSelectedDate(d.toISOString().slice(0, 10));
              }
            }}
            className="rounded border border-border px-2 py-0.5 text-xs text-gray-400 hover:text-white transition-colors disabled:opacity-40"
            disabled={selectedDate >= today}
            aria-label="Next day"
          >
            →
          </button>
        </div>
      </div>

      <p className="mb-3 text-[10px] text-gray-500">
        Historical signals for {new Date(selectedDate).toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" })}.
      </p>

      {/* Summary bar */}
      {signals.length > 0 && (
        <div className="mb-3 flex gap-3 text-[10px]">
          <span className="text-gray-500">{summary.total} signals</span>
          <span className="text-bullish">{summary.longs} long</span>
          <span className="text-bearish">{summary.shorts} short</span>
          <span className="text-gray-400">avg conf {summary.avgConf}%</span>
          <span className="text-bullish">{summary.winners} TP hit</span>
        </div>
      )}

      {isError && <p className="text-xs text-bearish mb-2">Failed to load historical signals.</p>}

      {isLoading ? (
        <div className="space-y-2">
          {[0, 1, 2].map((i) => <div key={i} className="h-10 animate-pulse rounded bg-white/5" />)}
        </div>
      ) : signals.length === 0 ? (
        <p className="py-8 text-center text-xs text-gray-600">No signals for this date.</p>
      ) : (
        <div className="max-h-64 overflow-y-auto space-y-1.5">
          {signals.map((s) => (
            <div key={s.id} className="flex items-center gap-3 rounded border border-border bg-background px-3 py-2 text-[11px]">
              <span className={`w-20 font-semibold ${DIR_COLOR[s.direction] ?? "text-gray-400"}`}>
                {s.asset}
              </span>
              <span className={`w-12 text-center ${DIR_COLOR[s.direction] ?? "text-gray-400"}`}>
                {s.direction}
              </span>
              <span className="w-12 text-center font-mono text-gray-400">{s.confidence.toFixed(0)}%</span>
              {s.entry_price && (
                <span className="font-mono text-gray-500">
                  ${s.entry_price.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                </span>
              )}
              <span className={`ml-auto rounded px-1.5 py-0.5 text-[9px] font-bold ${STATUS_BADGE[s.status] ?? "bg-white/10 text-gray-400"}`}>
                {s.status}
              </span>
              <span className="text-[9px] text-gray-600">
                {new Date(s.created_at).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
