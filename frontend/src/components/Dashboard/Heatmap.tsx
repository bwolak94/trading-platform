import { useEffect, useState } from "react";
import {
  fetchIndicators,
  type IndicatorData,
  type VolumeProfileBucket,
  type LiquidationLevel,
  type OrderBlockData,
  type FVGData,
} from "../../api/client";

interface HeatmapProps {
  asset: string;
  interval: string;
}

export function Heatmap({ asset, interval }: HeatmapProps) {
  const [data, setData] = useState<IndicatorData | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<"volume" | "liquidation" | "levels">("volume");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchIndicators(asset, interval, 300)
      .then((d) => { if (!cancelled) { setData(d); setLoading(false); } })
      .catch(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [asset, interval]);

  // Auto-refresh
  useEffect(() => {
    const timer = setInterval(() => {
      fetchIndicators(asset, interval, 300).then(setData).catch(() => {});
    }, 60_000);
    return () => clearInterval(timer);
  }, [asset, interval]);

  if (loading) {
    return (
      <div className="rounded-lg border border-border bg-surface p-4">
        <div className="flex items-center gap-2 py-8 text-sm text-gray-400 justify-center">
          <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          Loading heatmap...
        </div>
      </div>
    );
  }

  if (!data) return null;

  return (
    <div className="rounded-lg border border-border bg-surface">
      {/* Tabs */}
      <div className="flex gap-0 border-b border-border">
        {([
          { id: "volume" as const, label: "Volume Profile" },
          { id: "liquidation" as const, label: "Liquidation Heatmap" },
          { id: "levels" as const, label: "Order Blocks & FVGs" },
        ]).map((t) => (
          <button key={t.id} type="button" onClick={() => setTab(t.id)}
            className={`px-4 py-2.5 text-xs font-medium transition-colors ${
              tab === t.id ? "border-b-2 border-accent text-white" : "text-gray-400 hover:text-gray-200"
            }`} aria-label={t.label}>{t.label}</button>
        ))}
      </div>

      <div className="p-4">
        {tab === "volume" && <VolumeProfileView profile={data.volume_profile} poc={data.poc} price={data.current_price} />}
        {tab === "liquidation" && <LiquidationView levels={data.liquidation_levels} price={data.current_price} />}
        {tab === "levels" && <LevelsView obs={data.order_blocks} fvgs={data.fair_value_gaps} price={data.current_price} />}
      </div>
    </div>
  );
}

/* --- Volume Profile --- */

