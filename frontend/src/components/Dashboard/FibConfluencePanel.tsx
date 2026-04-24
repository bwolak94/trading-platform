/**
 * FibConfluencePanel
 * Displays Fibonacci confluence zones — price levels where multiple Fib levels converge.
 * Fetches from GET /api/v1/features/fib-confluence/{symbol}
 */

import { useQuery } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import axios from "axios";

// --------------- Types ---------------

interface FibConfluenceZone {
  price_center: number;
  price_high: number;
  price_low: number;
  confluence_score: number;
  is_support: boolean;
  strength: "WEAK" | "MODERATE" | "STRONG";
}

interface FibConfluenceResponse {
  symbol: string;
  current_price: number;
  zones: FibConfluenceZone[];
}

// --------------- Constants ---------------

const SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"];

const STRENGTH_CONFIG: Record<
  FibConfluenceZone["strength"],
  { badge: string; bar: string; label: string }
> = {
  WEAK: {
    badge: "bg-gray-700 text-gray-400",
    bar: "bg-gray-500",
    label: "text-gray-400",
  },
  MODERATE: {
    badge: "bg-yellow-500/20 text-yellow-400",
    bar: "bg-yellow-500",
    label: "text-yellow-400",
  },
  STRONG: {
    badge: "bg-orange-500/20 text-orange-400",
    bar: "bg-orange-500",
    label: "text-orange-400",
  },
};

function getConfluenceColor(score: number): string {
  if (score >= 4) return "bg-red-500";
  if (score === 3) return "bg-orange-500";
  if (score === 2) return "bg-yellow-500";
  return "bg-gray-500";
}

function formatPrice(price: number): string {
  if (price >= 10000) return `$${price.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
  if (price >= 100) return `$${price.toFixed(2)}`;
  return `$${price.toFixed(4)}`;
}

async function fetchFibConfluence(symbol: string): Promise<FibConfluenceResponse> {
  const { data } = await axios.get<FibConfluenceResponse>(
    `/api/v1/features/fib-confluence/${symbol}`
  );
  return data;
}

// --------------- Sub-components ---------------

interface ZoneBarProps {
  zone: FibConfluenceZone;
  currentPrice: number;
  maxScore: number;
}

function ZoneBar({ zone, currentPrice, maxScore }: ZoneBarProps) {
  const cfg = STRENGTH_CONFIG[zone.strength];
  const pctFromCurrent = (((zone.price_center - currentPrice) / currentPrice) * 100).toFixed(2);
  const isAbove = zone.price_center > currentPrice;
  const barWidth = Math.min((zone.confluence_score / Math.max(maxScore, 1)) * 100, 100);
  const barColor = getConfluenceColor(zone.confluence_score);
  const side = zone.is_support ? "SUPPORT" : "RESISTANCE";
  const sideColor = zone.is_support ? "text-green-400" : "text-red-400";

  return (
    <div className="rounded border border-border bg-gray-800/60 px-3 py-2.5 space-y-2">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="font-mono text-xs font-medium text-white">
            {formatPrice(zone.price_center)}
          </span>
          <span className={`text-[10px] font-medium ${sideColor}`}>{side}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold uppercase ${cfg.badge}`}>
            {zone.strength}
          </span>
          <span className={`text-xs font-mono ${isAbove ? "text-red-400" : "text-green-400"}`}>
            {isAbove ? "+" : ""}{pctFromCurrent}%
          </span>
        </div>
      </div>

      {/* Confluence bar */}
      <div>
        <div className="mb-0.5 flex items-center justify-between text-[10px] text-gray-500">
          <span>Confluence score</span>
          <span className="font-mono font-bold text-gray-300">{zone.confluence_score} levels</span>
        </div>
        <div className="h-2 w-full overflow-hidden rounded-full bg-gray-700">
          <div
            className={`h-full rounded-full transition-all duration-500 ${barColor}`}
            style={{ width: `${barWidth}%` }}
            role="progressbar"
            aria-valuenow={zone.confluence_score}
            aria-valuemin={0}
            aria-valuemax={maxScore}
            aria-label={`Confluence score ${zone.confluence_score}`}
          />
        </div>
      </div>

      {/* Range */}
      <div className="text-[10px] text-gray-500">
        Range: {formatPrice(zone.price_low)} – {formatPrice(zone.price_high)}
      </div>
    </div>
  );
}

