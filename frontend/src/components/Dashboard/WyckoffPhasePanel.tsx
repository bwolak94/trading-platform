/**
 * WyckoffPhasePanel
 * Displays Wyckoff phase detection results for a selected symbol and timeframe.
 * Fetches from GET /api/v1/features/wyckoff/{symbol}?timeframe=4h
 */

import { useQuery } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import axios from "axios";

// --------------- Types ---------------

interface WyckoffResult {
  phase: string;
  subphase: string;
  confidence: number;
  description: string;
  is_bullish: boolean;
  key_level: number;
}

// --------------- Constants ---------------

const SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"];
const TIMEFRAMES = ["1h", "4h", "1d"];

const PHASE_LABELS: Record<string, string> = {
  ACCUMULATION: "Accumulation",
  DISTRIBUTION: "Distribution",
  MARKUP: "Markup",
  MARKDOWN: "Markdown",
  RE_ACCUMULATION: "Re-Accumulation",
  RE_DISTRIBUTION: "Re-Distribution",
};

// --------------- Helpers ---------------

function getPhaseAccent(phase: string, is_bullish: boolean) {
  if (is_bullish) {
    return {
      border: "border-green-500",
      text: "text-green-400",
      badge: "bg-green-500/20 text-green-400",
      bar: "bg-green-500",
      dot: "bg-green-500",
    };
  }
  if (phase === "DISTRIBUTION" || phase === "MARKDOWN" || phase === "RE_DISTRIBUTION") {
    return {
      border: "border-red-500",
      text: "text-red-400",
      badge: "bg-red-500/20 text-red-400",
      bar: "bg-red-500",
      dot: "bg-red-500",
    };
  }
  return {
    border: "border-gray-600",
    text: "text-gray-400",
    badge: "bg-gray-700 text-gray-400",
    bar: "bg-gray-500",
    dot: "bg-gray-500",
  };
}

async function fetchWyckoff(symbol: string, timeframe: string): Promise<WyckoffResult> {
  const { data } = await axios.get<WyckoffResult>(
    `/api/v1/features/wyckoff/${symbol}`,
    { params: { timeframe } }
  );
  return data;
}

// --------------- Loading Skeleton ---------------

function WyckoffSkeleton() {
  return (
    <div className="space-y-3" aria-busy="true" aria-label="Loading Wyckoff data">
      <div className="h-8 w-40 animate-pulse rounded bg-white/5" />
      <div className="h-4 w-full animate-pulse rounded bg-white/5" />
      <div className="h-3 w-3/4 animate-pulse rounded bg-white/5" />
      <div className="h-16 animate-pulse rounded bg-white/5" />
    </div>
  );
}

// --------------- Main Component ---------------

export default function WyckoffPhasePanel() {
  const [symbol, setSymbol] = useState("BTCUSDT");
  const [timeframe, setTimeframe] = useState("4h");

  const { data, isLoading, isError, refetch, dataUpdatedAt } = useQuery<WyckoffResult>({
    queryKey: ["wyckoff", symbol, timeframe],
    queryFn: () => fetchWyckoff(symbol, timeframe),
    refetchInterval: 60_000,
    retry: 2,
  });

  const handleRefetch = useCallback(() => { void refetch(); }, [refetch]);

  const accent = data ? getPhaseAccent(data.phase, data.is_bullish) : null;
  const lastUpdated = dataUpdatedAt ? new Date(dataUpdatedAt).toLocaleTimeString() : null;

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-white">Wyckoff Phase</h2>
          {lastUpdated && (
            <p className="mt-0.5 text-xs text-gray-500">Updated: {lastUpdated}</p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <select
            value={timeframe}
            onChange={(e) => setTimeframe(e.target.value)}
            className="rounded border border-border bg-gray-800 px-2 py-1 text-xs text-gray-300 focus:outline-none focus:ring-1 focus:ring-blue-500"
            aria-label="Select timeframe"
          >
            {TIMEFRAMES.map((tf) => (
              <option key={tf} value={tf}>{tf}</option>
            ))}
          </select>
          <select
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            className="rounded border border-border bg-gray-800 px-2 py-1 text-xs text-gray-300 focus:outline-none focus:ring-1 focus:ring-blue-500"
            aria-label="Select symbol"
          >
            {SYMBOLS.map((s) => (
              <option key={s} value={s}>{s.replace("USDT", "")}</option>
            ))}
          </select>
          <button
            type="button"
            onClick={handleRefetch}
            className="rounded border border-border bg-gray-800 px-2 py-1 text-xs text-gray-400 hover:text-white transition-colors"
            aria-label="Refresh Wyckoff data"
          >
            Refresh
          </button>
        </div>
      </div>

      {/* Error state */}
      {isError && (
        <div className="mb-3 flex items-center justify-between rounded bg-red-500/10 px-3 py-2">
          <span className="text-xs text-red-400">Failed to load Wyckoff data</span>
          <button
            type="button"
            onClick={handleRefetch}
            className="text-xs text-red-400 underline hover:text-red-300"
          >
            Retry
          </button>
        </div>
      )}

      {/* Loading */}
      {isLoading && <WyckoffSkeleton />}

      {/* Data */}
      {data && accent && (
        <div className="space-y-4">
          {/* Phase badge row */}
          <div className={`flex items-center gap-3 rounded-lg border-l-4 ${accent.border} bg-gray-800/60 px-4 py-3`}>
            <div>
              <div className="flex items-center gap-2">
                <span className={`rounded px-2 py-0.5 text-xs font-bold uppercase tracking-wide ${accent.badge}`}>
                  {PHASE_LABELS[data.phase] ?? data.phase}
                </span>
                {data.subphase && (
                  <span className="rounded border border-gray-600 px-2 py-0.5 text-xs text-gray-400">
                    {data.subphase}
                  </span>
                )}
              </div>
              <p className={`mt-1 text-xs italic ${accent.text}`}>{data.description}</p>
            </div>
          </div>

          {/* Confidence bar */}
          <div>
            <div className="mb-1 flex items-center justify-between text-xs text-gray-500">
              <span>Phase Confidence</span>
              <span className="font-mono">{data.confidence.toFixed(0)}%</span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-gray-800">
              <div
                className={`h-full rounded-full transition-all duration-500 ${accent.bar}`}
                style={{ width: `${Math.min(data.confidence, 100)}%` }}
                role="progressbar"
                aria-valuenow={data.confidence}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label={`Wyckoff confidence ${data.confidence.toFixed(0)}%`}
              />
            </div>
          </div>

          {/* Key level */}
          <div className="flex items-center justify-between rounded bg-gray-800 px-3 py-2">
            <span className="text-xs text-gray-500">Key Price Level</span>
            <span className="font-mono text-sm font-semibold text-white">
              ${data.key_level.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </span>
          </div>

          {/* Insight box */}
          <div className={`rounded border ${accent.border} bg-gray-900/50 px-3 py-3`}>
            <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-500">
              Phase Insight
            </p>
            <p className="text-xs text-gray-300 leading-relaxed">{data.description}</p>
            <div className="mt-2 flex items-center gap-1.5">
              <div className={`h-2 w-2 rounded-full ${accent.dot}`} aria-hidden="true" />
              <span className={`text-xs font-medium ${accent.text}`}>
                {data.is_bullish ? "Bullish bias — watch for breakout" : "Bearish bias — watch for breakdown"}
              </span>
            </div>
          </div>
        </div>
      )}

      {!isLoading && !isError && !data && (
        <p className="text-sm text-gray-500">No Wyckoff data available for {symbol}</p>
      )}
    </div>
  );
}
