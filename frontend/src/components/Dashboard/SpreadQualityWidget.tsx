/**
 * SpreadQualityWidget
 * Shows entry quality score based on spread and order book depth.
 * Fetches from GET /api/v1/features/spread-quality/{symbol} — refreshes every 10 seconds.
 */

import { useQuery } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import axios from "axios";

// --------------- Types ---------------

interface SpreadQualityData {
  symbol: string;
  current_spread_pct: number;
  avg_spread_pct: number;
  spread_ratio: number;
  depth_imbalance: number;
  entry_quality_score: number;
  recommendation: string;
  slippage_estimate_pct: number;
}

// --------------- Constants ---------------

const SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"];

// --------------- Helpers ---------------

type QualityTier = "enter_now" | "ok" | "avoid";

function getQualityTier(score: number): QualityTier {
  if (score >= 8) return "enter_now";
  if (score >= 5) return "ok";
  return "avoid";
}

const QUALITY_STYLES: Record<
  QualityTier,
  { gauge: string; badge: string; gaugeBg: string; label: string; text: string }
> = {
  enter_now: {
    gauge: "#22c55e",
    badge: "bg-green-500/20 text-green-400 border-green-500/30",
    gaugeBg: "bg-green-500",
    label: "ENTER NOW",
    text: "text-green-400",
  },
  ok: {
    gauge: "#f59e0b",
    badge: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
    gaugeBg: "bg-yellow-500",
    label: "OK",
    text: "text-yellow-400",
  },
  avoid: {
    gauge: "#ef4444",
    badge: "bg-red-500/20 text-red-400 border-red-500/30",
    gaugeBg: "bg-red-500",
    label: "AVOID / WAIT",
    text: "text-red-400",
  },
};

interface SpreadQualityRaw {
  status: string;
  data: {
    symbol: string;
    spread_bps: number;
    estimated_slippage_pct: number;
    quality_score: number;
    quality_label: string;
    recommended: boolean;
    ask_depth_5levels_usd: number;
    best_bid: number;
    best_ask: number;
  };
}

const LABEL_RECOMMENDATIONS: Record<string, string> = {
  EXCELLENT: "Excellent entry conditions — proceed with full size.",
  GOOD: "Good entry conditions — standard position sizing.",
  FAIR: "Fair conditions — consider reducing position size by 30%.",
  POOR: "Poor conditions — avoid new entries, high spread risk.",
};

async function fetchSpreadQuality(symbol: string): Promise<SpreadQualityData> {
  const { data: envelope } = await axios.get<SpreadQualityRaw>(
    `/api/v1/features/spread-quality/${symbol}`
  );
  const raw = envelope.data ?? (envelope as unknown as SpreadQualityRaw["data"]);
  const spreadPct = (raw.spread_bps ?? 0) / 100;
  const label = raw.quality_label ?? "FAIR";
  return {
    symbol: raw.symbol ?? symbol,
    current_spread_pct: spreadPct,
    avg_spread_pct: spreadPct,
    spread_ratio: 1.0,
    depth_imbalance: 0.0,
    entry_quality_score: (raw.quality_score ?? 50) / 10,
    recommendation: LABEL_RECOMMENDATIONS[label] ?? label,
    slippage_estimate_pct: raw.estimated_slippage_pct ?? 0,
  };
}

// --------------- Score Gauge ---------------

interface ScoreGaugeProps {
  score: number;
  tier: QualityTier;
}

function ScoreGauge({ score, tier }: ScoreGaugeProps) {
  const styles = QUALITY_STYLES[tier];
  const clamped = Math.min(Math.max(score, 0), 10);
  const fraction = clamped / 10;

  // Semi-circle
  const cx = 60;
  const cy = 60;
  const r = 44;
  const angle = Math.PI - fraction * Math.PI;
  const x1 = cx + r * Math.cos(Math.PI);
  const y1 = cy + r * Math.sin(Math.PI);
  const x2 = cx + r * Math.cos(angle);
  const y2 = cy + r * Math.sin(angle);
  const largeArc = fraction > 0.5 ? 1 : 0;

  return (
    <div className="flex flex-col items-center" aria-label={`Entry quality score: ${score}/10 — ${styles.label}`}>
      <svg viewBox="0 0 120 70" className="w-32" aria-hidden="true">
        {/* Track */}
        <path
          d={`M ${cx + r * Math.cos(Math.PI)} ${cy + r * Math.sin(Math.PI)} A ${r} ${r} 0 0 1 ${cx + r * Math.cos(0)} ${cy + r * Math.sin(0)}`}
          fill="none"
          stroke="rgba(255,255,255,0.07)"
          strokeWidth="10"
          strokeLinecap="round"
        />
        {/* Progress */}
        {clamped > 0 && (
          <path
            d={`M ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2}`}
            fill="none"
            stroke={styles.gauge}
            strokeWidth="10"
            strokeLinecap="round"
            style={{ transition: "all 0.5s ease" }}
          />
        )}
        {/* Score text */}
        <text x={cx} y={cy - 4} textAnchor="middle" fill="white" fontSize="18" fontWeight="bold" fontFamily="monospace">
          {score.toFixed(1)}
        </text>
        <text x={cx} y={cy + 10} textAnchor="middle" fill="rgba(156,163,175,1)" fontSize="7.5">
          / 10
        </text>
      </svg>
    </div>
  );
}

