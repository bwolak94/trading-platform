/**
 * MarketProfilePanel
 * Displays Market Profile (TPO) Value Area analysis with POC, VAH, VAL.
 * Fetches from GET /api/v1/features/market-profile/{symbol}
 */

import { useQuery } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import axios from "axios";

// --------------- Types ---------------

interface MarketProfileData {
  symbol: string;
  poc: number;
  vah: number;
  val: number;
  value_area_width_pct: number;
  current_price: number;
  price_vs_va: string;
  single_prints: number[];
  signal: string;
  confidence: number;
  description: string;
}

// --------------- Constants ---------------

const SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"];

// --------------- Helpers ---------------

function getPriceVAStyle(priceVsVA: string): {
  badge: string;
  label: string;
} {
  const p = priceVsVA.toUpperCase();
  if (p.includes("ABOVE")) return { badge: "bg-red-500/20 text-red-400", label: "ABOVE VA" };
  if (p.includes("BELOW")) return { badge: "bg-green-500/20 text-green-400", label: "BELOW VA" };
  return { badge: "bg-blue-500/20 text-blue-400", label: "IN VALUE" };
}

function getSignalStyle(signal: string): string {
  const s = signal.toUpperCase();
  if (s.includes("BUY") || s.includes("LONG")) return "text-green-400";
  if (s.includes("SELL") || s.includes("SHORT")) return "text-red-400";
  return "text-yellow-400";
}

