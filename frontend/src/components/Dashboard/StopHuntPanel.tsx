/**
 * StopHuntPanel
 * Shows predicted stop hunt locations with direction, target, quality, and timing badges.
 * Fetches from GET /api/v1/features2/stop-hunt/{symbol}
 */

import { useQuery } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import axios from "axios";

// --------------- Types ---------------

interface StopHuntData {
  direction: string;
  target_price: number;
  current_price: number;
  confidence: number;
  quality: string;
  timing: string;
  description: string;
}

// --------------- Constants ---------------

type Timing = "IMMINENT" | "SOON" | "PENDING";
type Quality = "A" | "B" | "C";

const TIMING_STYLES: Record<
  Timing,
  { badge: string; label: string }
> = {
  IMMINENT: {
    badge: "animate-pulse bg-red-500/20 text-red-400 border border-red-500/40",
    label: "IMMINENT",
  },
  SOON: {
    badge: "bg-yellow-500/20 text-yellow-400 border border-yellow-500/40",
    label: "SOON",
  },
  PENDING: {
    badge: "bg-gray-700 text-gray-400 border border-gray-600",
    label: "PENDING",
  },
};

const QUALITY_STYLES: Record<
  Quality,
  { badge: string }
> = {
  A: { badge: "bg-green-500/20 text-green-400 border border-green-500/40" },
  B: { badge: "bg-yellow-500/20 text-yellow-400 border border-yellow-500/40" },
  C: { badge: "bg-gray-700 text-gray-400 border border-gray-600" },
};

const SYMBOL_OPTIONS = [
  "BTCUSDT",
  "ETHUSDT",
  "SOLUSDT",
  "BNBUSDT",
  "XRPUSDT",
  "ADAUSDT",
];

// --------------- Fetch helper ---------------

async function fetchStopHunt(symbol: string): Promise<StopHuntData> {
  const { data } = await axios.get<StopHuntData>(
    `/api/v1/features2/stop-hunt/${symbol}`,
  );
  return data;
}

// --------------- Sub-component: Price scale visual ---------------