// --------------- Skeleton ---------------

function SpreadSkeleton() {
  return (
    <div className="space-y-3" aria-busy="true" aria-label="Loading spread quality data">
      <div className="flex justify-center">
        <div className="h-20 w-32 animate-pulse rounded bg-white/5" />
      </div>
      <div className="h-8 animate-pulse rounded bg-white/5" />
      {[...Array(4)].map((_, i) => (
        <div key={i} className="h-4 animate-pulse rounded bg-white/5" />
      ))}
    </div>
  );
}

// --------------- Main Component ---------------

export default function SpreadQualityWidget() {
  const [symbol, setSymbol] = useState("BTCUSDT");

  const { data, isLoading, isError, refetch, dataUpdatedAt } = useQuery<SpreadQualityData>({
    queryKey: ["spread-quality", symbol],
    queryFn: () => fetchSpreadQuality(symbol),
    refetchInterval: 10_000,
    retry: 2,
  });

  const handleRefetch = useCallback(() => { void refetch(); }, [refetch]);
  const lastUpdated = dataUpdatedAt ? new Date(dataUpdatedAt).toLocaleTimeString() : null;

  const tier = data ? getQualityTier(data.entry_quality_score) : "avoid";
  const styles = QUALITY_STYLES[tier];

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-white">Entry Quality</h2>
          {lastUpdated && (
            <p className="mt-0.5 text-xs text-gray-500">
              Updated: {lastUpdated}{" "}
              <span className="text-blue-400">(live)</span>
            </p>
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
            aria-label="Refresh spread quality"
          >
            Refresh
          </button>
        </div>
      </div>

      {/* Error */}
      {isError && (
        <div className="mb-3 flex items-center justify-between rounded bg-red-500/10 px-3 py-2">
          <span className="text-xs text-red-400">Failed to load spread data</span>
          <button type="button" onClick={handleRefetch} className="text-xs text-red-400 underline hover:text-red-300">
            Retry
          </button>
        </div>
      )}

      {isLoading && <SpreadSkeleton />}

      {data && (
        <div className="space-y-4">
          {/* Score gauge */}
          <div className="flex flex-col items-center gap-1">
            <ScoreGauge score={data.entry_quality_score} tier={tier} />
            <span className={`rounded border px-3 py-1 text-sm font-bold ${styles.badge}`}>
              {styles.label}
            </span>
          </div>

          {/* Recommendation */}
          <div className={`rounded bg-gray-800/60 border border-gray-700 px-3 py-2`}>
            <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-500 mb-0.5">
              Recommendation
            </p>
            <p className={`text-xs font-medium ${styles.text}`}>{data.recommendation}</p>
          </div>

          {/* Stats */}
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div className="rounded bg-gray-800/60 p-2">
              <p className="text-[10px] text-gray-500">Current Spread</p>
              <p className="font-mono font-semibold text-gray-200">
                {data.current_spread_pct.toFixed(4)}%
              </p>
            </div>
            <div className="rounded bg-gray-800/60 p-2">
              <p className="text-[10px] text-gray-500">Avg Spread</p>
              <p className="font-mono font-semibold text-gray-200">
                {data.avg_spread_pct.toFixed(4)}%
              </p>
            </div>
            <div className="rounded bg-gray-800/60 p-2">
              <p className="text-[10px] text-gray-500">Spread Ratio</p>
              <p className={`font-mono font-semibold ${data.spread_ratio > 1.5 ? "text-red-400" : "text-gray-200"}`}>
                {data.spread_ratio.toFixed(2)}x
              </p>
            </div>
            <div className="rounded bg-gray-800/60 p-2">
              <p className="text-[10px] text-gray-500">Est. Slippage</p>
              <p className={`font-mono font-semibold ${data.slippage_estimate_pct > 0.05 ? "text-red-400" : "text-gray-200"}`}>
                {data.slippage_estimate_pct.toFixed(4)}%
              </p>
            </div>
          </div>

          {/* Depth imbalance */}
          <div>
            <div className="mb-1 flex items-center justify-between text-[10px] text-gray-500">
              <span>Depth Imbalance (bid/ask)</span>
              <span className={`font-mono ${data.depth_imbalance > 0 ? "text-green-400" : "text-red-400"}`}>
                {data.depth_imbalance > 0 ? "+" : ""}{data.depth_imbalance.toFixed(2)}
              </span>
            </div>
            <div className="relative h-2 w-full overflow-hidden rounded-full bg-gray-700">
              <div className="absolute left-1/2 top-0 bottom-0 w-px bg-gray-500" aria-hidden="true" />
              {data.depth_imbalance !== 0 && (
                <div
                  className={`absolute top-0 bottom-0 transition-all duration-500 ${data.depth_imbalance > 0 ? "bg-green-500" : "bg-red-500"}`}
                  style={{
                    left: data.depth_imbalance > 0 ? "50%" : `${50 - Math.min(Math.abs(data.depth_imbalance) * 25, 50)}%`,
                    width: `${Math.min(Math.abs(data.depth_imbalance) * 25, 50)}%`,
                  }}
                />
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
