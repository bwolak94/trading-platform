/**
 * Max Adverse Excursion (MAE) Tracker
 * Shows how far price moved against each closed trade before exit.
 * Helps identify whether stops are too tight or entries are poor quality.
 */

import { useQuery } from "@tanstack/react-query";
import { fetchClosedPositions } from "../../api/client";
import { fmtPct, colorClass } from "../../lib/format";

const MAE_BUCKETS = [
  { label: "0–0.5%", min: 0, max: 0.5 },
  { label: "0.5–1%", min: 0.5, max: 1 },
  { label: "1–2%", min: 1, max: 2 },
  { label: "2–3%", min: 2, max: 3 },
  { label: "3–5%", min: 3, max: 5 },
  { label: ">5%", min: 5, max: Infinity },
];

function DistributionBar({ label, count, max, wins, losses }: {
  label: string;
  count: number;
  max: number;
  wins: number;
  losses: number;
}) {
  const pct = max > 0 ? (count / max) * 100 : 0;
  const winRate = count > 0 ? (wins / count) * 100 : 0;
  return (
    <div>
      <div className="mb-0.5 flex justify-between text-[10px]">
        <span className="text-gray-400">{label}</span>
        <span className="text-gray-500">
          {count} trades · {winRate.toFixed(0)}% win
        </span>
      </div>
      <div className="relative h-4 w-full overflow-hidden rounded bg-background">
        {/* Win portion */}
        <div
          className="absolute left-0 top-0 h-full bg-bullish/50 transition-all"
          style={{ width: `${pct * (wins / Math.max(count, 1))}%` }}
          aria-hidden="true"
        />
        {/* Loss portion */}
        <div
          className="absolute top-0 h-full bg-bearish/50 transition-all"
          style={{
            left: `${pct * (wins / Math.max(count, 1))}%`,
            width: `${pct * (losses / Math.max(count, 1))}%`,
          }}
          aria-hidden="true"
        />
        <div
          className="absolute inset-0 flex items-center pl-2"
          role="progressbar"
          aria-valuenow={count}
          aria-valuemax={max}
          aria-label={`${label}: ${count} trades`}
        >
          {count > 0 && (
            <span className="text-[9px] font-mono text-white/70">{count}</span>
          )}
        </div>
      </div>
    </div>
  );
}

export function MAETrackerPanel() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["closed-positions-mae"],
    queryFn: () => fetchClosedPositions({ limit: 200 }),
    refetchInterval: 60_000,
    retry: false,
  });

  const positions = data?.positions ?? [];
  const withMAE = positions.filter((p) => p.mae_pct != null);

  // Build bucket distribution
  const buckets = MAE_BUCKETS.map((bucket) => {
    const inBucket = withMAE.filter((p) => {
      const mae = Math.abs(p.mae_pct ?? 0);
      return mae >= bucket.min && mae < bucket.max;
    });
    return {
      ...bucket,
      count: inBucket.length,
      wins: inBucket.filter((p) => (p.pnl_pct ?? 0) > 0).length,
      losses: inBucket.filter((p) => (p.pnl_pct ?? 0) <= 0).length,
    };
  });

  const maxCount = Math.max(...buckets.map((b) => b.count), 1);

  // Stats
  const avgMAE = withMAE.length
    ? withMAE.reduce((s, p) => s + Math.abs(p.mae_pct ?? 0), 0) / withMAE.length
    : 0;
  const stopTightCount = withMAE.filter((p) => Math.abs(p.mae_pct ?? 0) < 0.5).length;
  const stopTightPct = withMAE.length > 0 ? (stopTightCount / withMAE.length) * 100 : 0;

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-4 text-sm font-semibold text-white">MAE Tracker</h2>
      <p className="mb-3 text-[10px] text-gray-500">
        Max Adverse Excursion — how far price moved against you before exit.
        Bars show win (green) / loss (red) breakdown per bucket.
      </p>

      {isError && <p className="text-xs text-bearish mb-3">Unable to load trade history</p>}

      {isLoading && (
        <div className="space-y-2">
          {MAE_BUCKETS.map((b) => (
            <div key={b.label} className="h-4 animate-pulse rounded bg-white/5" />
          ))}
        </div>
      )}

      {!isLoading && withMAE.length === 0 && (
        <p className="py-4 text-center text-xs text-gray-600">
          No MAE data yet. Closed trades will appear here.
        </p>
      )}

      {!isLoading && withMAE.length > 0 && (
        <>
          <div className="mb-4 space-y-2">
            {buckets.map((b) => (
              <DistributionBar
                key={b.label}
                label={b.label}
                count={b.count}
                max={maxCount}
                wins={b.wins}
                losses={b.losses}
              />
            ))}
          </div>

          <div className="grid grid-cols-3 gap-2 text-xs">
            <div className="rounded bg-background px-2 py-2 text-center">
              <p className="text-gray-500">Avg MAE</p>
              <p className={`font-mono font-bold ${colorClass(-avgMAE)}`}>
                {fmtPct(avgMAE, { decimals: 2 })}
              </p>
            </div>
            <div className="rounded bg-background px-2 py-2 text-center">
              <p className="text-gray-500">Tight Stops</p>
              <p className="font-mono font-bold text-amber-400">
                {fmtPct(stopTightPct, { decimals: 0 })}
              </p>
            </div>
            <div className="rounded bg-background px-2 py-2 text-center">
              <p className="text-gray-500">Sample</p>
              <p className="font-mono font-bold text-gray-300">{withMAE.length}</p>
            </div>
          </div>

          <p className="mt-3 text-[9px] text-gray-600">
            If "Tight Stops" is &gt;40%, consider widening SL by 0.5–1×ATR to reduce premature exits.
          </p>
        </>
      )}
    </div>
  );
}
