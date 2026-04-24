/**
 * OptionsFlowPanel
 * Displays options market analysis: IV rank, PCR, GEX levels, max pain.
 * Fetches from GET /api/v1/features/options-flow/{symbol}
 */

import { useQuery } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import axios from "axios";

// --------------- Types ---------------

interface OptionsFlowData {
  symbol: string;
  bias: string;
  confidence: number;
  iv_rank: number;
  iv_signal: string;
  pcr_signal: string;
  gex_nearest_level: number;
  gex_signal: string;
  max_pain: number;
  description: string;
}

// --------------- Constants ---------------

const SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"];

// --------------- Helpers ---------------

function getBiasStyle(bias: string): { badge: string; dot: string; label: string } {
  const b = bias.toUpperCase();
  if (b.includes("BULL")) return { badge: "bg-green-500/20 text-green-400", dot: "bg-green-500", label: "text-green-400" };
  if (b.includes("BEAR")) return { badge: "bg-red-500/20 text-red-400", dot: "bg-red-500", label: "text-red-400" };
  return { badge: "bg-gray-700 text-gray-400", dot: "bg-gray-500", label: "text-gray-400" };
}

function getIVZone(ivRank: number): { label: string; color: string; arc: string } {
  if (ivRank < 30) return { label: "LOW", color: "text-green-400", arc: "#22c55e" };
  if (ivRank <= 70) return { label: "NORMAL", color: "text-yellow-400", arc: "#f59e0b" };
  return { label: "HIGH", color: "text-red-400", arc: "#ef4444" };
}

function getPCRStyle(signal: string): { arrow: string; color: string } {
  const s = signal.toUpperCase();
  if (s.includes("BULL")) return { arrow: "▲", color: "text-green-400" };
  if (s.includes("BEAR")) return { arrow: "▼", color: "text-red-400" };
  return { arrow: "●", color: "text-gray-400" };
}

