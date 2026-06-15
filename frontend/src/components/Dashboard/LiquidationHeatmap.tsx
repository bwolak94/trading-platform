import { useEffect, useRef, useState } from "react";
import {
  fetchLiquidationHeatmap,
  type ForcedLiquidation,
  type LiquidationBin,
  type LiquidationHeatmapData,
  type TheoreticalLevel,
} from "../../api/client";

interface LiquidationHeatmapProps {
  asset: string;
}

/** Format large USD values: $1.2M, $500K, etc. */
function fmtUsd(value: number): string {
  if (value >= 1e9) return `$${(value / 1e9).toFixed(1)}B`;
  if (value >= 1e6) return `$${(value / 1e6).toFixed(1)}M`;
  if (value >= 1e3) return `$${(value / 1e3).toFixed(1)}K`;
  if (value >= 1) return `$${value.toFixed(0)}`;
  return "$0";
}

/** Interpolate color based on intensity 0-1: deep purple -> magenta -> neon yellow */
function intensityColor(intensity: number): string {
  const clamped = Math.max(0, Math.min(1, intensity));
  if (clamped < 0.5) {
    // purple (#2d1b69) -> magenta (#d946ef)
    const t = clamped * 2;
    const r = Math.round(45 + (217 - 45) * t);
    const g = Math.round(27 + (70 - 27) * t);
    const b = Math.round(105 + (239 - 105) * t);
    return `rgb(${r}, ${g}, ${b})`;
  }
  // magenta (#d946ef) -> neon yellow (#facc15)
  const t = (clamped - 0.5) * 2;
  const r = Math.round(217 + (250 - 217) * t);
  const g = Math.round(70 + (204 - 70) * t);
  const b = Math.round(239 + (21 - 239) * t);
  return `rgb(${r}, ${g}, ${b})`;
}

