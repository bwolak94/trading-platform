import { useQuery } from "@tanstack/react-query";
import { useCallback, useMemo, useState } from "react";
import {
  fetchLiveRegimes,
  fetchActiveSignals,
  type LiveRegime,
} from "../api/client";

interface ScreenerRow {
  asset: string;
  regime: string;
  confidence: number;
  price: number;
  rsi: number;
  adx: number;
  signalCount: number;
  lastSignalDirection: string;
}

type SortField = keyof Pick<
  ScreenerRow,
  "asset" | "regime" | "rsi" | "adx" | "signalCount" | "lastSignalDirection" | "price" | "confidence"
>;

type SortDirection = "asc" | "desc";

const REGIME_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  TREND_UP: { bg: "bg-green-900/40", text: "text-green-400", label: "Trend Up" },
  TRENDING_UP: { bg: "bg-green-900/40", text: "text-green-400", label: "Trend Up" },
  TREND_DOWN: { bg: "bg-red-900/40", text: "text-red-400", label: "Trend Down" },
  TRENDING_DOWN: { bg: "bg-red-900/40", text: "text-red-400", label: "Trend Down" },
  CONSOLIDATION: { bg: "bg-yellow-900/40", text: "text-yellow-400", label: "Consolidation" },
  RANGING: { bg: "bg-yellow-900/40", text: "text-yellow-400", label: "Ranging" },
  CHOPPY: { bg: "bg-gray-700/40", text: "text-gray-400", label: "Choppy" },
  HIGH_VOLATILITY: { bg: "bg-orange-900/40", text: "text-orange-400", label: "High Vol" },
};

function getRegimeStyle(regime: string): { bg: string; text: string; label: string } {
  const normalized = regime.toUpperCase().replace(/[\s-]+/g, "_");
  return REGIME_STYLES[normalized] ?? { bg: "bg-gray-700/40", text: "text-gray-400", label: regime };
}

function formatPrice(price: number): string {
  if (price >= 1000) return price.toLocaleString("en-US", { maximumFractionDigits: 2 });
  if (price >= 1) return price.toLocaleString("en-US", { maximumFractionDigits: 4 });
  return price.toLocaleString("en-US", { maximumFractionDigits: 6 });
}

function getRsiColor(rsi: number): string {
  if (rsi >= 70) return "text-red-400";
  if (rsi <= 30) return "text-green-400";
  return "text-gray-300";
}

function getAdxColor(adx: number): string {
  if (adx >= 25) return "text-yellow-400";
  return "text-gray-400";
}

function getDirectionStyle(direction: string): { color: string; icon: string } {
  const upper = direction.toUpperCase();
  if (upper === "LONG" || upper === "BUY") return { color: "text-green-400", icon: "\u2191" };
  if (upper === "SHORT" || upper === "SELL") return { color: "text-red-400", icon: "\u2193" };
  return { color: "text-gray-400", icon: "\u2014" };
}

function SortIcon({ field, currentField, direction }: { field: SortField; currentField: SortField; direction: SortDirection }) {
  if (field !== currentField) {
    return <span className="ml-1 text-gray-600">{"\u2195"}</span>;
  }
  return <span className="ml-1 text-blue-400">{direction === "asc" ? "\u2191" : "\u2193"}</span>;
}

