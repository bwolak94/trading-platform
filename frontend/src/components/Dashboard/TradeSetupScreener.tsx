/**
 * Trade Setup Screener
 * Scans all tracked symbols and ranks by composite score.
 * Shows top N setups with direction, RSI, momentum and EMA trend.
 */

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import axios from "axios";
import { colorClass } from "../../lib/format";

interface Setup {
  symbol: string;
  price: number;
  change_24h_pct: number;
  volume_usdt_24h: number;
  rsi_14: number;
  ema_trend: "bullish" | "bearish";
  direction: "LONG" | "SHORT" | "NEUTRAL";
  composite_score: number;
}

interface ScreenerResponse {
  scanned: number;
  returned: number;
  direction_filter: string;
  setups: Setup[];
}

const DIRECTIONS = ["ALL", "LONG", "SHORT"] as const;
type DirectionFilter = (typeof DIRECTIONS)[number];

async function fetchScreener(topN: number, direction: string): Promise<ScreenerResponse> {
  const { data } = await axios.get("/api/v1/analysis/trade-screener", {
    params: { top_n: topN, direction },
  });
  return data as ScreenerResponse;
}

function DirectionBadge({ dir }: { dir: string }) {
  if (dir === "LONG") return <span className="rounded bg-bullish/20 px-1.5 py-0.5 text-[9px] font-bold text-bullish">LONG</span>;
  if (dir === "SHORT") return <span className="rounded bg-bearish/20 px-1.5 py-0.5 text-[9px] font-bold text-bearish">SHORT</span>;
  return <span className="rounded bg-white/10 px-1.5 py-0.5 text-[9px] text-gray-400">NEUTRAL</span>;
}

export function TradeSetupScreener() {
  const [topN, setTopN] = useState(5);
  const [direction, setDirection] = useState<DirectionFilter>("ALL");

  const { data, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: ["trade-screener", topN, direction],
    queryFn: () => fetchScreener(topN, direction),
    staleTime: 60_000,
    refetchInterval: 120_000,
    retry: false,
    placeholderData: (prev) => prev,
  });

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-white">Trade Setup Screener</h2>
        <div className="flex items-center gap-2">
          {data && (
            <span className="text-[10px] text-gray-500">
              {data.scanned} scanned
            </span>
          )}
          <button
            type="button"
            onClick={() => void refetch()}
            disabled={isFetching}
            className="rounded border border-border px-2 py-0.5 text-[10px] text-gray-400 hover:text-white transition-colors disabled:opacity-40"
            aria-label="Refresh screener"
          >
            {isFetching ? "…" : "↻"}
          </button>
        </div>
      </div>
      <p className="mb-3 text-[10px] text-gray-500">
        Composite score = momentum + RSI distance + volume. Green = feasible long, red = short.
      </p>

      {/* Filters */}
      <div className="mb-3 flex items-center gap-2">
        <div className="flex rounded border border-border overflow-hidden">
          {DIRECTIONS.map((d) => (
            <button
              key={d}
              type="button"
              onClick={() => { setDirection(d); }}
              className={`px-2 py-1 text-[10px] transition-colors ${
                direction === d ? "bg-accent text-white" : "text-gray-500 hover:text-gray-300"
              }`}
            >
              {d}
            </button>
          ))}
        </div>
        <select
          value={topN}
          onChange={(e) => { setTopN(Number(e.target.value)); }}
          className="rounded border border-border bg-background px-2 py-1 text-[10px] text-gray-300 focus:outline-none"
          aria-label="Number of setups"
        >
          {[3, 5, 8, 10].map((n) => <option key={n} value={n}>Top {n}</option>)}
        </select>
      </div>

      {isError && <p className="text-xs text-bearish mb-2">Failed to load screener data.</p>}

      {isLoading ? (
        <div className="space-y-2">
          {[0, 1, 2].map((i) => <div key={i} className="h-10 animate-pulse rounded bg-white/5" />)}
        </div>
      ) : (
        <div className="space-y-1.5">
          {(data?.setups ?? []).map((s, i) => (
            <div key={s.symbol} className="flex items-center gap-3 rounded border border-border bg-background px-3 py-2">
              <span className="w-4 text-[10px] text-gray-600 font-mono">#{i + 1}</span>
              <span className="w-16 text-xs font-medium text-gray-200">{s.symbol.replace("USDT", "")}</span>
              <DirectionBadge dir={s.direction} />
              <span className={`font-mono text-[11px] ${colorClass(s.change_24h_pct)}`}>
                {s.change_24h_pct >= 0 ? "+" : ""}{s.change_24h_pct.toFixed(1)}%
              </span>
              <span className="text-[10px] text-gray-500">RSI {s.rsi_14}</span>
              <span className={`text-[10px] ${s.ema_trend === "bullish" ? "text-bullish" : "text-bearish"}`}>
                EMA {s.ema_trend}
              </span>
              <span className="ml-auto font-mono text-[10px] text-accent font-bold">{s.composite_score}</span>
            </div>
          ))}
          {(!data?.setups || data.setups.length === 0) && (
            <p className="py-6 text-center text-xs text-gray-600">No setups found for current filter.</p>
          )}
        </div>
      )}
    </div>
  );
}