/** Time ago string. */
function timeAgo(timestampSec: number): string {
  const diff = Date.now() / 1000 - timestampSec;
  if (diff < 60) return `${Math.round(diff)}s ago`;
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.round(diff / 3600)}h ago`;
  return `${Math.round(diff / 86400)}d ago`;
}

type Tab = "heatmap" | "feed" | "levels";

export function LiquidationHeatmap({ asset }: LiquidationHeatmapProps) {
  const [data, setData] = useState<LiquidationHeatmapData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("heatmap");
  const [newIds, setNewIds] = useState<Set<number>>(new Set());
  const prevCountRef = useRef(0);

  // Fetch data
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchLiquidationHeatmap(asset, 5)
      .then((d) => {
        if (!cancelled) {
          setData(d);
          setLoading(false);
          prevCountRef.current = d.recent_liquidations.length;
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load");
          setLoading(false);
        }
      });
    return () => { cancelled = true; };
  }, [asset]);

  // Auto-refresh every 10s
  useEffect(() => {
    const timer = setInterval(() => {
      fetchLiquidationHeatmap(asset, 5)
        .then((d) => {
          // Detect new liquidations for pulse animation
          const prevCount = prevCountRef.current;
          if (d.recent_liquidations.length > prevCount) {
            const newCount = d.recent_liquidations.length - prevCount;
            const ids = new Set<number>();
            for (let i = 0; i < newCount; i++) {
              ids.add(i);
            }
            setNewIds(ids);
            setTimeout(() => { setNewIds(new Set()); }, 2000);
          }
          prevCountRef.current = d.recent_liquidations.length;
          setData(d);
          setError(null);
        })
        .catch(() => {});
    }, 10_000);
    return () => { clearInterval(timer); };
  }, [asset]);

  // Warning: price within 0.5% of high-intensity zone
  const warningZone = data?.bins.find(
    (bin) =>
      bin.intensity > 0.7 &&
      data.current_price > 0 &&
      Math.abs(bin.price_mid - data.current_price) / data.current_price < 0.005,
  );

  if (loading) {
    return (
      <div
        className="rounded-lg border border-border bg-[#0d1117] p-4"
        role="status"
        aria-label="Loading liquidation heatmap"
      >
        <div className="flex items-center gap-2 py-8 text-sm text-gray-400 justify-center">
          <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          Loading liquidation heatmap...
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="rounded-lg border border-border bg-[#0d1117] p-4">
        <div className="text-center py-8 text-sm text-gray-500">
          {error ?? "No liquidation data available"}
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-border bg-[#0d1117]" role="region" aria-label="Liquidation Heatmap">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <h3 className="text-sm font-semibold text-white">Liquidation Heatmap</h3>
        <div className="flex items-center gap-3 text-xs text-gray-400">
          <span>OI: {fmtUsd(data.open_interest * data.current_price)}</span>
          <span className="text-gray-600">|</span>
          <span>Price: <span className="text-white font-mono">${data.current_price.toLocaleString()}</span></span>
        </div>
      </div>

      {/* Warning banner */}
      {warningZone && (
        <div className="mx-4 mt-3 flex items-center gap-2 rounded border border-yellow-500/30 bg-yellow-500/10 px-3 py-2" role="alert">
          <span className="text-yellow-400 text-xs font-bold">WARNING</span>
          <span className="text-xs text-yellow-300">
            Price is within 0.5% of high-intensity liquidation zone at ${warningZone.price_mid.toLocaleString()} ({fmtUsd(warningZone.total_usd)})
          </span>
        </div>
      )}

      {/* Summary stats */}
      <div className="grid grid-cols-4 gap-2 px-4 py-3 text-xs">
        <div className="rounded bg-[#161b22] p-2 text-center">
          <div className="text-gray-500 mb-0.5">Long Liq</div>
          <div className="font-mono text-red-400 font-semibold">{fmtUsd(data.total_long_liq_usd)}</div>
        </div>
        <div className="rounded bg-[#161b22] p-2 text-center">
          <div className="text-gray-500 mb-0.5">Short Liq</div>
          <div className="font-mono text-green-400 font-semibold">{fmtUsd(data.total_short_liq_usd)}</div>
        </div>
        <div className="rounded bg-[#161b22] p-2 text-center">
          <div className="text-gray-500 mb-0.5">Net Pressure</div>
          <div className={`font-mono font-semibold ${data.total_long_liq_usd > data.total_short_liq_usd ? "text-red-400" : "text-green-400"}`}>
            {data.total_long_liq_usd > data.total_short_liq_usd ? "Bearish" : "Bullish"}
          </div>
        </div>
        <div className="rounded bg-[#161b22] p-2 text-center">
          <div className="text-gray-500 mb-0.5">Open Interest</div>
          <div className="font-mono text-white font-semibold">{fmtUsd(data.open_interest * data.current_price)}</div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-0 border-b border-border">
        {([
          { id: "heatmap" as const, label: "Density Chart" },
          { id: "feed" as const, label: "Liquidation Feed" },
          { id: "levels" as const, label: "Theoretical Levels" },
        ]).map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => { setTab(t.id); }}
            className={`px-4 py-2.5 text-xs font-medium transition-colors ${
              tab === t.id
                ? "border-b-2 border-purple-500 text-white"
                : "text-gray-400 hover:text-gray-200"
            }`}
            aria-label={`${t.label} tab`}
            aria-selected={tab === t.id}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="p-4">
        {tab === "heatmap" && (
          <DensityChart bins={data.bins} currentPrice={data.current_price} theoreticalLevels={data.theoretical_levels} />
        )}
        {tab === "feed" && (
          <LiquidationFeed liquidations={data.recent_liquidations} newIds={newIds} />
        )}
        {tab === "levels" && (
          <TheoreticalLevelsView levels={data.theoretical_levels} currentPrice={data.current_price} />
        )}
      </div>
    </div>
  );
}

/* --- Density Chart --- */

function DensityChart({
  bins,
  currentPrice,
  theoreticalLevels,
}: {
  bins: LiquidationBin[];
  currentPrice: number;
  theoreticalLevels: TheoreticalLevel[];
}) {
  if (bins.length === 0) {
    return (
      <div className="text-center py-8 text-xs text-gray-500">
        No liquidation data in this price range yet. Theoretical levels are shown in the Theoretical Levels tab.
      </div>
    );
  }

  const maxUsd = Math.max(...bins.map((b) => b.total_usd), 1);

  // Find which bins are near theoretical levels
  const levelPrices = new Map<number, TheoreticalLevel>();
  for (const level of theoreticalLevels) {
    // Find closest bin
    let closestBin: LiquidationBin | null = null;
    let closestDist = Infinity;
    for (const bin of bins) {
      const dist = Math.abs(bin.price_mid - level.price);
      if (dist < closestDist) {
        closestDist = dist;
        closestBin = bin;
      }
    }
    if (closestBin && closestDist / currentPrice < 0.01) {
      levelPrices.set(closestBin.price_mid, level);
    }
  }

  return (
    <div className="space-y-0.5" role="list" aria-label="Liquidation density chart">
      {bins.map((bin) => {
        const isCurrentPrice =
          currentPrice >= bin.price_low && currentPrice <= bin.price_high;
        const longPct = bin.total_usd > 0 ? (bin.long_usd / maxUsd) * 100 : 0;
        const shortPct = bin.total_usd > 0 ? (bin.short_usd / maxUsd) * 100 : 0;
        const theoryLevel = levelPrices.get(bin.price_mid);

        return (
          <div
            key={bin.price_low}
            className={`flex items-center gap-2 rounded px-2 py-1 ${
              isCurrentPrice ? "ring-1 ring-white/40 bg-white/5" : "bg-transparent"
            }`}
            role="listitem"
            aria-label={`Price ${bin.price_mid.toLocaleString()}: ${fmtUsd(bin.total_usd)} liquidations`}
          >
            {/* Price label */}
            <div className="w-20 flex-shrink-0 text-right">
              <span className={`font-mono text-[11px] ${isCurrentPrice ? "text-white font-bold" : "text-gray-400"}`}>
                ${bin.price_mid.toLocaleString()}
              </span>
              {isCurrentPrice && (
                <span className="ml-1 text-[9px] text-purple-400 font-bold">NOW</span>
              )}
            </div>

            {/* Long bar (left, red tint) */}
            <div className="flex-1 flex justify-end">
              <div
                className="h-3 rounded-l"
                style={{
                  width: `${longPct}%`,
                  backgroundColor: intensityColor(bin.intensity),
                  opacity: 0.6 + bin.intensity * 0.4,
                  filter: "hue-rotate(-20deg)",
                }}
              />
            </div>

            {/* Divider */}
            <div className="w-px h-3 bg-gray-700 flex-shrink-0" />

            {/* Short bar (right, green tint) */}
            <div className="flex-1">
              <div
                className="h-3 rounded-r"
                style={{
                  width: `${shortPct}%`,
                  backgroundColor: intensityColor(bin.intensity),
                  opacity: 0.6 + bin.intensity * 0.4,
                  filter: "hue-rotate(20deg)",
                }}
              />
            </div>

            {/* USD label */}
            <div className="w-16 flex-shrink-0 text-right">
              <span className="font-mono text-[10px] text-gray-500">{fmtUsd(bin.total_usd)}</span>
            </div>

            {/* Theoretical leverage label */}
            <div className="w-10 flex-shrink-0">
              {theoryLevel && (
                <span className={`text-[9px] font-bold px-1 rounded ${
                  theoryLevel.side === "long" ? "bg-red-500/20 text-red-400" : "bg-green-500/20 text-green-400"
                }`}>
                  {theoryLevel.leverage}x
                </span>
              )}
            </div>
          </div>
        );
      })}

      {/* Legend */}
      <div className="flex items-center justify-center gap-6 pt-3 text-[10px] text-gray-500">
        <div className="flex items-center gap-1">
          <div className="h-2 w-6 rounded" style={{ background: "linear-gradient(90deg, #2d1b69, #d946ef, #facc15)" }} />
          <span>Intensity</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="h-2 w-3 rounded bg-red-400/60" />
          <span>Long Liq (left)</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="h-2 w-3 rounded bg-green-400/60" />
          <span>Short Liq (right)</span>
        </div>
      </div>
    </div>
  );
}

/* --- Liquidation Feed --- */

function LiquidationFeed({
  liquidations,
  newIds,
}: {
  liquidations: ForcedLiquidation[];
  newIds: Set<number>;
}) {
  if (liquidations.length === 0) {
    return (
      <div className="text-center py-8 text-xs text-gray-500">
        No recent liquidations recorded yet.
      </div>
    );
  }

  return (
    <div className="space-y-1 max-h-96 overflow-y-auto" role="list" aria-label="Recent liquidation feed">
      {liquidations.map((liq, i) => {
        // SELL force order = long was liquidated (bearish), BUY = short was liquidated (bullish)
        const isLongLiq = liq.side === "SELL";
        const borderColor = isLongLiq ? "border-l-green-500" : "border-l-red-500";
        const isNew = newIds.has(i);

        return (
          <div
            key={`${liq.timestamp}-${i}`}
            className={`flex items-center justify-between rounded border-l-2 ${borderColor} bg-[#161b22] px-3 py-2 ${
              isNew ? "animate-pulse" : ""
            }`}
            role="listitem"
            aria-label={`${liq.side} liquidation at ${liq.price}`}
          >
            <div className="flex items-center gap-2">
              <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${
                isLongLiq
                  ? "bg-green-500/20 text-green-400"
                  : "bg-red-500/20 text-red-400"
              }`}>
                {isLongLiq ? "LONG LIQ" : "SHORT LIQ"}
              </span>
              <span className="font-mono text-xs text-white">
                {liq.symbol.replace("USDT", "")}
              </span>
            </div>
            <div className="flex items-center gap-3 text-xs">
              <span className="font-mono text-gray-300">${liq.price.toLocaleString()}</span>
              <span className="font-mono text-gray-400">{liq.quantity.toFixed(4)}</span>
              <span className={`font-mono font-semibold ${isLongLiq ? "text-green-400" : "text-red-400"}`}>
                {fmtUsd(liq.usd_value)}
              </span>
              <span className="text-gray-600 text-[10px]">{timeAgo(liq.timestamp)}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