function FibSkeleton() {
  return (
    <div className="space-y-3" aria-busy="true" aria-label="Loading Fibonacci confluence data">
      {[...Array(5)].map((_, i) => (
        <div key={i} className="h-16 animate-pulse rounded bg-white/5" />
      ))}
    </div>
  );
}

// --------------- Main Component ---------------

export default function FibConfluencePanel() {
  const [symbol, setSymbol] = useState("BTCUSDT");

  const { data, isLoading, isError, refetch, dataUpdatedAt } = useQuery<FibConfluenceResponse>({
    queryKey: ["fib-confluence", symbol],
    queryFn: () => fetchFibConfluence(symbol),
    refetchInterval: 60_000,
    retry: 2,
  });

  const handleRefetch = useCallback(() => { void refetch(); }, [refetch]);
  const lastUpdated = dataUpdatedAt ? new Date(dataUpdatedAt).toLocaleTimeString() : null;

  const supportZones = data?.zones.filter((z) => z.is_support) ?? [];
  const resistanceZones = data?.zones.filter((z) => !z.is_support) ?? [];
  const allZones = data?.zones ?? [];
  const maxScore = allZones.reduce((m, z) => Math.max(m, z.confluence_score), 1);

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-white">Fibonacci Confluence</h2>
          {lastUpdated && (
            <p className="mt-0.5 text-xs text-gray-500">Updated: {lastUpdated}</p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <select
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            className="rounded border border-border bg-gray-800 px-2 py-1 text-xs text-gray-300 focus:outline-none focus:ring-1 focus:ring-blue-500"
            aria-label="Select symbol"
          >
            {SYMBOLS.map((s) => (
              <option key={s} value={s}>{s.replace("USDT", "")}</option>
            ))}
          </select>
          <button
            type="button"
            onClick={handleRefetch}
            className="rounded border border-border bg-gray-800 px-2 py-1 text-xs text-gray-400 hover:text-white transition-colors"
            aria-label="Refresh Fibonacci confluence data"
          >
            Refresh
          </button>
        </div>
      </div>

      {/* Error */}
      {isError && (
        <div className="mb-3 flex items-center justify-between rounded bg-red-500/10 px-3 py-2">
          <span className="text-xs text-red-400">Failed to load Fibonacci data</span>
          <button type="button" onClick={handleRefetch} className="text-xs text-red-400 underline hover:text-red-300">
            Retry
          </button>
        </div>
      )}

      {isLoading && <FibSkeleton />}

      {data && (
        <div className="space-y-4">
          {/* Current price */}
          <div className="flex items-center justify-between rounded bg-blue-500/10 border border-blue-500/30 px-3 py-2">
            <span className="text-xs text-gray-400">Current Price</span>
            <span className="font-mono text-sm font-bold text-blue-400">
              {formatPrice(data.current_price)}
            </span>
          </div>

          {/* Legend */}
          <div className="flex gap-4 text-[10px] text-gray-500">
            <span className="flex items-center gap-1">
              <span className="inline-block h-2 w-2 rounded-full bg-yellow-500" aria-hidden="true" /> 2 levels
            </span>
            <span className="flex items-center gap-1">
              <span className="inline-block h-2 w-2 rounded-full bg-orange-500" aria-hidden="true" /> 3 levels
            </span>
            <span className="flex items-center gap-1">
              <span className="inline-block h-2 w-2 rounded-full bg-red-500" aria-hidden="true" /> 4+ levels
            </span>
          </div>

          {/* Resistance zones */}
          {resistanceZones.length > 0 && (
            <div>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-red-400">
                Resistance ({resistanceZones.length})
              </h3>
              <div className="space-y-2">
                {resistanceZones.map((zone, i) => (
                  <ZoneBar key={`res-${i}`} zone={zone} currentPrice={data.current_price} maxScore={maxScore} />
                ))}
              </div>
            </div>
          )}

          {/* Support zones */}
          {supportZones.length > 0 && (
            <div>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-green-400">
                Support ({supportZones.length})
              </h3>
              <div className="space-y-2">
                {supportZones.map((zone, i) => (
                  <ZoneBar key={`sup-${i}`} zone={zone} currentPrice={data.current_price} maxScore={maxScore} />
                ))}
              </div>
            </div>
          )}

          {allZones.length === 0 && (
            <p className="text-sm text-gray-500">No Fibonacci confluence zones detected</p>
          )}
        </div>
      )}
    </div>
  );
}
