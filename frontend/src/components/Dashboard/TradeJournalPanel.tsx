/**
 * TradeJournalPanel
 * AI-powered trade journal with pattern insights and improvement actions.
 * Fetches from GET /api/v1/features/trade-journal (with date range params)
 */

import { useQuery } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import axios from "axios";

// --------------- Types ---------------

interface JournalInsight {
  pattern_type: string;
  description: string;
  win_rate: number;
  sample_size: number;
  recommendation: string;
  severity: string;
}

interface JournalData {
  period_start: string;
  period_end: string;
  total_trades: number;
  win_rate: number;
  avg_return_pct: number;
  best_setup: string;
  worst_setup: string;
  key_insights: JournalInsight[];
  improvement_actions: string[];
  performance_trend: string;
}

type PeriodDays = 7 | 30 | 90;

// --------------- Helpers ---------------

type InsightSeverity = "CRITICAL" | "IMPORTANT" | "INFO";

function getSeverityStyle(severity: string): {
  badge: string;
  border: string;
} {
  const s = severity.toUpperCase() as InsightSeverity;
  if (s === "CRITICAL") return { badge: "bg-red-500/20 text-red-400", border: "border-red-500/30" };
  if (s === "IMPORTANT") return { badge: "bg-yellow-500/20 text-yellow-400", border: "border-yellow-500/30" };
  return { badge: "bg-blue-500/20 text-blue-400", border: "border-blue-500/20" };
}

function getTrendStyle(trend: string): { text: string; arrow: string } {
  const t = trend.toUpperCase();
  if (t.includes("IMPROVING") || t.includes("UP")) return { text: "text-green-400", arrow: "▲" };
  if (t.includes("DECLINING") || t.includes("DOWN")) return { text: "text-red-400", arrow: "▼" };
  return { text: "text-gray-400", arrow: "●" };
}

function getWinRateColor(wr: number): string {
  if (wr >= 0.6) return "text-green-400";
  if (wr >= 0.45) return "text-yellow-400";
  return "text-red-400";
}

function formatDateRange(start: string, end: string): string {
  const s = new Date(start).toLocaleDateString([], { month: "short", day: "numeric" });
  const e = new Date(end).toLocaleDateString([], { month: "short", day: "numeric" });
  return `${s} – ${e}`;
}

async function fetchJournal(days: PeriodDays): Promise<JournalData> {
  const endDate = new Date().toISOString().split("T")[0];
  const startDate = new Date(Date.now() - days * 24 * 60 * 60 * 1000)
    .toISOString()
    .split("T")[0];
  const { data } = await axios.get<JournalData>("/api/v1/features/trade-journal", {
    params: { start_date: startDate, end_date: endDate },
  });
  return data;
}

// --------------- Sub-components ---------------

interface InsightCardProps {
  insight: JournalInsight;
}

