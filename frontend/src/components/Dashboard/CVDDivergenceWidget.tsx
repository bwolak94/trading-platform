/**
 * CVDDivergenceWidget
 * Shows CVD vs price divergence alert with visual trend indicators.
 * Fetches from GET /api/v1/features2/cvd-divergence/{symbol}
 */

import { useQuery } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import axios from "axios";

// --------------- Types ---------------

interface CVDData {
  divergence_type: string;
  direction: string;
  confidence: number;
  candles: number;
  description: string;
  price_trend: number[];
  cvd_trend: number[];
}

// --------------- Constants ---------------

const SYMBOL_OPTIONS = [
  "BTCUSDT",
  "ETHUSDT",
  "SOLUSDT",
  "BNBUSDT",
  "XRPUSDT",
  "ADAUSDT",
];

// --------------- Helpers ---------------

function normalizeSeries(values: number[]): number[] {
  if (values.length === 0) return [];
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min;
  if (range === 0) return values.map(() => 0.5);
  return values.map((v) => (v - min) / range);
}

// --------------- Sub-component: Sparkline ---------------

function Sparkline({
  values,
  color,
  label,
}: {
  values: number[];
  color: string;
  label: string;
}) {
  const normalized = normalizeSeries(values);
  const width = 120;
  const height = 40;
  const count = normalized.length;

  if (count < 2) {
    return (
      <div
        className="flex h-10 w-[120px] items-center justify-center rounded bg-gray-800/60 text-[10px] text-gray-500"
        aria-label={`${label}: insufficient data`}
      >
        No data
      </div>
    );
  }

  const points = normalized.map((v, i) => {
    const x = (i / (count - 1)) * width;
    const y = height - v * height;
    return `${x},${y}`;
  });
  const polyline = points.join(" ");

  return (
    <div>
      <p className="mb-0.5 text-center text-[10px] text-gray-500">{label}</p>
      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        aria-label={`${label} sparkline`}
        role="img"
        className="rounded"
      >
        <rect width={width} height={height} fill="rgba(255,255,255,0.03)" rx="3" />
        <polyline
          points={polyline}
          fill="none"
          stroke={color}
          strokeWidth="1.5"
          strokeLinejoin="round"
          strokeLinecap="round"
        />
      </svg>
    </div>
  );
}

// --------------- Fetch helper ---------------

async function fetchCVDDivergence(symbol: string): Promise<CVDData> {
  const { data } = await axios.get<CVDData>(
    `/api/v1/features2/cvd-divergence/${symbol}`,
  );
  return data;
}

// --------------- Skeleton ---------------

function CVDSkeleton() {
  return (
    <div className="space-y-3" aria-busy="true" aria-label="Loading CVD divergence data">
      <div className="flex gap-4">
        <div className="h-10 w-[120px] animate-pulse rounded bg-white/5" />
        <div className="h-10 w-[120px] animate-pulse rounded bg-white/5" />
      </div>
      <div className="h-14 animate-pulse rounded bg-white/5" />
      <div className="h-4 animate-pulse rounded bg-white/5" />
    </div>
  );
}

// --------------- Main Component ---------------

