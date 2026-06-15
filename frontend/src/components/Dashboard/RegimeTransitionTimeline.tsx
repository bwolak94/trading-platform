/**
 * Regime Transition Timeline
 * Horizontal scrollable timeline of every regime change with timestamps,
 * duration, and P&L generated during each regime period.
 */

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import axios from "axios";

interface RegimeEvent {
  regime: string;
  started_at: string;
  ended_at: string | null;
  asset: string;
  confidence: number;
  pnl_during?: number | null;
}

const REGIME_STYLE: Record<string, { bg: string; text: string; border: string }> = {
  TREND_BULL:      { bg: "bg-bullish/20",    text: "text-bullish",   border: "border-bullish/30" },
  TREND_BEAR:      { bg: "bg-bearish/20",    text: "text-bearish",   border: "border-bearish/30" },
  CONSOLIDATION:   { bg: "bg-amber-500/20",  text: "text-amber-400", border: "border-amber-500/30" },
  HIGH_VOL_CHOPPY: { bg: "bg-purple-500/20", text: "text-purple-400", border: "border-purple-500/30" },
};

function durationLabel(started: string, ended: string | null): string {
  const start = new Date(started).getTime();
  const end = ended ? new Date(ended).getTime() : Date.now();
  const mins = Math.floor((end - start) / 60000);
  if (mins < 60) return `${mins}m`;
  if (mins < 1440) return `${Math.floor(mins / 60)}h`;
  return `${Math.floor(mins / 1440)}d`;
}

async function fetchRegimeHistory(asset: string): Promise<RegimeEvent[]> {
  const { data } = await axios.get(`/api/v1/market/regime/${asset}/history?limit=20`);
  return (data?.regimes ?? data?.data ?? []) as RegimeEvent[];
}

const ASSETS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"];

export function RegimeTransitionTimeline() {
  const [asset, setAsset] = useState("BTCUSDT");
  const { data, isLoading } = useQuery({
    queryKey: ["regime-history", asset],
    queryFn: () => fetchRegimeHistory(asset),
    staleTime: 60_000,
    refetchInterval: 60_000,
    retry: false,
    placeholderData: (prev) => prev,
  });

  const events = data ?? [];

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-white">Regime Timeline</h2>
        <select
          value={asset}
          onChange={(e) => { setAsset(e.target.value); }}
          className="rounded border border-border bg-background px-2 py-1 text-xs text-gray-300 focus:outline-none"
          aria-label="Select asset"
        >
          {ASSETS.map((a) => <option key={a} value={a}>{a.replace("USDT", "")}</option>)}
        </select>
      </div>
      <p className="mb-3 text-[10px] text-gray-500">
        Chronological regime transitions. Hover for P&L generated during each period.
      </p>

      {isLoading ? (
        <div className="h-20 animate-pulse rounded bg-white/5" />
      ) : events.length === 0 ? (
        <p className="py-6 text-center text-xs text-gray-600">No regime history available.</p>
      ) : (
        <div className="overflow-x-auto pb-2">
          <div className="flex min-w-max items-stretch gap-1">
            {events.map((ev, i) => {
              const style = REGIME_STYLE[ev.regime] ?? { bg: "bg-white/5", text: "text-gray-400", border: "border-border" };
              const dur = durationLabel(ev.started_at, ev.ended_at);
              const isActive = ev.ended_at === null;
              return (
                <div
                  key={i}
                  className={`relative flex min-w-[80px] flex-col rounded border px-2 py-2 ${style.bg} ${style.border} ${isActive ? "ring-1 ring-white/20" : ""}`}
                  title={`Started: ${new Date(ev.started_at).toLocaleString()}\nDuration: ${dur}\nConf: ${ev.confidence.toFixed(0)}%`}
                >
                  {isActive && (
                    <span className="absolute -top-1.5 right-1 rounded bg-bullish/80 px-1 py-px text-[8px] text-white font-bold">NOW</span>
                  )}
                  <p className={`text-[9px] font-bold ${style.text}`}>
                    {ev.regime.replace("_", " ")}
                  </p>
                  <p className="text-[8px] text-gray-500">{dur}</p>
                  <p className="text-[8px] text-gray-600">
                    {new Date(ev.started_at).toLocaleDateString(undefined, { month: "short", day: "numeric" })}
                  </p>
                  {ev.pnl_during != null && (
                    <p className={`text-[8px] font-mono ${ev.pnl_during >= 0 ? "text-bullish" : "text-bearish"}`}>
                      {ev.pnl_during >= 0 ? "+" : ""}{ev.pnl_during.toFixed(1)}%
                    </p>
                  )}
                  {/* Connector arrow */}
                  {i < events.length - 1 && (
                    <span className="absolute -right-1.5 top-1/2 -translate-y-1/2 text-gray-700 text-[10px]">›</span>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