function PriceScale({
  currentPrice,
  targetPrice,
  direction,
}: {
  currentPrice: number;
  targetPrice: number;
  direction: string;
}) {
  const isDown = direction === "DOWN";
  const diff = Math.abs(targetPrice - currentPrice);
  const pct = currentPrice > 0 ? (diff / currentPrice) * 100 : 0;

  return (
    <div className="rounded border border-border bg-gray-800/60 px-3 py-3">
      <p className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-gray-500">
        Price Scale
      </p>
      <div className="flex items-center gap-3">
        <div className="flex flex-1 flex-col items-center gap-1">
          <span className="text-[10px] text-gray-500">Current</span>
          <span className="font-mono text-sm font-bold text-gray-200">
            {currentPrice.toLocaleString()}
          </span>
        </div>
        <div className="flex flex-col items-center gap-0.5">
          <span
            className={`text-lg font-bold ${isDown ? "text-red-400" : "text-green-400"}`}
            aria-hidden="true"
          >
            {isDown ? "↓" : "↑"}
          </span>
          <span className="text-[10px] font-mono text-gray-500">
            {pct.toFixed(2)}%
          </span>
        </div>
        <div className="flex flex-1 flex-col items-center gap-1">
          <span className="text-[10px] text-gray-500">Target</span>
          <span
            className={`font-mono text-sm font-bold ${
              isDown ? "text-red-400" : "text-green-400"
            }`}
          >
            {targetPrice.toLocaleString()}
          </span>
        </div>
      </div>
      {/* Visual bar */}
      <div className="mt-2 h-1.5 w-full rounded-full bg-gray-700 overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-500 ${
            isDown ? "bg-red-500 ml-auto" : "bg-green-500"
          }`}
          style={{ width: `${Math.min(pct * 10, 80)}%` }}
        />
      </div>
    </div>
  );
}

// --------------- Skeleton ---------------

function StopHuntSkeleton() {
  return (
    <div className="space-y-3" aria-busy="true" aria-label="Loading stop hunt data">
      <div className="flex gap-2">
        <div className="h-7 w-24 animate-pulse rounded bg-white/5" />
        <div className="h-7 w-16 animate-pulse rounded bg-white/5" />
        <div className="h-7 w-16 animate-pulse rounded bg-white/5" />
      </div>
      <div className="h-20 animate-pulse rounded bg-white/5" />
      <div className="h-12 animate-pulse rounded bg-white/5" />
    </div>
  );
}

// --------------- Main Component ---------------

export default function StopHuntPanel() {
  const [symbol, setSymbol] = useState("BTCUSDT");

  const { data, isLoading, isError, refetch } = useQuery<StopHuntData>({
    queryKey: ["stop-hunt", symbol],
    queryFn: () => fetchStopHunt(symbol),
    refetchInterval: 60_000,
    retry: 2,
  });

  const handleRetry = useCallback(() => {
    void refetch();
  }, [refetch]);

  const timing = ((data?.timing ?? "PENDING") as Timing);
  const quality = ((data?.quality ?? "C") as Quality);
  const timingStyle = TIMING_STYLES[timing] ?? TIMING_STYLES.PENDING;
  const qualityStyle = QUALITY_STYLES[quality] ?? QUALITY_STYLES.C;
  const isDown = data?.direction === "DOWN";

  return (
    <div className="rounded-lg border border-border bg-gray-900 p-4">
      {/* Header */}
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-white">Stop Hunt Radar</h2>
        <select
          value={symbol}
          onChange={(e) => { setSymbol(e.target.value); }}
          className="rounded border border-border bg-gray-800 px-2 py-1 text-xs text-gray-300 focus:outline-none focus:ring-1 focus:ring-blue-500"
          aria-label="Select symbol for stop hunt analysis"
        >
          {SYMBOL_OPTIONS.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>

      {/* Error */}
      {isError && (
        <div className="mb-3 flex items-center justify-between rounded bg-red-500/10 px-3 py-2">
          <span className="text-xs text-red-400">
            Failed to load stop hunt data
          </span>
          <button
            type="button"
            onClick={handleRetry}
            className="text-xs text-red-400 underline hover:text-red-300"
            aria-label="Retry loading stop hunt data"
          >
            Retry
          </button>
        </div>
      )}

      {isLoading && <StopHuntSkeleton />}

      {data && (
        <div className="space-y-3">
          {/* Direction + badges */}
          <div className="flex items-center gap-2 flex-wrap">
            <div
              className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 font-bold text-sm ${
                isDown
                  ? "bg-red-500/15 text-red-400 border border-red-500/30"
                  : "bg-green-500/15 text-green-400 border border-green-500/30"
              }`}
            >
              <span aria-hidden="true">{isDown ? "↓" : "↑"}</span>
              <span>{data.direction}</span>
            </div>
            <span
              className={`rounded px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide ${qualityStyle.badge}`}
              aria-label={`Quality grade ${quality}`}
            >
              Grade {quality}
            </span>
            <span
              className={`rounded px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide ${timingStyle.badge}`}
              aria-label={`Timing: ${timingStyle.label}`}
            >
              {timingStyle.label}
            </span>
          </div>

          {/* Price scale */}
          <PriceScale
            currentPrice={data.current_price ?? 0}
            targetPrice={data.target_price}
            direction={data.direction}
          />

          {/* Confidence */}
          <div>
            <div className="mb-1 flex items-center justify-between text-[10px] text-gray-500">
              <span>Confidence</span>
              <span className="font-mono text-gray-300">
                {(data.confidence * 100).toFixed(0)}%
              </span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-gray-700">
              <div
                className={`h-full rounded-full transition-all duration-500 ${
                  data.confidence >= 0.7
                    ? "bg-green-500"
                    : data.confidence >= 0.5
                      ? "bg-yellow-500"
                      : "bg-red-500"
                }`}
                style={{ width: `${data.confidence * 100}%` }}
                role="progressbar"
                aria-valuenow={data.confidence * 100}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label="Stop hunt confidence"
              />
            </div>
          </div>

          {/* Description */}
          <p className="text-xs italic text-gray-400 leading-relaxed">
            {data.description}
          </p>
        </div>
      )}
    </div>
  );
}