export default function CVDDivergenceWidget() {
  const [symbol, setSymbol] = useState("BTCUSDT");

  const { data, isLoading, isError, refetch } = useQuery<CVDData>({
    queryKey: ["cvd-divergence", symbol],
    queryFn: () => fetchCVDDivergence(symbol),
    refetchInterval: 60_000,
    retry: 2,
  });

  const handleRetry = useCallback(() => {
    void refetch();
  }, [refetch]);

  const isDivergent =
    data &&
    data.divergence_type !== "NONE" &&
    data.divergence_type !== "none";

  const isBearish =
    isDivergent && data.direction === "BEARISH";
  const isBullish =
    isDivergent && data.direction === "BULLISH";

  return (
    <div
      className={`rounded-lg border bg-gray-900 p-4 ${
        isBearish
          ? "border-red-500/50"
          : isBullish
            ? "border-green-500/50"
            : "border-border"
      }`}
    >
      {/* Header */}
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-white">CVD Divergence</h2>
        <select
          value={symbol}
          onChange={(e) => { setSymbol(e.target.value); }}
          className="rounded border border-border bg-gray-800 px-2 py-1 text-xs text-gray-300 focus:outline-none focus:ring-1 focus:ring-blue-500"
          aria-label="Select symbol for CVD divergence"
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
            Failed to load CVD data
          </span>
          <button
            type="button"
            onClick={handleRetry}
            className="text-xs text-red-400 underline hover:text-red-300"
            aria-label="Retry loading CVD data"
          >
            Retry
          </button>
        </div>
      )}

      {isLoading && <CVDSkeleton />}

      {data && (
        <div className="space-y-3">
          {/* Alert banner */}
          {isBearish && (
            <div
              className="rounded border border-red-500/40 bg-red-500/10 px-3 py-2 text-center"
              role="alert"
              aria-live="polite"
            >
              <p className="text-sm font-bold uppercase tracking-wide text-red-400">
                Distribution Detected
              </p>
              <p className="text-[10px] text-red-300/70">
                CVD falling while price rising — bearish divergence
              </p>
            </div>
          )}

          {isBullish && (
            <div
              className="rounded border border-green-500/40 bg-green-500/10 px-3 py-2 text-center"
              role="alert"
              aria-live="polite"
            >
              <p className="text-sm font-bold uppercase tracking-wide text-green-400">
                Accumulation Detected
              </p>
              <p className="text-[10px] text-green-300/70">
                CVD rising while price falling — bullish divergence
              </p>
            </div>
          )}

          {!isDivergent && (
            <div className="rounded bg-gray-800/60 px-3 py-2 text-center">
              <p className="text-xs text-gray-400">
                No divergence detected — price and CVD aligned
              </p>
            </div>
          )}

          {/* Sparklines */}
          {(data.price_trend?.length > 1 || data.cvd_trend?.length > 1) && (
            <div className="flex items-end justify-center gap-6">
              <Sparkline
                values={data.price_trend ?? []}
                color={isBearish ? "#ef4444" : isBullish ? "#22c55e" : "#6b7280"}
                label="Price Trend"
              />
              <Sparkline
                values={data.cvd_trend ?? []}
                color={isBearish ? "#f97316" : isBullish ? "#3b82f6" : "#6b7280"}
                label="CVD Trend"
              />
            </div>
          )}

          {/* Stats */}
          {isDivergent && (
            <div className="grid grid-cols-3 gap-2 text-xs">
              <div className="rounded bg-gray-800/60 px-2 py-1.5 text-center">
                <p className="text-[10px] text-gray-500">Type</p>
                <p className="font-semibold text-gray-200 capitalize">
                  {data.divergence_type.replace("_", " ").toLowerCase()}
                </p>
              </div>
              <div className="rounded bg-gray-800/60 px-2 py-1.5 text-center">
                <p className="text-[10px] text-gray-500">Confidence</p>
                <p
                  className={`font-semibold ${
                    data.confidence >= 0.7
                      ? "text-green-400"
                      : data.confidence >= 0.5
                        ? "text-yellow-400"
                        : "text-gray-300"
                  }`}
                >
                  {(data.confidence * 100).toFixed(0)}%
                </p>
              </div>
              <div className="rounded bg-gray-800/60 px-2 py-1.5 text-center">
                <p className="text-[10px] text-gray-500">Candles</p>
                <p className="font-semibold text-gray-200">{data.candles}</p>
              </div>
            </div>
          )}

          {/* Description */}
          <p className="text-xs italic text-gray-400 leading-relaxed">
            {data.description}
          </p>
        </div>
      )}
    </div>
  );
}