function formatPrice(price: number): string {
  if (price >= 10000) return `$${price.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
  if (price >= 100) return `$${price.toFixed(2)}`;
  return `$${price.toFixed(4)}`;
}

async function fetchMarketProfile(symbol: string): Promise<MarketProfileData> {
  const { data } = await axios.get<MarketProfileData>(
    `/api/v1/features/market-profile/${symbol}`
  );
  return data;
}

// --------------- Mini Profile Visualization ---------------

interface MiniProfileProps {
  data: MarketProfileData;
}

function MiniProfileVisualization({ data }: MiniProfileProps) {
  const prices = [data.vah, data.poc, data.val, data.current_price, ...data.single_prints];
  const minP = Math.min(...prices) * 0.9995;
  const maxP = Math.max(...prices) * 1.0005;
  const range = maxP - minP;

  const toY = (price: number): number => {
    // 0 = top (high), 100 = bottom (low)
    return ((maxP - price) / range) * 100;
  };

  const vahY = toY(data.vah);
  const valY = toY(data.val);
  const pocY = toY(data.poc);
  const curY = toY(data.current_price);

  return (
    <div
      className="relative h-36 w-full overflow-hidden rounded border border-gray-700 bg-gray-900"
      aria-label="Market profile visualization"
    >
      {/* Value area shading */}
      <div
        className="absolute left-0 right-0 bg-blue-500/10 border-y border-blue-500/20"
        style={{ top: `${vahY}%`, height: `${valY - vahY}%` }}
        aria-label={`Value area from VAL ${formatPrice(data.val)} to VAH ${formatPrice(data.vah)}`}
      />

      {/* VAH line */}
      <div
        className="absolute left-0 right-0 border-t border-dashed border-red-400/60"
        style={{ top: `${vahY}%` }}
        aria-hidden="true"
      >
        <span className="absolute left-1 -top-3 text-[9px] text-red-400 font-mono">
          VAH {formatPrice(data.vah)}
        </span>
      </div>

      {/* VAL line */}
      <div
        className="absolute left-0 right-0 border-t border-dashed border-green-400/60"
        style={{ top: `${valY}%` }}
        aria-hidden="true"
      >
        <span className="absolute left-1 text-[9px] text-green-400 font-mono">
          VAL {formatPrice(data.val)}
        </span>
      </div>

      {/* POC line */}
      <div
        className="absolute left-0 right-0 border-t-2 border-yellow-400"
        style={{ top: `${pocY}%` }}
        aria-hidden="true"
      >
        <span className="absolute right-1 -top-3 text-[9px] text-yellow-400 font-bold font-mono">
          POC {formatPrice(data.poc)}
        </span>
      </div>

      {/* Current price indicator */}
      <div
        className="absolute left-0 right-0 border-t border-white/80"
        style={{ top: `${curY}%` }}
        aria-hidden="true"
      >
        <span className="absolute right-1 text-[9px] text-white font-mono">
          {formatPrice(data.current_price)}
        </span>
      </div>

      {/* Single prints */}
      {data.single_prints.slice(0, 3).map((sp, i) => {
        const spY = toY(sp);
        return (
          <div
            key={i}
            className="absolute left-0 right-0 border-t border-orange-400/40 border-dashed"
            style={{ top: `${spY}%` }}
            aria-hidden="true"
          />
        );
      })}
    </div>
  );
}

// --------------- Skeleton ---------------

function ProfileSkeleton() {
  return (
    <div className="space-y-3" aria-busy="true" aria-label="Loading market profile data">
      <div className="h-6 w-32 animate-pulse rounded bg-white/5" />
      <div className="h-36 animate-pulse rounded bg-white/5" />
      <div className="h-4 w-full animate-pulse rounded bg-white/5" />
      <div className="h-4 w-3/4 animate-pulse rounded bg-white/5" />
    </div>
  );
}

// --------------- Main Component ---------------

export default function MarketProfilePanel() {
  const [symbol, setSymbol] = useState("BTCUSDT");

  const { data, isLoading, isError, refetch, dataUpdatedAt } = useQuery<MarketProfileData>({
    queryKey: ["market-profile", symbol],
    queryFn: () => fetchMarketProfile(symbol),
    refetchInterval: 60_000,
    retry: 2,
  });

  const handleRefetch = useCallback(() => { void refetch(); }, [refetch]);
  const lastUpdated = dataUpdatedAt ? new Date(dataUpdatedAt).toLocaleTimeString() : null;

  const priceVAStyle = data ? getPriceVAStyle(data.price_vs_va) : null;
  const signalColor = data ? getSignalStyle(data.signal) : "";

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-white">Market Profile (TPO)</h2>
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
            aria-label="Refresh market profile data"
          >
            Refresh
          </button>
        </div>
      </div>

      {/* Error */}
      {isError && (
        <div className="mb-3 flex items-center justify-between rounded bg-red-500/10 px-3 py-2">
          <span className="text-xs text-red-400">Failed to load market profile</span>
          <button type="button" onClick={handleRefetch} className="text-xs text-red-400 underline hover:text-red-300">
            Retry
          </button>
        </div>
      )}

      {isLoading && <ProfileSkeleton />}

      {data && priceVAStyle && (
        <div className="space-y-4">
          {/* Price vs VA badge */}
          <div className="flex items-center justify-between">
            <span className={`rounded px-2 py-0.5 text-xs font-bold ${priceVAStyle.badge}`}>
              {priceVAStyle.label}
            </span>
            <span className="text-xs text-gray-500">
              VA Width: <span className="font-mono text-gray-300">{data.value_area_width_pct.toFixed(2)}%</span>
            </span>
          </div>

          {/* Mini visualization */}
          <MiniProfileVisualization data={data} />

          {/* Key levels grid */}
          <div className="grid grid-cols-3 gap-2">
            <div className="rounded bg-red-500/10 border border-red-500/20 p-2 text-center">
              <p className="text-[10px] text-red-400 font-semibold">VAH</p>
              <p className="font-mono text-xs font-bold text-white">{formatPrice(data.vah)}</p>
            </div>
            <div className="rounded bg-yellow-500/10 border border-yellow-500/20 p-2 text-center">
              <p className="text-[10px] text-yellow-400 font-semibold">POC</p>
              <p className="font-mono text-xs font-bold text-white">{formatPrice(data.poc)}</p>
            </div>
            <div className="rounded bg-green-500/10 border border-green-500/20 p-2 text-center">
              <p className="text-[10px] text-green-400 font-semibold">VAL</p>
              <p className="font-mono text-xs font-bold text-white">{formatPrice(data.val)}</p>
            </div>
          </div>

          {/* Signal */}
          <div className="flex items-center justify-between rounded bg-gray-800/60 border border-border px-3 py-2">
            <span className="text-xs text-gray-400">Signal</span>
            <div className="flex items-center gap-2">
              <span className={`text-xs font-bold ${signalColor}`}>{data.signal}</span>
              <span className="font-mono text-xs text-gray-500">{data.confidence.toFixed(0)}%</span>
            </div>
          </div>

          {/* Description */}
          <p className="text-xs text-gray-400 italic leading-relaxed">{data.description}</p>

          {/* Single prints info */}
          {data.single_prints.length > 0 && (
            <div className="flex items-center gap-2 text-[10px] text-gray-500">
              <span className="inline-block h-0.5 w-4 border-t border-dashed border-orange-400/60" aria-hidden="true" />
              <span>{data.single_prints.length} single print area{data.single_prints.length > 1 ? "s" : ""} (unfair prices)</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