function formatPrice(price: number): string {
  if (price >= 10000) return `$${price.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
  if (price >= 100) return `$${price.toFixed(2)}`;
  return `$${price.toFixed(4)}`;
}

async function fetchOptionsFlow(symbol: string): Promise<OptionsFlowData> {
  const { data } = await axios.get<OptionsFlowData>(`/api/v1/features/options-flow/${symbol}`);
  return data;
}

// --------------- IV Gauge ---------------

interface IVGaugeProps {
  ivRank: number;
}

function IVGauge({ ivRank }: IVGaugeProps) {
  const zone = getIVZone(ivRank);
  const clamped = Math.min(Math.max(ivRank, 0), 100);
  const cx = 60;
  const cy = 60;
  const r = 44;
  // Semi-circle: left = PI, right = 0, going through top
  const angle = Math.PI - (clamped / 100) * Math.PI;
  const x1 = cx + r * Math.cos(Math.PI);
  const y1 = cy + r * Math.sin(Math.PI);
  const x2 = cx + r * Math.cos(angle);
  const y2 = cy + r * Math.sin(angle);
  const largeArc = clamped > 50 ? 1 : 0;

  return (
    <div className="flex flex-col items-center" aria-label={`IV Rank: ${ivRank} — ${zone.label}`}>
      <svg viewBox="0 0 120 70" className="w-28" aria-hidden="true">
        {/* Track */}
        <path
          d={`M ${cx + r * Math.cos(Math.PI)} ${cy + r * Math.sin(Math.PI)} A ${r} ${r} 0 0 1 ${cx + r * Math.cos(0)} ${cy + r * Math.sin(0)}`}
          fill="none"
          stroke="rgba(255,255,255,0.07)"
          strokeWidth="9"
          strokeLinecap="round"
        />
        {/* Zone bands */}
        {/* Low band: 0-30 */}
        <path
          d={`M ${cx + r * Math.cos(Math.PI)} ${cy + r * Math.sin(Math.PI)} A ${r} ${r} 0 0 1 ${cx + r * Math.cos(Math.PI - 0.3 * Math.PI)} ${cy + r * Math.sin(Math.PI - 0.3 * Math.PI)}`}
          fill="none"
          stroke="rgba(34,197,94,0.3)"
          strokeWidth="9"
          strokeLinecap="round"
        />
        {/* Progress arc */}
        {clamped > 0 && (
          <path
            d={`M ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2}`}
            fill="none"
            stroke={zone.arc}
            strokeWidth="9"
            strokeLinecap="round"
            style={{ transition: "all 0.5s ease" }}
          />
        )}
        {/* Center text */}
        <text x={cx} y={cy - 4} textAnchor="middle" fill="white" fontSize="14" fontWeight="bold" fontFamily="monospace">
          {ivRank.toFixed(0)}
        </text>
        <text x={cx} y={cy + 10} textAnchor="middle" fill="rgba(156,163,175,1)" fontSize="8">
          IV RANK
        </text>
      </svg>
      <span className={`text-xs font-bold ${zone.color}`}>{zone.label} IV</span>
    </div>
  );
}

// --------------- Skeleton ---------------

function OptionsSkeleton() {
  return (
    <div className="space-y-4" aria-busy="true" aria-label="Loading options flow data">
      <div className="h-6 w-32 animate-pulse rounded bg-white/5" />
      <div className="flex justify-center">
        <div className="h-24 w-28 animate-pulse rounded bg-white/5" />
      </div>
      <div className="h-12 animate-pulse rounded bg-white/5" />
      <div className="h-16 animate-pulse rounded bg-white/5" />
    </div>
  );
}

// --------------- Main Component ---------------

export default function OptionsFlowPanel() {
  const [symbol, setSymbol] = useState("BTCUSDT");

  const { data, isLoading, isError, refetch, dataUpdatedAt } = useQuery<OptionsFlowData>({
    queryKey: ["options-flow", symbol],
    queryFn: () => fetchOptionsFlow(symbol),
    refetchInterval: 60_000,
    retry: 2,
  });

  const handleRefetch = useCallback(() => { void refetch(); }, [refetch]);
  const lastUpdated = dataUpdatedAt ? new Date(dataUpdatedAt).toLocaleTimeString() : null;

  const biasStyle = data ? getBiasStyle(data.bias) : null;
  const pcrStyle = data ? getPCRStyle(data.pcr_signal) : null;

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-white">Options Flow</h2>
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
            aria-label="Refresh options flow"
          >
            Refresh
          </button>
        </div>
      </div>

      {/* Error */}
      {isError && (
        <div className="mb-3 flex items-center justify-between rounded bg-red-500/10 px-3 py-2">
          <span className="text-xs text-red-400">Failed to load options data</span>
          <button type="button" onClick={handleRefetch} className="text-xs text-red-400 underline hover:text-red-300">
            Retry
          </button>
        </div>
      )}

      {isLoading && <OptionsSkeleton />}

      {data && biasStyle && pcrStyle && (
        <div className="space-y-4">
          {/* Overall bias badge */}
          <div className={`flex items-center justify-between rounded-lg border border-gray-700 px-3 py-2.5`}>
            <div className="flex items-center gap-2">
              <div className={`h-2.5 w-2.5 rounded-full ${biasStyle.dot}`} aria-hidden="true" />
              <span className="text-xs text-gray-400">Overall Bias</span>
            </div>
            <div className="flex items-center gap-2">
              <span className={`rounded px-2 py-0.5 text-xs font-bold uppercase ${biasStyle.badge}`}>
                {data.bias}
              </span>
              <span className="font-mono text-xs text-gray-500">{data.confidence.toFixed(0)}%</span>
            </div>
          </div>

          {/* Section 1: IV Rank */}
          <div className="rounded border border-border bg-gray-800/60 px-3 py-3">
            <p className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-gray-500">
              Implied Volatility Rank
            </p>
            <div className="flex items-center gap-4">
              <IVGauge ivRank={data.iv_rank} />
              <div className="flex-1 space-y-1.5">
                {/* Zone markers */}
                {[
                  { label: "Low (<30)", color: "bg-green-500" },
                  { label: "Normal (30-70)", color: "bg-yellow-500" },
                  { label: "High (>70)", color: "bg-red-500" },
                ].map(({ label, color }) => (
                  <div key={label} className="flex items-center gap-2 text-[10px] text-gray-500">
                    <span className={`inline-block h-1.5 w-3 rounded-full ${color}`} aria-hidden="true" />
                    {label}
                  </div>
                ))}
                <p className="mt-1 text-xs text-gray-300 italic">{data.iv_signal}</p>
              </div>
            </div>
          </div>

          {/* Section 2: Put/Call Ratio */}
          <div className="rounded border border-border bg-gray-800/60 px-3 py-3">
            <p className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-gray-500">
              Put / Call Ratio Signal
            </p>
            <div className="flex items-center justify-between">
              <span className="text-xs text-gray-300">{data.pcr_signal}</span>
              <span className={`text-xl font-bold ${pcrStyle.color}`} aria-hidden="true">
                {pcrStyle.arrow}
              </span>
            </div>
          </div>

          {/* Section 3: GEX + Max Pain */}
          <div className="rounded border border-border bg-gray-800/60 px-3 py-3 space-y-2">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-500">
              GEX &amp; Max Pain
            </p>
            <div className="flex items-center justify-between">
              <span className="text-xs text-gray-400">Nearest GEX Level</span>
              <span className="font-mono text-xs font-semibold text-blue-400">
                {formatPrice(data.gex_nearest_level)}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-gray-400">GEX Signal</span>
              <span className="text-xs text-gray-300">{data.gex_signal}</span>
            </div>
            <div className="flex items-center justify-between rounded bg-yellow-500/10 border border-yellow-500/30 px-2 py-1.5">
              <span className="text-xs text-yellow-500 font-medium">Max Pain</span>
              <span className="font-mono text-sm font-bold text-yellow-400">
                {formatPrice(data.max_pain)}
              </span>
            </div>
          </div>

          {/* Description */}
          <p className="text-xs text-gray-400 italic leading-relaxed">{data.description}</p>
        </div>
      )}
    </div>
  );
}