/* --- Theoretical Levels --- */

function TheoreticalLevelsView({
  levels,
  currentPrice,
}: {
  levels: TheoreticalLevel[];
  currentPrice: number;
}) {
  if (levels.length === 0) {
    return (
      <div className="text-center py-8 text-xs text-gray-500">
        No theoretical levels available. Waiting for Open Interest data.
      </div>
    );
  }

  const shortLevels = levels
    .filter((l) => l.side === "short")
    .sort((a, b) => a.price - b.price);
  const longLevels = levels
    .filter((l) => l.side === "long")
    .sort((a, b) => b.price - a.price);

  return (
    <div className="space-y-4" role="list" aria-label="Theoretical liquidation levels">
      {/* Short liquidation levels (above price) */}
      <div>
        <h4 className="mb-2 text-xs font-medium uppercase tracking-wide text-red-400">
          Short Liquidation Zones (Above)
        </h4>
        <div className="space-y-1">
          {shortLevels.map((level) => (
            <TheoreticalBar key={`${level.side}-${level.leverage}`} level={level} currentPrice={currentPrice} />
          ))}
        </div>
      </div>

      {/* Current price */}
      <div className="flex items-center gap-3 rounded bg-purple-500/10 px-3 py-2" aria-label="Current price">
        <span className="text-xs text-gray-400">Current Price</span>
        <span className="font-mono font-bold text-white">${currentPrice.toLocaleString()}</span>
      </div>

      {/* Long liquidation levels (below price) */}
      <div>
        <h4 className="mb-2 text-xs font-medium uppercase tracking-wide text-green-400">
          Long Liquidation Zones (Below)
        </h4>
        <div className="space-y-1">
          {longLevels.map((level) => (
            <TheoreticalBar key={`${level.side}-${level.leverage}`} level={level} currentPrice={currentPrice} />
          ))}
        </div>
      </div>
    </div>
  );
}

