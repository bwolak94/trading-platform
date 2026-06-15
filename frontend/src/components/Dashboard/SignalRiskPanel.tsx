/**
 * SignalRiskPanel
 * Shows signal invalidation / "what could go wrong" risk factors.
 * Fetches from GET /api/v1/features2/signal-invalidation/{symbol}
 */

import { useQuery } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import axios from "axios";

// --------------- Types ---------------

interface RiskFactor {
  risk_name: string;
  severity: "HIGH" | "MEDIUM" | "LOW";
  description: string;
  probability: number;
  monitor_price: number | null;
}

interface InvalidationData {
  symbol: string;
  overall_risk: "HIGH" | "MEDIUM" | "LOW";
  summary: string;
  risk_factors: RiskFactor[];
}

// --------------- Constants ---------------

type Severity = "HIGH" | "MEDIUM" | "LOW";

const SEVERITY_STYLES: Record<
  Severity,
  { badge: string; border: string; bg: string }
> = {
  HIGH: {
    badge: "bg-red-500/20 text-red-400 border border-red-500/30",
    border: "border-red-500/30",
    bg: "bg-red-500/5",
  },
  MEDIUM: {
    badge: "bg-yellow-500/20 text-yellow-400 border border-yellow-500/30",
    border: "border-yellow-500/30",
    bg: "bg-yellow-500/5",
  },
  LOW: {
    badge: "bg-gray-700 text-gray-400 border border-gray-600",
    border: "border-gray-700",
    bg: "bg-gray-800/40",
  },
};

const OVERALL_BORDER: Record<Severity, string> = {
  HIGH: "border-red-500",
  MEDIUM: "border-yellow-500",
  LOW: "border-gray-600",
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

async function fetchInvalidation(symbol: string): Promise<InvalidationData> {
  const { data } = await axios.get<InvalidationData>(
    `/api/v1/features2/signal-invalidation/${symbol}`,
  );
  return data;
}

// --------------- Skeleton ---------------

function RiskSkeleton() {
  return (
    <div className="space-y-2" aria-busy="true" aria-label="Loading risk factors">
      {[...Array(4)].map((_, i) => (
        <div key={i} className="h-16 animate-pulse rounded border border-gray-700 bg-white/5" />
      ))}
    </div>
  );
}

// --------------- Sub-components ---------------

function SeverityBadge({ severity }: { severity: Severity }) {
  const style = SEVERITY_STYLES[severity] ?? SEVERITY_STYLES.LOW;
  return (
    <span
      className={`rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide ${style.badge}`}
    >
      {severity}
    </span>
  );
}

// --------------- Main Component ---------------

export default function SignalRiskPanel() {
  const [symbol, setSymbol] = useState("BTCUSDT");

  const { data, isLoading, isError, refetch } = useQuery<InvalidationData>({
    queryKey: ["signal-invalidation", symbol],
    queryFn: () => fetchInvalidation(symbol),
    refetchInterval: 60_000,
    retry: 2,
  });

  const handleRetry = useCallback(() => {
    void refetch();
  }, [refetch]);

  const overallRisk = (data?.overall_risk ?? "LOW") as Severity;
  const overallStyle = SEVERITY_STYLES[overallRisk];
  const borderColor = OVERALL_BORDER[overallRisk];

  // Sort: HIGH first, then MEDIUM, then LOW
  const severityOrder: Record<Severity, number> = { HIGH: 0, MEDIUM: 1, LOW: 2 };
  const sorted = data?.risk_factors
    ? [...data.risk_factors].sort(
        (a, b) =>
          severityOrder[a.severity as Severity] -
          severityOrder[b.severity as Severity],
      )
    : [];

  const topRisk = sorted[0];

  return (
    <div className={`rounded-lg border-2 ${borderColor} bg-gray-900 p-4`}>
      {/* Header */}
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold text-white">
            Signal Risk Factors
          </h2>
          {data && <SeverityBadge severity={overallRisk} />}
        </div>
        <select
          value={symbol}
          onChange={(e) => { setSymbol(e.target.value); }}
          className="rounded border border-border bg-gray-800 px-2 py-1 text-xs text-gray-300 focus:outline-none focus:ring-1 focus:ring-blue-500"
          aria-label="Select symbol"
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
          <span className="text-xs text-red-400">Failed to load risk factors</span>
          <button
            type="button"
            onClick={handleRetry}
            className="text-xs text-red-400 underline hover:text-red-300"
            aria-label="Retry loading risk factors"
          >
            Retry
          </button>
        </div>
      )}

      {isLoading && <RiskSkeleton />}

      {data && (
        <div className="space-y-3">
          {/* Top risk highlight */}
          {topRisk && (
            <div
              className={`rounded border ${overallStyle.border} ${overallStyle.bg} px-3 py-2`}
            >
              <div className="mb-1 flex items-center gap-2">
                <span className="text-[10px] font-semibold uppercase tracking-wide text-gray-500">
                  Top Risk
                </span>
                <SeverityBadge severity={topRisk.severity as Severity} />
              </div>
              <p className="text-sm font-bold text-gray-100">
                {topRisk.risk_name}
              </p>
              <p className="mt-0.5 text-xs text-gray-400">
                {topRisk.description}
              </p>
              {topRisk.monitor_price !== null && (
                <p className="mt-1 text-xs">
                  <span className="text-gray-500">Watch level: </span>
                  <span className="font-mono font-bold text-gray-200">
                    {topRisk.monitor_price.toLocaleString()}
                  </span>
                </p>
              )}
            </div>
          )}

          {/* Remaining risk factors */}
          <div className="space-y-2">
            {sorted.slice(1).map((factor) => {
              const sev = factor.severity as Severity;
              const style = SEVERITY_STYLES[sev] ?? SEVERITY_STYLES.LOW;
              return (
                <div
                  key={factor.risk_name}
                  className={`rounded border ${style.border} ${style.bg} px-3 py-2`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2 flex-1 min-w-0">
                      <SeverityBadge severity={sev} />
                      <span className="truncate text-xs font-semibold text-gray-200">
                        {factor.risk_name}
                      </span>
                    </div>
                    <span className="shrink-0 font-mono text-xs text-gray-400">
                      {(factor.probability * 100).toFixed(0)}%
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-gray-400">
                    {factor.description}
                  </p>
                  {factor.monitor_price !== null && (
                    <p className="mt-0.5 text-[10px] text-gray-500">
                      Watch:{" "}
                      <span className="font-mono text-gray-300">
                        {factor.monitor_price.toLocaleString()}
                      </span>
                    </p>
                  )}
                </div>
              );
            })}
          </div>

          {/* Summary */}
          {data.summary && (
            <p className="text-xs italic text-gray-500 leading-relaxed border-t border-border pt-2">
              {data.summary}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
