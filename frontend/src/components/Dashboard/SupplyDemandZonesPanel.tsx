/**
 * SupplyDemandZonesPanel
 * Displays institutional supply and demand zones relative to current price.
 * Fetches from GET /api/v1/features/supply-demand/{symbol}
 */

import { useQuery } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import axios from "axios";

// --------------- Types ---------------

interface SDZone {
  zone_type: "DEMAND" | "SUPPLY";
  price_high: number;
  price_low: number;
  price_mid: number;
  strength: number;
  is_fresh: boolean;
  touch_count: number;
  explosive_move_pct: number;
}

interface SDZonesResponse {
  symbol: string;
  current_price: number;
  zones: SDZone[];
}

// --------------- Constants ---------------

const SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"];

// --------------- Helpers ---------------

function formatPrice(price: number): string {
  if (price >= 10000) return `$${price.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
  if (price >= 100) return `$${price.toFixed(2)}`;
  return `$${price.toFixed(4)}`;
}

function getPctDistance(current: number, mid: number): string {
  const pct = ((mid - current) / current) * 100;
  return pct >= 0 ? `+${pct.toFixed(2)}%` : `${pct.toFixed(2)}%`;
}

async function fetchSDZones(symbol: string): Promise<SDZonesResponse> {
  const { data } = await axios.get<SDZonesResponse>(`/api/v1/features/supply-demand/${symbol}`);
  return data;
}

// --------------- Sub-components ---------------

interface ZoneCardProps {
  zone: SDZone;
  currentPrice: number;
}

function ZoneCard({ zone, currentPrice }: ZoneCardProps) {
  const isDemand = zone.zone_type === "DEMAND";
  const pctDistance = getPctDistance(currentPrice, zone.price_mid);
  const isAbove = zone.price_mid > currentPrice;

  const cardStyle = isDemand
    ? "border-green-500/30 bg-green-500/5"
    : "border-red-500/30 bg-red-500/5";
  const strengthBarColor = isDemand ? "bg-green-500" : "bg-red-500";
  const priceColor = isDemand ? "text-green-400" : "text-red-400";
  const distColor = isAbove ? "text-red-400" : "text-green-400";

  return (
    <div className={`rounded border ${cardStyle} p-3 space-y-2`}>
      {/* Header row */}
      <div className="flex items-center justify-between">
        <span className={`font-mono text-xs font-semibold ${priceColor}`}>
          {formatPrice(zone.price_low)} – {formatPrice(zone.price_high)}
        </span>
        <div className="flex items-center gap-1.5">
          {zone.is_fresh && (
            <span className="rounded bg-blue-500/20 px-1.5 py-0.5 text-[10px] font-bold text-blue-400 uppercase tracking-wide">
              FRESH
            </span>
          )}
          {!zone.is_fresh && (
            <span className="rounded bg-gray-700 px-1.5 py-0.5 text-[10px] text-gray-400 uppercase">
              TESTED
            </span>
          )}
        </div>
      </div>

      {/* Strength bar */}
      <div>
        <div className="mb-0.5 flex items-center justify-between text-[10px] text-gray-500">
          <span>Strength</span>
          <span className="font-mono">{zone.strength.toFixed(0)}%</span>
        </div>
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-gray-700">
          <div
            className={`h-full rounded-full transition-all ${strengthBarColor}`}
            style={{ width: `${Math.min(zone.strength, 100)}%` }}
            role="progressbar"
            aria-valuenow={zone.strength}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={`Zone strength ${zone.strength.toFixed(0)}%`}
          />
        </div>
      </div>

      {/* Stats row */}
      <div className="flex items-center justify-between text-[10px] text-gray-500">
        <span>
          Touches: <span className="text-gray-300">{zone.touch_count}</span>
        </span>
        <span>
          Move: <span className="text-gray-300">+{zone.explosive_move_pct.toFixed(1)}%</span>
        </span>
        <span className={distColor}>{pctDistance} away</span>
      </div>
    </div>
  );
}

function SDSkeleton() {
  return (
    <div className="space-y-3" aria-busy="true" aria-label="Loading supply demand zones">
      {[...Array(4)].map((_, i) => (
        <div key={i} className="h-20 animate-pulse rounded bg-white/5" />
      ))}
    </div>
  );
}

// --------------- Main Component ---------------

export default function SupplyDemandZonesPanel() {
  const [symbol, setSymbol] = useState("BTCUSDT");

  const { data, isLoading, isError, refetch, dataUpdatedAt } = useQuery<SDZonesResponse>({
    queryKey: ["supply-demand", symbol],
    queryFn: () => fetchSDZones(symbol),
    refetchInterval: 60_000,
    retry: 2,
  });

  const handleRefetch = useCallback(() => { void refetch(); }, [refetch]);
  const lastUpdated = dataUpdatedAt ? new Date(dataUpdatedAt).toLocaleTimeString() : null;

  const demandZones = data?.zones.filter((z) => z.zone_type === "DEMAND").slice(0, 4) ?? [];
  const supplyZones = data?.zones.filter((z) => z.zone_type === "SUPPLY").slice(0, 4) ?? [];

  // Nearest zone logic
  const allZones = data?.zones ?? [];
  const nearestZone = allZones.reduce<SDZone | null>((nearest, zone) => {
    if (!data) return nearest;
    const dist = Math.abs(zone.price_mid - data.current_price);
    if (!nearest) return zone;
    const nearestDist = Math.abs(nearest.price_mid - data.current_price);
    return dist < nearestDist ? zone : nearest;
  }, null);

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-white">Supply & Demand Zones</h2>
          {lastUpdated && (
            <p className="mt-0.5 text-xs text-gray-500">Updated: {lastUpdated}</p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <select
            value={symbol}
            onChange={(e) => { setSymbol(e.target.value); }}
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
            aria-label="Refresh supply demand zones"
          >
            Refresh
          </button>
        </div>
      </div>

      {/* Error */}
      {isError && (
        <div className="mb-3 flex items-center justify-between rounded bg-red-500/10 px-3 py-2">
          <span className="text-xs text-red-400">Failed to load zone data</span>
          <button type="button" onClick={handleRefetch} className="text-xs text-red-400 underline hover:text-red-300">
            Retry
          </button>
        </div>
      )}

      {isLoading && <SDSkeleton />}

      {data && (
        <div className="space-y-4">
          {/* Current price indicator */}
          <div className="flex items-center justify-between rounded bg-blue-500/10 border border-blue-500/30 px-3 py-2">
            <span className="text-xs text-gray-400">Current Price</span>
            <span className="font-mono text-sm font-bold text-blue-400">
              {formatPrice(data.current_price)}
            </span>
          </div>

          {/* Nearest zone highlight */}
          {nearestZone && (
            <div className="rounded border border-yellow-500/30 bg-yellow-500/5 px-3 py-2">
              <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-yellow-500">
                Nearest Zone
              </p>
              <div className="flex items-center justify-between">
                <span className={`text-xs font-medium ${nearestZone.zone_type === "DEMAND" ? "text-green-400" : "text-red-400"}`}>
                  {nearestZone.zone_type} — {formatPrice(nearestZone.price_low)} – {formatPrice(nearestZone.price_high)}
                </span>
                {nearestZone.is_fresh && (
                  <span className="rounded bg-blue-500/20 px-1.5 py-0.5 text-[10px] font-bold text-blue-400">FRESH</span>
                )}
              </div>
            </div>
          )}

          {/* Two-column zones */}
          <div className="grid grid-cols-2 gap-3">
            {/* Demand zones */}
            <div>
              <h3 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-green-400">
                <span className="inline-block h-2 w-2 rounded-full bg-green-500" aria-hidden="true" />
                Demand
              </h3>
              <div className="space-y-2">
                {demandZones.length === 0 && (
                  <p className="text-xs text-gray-600 italic">No demand zones</p>
                )}
                {demandZones.map((zone, i) => (
                  <ZoneCard key={`demand-${i}`} zone={zone} currentPrice={data.current_price} />
                ))}
              </div>
            </div>

            {/* Supply zones */}
            <div>
              <h3 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-red-400">
                <span className="inline-block h-2 w-2 rounded-full bg-red-500" aria-hidden="true" />
                Supply
              </h3>
              <div className="space-y-2">
                {supplyZones.length === 0 && (
                  <p className="text-xs text-gray-600 italic">No supply zones</p>
                )}
                {supplyZones.map((zone, i) => (
                  <ZoneCard key={`supply-${i}`} zone={zone} currentPrice={data.current_price} />
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
