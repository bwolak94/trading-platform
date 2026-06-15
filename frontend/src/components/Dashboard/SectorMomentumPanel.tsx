import { useQuery } from "@tanstack/react-query";
import { fetchSectorMomentum } from "../../api/client";
import type { SectorMomentumData, SectorMomentumEntry } from "../../api/client";

/* ── Helpers ──────────────────────────────────────────────────────── */

const SCORE_MAX = 15; // visual clamp for the bar width

function scoreBarWidth(score: number): string {
  const clamped = Math.min(Math.abs(score), SCORE_MAX);
  return `${(clamped / SCORE_MAX) * 100}%`;
}

function changeClass(value: number): string {
  if (value > 0) return "text-bullish";
  if (value < 0) return "text-bearish";
  return "text-gray-400";
}

function formatChange(value: number): string {
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
}

/* ── SectorRow ────────────────────────────────────────────────────── */

interface SectorRowProps {
  entry: SectorMomentumEntry;
  rank: number;
}

function SectorRow({ entry, rank }: SectorRowProps) {
  const isPositive = entry.momentum_score >= 0;
  const barColor = isPositive ? "bg-bullish" : "bg-bearish";

  return (
    <div
      className="flex flex-col gap-1.5 rounded-lg border border-border bg-surface p-3 hover:border-border/70 transition-colors"
      role="row"
      aria-label={`${entry.sector}: momentum score ${entry.momentum_score}`}
    >
      {/* Top row: rank + name + score */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-xs font-bold text-gray-600 w-5 shrink-0">#{rank}</span>
          <span className="text-sm font-semibold text-white truncate">{entry.sector}</span>
          <span className="text-xs text-gray-500 shrink-0">{entry.symbol_count} coins</span>
        </div>
        <span
          className={`text-sm font-bold tabular-nums shrink-0 ${isPositive ? "text-bullish" : "text-bearish"}`}
          aria-label={`Score: ${entry.momentum_score}`}
        >
          {entry.momentum_score > 0 ? "+" : ""}
          {entry.momentum_score.toFixed(2)}
        </span>
      </div>

      {/* Momentum bar */}
      <div
        className="h-1.5 w-full rounded-full bg-border overflow-hidden"
        role="progressbar"
        aria-valuenow={entry.momentum_score}
        aria-valuemin={-SCORE_MAX}
        aria-valuemax={SCORE_MAX}
      >
        <div
          className={`h-full rounded-full transition-all ${barColor}`}
          style={{ width: scoreBarWidth(entry.momentum_score) }}
        />
      </div>

      {/* Bottom row: 1d / 7d changes + top performers */}
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-3">
          <span className="text-xs text-gray-500">
            1d:{" "}
            <span className={`font-medium ${changeClass(entry.avg_1d_change)}`}>
              {formatChange(entry.avg_1d_change)}
            </span>
          </span>
          <span className="text-xs text-gray-500">
            7d:{" "}
            <span className={`font-medium ${changeClass(entry.avg_7d_change)}`}>
              {formatChange(entry.avg_7d_change)}
            </span>
          </span>
        </div>
        {/* Top performer chips */}
        {entry.top_performers.length > 0 && (
          <div className="flex items-center gap-1 flex-wrap" aria-label="Top performers">
            {entry.top_performers.map((sym) => (
              <span
                key={sym}
                className="rounded bg-accent/10 border border-accent/20 px-1.5 py-0.5 text-xs font-medium text-accent"
              >
                {sym}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/* ── SectorMomentumPanel ──────────────────────────────────────────── */

export function SectorMomentumPanel() {
  const { data, isLoading, isError } = useQuery<SectorMomentumData>({
    queryKey: ["sectorMomentum"],
    queryFn: fetchSectorMomentum,
    refetchInterval: 10 * 60 * 1000, // 10 min
    staleTime: 9 * 60 * 1000,
  });

  const sectors = data?.sectors ?? [];

  return (
    <section
      aria-label="Sector Momentum Ranking"
      className="rounded-xl border border-border bg-background p-4 space-y-3"
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-white uppercase tracking-wide">
          Sector Momentum
        </h2>
        <div className="flex items-center gap-2">
          {isLoading && (
            <span className="text-xs text-gray-500 animate-pulse">Loading...</span>
          )}
          {isError && (
            <span className="text-xs text-bearish">Data unavailable</span>
          )}
          {!isLoading && !isError && sectors.length > 0 && (
            <span className="text-xs text-gray-500">{sectors.length} sectors</span>
          )}
        </div>
      </div>

      {/* Legend */}
      <div className="flex items-center gap-4 text-xs text-gray-500">
        <span>Score = 40% × 1d avg + 60% × 7d avg</span>
        <span className="text-gray-600">· Updated every 10 min</span>
      </div>

      {/* Sector rows */}
      {sectors.length === 0 && !isLoading ? (
        <div className="rounded-lg border border-border bg-surface p-6 text-center text-xs text-gray-500">
          No sector data available
        </div>
      ) : (
        <div className="space-y-2" role="table" aria-label="Sector rankings">
          {sectors.map((entry: SectorMomentumEntry, idx: number) => (
            <SectorRow key={entry.sector} entry={entry} rank={idx + 1} />
          ))}
        </div>
      )}
    </section>
  );
}
