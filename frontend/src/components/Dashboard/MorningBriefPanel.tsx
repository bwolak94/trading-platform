/**
 * AI Morning Brief Panel
 * Shows a daily summary: overnight moves, highest-confidence signal,
 * regime outlook. Generated deterministically from live data.
 */

import { useQuery } from "@tanstack/react-query";
import axios from "axios";
import { fetchActiveSignals, fetchLiveRegimes } from "../../api/client";
import { fmtPct, colorClass } from "../../lib/format";

interface OHLCVBar { close: number; open: number }

async function fetchOvernightMove(symbol: string): Promise<{ symbol: string; change: number }> {
  const { data } = await axios.get(`/api/v1/market/ohlcv`, {
    params: { symbol, timeframe: "4h", limit: 2 },
  });
  const bars: OHLCVBar[] = data.candles ?? data.data ?? data ?? [];
  if (bars.length < 2) return { symbol, change: 0 };
  const prev = bars[0]?.close ?? 0;
  const curr = bars[1]?.close ?? bars[0]?.close ?? 0;
  return { symbol, change: prev > 0 ? ((curr - prev) / prev) * 100 : 0 };
}

const SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"];

export function MorningBriefPanel() {
  const signalsQ = useQuery({ queryKey: ["signals-brief"], queryFn: fetchActiveSignals, staleTime: 5 * 60_000, retry: false });
  const regimesQ = useQuery({ queryKey: ["regimes-brief"], queryFn: fetchLiveRegimes, staleTime: 5 * 60_000, retry: false });
  const movesQ = useQuery({
    queryKey: ["overnight-moves"],
    queryFn: () => Promise.all(SYMBOLS.map(fetchOvernightMove)),
    refetchInterval: 15 * 60_000,
    staleTime: 10 * 60_000,
    retry: false,
  });

  const signals = signalsQ.data?.data ?? [];
  const regimes = regimesQ.data ?? [];
  const moves = movesQ.data ?? [];

  const topSignal = [...signals]
    .filter((s) => s.status === "ACTIVE")
    .sort((a, b) => (b.confidence ?? 0) - (a.confidence ?? 0))[0];

  const dominantRegime = regimes.length
    ? regimes.sort((a, b) => b.confidence - a.confidence)[0]
    : null;

  const isLoading = signalsQ.isLoading || regimesQ.isLoading || movesQ.isLoading;
  const today = new Date().toLocaleDateString("en-US", { weekday: "long", month: "short", day: "numeric" });

  return (
    <div className="rounded-lg border border-accent/30 bg-accent/5 p-4">
      <div className="mb-3 flex items-center gap-2">
        <span className="text-base" aria-hidden="true">☀️</span>
        <div>
          <h2 className="text-sm font-semibold text-white">Morning Brief</h2>
          <p className="text-[10px] text-gray-500">{today}</p>
        </div>
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {[0, 1, 2].map((i) => <div key={i} className="h-6 animate-pulse rounded bg-white/5" />)}
        </div>
      ) : (
        <div className="space-y-3">
          {/* Overnight moves */}
          <div>
            <p className="mb-1.5 text-[10px] font-medium uppercase tracking-wide text-gray-500">4h Moves</p>
            <div className="flex gap-3 flex-wrap">
              {moves.map((m) => (
                <div key={m.symbol} className="flex items-center gap-1 text-xs">
                  <span className="text-gray-400">{m.symbol.replace("USDT", "")}</span>
                  <span className={`font-mono font-bold ${colorClass(m.change)}`}>
                    {fmtPct(m.change, { showSign: true, decimals: 1 })}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Dominant regime */}
          {dominantRegime && (
            <div>
              <p className="mb-1 text-[10px] font-medium uppercase tracking-wide text-gray-500">Dominant Regime</p>
              <div className="flex items-center gap-2 text-xs">
                <span className="font-semibold text-white">{dominantRegime.asset.replace("USDT", "")}</span>
                <span className="rounded bg-white/10 px-1.5 py-0.5 text-[10px] text-gray-300">
                  {dominantRegime.regime.replace(/_/g, " ")}
                </span>
                <span className="text-gray-500">{(dominantRegime.confidence * 100).toFixed(0)}% conf</span>
              </div>
            </div>
          )}

          {/* Top signal */}
          {topSignal ? (
            <div>
              <p className="mb-1 text-[10px] font-medium uppercase tracking-wide text-gray-500">Top Signal</p>
              <div className="flex items-center gap-2 text-xs">
                <span className={`font-semibold ${topSignal.direction === "LONG" ? "text-bullish" : "text-bearish"}`}>
                  {topSignal.direction === "LONG" ? "🟢" : "🔴"} {topSignal.asset.replace("USDT", "")} {topSignal.direction}
                </span>
                <span className="text-gray-500">{(topSignal.confidence ?? 0).toFixed(0)}% confidence</span>
              </div>
            </div>
          ) : (
            <p className="text-xs text-gray-600">No active signals.</p>
          )}

          {/* Actionable summary */}
          <div className="rounded bg-background/60 px-3 py-2 text-[10px] text-gray-400 italic">
            {dominantRegime?.regime?.includes("BULL")
              ? "Market in bullish regime — favour long setups, tighten shorts."
              : dominantRegime?.regime?.includes("BEAR")
              ? "Bearish regime active — reduce long exposure, consider hedges."
              : "Neutral/consolidation regime — wait for breakout confirmation before sizing up."}
          </div>
        </div>
      )}
    </div>
  );
}
