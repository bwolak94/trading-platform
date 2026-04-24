/**
 * ConfidencePercentileWidget
 * Shows how a signal's confidence ranks vs historical distribution.
 * Fetches from GET /api/v1/features/confidence-percentile?confidence={val}&symbol={sym}
 */

import { useQuery } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import axios from "axios";

// --------------- Types ---------------

interface PercentileData {
  signal_confidence: number;
  percentile: number;
  percentile_label: string;
  historical_count: number;
  historical_mean: number;
  historical_p75: number;
  historical_p90: number;
  is_exceptional: boolean;
  recommendation: string;
}

// --------------- Constants ---------------

const SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"];

// --------------- Helpers ---------------

function getPercentileStyle(percentile: number, isExceptional: boolean): {
  badge: string;
  label: string;
  color: string;
  barColor: string;
} {
  if (isExceptional || percentile >= 95) {
    return {
      badge: "bg-purple-500/20 text-purple-300 border-purple-500/30",
      label: "TOP 5%",
      color: "text-purple-300",
      barColor: "bg-purple-500",
    };
  }
  if (percentile >= 85) {
    return {
      badge: "bg-green-500/20 text-green-400 border-green-500/30",
      label: "TOP 15%",
      color: "text-green-400",
      barColor: "bg-green-500",
    };
  }
  if (percentile >= 50) {
    return {
      badge: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
      label: "AVERAGE",
      color: "text-yellow-400",
      barColor: "bg-yellow-500",
    };
  }
  return {
    badge: "bg-gray-700 text-gray-400 border-gray-600",
    label: "BELOW AVERAGE",
    color: "text-gray-400",
    barColor: "bg-gray-500",
  };
}

async function fetchConfidencePercentile(confidence: number, symbol: string): Promise<PercentileData> {
  const { data } = await axios.get<PercentileData>("/api/v1/features/confidence-percentile", {
    params: { confidence, symbol },
  });
  return data;
}

// --------------- Distribution Curve (simplified bar chart) ---------------

interface DistributionBarProps {
  data: PercentileData;
}

function DistributionBars({ data }: DistributionBarProps) {
  // Simulate a rough distribution with 5 buckets
  const buckets = [
    { label: "<50%", pct: 20, isActive: data.signal_confidence < 50 },
    { label: "50-65%", pct: 35, isActive: data.signal_confidence >= 50 && data.signal_confidence < 65 },
    { label: "65-75%", pct: 25, isActive: data.signal_confidence >= 65 && data.signal_confidence < 75 },
    { label: "75-85%", pct: 12, isActive: data.signal_confidence >= 75 && data.signal_confidence < 85 },
    { label: ">85%", pct: 8, isActive: data.signal_confidence >= 85 },
  ];

  return (
    <div
      className="flex items-end gap-1 h-16"
      aria-label="Historical confidence distribution"
      role="img"
    >
      {buckets.map(({ label, pct, isActive }) => (
        <div key={label} className="flex flex-1 flex-col items-center gap-0.5">
          <div
            className={`w-full rounded-t transition-all ${isActive ? "bg-blue-500" : "bg-gray-700"}`}
            style={{ height: `${pct * 0.6}px` }}
            aria-hidden="true"
          />
          <span className={`text-[9px] ${isActive ? "text-blue-400" : "text-gray-600"}`}>{label}</span>
        </div>
      ))}
    </div>
  );
}

// --------------- Skeleton ---------------

function PercentileSkeleton() {
  return (
    <div className="space-y-3" aria-busy="true" aria-label="Loading percentile data">
      <div className="h-6 w-32 animate-pulse rounded bg-white/5" />
      <div className="h-16 animate-pulse rounded bg-white/5" />
      {[...Array(3)].map((_, i) => (
        <div key={i} className="h-4 animate-pulse rounded bg-white/5" />
      ))}
    </div>
  );
}

// --------------- Main Component ---------------

