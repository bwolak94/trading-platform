/**
 * PatternPerformancePanel
 * Shows which chart patterns are working right now vs underperforming.
 * Fetches from GET /api/v1/features2/pattern-performance
 */

import { useQuery } from "@tanstack/react-query";
import { useCallback } from "react";
import axios from "axios";

// --------------- Types ---------------

interface PatternData {
  name: string;
  win_rate: number;
  sample: number;
  active: boolean;
  reason?: string;
}

interface PatternResponse {
  patterns: PatternData[];
  updated_at: string;
}

// --------------- Fetch helper ---------------

async function fetchPatternPerformance(): Promise<PatternResponse> {
  const { data } = await axios.get<PatternResponse>(
    "/api/v1/features2/pattern-performance",
  );
  return data;
}

// --------------- Helpers ---------------

function winRateColor(winRate: number, active: boolean): string {
  if (!active) return "text-gray-500";
  if (winRate >= 70) return "text-green-400";
  if (winRate >= 55) return "text-yellow-400";
  return "text-red-400";
}

function winRateBarColor(winRate: number, active: boolean): string {
  if (!active) return "bg-gray-700";
  if (winRate >= 70) return "bg-green-500";
  if (winRate >= 55) return "bg-yellow-500";
  return "bg-red-500";
}

// --------------- Skeleton ---------------

function PatternSkeleton() {
  return (
    <div className="space-y-2" aria-busy="true" aria-label="Loading pattern performance">
      {[...Array(6)].map((_, i) => (
        <div key={i} className="h-10 animate-pulse rounded border border-gray-700 bg-white/5" />
      ))}
    </div>
  );
}

// --------------- Sub-component: Pattern row ---------------

function PatternRow({ pattern }: { pattern: PatternData }) {
  const winRatePct = Math.min(Math.max(pattern.win_rate, 0), 100);

  return (
    <div
      className={`rounded border px-3 py-2 ${
        pattern.active
          ? "border-gray-700/60 bg-gray-800/30 hover:bg-gray-800/50"
          : "border-gray-800 bg-gray-800/10 opacity-70"
      } transition-colors`}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 flex-1 min-w-0">
          <span
            className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-bold uppercase ${
              pattern.active
                ? "bg-green-500/20 text-green-400"
                : "bg-gray-700 text-gray-500"
            }`}
            aria-label={pattern.active ? "Active pattern" : "Inactive pattern"}
          >
            {pattern.active ? "ACTIVE" : "OFF"}
          </span>
          <span
            className={`truncate text-xs font-semibold ${
              pattern.active ? "text-gray-200" : "text-gray-500"
            }`}
          >
            {pattern.name}
          </span>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          <span className="text-[10px] text-gray-500">
            n={pattern.sample}
          </span>
          <span
            className={`font-mono text-xs font-bold ${winRateColor(winRatePct, pattern.active)}`}
          >
            {winRatePct.toFixed(0)}%
          </span>
        </div>
      </div>

      {/* Win rate bar */}
      <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-gray-700">
        <div
          className={`h-full rounded-full transition-all duration-500 ${winRateBarColor(winRatePct, pattern.active)}`}
          style={{ width: `${winRatePct}%` }}
          role="progressbar"
          aria-valuenow={winRatePct}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`Win rate: ${winRatePct.toFixed(0)}%`}
        />
      </div>

      {/* Inactive reason */}
      {!pattern.active && pattern.reason && (
        <p className="mt-1 text-[10px] italic text-gray-600">
          {pattern.reason}
        </p>
      )}
    </div>
  );
}

// --------------- Main Component ---------------

export default function PatternPerformancePanel() {
  const { data, isLoading, isError, refetch, dataUpdatedAt } =
    useQuery<PatternResponse>({
      queryKey: ["pattern-performance"],
      queryFn: fetchPatternPerformance,
      refetchInterval: 5 * 60_000,
      retry: 2,
    });

  const handleRetry = useCallback(() => {
    void refetch();
  }, [refetch]);

  const lastUpdated = dataUpdatedAt
    ? new Date(dataUpdatedAt).toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
      })
    : null;

  // Sort by win rate descending, then split active/inactive
  const sorted = data?.patterns
    ? [...data.patterns].sort((a, b) => b.win_rate - a.win_rate)
    : [];

  const active = sorted.filter((p) => p.active);
  const inactive = sorted.filter((p) => !p.active);

  return (
    <div className="rounded-lg border border-border bg-gray-900 p-4">
      {/* Header */}
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-white">
            Pattern Performance
          </h2>
          {lastUpdated && (
            <p className="text-[10px] text-gray-500">
              Last updated {lastUpdated}
            </p>
          )}
        </div>
        {data && (
          <div className="flex items-center gap-2 text-[10px] text-gray-500">
            <span className="text-green-400 font-semibold">
              {active.length} active
            </span>
            <span>/</span>
            <span className="text-gray-500">{inactive.length} disabled</span>
          </div>
        )}
      </div>

      {/* Error */}
      {isError && (
        <div className="mb-3 flex items-center justify-between rounded bg-red-500/10 px-3 py-2">
          <span className="text-xs text-red-400">
            Failed to load pattern data
          </span>
          <button
            type="button"
            onClick={handleRetry}
            className="text-xs text-red-400 underline hover:text-red-300"
            aria-label="Retry loading pattern performance"
          >
            Retry
          </button>
        </div>
      )}

      {isLoading && <PatternSkeleton />}

      {data && (
        <div className="space-y-4">
          {/* Active patterns */}
          {active.length > 0 && (
            <div>
              <p className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-green-400">
                Active Patterns
              </p>
              <div className="space-y-1.5">
                {active.map((p) => (
                  <PatternRow key={p.name} pattern={p} />
                ))}
              </div>
            </div>
          )}

          {/* Inactive patterns */}
          {inactive.length > 0 && (
            <div>
              <p className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-gray-600">
                Disabled Patterns
              </p>
              <div className="space-y-1.5">
                {inactive.map((p) => (
                  <PatternRow key={p.name} pattern={p} />
                ))}
              </div>
            </div>
          )}

          {sorted.length === 0 && (
            <p className="py-4 text-center text-xs text-gray-500">
              No pattern data available
            </p>
          )}
        </div>
      )}
    </div>
  );
}
