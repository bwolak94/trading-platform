/**
 * OvernightGapWidget
 * Shows overnight/weekend gap risk for positions with countdown to next gap event.
 * Fetches from GET /api/v1/features2/overnight-gap/{symbol}
 */

import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useState } from "react";
import axios from "axios";

// --------------- Types ---------------

interface GapData {
  risk_level: string;
  recommendation: string;
  avg_gap_pct: number;
  max_gap_pct: number;
  gap_exceeds_stop: boolean;
  next_event: string;
  hours_until: number;
  description: string;
}

// --------------- Constants ---------------

type RiskLevel = "LOW" | "MEDIUM" | "HIGH" | "EXTREME";

const RISK_STYLES: Record<
  RiskLevel,
  { border: string; badge: string; text: string; bg: string }
> = {
  LOW: {
    border: "border-green-500/30",
    badge: "bg-green-500/20 text-green-400",
    text: "text-green-400",
    bg: "bg-green-500/5",
  },
  MEDIUM: {
    border: "border-yellow-500/30",
    badge: "bg-yellow-500/20 text-yellow-400",
    text: "text-yellow-400",
    bg: "bg-yellow-500/5",
  },
  HIGH: {
    border: "border-red-500/30",
    badge: "bg-red-500/20 text-red-400",
    text: "text-red-400",
    bg: "bg-red-500/5",
  },
  EXTREME: {
    border: "border-red-500",
    badge: "animate-pulse bg-red-500/30 text-red-300",
    text: "text-red-300",
    bg: "bg-red-500/10",
  },
};

const SYMBOL_OPTIONS = [
  "BTCUSDT",
  "ETHUSDT",
  "SOLUSDT",
  "BNBUSDT",
  "XRPUSDT",
  "ADAUSDT",
  "EURUSD",
  "GBPUSD",
];

// --------------- Countdown hook ---------------

function useHoursCountdown(hoursUntil: number): string {
  const [display, setDisplay] = useState("");

  useEffect(() => {
    const targetMs = Date.now() + hoursUntil * 3_600_000;

    const tick = () => {
      const diff = targetMs - Date.now();
      if (diff <= 0) {
        setDisplay("00:00:00");
        return;
      }
      const h = Math.floor(diff / 3_600_000);
      const m = Math.floor((diff % 3_600_000) / 60_000);
      const s = Math.floor((diff % 60_000) / 1_000);
      setDisplay(
        `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`,
      );
    };

    tick();
    const id = setInterval(tick, 1_000);
    return () => clearInterval(id);
  }, [hoursUntil]);

  return display;
}

// --------------- Fetch helper ---------------

async function fetchOvernightGap(symbol: string): Promise<GapData> {
  const { data } = await axios.get<GapData>(
    `/api/v1/features2/overnight-gap/${symbol}`,
  );
  return data;
}

// --------------- Skeleton ---------------

function GapSkeleton() {
  return (
    <div className="space-y-2" aria-busy="true" aria-label="Loading gap risk data">
      <div className="h-8 w-full animate-pulse rounded bg-white/5" />
      <div className="h-16 animate-pulse rounded bg-white/5" />
      <div className="grid grid-cols-3 gap-2">
        {[...Array(3)].map((_, i) => (
          <div key={i} className="h-12 animate-pulse rounded bg-white/5" />
        ))}
      </div>
    </div>
  );
}

// --------------- Main Component ---------------

export default function OvernightGapWidget() {
  const [symbol, setSymbol] = useState("BTCUSDT");

  const { data, isLoading, isError, refetch } = useQuery<GapData>({
    queryKey: ["overnight-gap", symbol],
    queryFn: () => fetchOvernightGap(symbol),
    refetchInterval: 5 * 60_000,
    retry: 2,
  });

  const handleRetry = useCallback(() => {
    void refetch();
  }, [refetch]);

  const riskLevel = (data?.risk_level ?? "LOW") as RiskLevel;
  const styles = RISK_STYLES[riskLevel] ?? RISK_STYLES.LOW;
  const countdown = useHoursCountdown(data?.hours_until ?? 0);

  return (
    <div className={`rounded-lg border-2 ${styles.border} bg-gray-900 p-4`}>
      {/* Header */}
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold text-white">
            Overnight Gap Risk
          </h2>
          {data && (
            <span
              className={`rounded px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide ${styles.badge}`}
              aria-label={`Risk level: ${riskLevel}`}
            >
              {riskLevel}
            </span>
          )}
        </div>
        <select
          value={symbol}
          onChange={(e) => setSymbol(e.target.value)}
          className="rounded border border-border bg-gray-800 px-2 py-1 text-xs text-gray-300 focus:outline-none focus:ring-1 focus:ring-blue-500"
          aria-label="Select symbol for gap risk"
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
            Failed to load gap risk data
          </span>
          <button
            type="button"
            onClick={handleRetry}
            className="text-xs text-red-400 underline hover:text-red-300"
            aria-label="Retry loading gap risk data"
          >
            Retry
          </button>
        </div>
      )}

      {isLoading && <GapSkeleton />}

      {data && (
        <div className="space-y-3">
          {/* SL too close warning */}
          {data.gap_exceeds_stop && (
            <div
              className="rounded border border-red-500 bg-red-500/10 px-3 py-2"
              role="alert"
              aria-live="assertive"
            >
              <p className="text-xs font-bold text-red-400">
                SL too close to avg gap! — Gap risk exceeds your stop loss distance
              </p>
            </div>
          )}

          {/* Next event countdown */}
          <div className={`rounded border border-border ${styles.bg} px-3 py-2`}>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-500">
                  Next Gap Event
                </p>
                <p className="text-sm font-bold text-gray-200">
                  {data.next_event.replace("_", " ")}
                </p>
              </div>
              <div className="text-right">
                <p className={`font-mono text-xl font-bold ${styles.text}`}>
                  {countdown}
                </p>
                <p className="text-[10px] text-gray-500">until event</p>
              </div>
            </div>
          </div>

          {/* Stats */}
          <div className="grid grid-cols-3 gap-2 text-xs">
            <div className="rounded bg-gray-800/60 px-2 py-1.5 text-center">
              <p className="text-[10px] text-gray-500">Avg Gap</p>
              <p className={`font-mono font-bold ${styles.text}`}>
                {data.avg_gap_pct.toFixed(2)}%
              </p>
            </div>
            <div className="rounded bg-gray-800/60 px-2 py-1.5 text-center">
              <p className="text-[10px] text-gray-500">Max Gap</p>
              <p className="font-mono font-bold text-orange-400">
                {data.max_gap_pct.toFixed(2)}%
              </p>
            </div>
            <div className="rounded bg-gray-800/60 px-2 py-1.5 text-center">
              <p className="text-[10px] text-gray-500">Exceeds SL</p>
              <p
                className={`font-bold ${
                  data.gap_exceeds_stop ? "text-red-400" : "text-green-400"
                }`}
              >
                {data.gap_exceeds_stop ? "YES" : "NO"}
              </p>
            </div>
          </div>

          {/* Recommendation */}
          <div className={`rounded border border-border ${styles.bg} px-3 py-2`}>
            <p className="mb-0.5 text-[10px] font-semibold uppercase tracking-wide text-gray-500">
              Recommendation
            </p>
            <p className={`text-xs font-semibold ${styles.text}`}>
              {data.recommendation}
            </p>
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