function VolumeProfileView({ profile, poc, price }: {
  profile: VolumeProfileBucket[]; poc: VolumeProfileBucket | null; price: number;
}) {
  // Show only buckets near current price (top 30 by volume)
  const sorted = [...profile].sort((a, b) => b.total_volume - a.total_volume).slice(0, 30)
    .sort((a, b) => b.price_mid - a.price_mid);

  return (
    <div className="space-y-1">
      <div className="mb-3 flex items-center justify-between text-xs text-gray-400">
        <span>Price Level</span>
        <span>Volume (Buy / Sell)</span>
      </div>
      {sorted.map((bucket, i) => {
        const isPoc = poc && bucket.price_mid === poc.price_mid;
        const isNearPrice = Math.abs(bucket.price_mid - price) / price < 0.005;
        const buyPct = bucket.total_volume > 0 ? (bucket.buy_volume / bucket.total_volume) * 100 : 50;

        return (
          <div key={i} className={`relative rounded px-2 py-1.5 ${isPoc ? "ring-1 ring-accent" : ""} ${isNearPrice ? "bg-accent/10" : "bg-background"}`}>
            <div className="flex items-center justify-between text-xs">
              <div className="flex items-center gap-2">
                <span className={`font-mono ${isNearPrice ? "text-accent font-bold" : "text-white"}`}>
                  ${bucket.price_mid.toLocaleString()}
                </span>
                {isPoc && <span className="rounded bg-accent/20 px-1 py-0.5 text-accent text-[10px] font-bold">POC</span>}
                {isNearPrice && <span className="text-accent text-[10px]">CURRENT</span>}
              </div>
              <span className="font-mono text-gray-400">{fmtVol(bucket.total_volume)}</span>
            </div>
            {/* Volume bar */}
            <div className="mt-1 flex h-1.5 overflow-hidden rounded-full">
              <div className="bg-bullish/60 rounded-l-full" style={{ width: `${buyPct * bucket.pct_of_max / 100}%` }} />
              <div className="bg-bearish/60 rounded-r-full" style={{ width: `${(100 - buyPct) * bucket.pct_of_max / 100}%` }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

/* --- Liquidation Heatmap --- */

function LiquidationView({ levels, price }: { levels: LiquidationLevel[]; price: number }) {
  const shorts = levels.filter((l) => l.side === "short").sort((a, b) => a.price - b.price);
  const longs = levels.filter((l) => l.side === "long").sort((a, b) => b.price - a.price);

  return (
    <div className="space-y-4">
      {/* Short liquidations (above price) */}
      <div>
        <h4 className="mb-2 text-xs font-medium uppercase tracking-wide text-bearish">Short Liquidations (Above)</h4>
        <div className="space-y-1">
          {shorts.map((liq, i) => (
            <LiqBar key={i} liq={liq} price={price} side="short" />
          ))}
        </div>
      </div>

      {/* Current price */}
      <div className="flex items-center gap-3 rounded bg-accent/10 px-3 py-2">
        <span className="text-xs text-gray-400">Current Price</span>
        <span className="font-mono font-bold text-white">${price.toLocaleString()}</span>
      </div>

      {/* Long liquidations (below price) */}
      <div>
        <h4 className="mb-2 text-xs font-medium uppercase tracking-wide text-bullish">Long Liquidations (Below)</h4>
        <div className="space-y-1">
          {longs.map((liq, i) => (
            <LiqBar key={i} liq={liq} price={price} side="long" />
          ))}
        </div>
      </div>
    </div>
  );
}

function LiqBar({ liq, price: _price, side }: { liq: LiquidationLevel; price: number; side: string }) {
  const color = side === "short" ? "bg-bearish" : "bg-bullish";
  return (
    <div className="flex items-center gap-3 rounded bg-background px-2 py-1.5">
      <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${side === "short" ? "bg-bearish/20 text-bearish" : "bg-bullish/20 text-bullish"}`}>
        {liq.leverage}x
      </span>
      <span className="font-mono text-xs text-white">${liq.price.toLocaleString()}</span>
      <span className="text-[10px] text-gray-500">{liq.distance_pct.toFixed(1)}% away</span>
      <div className="ml-auto h-2 w-24 overflow-hidden rounded-full bg-surface">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${liq.intensity}%`, opacity: 0.7 }} />
      </div>
    </div>
  );
}

/* --- Order Blocks & FVGs --- */

function LevelsView({ obs, fvgs, price: _price }: { obs: OrderBlockData[]; fvgs: FVGData[]; price: number }) {
  const activeObs = obs.filter((ob) => ob.status === "active").slice(-8);
  const activeFvgs = fvgs.filter((f) => !f.filled).slice(-8);

  return (
    <div className="space-y-4">
      {/* Order Blocks */}
      <div>
        <h4 className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-500">Order Blocks</h4>
        {activeObs.length === 0 && <p className="text-xs text-gray-600 italic">No active order blocks</p>}
        <div className="space-y-1.5">
          {activeObs.map((ob, i) => (
            <div key={i} className={`flex items-center justify-between rounded border px-3 py-2 ${
              ob.signal === "LONG" ? "border-bullish/30 bg-bullish/5" : "border-bearish/30 bg-bearish/5"
            }`}>
              <div className="flex items-center gap-2">
                <span className={`rounded px-2 py-0.5 text-xs font-bold ${
                  ob.signal === "LONG" ? "bg-bullish/20 text-bullish" : "bg-bearish/20 text-bearish"
                }`}>{ob.signal}</span>
                <span className="text-xs text-gray-400">{ob.type === "bullish" ? "Demand Zone" : "Supply Zone"}</span>
              </div>
              <div className="flex items-center gap-3 text-xs">
                <span className="font-mono text-white">${ob.low.toLocaleString()} — ${ob.high.toLocaleString()}</span>
                <span className="text-gray-500">{ob.distance_pct.toFixed(1)}%</span>
                <div className="flex items-center gap-1" title={`Strength: ${ob.strength.toFixed(1)}`}>
                  {Array.from({ length: Math.min(Math.round(ob.strength), 5) }).map((_, j) => (
                    <span key={j} className={`h-1.5 w-1.5 rounded-full ${ob.signal === "LONG" ? "bg-bullish" : "bg-bearish"}`} />
                  ))}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* FVGs */}
      <div>
        <h4 className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-500">Fair Value Gaps</h4>
        {activeFvgs.length === 0 && <p className="text-xs text-gray-600 italic">No unfilled FVGs</p>}
        <div className="space-y-1.5">
          {activeFvgs.map((fvg, i) => (
            <div key={i} className={`flex items-center justify-between rounded border px-3 py-2 ${
              fvg.signal === "LONG" ? "border-bullish/20 bg-bullish/5" : fvg.signal === "SHORT" ? "border-bearish/20 bg-bearish/5" : "border-border bg-background"
            }`}>
              <div className="flex items-center gap-2">
                <span className={`rounded px-2 py-0.5 text-xs font-bold ${
                  fvg.signal === "LONG" ? "bg-bullish/20 text-bullish" : fvg.signal === "SHORT" ? "bg-bearish/20 text-bearish" : "bg-gray-700 text-gray-400"
                }`}>{fvg.signal}</span>
                <span className="text-xs text-gray-400">{fvg.type === "bullish" ? "Gap Up" : "Gap Down"}</span>
              </div>
              <div className="flex items-center gap-3 text-xs">
                <span className="font-mono text-white">${fvg.bottom.toLocaleString()} — ${fvg.top.toLocaleString()}</span>
                <span className="text-gray-500">{fvg.size_pct.toFixed(2)}%</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function fmtVol(v: number): string {
  if (v >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `${(v / 1e3).toFixed(1)}K`;
  return v.toFixed(0);
}