function InsightCard({ insight }: InsightCardProps) {
  const style = getSeverityStyle(insight.severity);

  return (
    <div className={`rounded border ${style.border} bg-gray-800/50 px-3 py-3 space-y-1.5`}>
      <div className="flex items-start justify-between gap-2">
        <span className="text-xs font-medium text-gray-200">{insight.pattern_type}</span>
        <span className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-bold uppercase ${style.badge}`}>
          {insight.severity}
        </span>
      </div>
      <p className="text-[11px] text-gray-400 leading-relaxed">{insight.description}</p>
      <div className="flex items-center justify-between text-[10px] text-gray-500">
        <span>
          WR: <span className={`font-mono font-bold ${getWinRateColor(insight.win_rate)}`}>
            {(insight.win_rate * 100).toFixed(0)}%
          </span>
        </span>
        <span>n={insight.sample_size}</span>
      </div>
      {insight.recommendation && (
        <p className="text-[10px] text-blue-400 italic">{insight.recommendation}</p>
      )}
    </div>
  );
}

// --------------- Skeleton ---------------

function JournalSkeleton() {
  return (
    <div className="space-y-3" aria-busy="true" aria-label="Loading journal data">
      <div className="h-16 animate-pulse rounded bg-white/5" />
      {[...Array(3)].map((_, i) => (
        <div key={i} className="h-20 animate-pulse rounded bg-white/5" />
      ))}
      <div className="h-24 animate-pulse rounded bg-white/5" />
    </div>
  );
}

// --------------- Main Component ---------------

export default function TradeJournalPanel() {
  const [period, setPeriod] = useState<PeriodDays>(30);

  const { data, isLoading, isError, refetch, dataUpdatedAt } = useQuery<JournalData>({
    queryKey: ["trade-journal", period],
    queryFn: () => fetchJournal(period),
    refetchInterval: 5 * 60_000,
    retry: 2,
  });

  const handleRefetch = useCallback(() => { void refetch(); }, [refetch]);
  const lastUpdated = dataUpdatedAt ? new Date(dataUpdatedAt).toLocaleTimeString() : null;

  const trendStyle = data ? getTrendStyle(data.performance_trend) : null;

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-white">Trade Journal</h2>
          {lastUpdated && (
            <p className="mt-0.5 text-xs text-gray-500">Updated: {lastUpdated}</p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <select
            value={period}
            onChange={(e) => setPeriod(parseInt(e.target.value) as PeriodDays)}
            className="rounded border border-border bg-gray-800 px-2 py-1 text-xs text-gray-300 focus:outline-none focus:ring-1 focus:ring-blue-500"
            aria-label="Select period"
          >
            <option value={7}>Last 7d</option>
            <option value={30}>Last 30d</option>
            <option value={90}>Last 90d</option>
          </select>
          <button
            type="button"
            onClick={handleRefetch}
            className="rounded border border-border bg-gray-800 px-2 py-1 text-xs text-gray-400 hover:text-white transition-colors"
            aria-label="Refresh journal data"
          >
            Refresh
          </button>
        </div>
      </div>

      {/* Error */}
      {isError && (
        <div className="mb-3 flex items-center justify-between rounded bg-red-500/10 px-3 py-2">
          <span className="text-xs text-red-400">Failed to load journal data</span>
          <button type="button" onClick={handleRefetch} className="text-xs text-red-400 underline hover:text-red-300">
            Retry
          </button>
        </div>
      )}

      {isLoading && <JournalSkeleton />}

      {data && trendStyle && (
        <div className="space-y-4">
          {/* Date range */}
          <p className="text-[10px] text-gray-500">
            Period: {formatDateRange(data.period_start, data.period_end)}
          </p>

          {/* Performance Summary */}
          <div className="rounded border border-border bg-gray-800/60 px-3 py-3">
            <p className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-gray-500">
              Performance Summary
            </p>
            <div className="grid grid-cols-3 gap-3">
              <div className="text-center">
                <p className="text-[10px] text-gray-500">Total Trades</p>
                <p className="font-mono text-lg font-bold text-white">{data.total_trades}</p>
              </div>
              <div className="text-center">
                <p className="text-[10px] text-gray-500">Win Rate</p>
                <p className={`font-mono text-lg font-bold ${getWinRateColor(data.win_rate)}`}>
                  {(data.win_rate * 100).toFixed(1)}%
                </p>
              </div>
              <div className="text-center">
                <p className="text-[10px] text-gray-500">Avg Return</p>
                <p className={`font-mono text-lg font-bold ${data.avg_return_pct >= 0 ? "text-green-400" : "text-red-400"}`}>
                  {data.avg_return_pct >= 0 ? "+" : ""}{data.avg_return_pct.toFixed(2)}%
                </p>
              </div>
            </div>

            {/* Trend */}
            <div className="mt-2 flex items-center gap-1.5 border-t border-border pt-2">
              <span className={`text-sm ${trendStyle.text}`} aria-hidden="true">{trendStyle.arrow}</span>
              <span className={`text-xs font-medium ${trendStyle.text}`}>
                Trend: {data.performance_trend}
              </span>
            </div>
          </div>

          {/* Best/Worst Setups */}
          <div className="grid grid-cols-2 gap-2">
            <div className="rounded border border-green-500/20 bg-green-500/5 px-3 py-2">
              <p className="mb-1 text-[10px] font-semibold text-green-400 uppercase tracking-wide">
                Best Setup
              </p>
              <p className="text-xs text-gray-200 font-medium">{data.best_setup}</p>
            </div>
            <div className="rounded border border-red-500/20 bg-red-500/5 px-3 py-2">
              <p className="mb-1 text-[10px] font-semibold text-red-400 uppercase tracking-wide">
                Worst Setup
              </p>
              <p className="text-xs text-gray-200 font-medium">{data.worst_setup}</p>
            </div>
          </div>

          {/* Key Insights */}
          {data.key_insights.length > 0 && (
            <div>
              <p className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-gray-500">
                Key Insights
              </p>
              <div className="space-y-2">
                {data.key_insights.map((insight, i) => (
                  <InsightCard key={i} insight={insight} />
                ))}
              </div>
            </div>
          )}

          {/* Improvement Actions */}
          {data.improvement_actions.length > 0 && (
            <div className="rounded border border-border bg-gray-800/60 px-3 py-3">
              <p className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-gray-500">
                Improvement Actions
              </p>
              <ul className="space-y-1.5" aria-label="Improvement action checklist">
                {data.improvement_actions.map((action, i) => (
                  <li key={i} className="flex items-start gap-2 text-xs text-gray-300">
                    <span
                      className="mt-0.5 flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded border border-gray-600"
                      aria-hidden="true"
                    />
                    <span>{action}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
