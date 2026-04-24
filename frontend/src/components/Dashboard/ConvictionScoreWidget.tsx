/**
 * ConvictionScoreWidget
 * Displays pre-entry conviction score with grade badge, progress bar, and criteria checklist.
 * Fetches from GET /api/v1/features2/pre-entry-score/{symbol}
 */

import { useQuery } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import axios from "axios";

// --------------- Types ---------------

interface ConvictionData {
  total_score: number;
  grade: string;
  criteria_passed: string[];
  criteria_failed: string[];
  should_emit: boolean;
  checklist_text: string;
}

// --------------- Constants ---------------

type Grade = "A+" | "A" | "B" | "C" | "F";

const GRADE_STYLES: Record<
  Grade,
  { badge: string; bar: string; text: string }
> = {
  "A+": {
    badge: "bg-green-500/20 text-green-400 border border-green-500/40",
    bar: "bg-green-500",
    text: "text-green-400",
  },
  A: {
    badge: "bg-green-500/15 text-green-400 border border-green-500/30",
    bar: "bg-green-400",
    text: "text-green-400",
  },
  B: {
    badge: "bg-yellow-500/20 text-yellow-400 border border-yellow-500/40",
    bar: "bg-yellow-500",
    text: "text-yellow-400",
  },
  C: {
    badge: "bg-orange-500/20 text-orange-400 border border-orange-500/40",
    bar: "bg-orange-500",
    text: "text-orange-400",
  },
  F: {
    badge: "bg-red-500/20 text-red-400 border border-red-500/40",
    bar: "bg-red-500",
    text: "text-red-400",
  },
};

const DEFAULT_GRADE_STYLE = GRADE_STYLES.F;

const SYMBOL_OPTIONS = [
  "BTCUSDT",
  "ETHUSDT",
  "SOLUSDT",
  "BNBUSDT",
  "XRPUSDT",
  "ADAUSDT",
];

// --------------- Helpers ---------------

function gradeFromScore(score: number): Grade {
  if (score >= 9) return "A+";
  if (score >= 8) return "A";
  if (score >= 6) return "B";
  if (score >= 4) return "C";
  return "F";
}

function getGradeStyle(grade: string) {
  const normalized = grade.toUpperCase() as Grade;
  return GRADE_STYLES[normalized] ?? DEFAULT_GRADE_STYLE;
}

async function fetchConvictionScore(symbol: string): Promise<ConvictionData> {
  const { data } = await axios.get<ConvictionData>(
    `/api/v1/features2/pre-entry-score/${symbol}`,
  );
  return data;
}

// --------------- Skeleton ---------------

function ConvictionSkeleton() {
  return (
    <div className="space-y-3" aria-busy="true" aria-label="Loading conviction score">
      <div className="flex items-center justify-between">
        <div className="h-10 w-20 animate-pulse rounded bg-white/5" />
        <div className="h-8 w-14 animate-pulse rounded bg-white/5" />
      </div>
      <div className="h-3 w-full animate-pulse rounded bg-white/5" />
      <div className="space-y-2">
        {[...Array(5)].map((_, i) => (
          <div key={i} className="h-4 w-full animate-pulse rounded bg-white/5" />
        ))}
      </div>
    </div>
  );
}

// --------------- Main Component ---------------

export default function ConvictionScoreWidget() {
  const [symbol, setSymbol] = useState("BTCUSDT");

  const { data, isLoading, isError, refetch } = useQuery<ConvictionData>({
    queryKey: ["conviction-score", symbol],
    queryFn: () => fetchConvictionScore(symbol),
    refetchInterval: 60_000,
    retry: 2,
  });

  const handleRetry = useCallback(() => {
    void refetch();
  }, [refetch]);

  const displayGrade = data?.grade ?? (data ? gradeFromScore(data.total_score) : "F");
  const gradeStyle = data ? getGradeStyle(displayGrade) : DEFAULT_GRADE_STYLE;
  const scoreFraction = data ? Math.min(data.total_score / 10, 1) : 0;
  const isHighConviction = (data?.total_score ?? 0) >= 8;

  return (
    <div className="rounded-lg border border-border bg-gray-900 p-4">
      {/* Header */}
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-white">Conviction Score</h2>
        <select
          value={symbol}
          onChange={(e) => setSymbol(e.target.value)}
          className="rounded border border-border bg-gray-800 px-2 py-1 text-xs text-gray-300 focus:outline-none focus:ring-1 focus:ring-blue-500"
          aria-label="Select symbol for conviction score"
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
          <span className="text-xs text-red-400">Failed to load score</span>
          <button
            type="button"
            onClick={handleRetry}
            className="text-xs text-red-400 underline hover:text-red-300"
            aria-label="Retry loading conviction score"
          >
            Retry
          </button>
        </div>
      )}

      {isLoading && <ConvictionSkeleton />}

      {data && (
        <div className="space-y-3">
          {/* HIGH CONVICTION banner */}
          {isHighConviction && (
            <div
              className="rounded border border-green-500/40 bg-green-500/10 px-3 py-1.5 text-center"
              role="status"
              aria-live="polite"
            >
              <span className="text-xs font-bold uppercase tracking-widest text-green-400">
                High Conviction
              </span>
            </div>
          )}

          {/* Score + grade */}
          <div className="flex items-center justify-between">
            <div>
              <span
                className={`font-mono text-4xl font-bold ${gradeStyle.text}`}
              >
                {data.total_score.toFixed(1)}
              </span>
              <span className="ml-1 text-lg text-gray-500">/10</span>
            </div>
            <span
              className={`rounded-lg px-3 py-1.5 text-xl font-bold ${gradeStyle.badge}`}
              aria-label={`Grade ${displayGrade}`}
            >
              {displayGrade}
            </span>
          </div>

          {/* Progress bar */}
          <div
            className="h-3 w-full overflow-hidden rounded-full bg-gray-700"
            role="progressbar"
            aria-valuenow={data.total_score}
            aria-valuemin={0}
            aria-valuemax={10}
            aria-label="Conviction score progress"
          >
            <div
              className={`h-full rounded-full transition-all duration-500 ${gradeStyle.bar}`}
              style={{ width: `${scoreFraction * 100}%` }}
            />
          </div>

          {/* Checklist */}
          <div className="space-y-1.5">
            {data.criteria_passed.map((criterion) => (
              <div key={criterion} className="flex items-start gap-2">
                <span
                  className="mt-0.5 shrink-0 text-green-400"
                  aria-hidden="true"
                >
                  ✓
                </span>
                <span className="text-xs text-green-300">{criterion}</span>
              </div>
            ))}
            {data.criteria_failed.map((criterion) => (
              <div key={criterion} className="flex items-start gap-2">
                <span
                  className="mt-0.5 shrink-0 text-red-400"
                  aria-hidden="true"
                >
                  ✗
                </span>
                <span className="text-xs text-red-300/80">{criterion}</span>
              </div>
            ))}
          </div>

          {/* Summary text */}
          {data.checklist_text && (
            <p className="rounded bg-gray-800/60 px-2 py-1.5 text-[10px] italic text-gray-400 leading-relaxed">
              {data.checklist_text}
            </p>
          )}

          {/* Emit recommendation */}
          <div className="flex items-center gap-2">
            <span
              className={`rounded px-2 py-0.5 text-[10px] font-bold uppercase ${
                data.should_emit
                  ? "bg-green-500/20 text-green-400"
                  : "bg-gray-700 text-gray-400"
              }`}
            >
              {data.should_emit ? "Signal Recommended" : "Do Not Enter"}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
