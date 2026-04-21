import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchSignalHistory } from "../../api/client";

const DIRECTIONS = ["ALL", "LONG", "SHORT"] as const;
type DirectionFilter = (typeof DIRECTIONS)[number];

function DirectionBadge({ direction }: { direction: string }) {
  return (
    <span
      className={`inline-block rounded px-1.5 py-0.5 text-xs font-bold ${
        direction === "LONG"
          ? "bg-green-500/15 text-green-400"
          : direction === "SHORT"
            ? "bg-red-500/15 text-red-400"
            : "bg-border/50 text-muted-foreground"
      }`}
    >
      {direction}
    </span>
  );
}

function ConfidenceBar({ value }: { value: number }) {
  return (
    <div className="flex items-center gap-1.5">
      <div className="h-1 w-12 overflow-hidden rounded-full bg-border/50">
        <div
          className={`h-full rounded-full ${value >= 70 ? "bg-green-400" : value >= 55 ? "bg-yellow-400" : "bg-orange-400"}`}
          style={{ width: `${value}%` }}
        />
      </div>
      <span className="text-xs tabular-nums text-muted-foreground">{value}%</span>
    </div>
  );
}

export function SignalHistoryPanel() {
  const [dirFilter, setDirFilter] = useState<DirectionFilter>("ALL");
  const [assetFilter, setAssetFilter] = useState("");
  const [page, setPage] = useState(0);
  const pageSize = 20;

  const { data, isLoading } = useQuery({
    queryKey: ["signal-history", dirFilter, assetFilter, page],
    queryFn: () =>
      fetchSignalHistory({
        direction: dirFilter !== "ALL" ? dirFilter : undefined,
        asset: assetFilter.trim() || undefined,
        limit: pageSize,
        offset: page * pageSize,
      }),
    refetchInterval: 60_000,
  });

  const signals = data?.data ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.ceil(total / pageSize);

  return (
    <div className="flex flex-col gap-4 rounded-xl border border-border bg-background p-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-base font-semibold text-foreground">Signal History</h2>
          <p className="text-xs text-muted-foreground">{total} signals total</p>
        </div>

        {/* Filters */}
        <div className="flex flex-wrap items-center gap-2">
          <input
            type="text"
            value={assetFilter}
            onChange={(e) => { setAssetFilter(e.target.value.toUpperCase()); setPage(0); }}
            placeholder="Filter by asset..."
            className="h-8 rounded border border-border bg-surface px-2 text-xs text-foreground placeholder:text-muted-foreground focus:border-accent focus:outline-none w-32"
            aria-label="Filter signals by asset"
          />
          <div className="flex rounded-md border border-border overflow-hidden" role="group" aria-label="Direction filter">
            {DIRECTIONS.map((d) => (
              <button
                key={d}
                type="button"
                onClick={() => { setDirFilter(d); setPage(0); }}
                className={`h-8 px-3 text-xs font-medium transition-colors ${
                  dirFilter === d
                    ? "bg-accent text-accent-foreground"
                    : "bg-transparent text-muted-foreground hover:text-foreground"
                }`}
                aria-pressed={dirFilter === d}
              >
                {d}
              </button>
            ))}
          </div>
        </div>
      </div>

      {isLoading ? (
        <div className="flex h-40 items-center justify-center text-sm text-muted-foreground">
          Loading signals...
        </div>
      ) : signals.length === 0 ? (
        <div className="flex h-40 items-center justify-center rounded-lg border border-border/50 text-sm text-muted-foreground">
          No signals match your filters
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs" role="table" aria-label="Signal history table">
            <thead>
              <tr className="border-b border-border/50">
                <th className="pb-2 pr-3 text-left font-medium text-muted-foreground">Asset</th>
                <th className="pb-2 pr-3 text-left font-medium text-muted-foreground">Dir</th>
                <th className="pb-2 pr-3 text-left font-medium text-muted-foreground">Confidence</th>
                <th className="pb-2 pr-3 text-left font-medium text-muted-foreground hidden sm:table-cell">Strategy</th>
                <th className="pb-2 pr-3 text-left font-medium text-muted-foreground hidden md:table-cell">Entry</th>
                <th className="pb-2 text-left font-medium text-muted-foreground">Status</th>
              </tr>
            </thead>
            <tbody>
              {signals.map((sig) => (
                <tr key={sig.id} className="border-b border-border/30 hover:bg-accent/5 transition-colors">
                  <td className="py-2 pr-3 font-medium text-foreground">{sig.asset}</td>
                  <td className="py-2 pr-3">
                    <DirectionBadge direction={sig.direction} />
                  </td>
                  <td className="py-2 pr-3">
                    <ConfidenceBar value={sig.confidence} />
                  </td>
                  <td className="py-2 pr-3 text-muted-foreground hidden sm:table-cell">{sig.strategy_name ?? "—"}</td>
                  <td className="py-2 pr-3 font-mono text-muted-foreground hidden md:table-cell">
                    {sig.entry_price?.toFixed(4) ?? "—"}
                  </td>
                  <td className="py-2">
                    <span className={`rounded px-1.5 py-0.5 text-xs ${
                      sig.status === "ACTIVE" ? "bg-blue-500/15 text-blue-400" : "bg-border/50 text-muted-foreground"
                    }`}>
                      {sig.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>Page {page + 1} of {totalPages}</span>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              className="rounded border border-border px-2 py-1 disabled:opacity-40 hover:text-foreground"
              aria-label="Previous page"
            >
              ←
            </button>
            <button
              type="button"
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
              disabled={page >= totalPages - 1}
              className="rounded border border-border px-2 py-1 disabled:opacity-40 hover:text-foreground"
              aria-label="Next page"
            >
              →
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