function TheoreticalBar({
  level,
  currentPrice,
}: {
  level: TheoreticalLevel;
  currentPrice: number;
}) {
  const distPct = currentPrice > 0
    ? Math.abs(level.price - currentPrice) / currentPrice * 100
    : 0;
  const isShort = level.side === "short";
  const barWidth = Math.min(100, (level.leverage / 100) * 100);

  return (
    <div className="flex items-center gap-3 rounded bg-[#161b22] px-2 py-1.5" role="listitem">
      <span
        className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${
          isShort ? "bg-red-500/20 text-red-400" : "bg-green-500/20 text-green-400"
        }`}
      >
        {level.leverage}x
      </span>
      <span className="font-mono text-xs text-white w-24">${level.price.toLocaleString()}</span>
      <span className="text-[10px] text-gray-500 w-16">{distPct.toFixed(1)}% away</span>
      <span className="font-mono text-[10px] text-gray-400 w-16">{fmtUsd(level.estimated_usd)}</span>
      <div className="ml-auto h-2 w-24 overflow-hidden rounded-full bg-[#0d1117]">
        <div
          className={`h-full rounded-full ${isShort ? "bg-red-500" : "bg-green-500"}`}
          style={{ width: `${barWidth}%`, opacity: 0.7 }}
        />
      </div>
    </div>
  );
}