export function ScreenerPage() {
  const [sortField, setSortField] = useState<SortField>("asset");
  const [sortDirection, setSortDirection] = useState<SortDirection>("asc");

  const { data: regimes, isLoading: isLoadingRegimes, error: regimesError } = useQuery({
    queryKey: ["live-regimes"],
    queryFn: fetchLiveRegimes,
    refetchInterval: 15_000,
  });

  const { data: signalsData, isLoading: isLoadingSignals } = useQuery({
    queryKey: ["active-signals"],
    queryFn: fetchActiveSignals,
    refetchInterval: 15_000,
  });

  const rows: ScreenerRow[] = useMemo(() => {
    if (!regimes) return [];

    const signalsByAsset = new Map<string, { count: number; lastDirection: string }>();

    if (signalsData?.data) {
      for (const signal of signalsData.data) {
        const existing = signalsByAsset.get(signal.asset);
        if (existing) {
          existing.count += 1;
        } else {
          signalsByAsset.set(signal.asset, {
            count: 1,
            lastDirection: signal.direction ?? "HOLD",
          });
        }
      }
    }

    return regimes.map((r: LiveRegime) => {
      const signalInfo = signalsByAsset.get(r.asset);
      return {
        asset: r.asset,
        regime: r.regime,
        confidence: r.confidence,
        price: r.price,
        rsi: r.rsi,
        adx: r.adx,
        signalCount: signalInfo?.count ?? 0,
        lastSignalDirection: signalInfo?.lastDirection ?? "NONE",
      };
    });
  }, [regimes, signalsData]);

  const sortedRows = useMemo(() => {
    const sorted = [...rows];
    sorted.sort((a, b) => {
      const aVal = a[sortField];
      const bVal = b[sortField];

      if (typeof aVal === "string" && typeof bVal === "string") {
        const cmp = aVal.localeCompare(bVal);
        return sortDirection === "asc" ? cmp : -cmp;
      }

      const numA = Number(aVal);
      const numB = Number(bVal);
      return sortDirection === "asc" ? numA - numB : numB - numA;
    });
    return sorted;
  }, [rows, sortField, sortDirection]);

  const handleSort = useCallback(
    (field: SortField) => {
      if (field === sortField) {
        setSortDirection((prev) => (prev === "asc" ? "desc" : "asc"));
      } else {
        setSortField(field);
        setSortDirection("asc");
      }
    },
    [sortField],
  );

  const isLoading = isLoadingRegimes || isLoadingSignals;

  if (regimesError) {
    return (
      <div className="rounded-lg border border-red-800 bg-red-900/20 p-6 text-center">
        <p className="text-red-400">Failed to load screener data. Please try again later.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white">Market Screener</h1>
          <p className="text-sm text-gray-400">
            {rows.length} tracked asset{rows.length !== 1 ? "s" : ""} &middot; Auto-refreshes every 15s
          </p>
        </div>
        {isLoading && (
          <div className="flex items-center gap-2 text-sm text-gray-400">
            <div className="h-3 w-3 animate-spin rounded-full border-2 border-gray-500 border-t-blue-400" />
            Updating...
          </div>
        )}
      </div>

      <div className="-mx-4 overflow-x-auto px-4 md:mx-0 md:px-0">
        <table className="w-full min-w-[700px] text-sm" role="grid" aria-label="Market screener table">
          <thead>
            <tr className="border-b border-border text-left text-gray-400">
              <SortableHeader field="asset" label="Asset" sortField={sortField} sortDirection={sortDirection} onSort={handleSort} />
              <SortableHeader field="price" label="Price" sortField={sortField} sortDirection={sortDirection} onSort={handleSort} className="text-right" />
              <SortableHeader field="regime" label="Regime" sortField={sortField} sortDirection={sortDirection} onSort={handleSort} />
              <SortableHeader field="confidence" label="Conf." sortField={sortField} sortDirection={sortDirection} onSort={handleSort} className="text-right" />
              <SortableHeader field="rsi" label="RSI" sortField={sortField} sortDirection={sortDirection} onSort={handleSort} className="text-right" />
              <SortableHeader field="adx" label="ADX" sortField={sortField} sortDirection={sortDirection} onSort={handleSort} className="text-right" />
              <SortableHeader field="signalCount" label="Signals" sortField={sortField} sortDirection={sortDirection} onSort={handleSort} className="text-right" />
              <SortableHeader field="lastSignalDirection" label="Last Dir." sortField={sortField} sortDirection={sortDirection} onSort={handleSort} className="text-center" />
            </tr>
          </thead>
          <tbody>
            {isLoading && rows.length === 0 ? (
              Array.from({ length: 6 }).map((_, i) => (
                <tr key={`skeleton-${i}`} className="border-b border-border/50">
                  {Array.from({ length: 8 }).map((_, j) => (
                    <td key={`skeleton-cell-${i}-${j}`} className="px-3 py-3">
                      <div className="h-4 animate-pulse rounded bg-gray-700/50" />
                    </td>
                  ))}
                </tr>
              ))
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={8} className="py-12 text-center text-gray-500">
                  No tracked assets found. Start the analysis engine to populate data.
                </td>
              </tr>
            ) : (
              sortedRows.map((row) => {
                const regimeStyle = getRegimeStyle(row.regime);
                const dirStyle = getDirectionStyle(row.lastSignalDirection);

                return (
                  <tr
                    key={row.asset}
                    className="border-b border-border/50 transition-colors hover:bg-surface/50"
                  >
                    <td className="px-3 py-3 font-medium text-white">{row.asset}</td>
                    <td className="px-3 py-3 text-right font-mono text-gray-300">
                      {formatPrice(row.price)}
                    </td>
                    <td className="px-3 py-3">
                      <span
                        className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${regimeStyle.bg} ${regimeStyle.text}`}
                      >
                        {regimeStyle.label}
                      </span>
                    </td>
                    <td className="px-3 py-3 text-right font-mono text-gray-300">
                      {(row.confidence * 100).toFixed(0)}%
                    </td>
                    <td className={`px-3 py-3 text-right font-mono ${getRsiColor(row.rsi)}`}>
                      {row.rsi.toFixed(1)}
                    </td>
                    <td className={`px-3 py-3 text-right font-mono ${getAdxColor(row.adx)}`}>
                      {row.adx.toFixed(1)}
                    </td>
                    <td className="px-3 py-3 text-right font-mono text-gray-300">
                      {row.signalCount > 0 ? (
                        <span className="rounded bg-blue-900/30 px-1.5 py-0.5 text-blue-400">
                          {row.signalCount}
                        </span>
                      ) : (
                        <span className="text-gray-600">0</span>
                      )}
                    </td>
                    <td className={`px-3 py-3 text-center font-medium ${dirStyle.color}`}>
                      {dirStyle.icon} {row.lastSignalDirection !== "NONE" ? row.lastSignalDirection : "\u2014"}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function SortableHeader({
  field,
  label,
  sortField,
  sortDirection,
  onSort,
  className = "",
}: {
  field: SortField;
  label: string;
  sortField: SortField;
  sortDirection: SortDirection;
  onSort: (field: SortField) => void;
  className?: string;
}) {
  return (
    <th className={`px-3 py-2 font-medium ${className}`}>
      <button
        type="button"
        onClick={() => onSort(field)}
        className="inline-flex items-center gap-0.5 transition-colors hover:text-white"
        aria-label={`Sort by ${label}`}
      >
        {label}
        <SortIcon field={field} currentField={sortField} direction={sortDirection} />
      </button>
    </th>
  );
}