export default function ConfidencePercentileWidget() {
  const [symbol, setSymbol] = useState("BTCUSDT");
  const [confidence, setConfidence] = useState(75);

  const { data, isLoading, isError, refetch, dataUpdatedAt } = useQuery<PercentileData>({
    queryKey: ["confidence-percentile", symbol, confidence],
    queryFn: () => fetchConfidencePercentile(confidence, symbol),
    refetchInterval: 60_000,
    retry: 2,
  });

  const handleRefetch = useCallback(() => { void refetch(); }, [refetch]);
  const lastUpdated = dataUpdatedAt ? new Date(dataUpdatedAt).toLocaleTimeString() : null;

  const style = data ? getPercentileStyle(data.percentile, data.is_exceptional) : null;

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-white">Confidence Percentile</h2>
          {lastUpdated && (
            <p className="mt-0.5 text-xs text-gray-500">Updated: {lastUpdated}</p>
          )}
        </div>
        <div className="flex items-center gap-2">
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
            aria-label="Refresh percentile data"
          >
            Refresh
          </button>
        </div>
      </div>

      {/* Confidence input */}
      <div className="mb-4">
        <label htmlFor="confidence-value" className="mb-1 block text-xs text-gray-400">
          Signal Confidence to Evaluate
        </label>
        <div className="flex items-center gap-3">
          <input
            id="confidence-value"
            type="range"
            min={0}
            max={100}
            step={1}
            value={confidence}
            onChange={(e) => setConfidence(parseInt(e.target.value))}
            className="flex-1 accent-blue-500"
            aria-label={`Signal confidence: ${confidence}%`}
          />
          <span className="w-12 font-mono text-sm font-bold text-blue-400 text-right">
            {confidence}%
          </span>
        </div>
      </div>

      {/* Error */}
      {isError && (
        <div className="mb-3 flex items-center justify-between rounded bg-red-500/10 px-3 py-2">
          <span className="text-xs text-red-400">Failed to load percentile data</span>
          <button type="button" onClick={handleRefetch} className="text-xs text-red-400 underline hover:text-red-300">
            Retry
          </button>
        </div>
      )}

      {isLoading && <PercentileSkeleton />}

      {data && style && (
        <div className="space-y-4">
          {/* Rank badge */}
          <div className="flex items-center justify-between">
            <span className={`rounded border px-3 py-1 text-sm font-bold ${style.badge}`}>
              {style.label}
            </span>
            <div className="text-right">
              <p className={`font-mono text-xl font-bold ${style.color}`}>
                {data.percentile.toFixed(0)}th
              </p>
              <p className="text-[10px] text-gray-500">percentile</p>
            </div>
          </div>

          {/* Distribution visualization */}
          <div className="rounded border border-border bg-gray-800/60 p-3">
            <p className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-gray-500">
              Historical Distribution ({data.historical_count.toLocaleString()} signals)
            </p>
            <DistributionBars data={data} />

            {/* Marker line */}
            <div className="mt-2 flex items-center justify-between text-[10px] text-gray-500">
              <span>Your signal is highlighted</span>
              <span className="flex items-center gap-1">
                <span className="inline-block h-2 w-2 rounded-full bg-blue-500" aria-hidden="true" />
                {data.signal_confidence.toFixed(0)}%
              </span>
            </div>
          </div>

          {/* Stats */}
          <div className="grid grid-cols-3 gap-2">
            <div className="rounded bg-gray-800/60 p-2 text-center">
              <p className="text-[10px] text-gray-500">Mean</p>
              <p className="font-mono text-xs font-semibold text-gray-200">
                {data.historical_mean.toFixed(0)}%
              </p>
            </div>
            <div className="rounded bg-gray-800/60 p-2 text-center">
              <p className="text-[10px] text-gray-500">P75</p>
              <p className="font-mono text-xs font-semibold text-gray-200">
                {data.historical_p75.toFixed(0)}%
              </p>
            </div>
            <div className="rounded bg-gray-800/60 p-2 text-center">
              <p className="text-[10px] text-gray-500">P90</p>
              <p className="font-mono text-xs font-semibold text-gray-200">
                {data.historical_p90.toFixed(0)}%
              </p>
            </div>
          </div>

          {/* Percentile bar */}
          <div>
            <div className="mb-1 flex items-center justify-between text-[10px] text-gray-500">
              <span>0th percentile</span>
              <span>100th percentile</span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-gray-700">
              <div
                className={`h-full rounded-full transition-all duration-500 ${style.barColor}`}
                style={{ width: `${data.percentile}%` }}
                role="progressbar"
                aria-valuenow={data.percentile}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label={`Percentile rank: ${data.percentile.toFixed(0)}%`}
              />
            </div>
          </div>

          {/* Recommendation */}
          <div className="rounded bg-gray-800/60 border border-border px-3 py-2">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-500 mb-0.5">
              Recommendation
            </p>
            <p className={`text-xs font-medium ${style.color}`}>{data.recommendation}</p>
          </div>
        </div>
      )}
    </div>
  );
}
