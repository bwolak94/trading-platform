import { useEffect, useState } from "react";
import { fetchOrderFlow, fetchKlines, type OrderFlowData, type PriceCluster } from "../../api/client";

interface OrderFlowPanelProps {
  asset: string;
  timeframe: string;
}

export function OrderFlowPanel({ asset, timeframe }: OrderFlowPanelProps) {
  const [data, setData] = useState<OrderFlowData | null>(null);
  const [livePrice, setLivePrice] = useState<number>(0);
  const [loading, setLoading] = useState(true);

  const binanceAsset = asset.replace("/", "").toUpperCase();

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchOrderFlow(binanceAsset, timeframe, 10)
      .then((d) => { if (!cancelled) { setData(d); setLoading(false); } })
      .catch(() => { if (!cancelled) setLoading(false); });

    const timer = setInterval(() => {
      fetchOrderFlow(binanceAsset, timeframe, 10)
        .then((d) => { if (!cancelled) setData(d); })
        .catch(() => {});
    }, 5000);

    // Fetch live price every 2s from klines (always current)
    const priceTimer = setInterval(() => {
      if (cancelled) return;
      fetchKlines(binanceAsset, "1m", 1)
        .then((k) => { if (!cancelled && k.length > 0) setLivePrice(k[k.length - 1]!.close); })
        .catch(() => {});
    }, 2000);
    // Initial price fetch
    fetchKlines(binanceAsset, "1m", 1)
      .then((k) => { if (!cancelled && k.length > 0) setLivePrice(k[k.length - 1]!.close); })
      .catch(() => {});

    return () => { cancelled = true; clearInterval(timer); clearInterval(priceTimer); };
  }, [binanceAsset, timeframe]);

  if (loading || !data) {
    return (
      <div className="rounded-lg border border-border bg-surface p-4">
        <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-500">Order Flow</h3>
        <div className="flex items-center gap-2 py-4 text-xs text-gray-400">
          <svg className="h-3 w-3 animate-spin" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          Collecting trades...
        </div>
      </div>
    );
  }

  const latestWindow = data.windows.at(-1) ?? null;

  // Direction prediction based on order flow
  const prediction = predictDirection(data, latestWindow);

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-xs font-medium uppercase tracking-wide text-gray-500">Order Flow — Live</h3>
        <span className="flex items-center gap-1 text-xs text-gray-500">
          <span className="h-1.5 w-1.5 rounded-full bg-bullish animate-pulse" />5s
        </span>
      </div>

      {/* Direction Prediction */}
      <div className={`mb-3 rounded border px-3 py-2 ${
        prediction.direction === "UP" ? "border-bullish/30 bg-bullish/5" :
        prediction.direction === "DOWN" ? "border-bearish/30 bg-bearish/5" :
        "border-border bg-background"
      }`}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className={`text-lg ${
              prediction.direction === "UP" ? "text-bullish" : prediction.direction === "DOWN" ? "text-bearish" : "text-gray-400"
            }`}>
              {prediction.direction === "UP" ? "↑" : prediction.direction === "DOWN" ? "↓" : "→"}
            </span>
            <div>
              <span className={`text-sm font-bold ${
                prediction.direction === "UP" ? "text-bullish" : prediction.direction === "DOWN" ? "text-bearish" : "text-gray-400"
              }`}>
                {prediction.direction === "UP" ? "BULLISH" : prediction.direction === "DOWN" ? "BEARISH" : "NEUTRAL"}
              </span>
              <span className="ml-2 text-xs text-gray-500">({prediction.confidence}%)</span>
            </div>
          </div>
          <span className="font-mono text-sm text-white">${(livePrice || data.current_price).toLocaleString()}</span>
        </div>
        <p className="mt-1 text-xs text-gray-400">{prediction.reason}</p>
      </div>

      {/* Cumulative Delta */}
      <div className="mb-3 flex items-center justify-between rounded bg-background px-3 py-2">
        <span className="text-xs text-gray-400">Cumulative Delta</span>
        <span className={`font-mono text-sm font-bold ${data.cumulative_delta >= 0 ? "text-bullish" : "text-bearish"}`}>
          {data.cumulative_delta >= 0 ? "+" : ""}{data.cumulative_delta.toFixed(3)}
        </span>
      </div>

      {/* Imbalances */}
      {data.imbalances.length > 0 && (
        <div className="mb-3">
          <span className="mb-1 block text-xs text-gray-500">Active Imbalances</span>
          <div className="space-y-1">
            {data.imbalances.slice(0, 5).map((imb, i) => (
              <div key={i} className={`flex items-center justify-between rounded px-2 py-1 text-xs ${
                imb.type === "BUY" ? "bg-bullish/10" : "bg-bearish/10"
              }`}>
                <span className={`font-bold ${imb.type === "BUY" ? "text-bullish" : "text-bearish"}`}>
                  {imb.type}
                </span>
                <span className="font-mono text-white">${imb.price.toLocaleString()}</span>
                <span className="text-gray-400">{imb.ratio.toFixed(1)}x</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Latest Window Clusters */}
      {latestWindow && latestWindow.clusters.length > 0 && (
        <div>
          <div className="mb-1 flex items-center justify-between text-xs text-gray-500">
            <span>Price Level</span>
            <span>Bid | Ask</span>
          </div>
          <div className="max-h-[200px] space-y-0.5 overflow-y-auto">
            {latestWindow.clusters
              .sort((a, b) => b.price - a.price)
              .map((cluster, i) => (
                <ClusterRow key={i} cluster={cluster} maxVol={
                  Math.max(...latestWindow.clusters.map((c) => c.bid_vol + c.ask_vol), 0.001)
                } />
              ))}
          </div>
        </div>
      )}

      {/* Delta History (last N windows) */}
      {data.windows.length > 1 && (
        <div className="mt-3">
          <span className="mb-1 block text-xs text-gray-500">Delta per Candle</span>
          <div className="flex items-end gap-0.5" style={{ height: 40 }}>
            {data.windows.slice(-20).map((w, i) => {
              const maxDelta = Math.max(...data.windows.map((w2) => Math.abs(w2.delta)), 0.001);
              const h = Math.max(2, Math.abs(w.delta) / maxDelta * 36);
              return (
                <div key={i} className="flex-1 flex flex-col items-center justify-end" style={{ height: 40 }}>
                  <div
                    className={`w-full rounded-sm ${w.delta >= 0 ? "bg-bullish" : "bg-bearish"}`}
                    style={{ height: `${h}px`, opacity: 0.7 }}
                    title={`Delta: ${w.delta.toFixed(3)} | ${new Date(w.time * 1000).toLocaleTimeString()}`}
                  />
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

function ClusterRow({ cluster, maxVol }: { cluster: PriceCluster; maxVol: number }) {
  const totalVol = cluster.bid_vol + cluster.ask_vol;
  const volPct = (totalVol / maxVol) * 100;
  const bidPct = totalVol > 0 ? (cluster.bid_vol / totalVol) * 100 : 50;

  // Heatmap color based on volume intensity
  const intensity = Math.min(volPct, 100);
  const bg = intensity > 70 ? "bg-cyan-900/40" : intensity > 40 ? "bg-blue-900/30" : "bg-background";

  return (
    <div className={`relative flex items-center justify-between rounded px-2 py-0.5 text-xs ${bg} ${
      cluster.imbalance === "BUY" ? "ring-1 ring-bullish/50" : cluster.imbalance === "SELL" ? "ring-1 ring-bearish/50" : ""
    }`}>
      {/* Volume bar background */}
      <div className="absolute inset-0 flex overflow-hidden rounded">
        <div className="bg-bullish/10" style={{ width: `${bidPct * volPct / 100}%` }} />
        <div className="bg-bearish/10" style={{ width: `${(100 - bidPct) * volPct / 100}%` }} />
      </div>

      <span className="relative font-mono text-gray-300">${cluster.price.toLocaleString()}</span>
      <div className="relative flex items-center gap-1">
        <span className="font-mono text-bullish">{cluster.bid_vol.toFixed(3)}</span>
        <span className="text-gray-600">|</span>
        <span className="font-mono text-bearish">{cluster.ask_vol.toFixed(3)}</span>
        {cluster.imbalance && (
          <span className={`ml-1 rounded px-1 py-0.5 text-[9px] font-bold ${
            cluster.imbalance === "BUY" ? "bg-bullish/20 text-bullish" : "bg-bearish/20 text-bearish"
          }`}>{cluster.imbalance}</span>
        )}
      </div>
    </div>
  );
}

interface Prediction {
  direction: "UP" | "DOWN" | "NEUTRAL";
  confidence: number;
  reason: string;
}

function predictDirection(data: OrderFlowData, latest: OrderFlowData["windows"][number] | null): Prediction {
  if (!latest || data.windows.length < 2) {
    return { direction: "NEUTRAL", confidence: 30, reason: "Collecting data — need more candles for prediction" };
  }

  let score = 0;
  const reasons: string[] = [];

  // 1. Cumulative Delta direction
  if (data.cumulative_delta > 0) {
    score += 2;
    reasons.push("Cum. Delta positive (buyers dominant)");
  } else if (data.cumulative_delta < 0) {
    score -= 2;
    reasons.push("Cum. Delta negative (sellers dominant)");
  }

  // 2. Latest candle delta
  if (latest.delta > 0) {
    score += 1;
    reasons.push("Last candle delta positive");
  } else if (latest.delta < 0) {
    score -= 1;
    reasons.push("Last candle delta negative");
  }

  // 3. Delta trend (last 3 windows)
  const recentWindows = data.windows.slice(-3);
  const deltaTrend = recentWindows.reduce((sum, w) => sum + w.delta, 0);
  if (deltaTrend > 0) {
    score += 1;
    reasons.push("Delta trending up over last 3 candles");
  } else if (deltaTrend < 0) {
    score -= 1;
    reasons.push("Delta trending down over last 3 candles");
  }

  // 4. Imbalances
  const buyImbalances = data.imbalances.filter((i) => i.type === "BUY").length;
  const sellImbalances = data.imbalances.filter((i) => i.type === "SELL").length;
  if (buyImbalances > sellImbalances) {
    score += 1;
    reasons.push(`${buyImbalances} buy imbalances vs ${sellImbalances} sell`);
  } else if (sellImbalances > buyImbalances) {
    score -= 1;
    reasons.push(`${sellImbalances} sell imbalances vs ${buyImbalances} buy`);
  }

  // 5. Volume absorption — large bid at bottom or ask at top
  const clusters = latest.clusters;
  if (clusters.length > 0) {
    const sorted = [...clusters].sort((a, b) => a.price - b.price);
    const bottom = sorted[0];
    const top = sorted[sorted.length - 1];
    if (bottom && bottom.bid_vol > bottom.ask_vol * 2) {
      score += 1;
      reasons.push("Strong bid absorption at bottom");
    }
    if (top && top.ask_vol > top.bid_vol * 2) {
      score -= 1;
      reasons.push("Strong ask pressure at top");
    }
  }

  const maxScore = 6;
  const confidence = Math.min(90, Math.max(20, Math.round(Math.abs(score) / maxScore * 80 + 20)));

  if (score >= 2) return { direction: "UP", confidence, reason: reasons.slice(0, 2).join(". ") };
  if (score <= -2) return { direction: "DOWN", confidence, reason: reasons.slice(0, 2).join(". ") };
  return { direction: "NEUTRAL", confidence: 30, reason: reasons.slice(0, 2).join(". ") || "Mixed signals" };
}
