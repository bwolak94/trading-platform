import { useQuery } from "@tanstack/react-query";
import { fetchMonteCarloVar } from "../../api/client";
import type { MonteCarloVarData } from "../../api/client";

/* ── Helpers ──────────────────────────────────────────────────────────── */

function pct(value: number): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function pctClass(value: number): string {
  return value >= 0 ? "text-green-400" : "text-red-400";
}

/* ── Range Bar: visual cone indicator ─────────────────────────────────── */

interface RangeBarProps {
  worstCase: number;
  var99: number;
  var95: number;
  median: number;
  expected: number;
  bestCase: number;
}

function RangeBar({ worstCase, var99, var95, median, expected, bestCase }: RangeBarProps) {
  const min = Math.min(worstCase, -1);
  const max = Math.max(bestCase, 1);
  const span = max - min;

  const toLeft = (v: number): string => `${Math.max(0, Math.min(100, ((v - min) / span) * 100)).toFixed(1)}%`;

  return (
    <div className="relative h-8 w-full rounded-full bg-gray-800" role="img" aria-label="Monte Carlo range bar">
      {/* Full range — worst to best */}
      <div
        className="absolute top-1/4 h-1/2 rounded-full bg-gray-600/40"
        style={{ left: toLeft(worstCase), right: `${100 - parseFloat(toLeft(bestCase))}%` }}
      />
      {/* VaR 99 to VaR 95 band (deep red) */}
      <div
        className="absolute top-1/4 h-1/2 bg-red-700/60"
        style={{ left: toLeft(worstCase), width: `${parseFloat(toLeft(var99)) - parseFloat(toLeft(worstCase))}%` }}
      />
      {/* VaR 95 to median band (amber) */}
      <div
        className="absolute top-1/4 h-1/2 bg-amber-600/50"
        style={{ left: toLeft(var99), width: `${parseFloat(toLeft(var95)) - parseFloat(toLeft(var99))}%` }}
      />
      {/* Median to best (green) */}
      <div
        className="absolute top-1/4 h-1/2 rounded-r-full bg-green-700/50"
        style={{ left: toLeft(median), right: `${100 - parseFloat(toLeft(bestCase))}%` }}
      />
      {/* Expected return marker */}
      <div
        className="absolute top-0 h-full w-0.5 bg-white/80"
        style={{ left: toLeft(expected) }}
        title={`Expected: ${pct(expected)}`}
      />
      {/* Zero line */}
      <div
        className="absolute top-0 h-full w-px bg-gray-400/60"
        style={{ left: toLeft(0) }}
        title="Break-even"
      />
    </div>
  );
}

/* ── Stat Tile ────────────────────────────────────────────────────────── */

interface StatTileProps {
  label: string;
  value: string;
  valueClass?: string;
  description?: string;
}

function StatTile({ label, value, valueClass = "text-foreground", description }: StatTileProps) {
  return (
    <div className="rounded-lg border border-border bg-surface/50 p-3">
      <p className="mb-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className={`text-base font-bold tabular-nums ${valueClass}`}>{value}</p>
      {description && <p className="mt-0.5 text-[10px] text-muted-foreground/70">{description}</p>}
    </div>
  );
}

/* ── Loading Skeleton ─────────────────────────────────────────────────── */

function Skeleton() {
  return (
    <div className="animate-pulse space-y-3">
      <div className="h-8 w-full rounded-full bg-gray-800" />
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {Array.from({ length: 6 }).map((_, i) => (
          // biome-ignore lint/suspicious/noArrayIndexKey: skeleton tiles have no meaningful identity
          <div key={i} className="h-16 rounded-lg bg-gray-800" />
        ))}
      </div>
    </div>
  );
}

/* ── Panel ────────────────────────────────────────────────────────────── */

export function MonteCarloPanel() {
  const { data, isLoading, isError } = useQuery<MonteCarloVarData>({
    queryKey: ["monteCarlo"],
    queryFn: () => fetchMonteCarloVar(1000, 20),
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

  const isPositive = data && !data.error && data.expected_return >= 0;

  return (
    <section
      className="rounded-xl border border-border bg-background p-4 sm:p-5"
      aria-labelledby="monte-carlo-heading"
    >
      {/* Header */}
      <div className="mb-4 flex items-start justify-between gap-2">
        <div>
          <h2
            id="monte-carlo-heading"
            className="text-sm font-semibold text-foreground"
          >
            Monte Carlo VaR
          </h2>
          {data && !data.error && (
            <p className="mt-0.5 text-[11px] text-muted-foreground">
              Based on closed trades &mdash; {data.horizon}-trade horizon &mdash; {data.simulations.toLocaleString()} simulations
            </p>
          )}
        </div>
        <span
          className={`rounded px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide ${
            isPositive
              ? "bg-green-500/10 text-green-400"
              : "bg-red-500/10 text-red-400"
          }`}
        >
          {isPositive ? "Positive Edge" : data?.error ? "No Data" : "Negative Edge"}
        </span>
      </div>

      {/* Content */}
      {isLoading && <Skeleton />}

      {isError && (
        <p className="text-center text-xs text-muted-foreground" role="alert">
          Failed to load Monte Carlo data.
        </p>
      )}

      {data?.error && (
        <p className="text-center text-xs text-muted-foreground" role="status">
          {data.error}
        </p>
      )}

      {data && !data.error && (
        <div className="space-y-4">
          {/* Cone chart */}
          <RangeBar
            worstCase={data.worst_case}
            var99={data.var_99}
            var95={data.var_95}
            median={data.median}
            expected={data.expected_return}
            bestCase={data.best_case}
          />

          {/* Legend */}
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-[10px] text-muted-foreground">
            <span className="flex items-center gap-1">
              <span className="inline-block h-2 w-3 rounded-sm bg-red-700/60" />
              Worst 1%
            </span>
            <span className="flex items-center gap-1">
              <span className="inline-block h-2 w-3 rounded-sm bg-amber-600/50" />
              VaR 95&ndash;99
            </span>
            <span className="flex items-center gap-1">
              <span className="inline-block h-2 w-3 rounded-sm bg-green-700/50" />
              Median&ndash;Best
            </span>
            <span className="flex items-center gap-1">
              <span className="inline-block h-0.5 w-3 bg-white/80" />
              Expected
            </span>
          </div>

          {/* Stats grid */}
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            <StatTile
              label="VaR 95%"
              value={pct(data.var_95)}
              valueClass={pctClass(data.var_95)}
              description="Worst 5% scenario"
            />
            <StatTile
              label="VaR 99%"
              value={pct(data.var_99)}
              valueClass="text-red-400"
              description="Worst 1% scenario"
            />
            <StatTile
              label="Expected Return"
              value={pct(data.expected_return)}
              valueClass={pctClass(data.expected_return)}
              description={`Over ${data.horizon} trades`}
            />
            <StatTile
              label="Median"
              value={pct(data.median)}
              valueClass={pctClass(data.median)}
              description="50th percentile"
            />
            <StatTile
              label="Best Case"
              value={pct(data.best_case)}
              valueClass="text-green-400"
              description="Max simulation"
            />
            <StatTile
              label="Worst Case"
              value={pct(data.worst_case)}
              valueClass="text-red-400"
              description="Min simulation"
            />
          </div>
        </div>
      )}
    </section>
  );
}
