import {
  type IChartApi,
  type ISeriesApi,
  type CandlestickData,
  type HistogramData,
  type LineData,
  type Time,
  type MouseEventParams,
  type SeriesMarker,
  createChart,
  ColorType,
  CrosshairMode,
  LineStyle,
  PriceScaleMode,
} from "lightweight-charts";
import { useEffect, useRef, useState } from "react";
import {
  fetchKlines,
  fetchIndicators,
  fetchLiquidationHeatmap,
  type KlineData,
  type LiquidationHeatmapData,
  type IndicatorData,
  type OrderBlockData,
  type FVGData,
} from "../../api/client";

const CRYPTO_ASSETS = [
  { label: "BTC/USDT", value: "BTCUSDT" },
  { label: "ETH/USDT", value: "ETHUSDT" },
  { label: "SOL/USDT", value: "SOLUSDT" },
  { label: "BNB/USDT", value: "BNBUSDT" },
  { label: "XRP/USDT", value: "XRPUSDT" },
  { label: "DOGE/USDT", value: "DOGEUSDT" },
  { label: "ADA/USDT", value: "ADAUSDT" },
  { label: "AVAX/USDT", value: "AVAXUSDT" },
  { label: "DOT/USDT", value: "DOTUSDT" },
  { label: "LINK/USDT", value: "LINKUSDT" },
  { label: "MATIC/USDT", value: "MATICUSDT" },
  { label: "UNI/USDT", value: "UNIUSDT" },
  { label: "ATOM/USDT", value: "ATOMUSDT" },
  { label: "LTC/USDT", value: "LTCUSDT" },
  { label: "FIL/USDT", value: "FILUSDT" },
  { label: "APT/USDT", value: "APTUSDT" },
  { label: "ARB/USDT", value: "ARBUSDT" },
  { label: "OP/USDT", value: "OPUSDT" },
  { label: "SUI/USDT", value: "SUIUSDT" },
  { label: "PEPE/USDT", value: "PEPEUSDT" },
] as const;
const FOREX_ASSETS = [
  { label: "EUR/USD", value: "EURUSD" },
  { label: "GBP/USD", value: "GBPUSD" },
  { label: "XAU/USD (Gold)", value: "XAUUSD" },
  { label: "GBP/JPY", value: "GBPJPY" },
] as const;
const ALL_ASSETS = [...CRYPTO_ASSETS, ...FOREX_ASSETS];
const TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d"] as const;
const CANDLE_COUNTS = [100, 200, 300, 500, 1000] as const;

type Asset = (typeof ALL_ASSETS)[number]["value"];
type Timeframe = (typeof TIMEFRAMES)[number];
type CandleCountOption = (typeof CANDLE_COUNTS)[number];

const CRYPTO_SET = new Set<string>(CRYPTO_ASSETS.map((a) => a.value));

interface OHLCVInfo {
  open: number; high: number; low: number; close: number;
  volume: number; change: number; changePct: number;
}

// Indicator toggle definitions
const INDICATOR_GROUPS = [
  {
    label: "Trend",
    items: [
      { id: "ema_20", label: "EMA 20", color: "#f59e0b" },
      { id: "ema_50", label: "EMA 50", color: "#3b82f6" },
      { id: "ema_200", label: "EMA 200", color: "#ef4444" },
    ],
  },
  {
    label: "Volatility",
    items: [
      { id: "bb", label: "Bollinger Bands", color: "#8b5cf6" },
    ],
  },
  {
    label: "SMC",
    items: [
      { id: "order_blocks", label: "Order Blocks", color: "#06b6d4" },
      { id: "fvg", label: "Fair Value Gaps", color: "#f97316" },
    ],
  },
  {
    label: "Levels",
    items: [
      { id: "liquidations", label: "Liquidation Levels", color: "#ec4899" },
      { id: "liq_heatmap", label: "Liquidation Heatmap", color: "#facc15" },
    ],
  },
] as const;

type IndicatorId = "ema_20" | "ema_50" | "ema_200" | "bb" | "order_blocks" | "fvg" | "liquidations" | "liq_heatmap";

function fmt(p: number): string {
  if (p >= 1000) return p.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (p >= 1) return p.toFixed(4);
  return p.toFixed(8);
}
function fmtVol(v: number): string {
  if (v >= 1e6) return `${(v / 1e6).toFixed(2)}M`;
  if (v >= 1e3) return `${(v / 1e3).toFixed(2)}K`;
  return v.toFixed(2);
}

interface PriceChartProps {
  onAssetChange?: (asset: string, timeframe: string) => void;
  activePosition?: Record<string, { type: string; entry: number; sl: number; tps: number[]; action: string; strategy: string; confidence: number }>;
  compact?: boolean;
}

export function PriceChart({ onAssetChange, activePosition, compact }: PriceChartProps = {}) {
  const [asset, setAsset] = useState<Asset>("BTCUSDT");
  const [tf, setTf] = useState<Timeframe>("1h");
  const [count, setCount] = useState<CandleCountOption>(300);
  const [activeIndicators, setActiveIndicators] = useState<Set<IndicatorId>>(new Set(["ema_20", "ema_50"]));
  const [showIndicatorPanel, setShowIndicatorPanel] = useState(false);

  const isCrypto = CRYPTO_SET.has(asset);
  const label = ALL_ASSETS.find((a) => a.value === asset)?.label ?? asset;

  const toggleIndicator = (id: IndicatorId) => {
    setActiveIndicators((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  // Serialize active indicators to string for key
  const indicatorKey = Array.from(activeIndicators).sort().join(",");

  return (
    <div className="rounded-lg border border-border bg-surface">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-4 py-2">
        <div className="flex items-center gap-2">
          <select value={asset} onChange={(e) => { const v = e.target.value as Asset; setAsset(v); onAssetChange?.(v, tf); }}
            className="rounded border border-border bg-background px-3 py-1.5 text-sm font-semibold text-white focus:outline-none"
            aria-label="Select pair">
            {ALL_ASSETS.map((a) => <option key={a.value} value={a.value}>{a.label}</option>)}
          </select>

          <div className="flex gap-0.5">
            {TIMEFRAMES.map((t) => (
              <button key={t} type="button" onClick={() => { setTf(t); onAssetChange?.(asset, t); }}
                className={`rounded px-2.5 py-1 text-xs font-medium ${tf === t ? "bg-accent text-white" : "bg-background text-gray-400 hover:text-white"}`}
                aria-label={`${t} timeframe`}>{t.toUpperCase()}</button>
            ))}
          </div>

          <span className="text-gray-600">|</span>

          <div className="flex gap-0.5">
            {CANDLE_COUNTS.map((c) => (
              <button key={c} type="button" onClick={() => setCount(c)}
                className={`rounded px-2 py-1 text-xs ${count === c ? "bg-accent text-white" : "bg-background text-gray-400 hover:text-white"}`}
                aria-label={`${c} candles`}>{c}</button>
            ))}
          </div>
        </div>

        {/* Indicators toggle button */}
        <button type="button" onClick={() => setShowIndicatorPanel(!showIndicatorPanel)}
          className={`flex items-center gap-1.5 rounded px-3 py-1.5 text-xs font-medium ${showIndicatorPanel ? "bg-accent text-white" : "bg-background text-gray-400 hover:text-white"}`}
          aria-label="Toggle indicators panel">
          <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
          </svg>
          Indicators ({activeIndicators.size})
        </button>
      </div>

      {/* Indicator panel */}
      {showIndicatorPanel && (
        <div className="flex flex-wrap gap-4 border-b border-border bg-background/50 px-4 py-3">
          {INDICATOR_GROUPS.map((group) => (
            <div key={group.label}>
              <span className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-gray-500">{group.label}</span>
              <div className="flex flex-wrap gap-1.5">
                {group.items.map((ind) => {
                  const active = activeIndicators.has(ind.id as IndicatorId);
                  return (
                    <button key={ind.id} type="button"
                      onClick={() => toggleIndicator(ind.id as IndicatorId)}
                      className={`flex items-center gap-1.5 rounded border px-2.5 py-1 text-xs transition-colors ${
                        active ? "border-transparent text-white" : "border-border text-gray-500 hover:text-gray-300"
                      }`}
                      style={active ? { backgroundColor: ind.color + "25", borderColor: ind.color + "60" } : {}}
                      aria-label={`Toggle ${ind.label}`} aria-pressed={active}>
                      <span className="h-2 w-2 rounded-full" style={{ backgroundColor: ind.color, opacity: active ? 1 : 0.3 }} />
                      {ind.label}
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Chart — all pairs now supported */}
      <ChartCanvas key={`${asset}-${tf}-${count}-${indicatorKey}`}
        asset={asset} timeframe={tf} candleLimit={count}
        activeIndicators={activeIndicators} activePosition={activePosition} compact={compact} />

      {/* Footer */}
      <div className="flex items-center justify-between border-t border-border px-4 py-1.5 text-xs text-gray-500">
        <span>{isCrypto ? "Binance Spot" : "Forex / Yahoo Finance"}</span>
        <div className="flex gap-2">
          {Array.from(activeIndicators).map((id) => {
            const ind = INDICATOR_GROUPS.flatMap((g) => g.items).find((i) => i.id === id);
            return ind ? <span key={id} className="flex items-center gap-1">
              <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: ind.color }} />{ind.label}
            </span> : null;
          })}
        </div>
        <span className="flex items-center gap-1">
          <span className="h-1.5 w-1.5 rounded-full bg-bullish animate-pulse" />Live
        </span>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Chart canvas — remounts via key on param change                   */
/* ------------------------------------------------------------------ */

function ChartCanvas({ asset, timeframe, candleLimit, activeIndicators, activePosition, compact }: {
  asset: string; timeframe: string; candleLimit: number; activeIndicators: Set<IndicatorId>;
  activePosition?: Record<string, { type: string; entry: number; sl: number; tps: number[]; action: string; strategy: string; confidence: number }>;
  compact?: boolean;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [bar, setBar] = useState<OHLCVInfo | null>(null);
  const [hover, setHover] = useState<OHLCVInfo | null>(null);
  const [loading, setLoading] = useState(true);

  const display = hover ?? bar;

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    let cancelled = false;

    const chart = createChart(el, {
      width: el.clientWidth, height: compact ? 350 : 550,
      layout: { background: { type: ColorType.Solid, color: "#0d1117" }, textColor: "#8b949e", fontFamily: "'Inter', sans-serif" },
      grid: { vertLines: { color: "#1c2128", style: LineStyle.Dotted }, horzLines: { color: "#1c2128", style: LineStyle.Dotted } },
      crosshair: { mode: CrosshairMode.Normal,
        vertLine: { width: 1, color: "#3b4252", style: LineStyle.Dashed, labelBackgroundColor: "#2563eb" },
        horzLine: { width: 1, color: "#3b4252", style: LineStyle.Dashed, labelBackgroundColor: "#2563eb" } },
      rightPriceScale: { borderColor: "#1c2128", scaleMargins: { top: 0.05, bottom: 0.25 }, mode: PriceScaleMode.Normal, autoScale: true },
      timeScale: { borderColor: "#1c2128", timeVisible: true, secondsVisible: false, rightOffset: 5, barSpacing: 8, minBarSpacing: 2 },
    });

    const cs = chart.addCandlestickSeries({
      upColor: "#00d4aa", downColor: "#ff4757",
      borderUpColor: "#00d4aa", borderDownColor: "#ff4757",
      wickUpColor: "#00d4aa", wickDownColor: "#ff4757",
    });
    const vs = chart.addHistogramSeries({ priceFormat: { type: "volume" }, priceScaleId: "volume" });
    chart.priceScale("volume").applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });

    // Indicator line series refs + price line tracking
    const indicatorSeries: ISeriesApi<"Line">[] = [];
    const priceLines: ReturnType<typeof cs.createPriceLine>[] = [];

    chart.subscribeCrosshairMove((p: MouseEventParams) => {
      if (!p.time || !p.seriesData) { setHover(null); return; }
      const c = p.seriesData.get(cs) as CandlestickData<Time> | undefined;
      const v = p.seriesData.get(vs) as HistogramData<Time> | undefined;
      if (c) {
        const ch = c.close - c.open;
        setHover({ open: c.open, high: c.high, low: c.low, close: c.close, volume: v?.value ?? 0, change: ch, changePct: c.open ? (ch / c.open) * 100 : 0 });
      }
    });

    const onResize = () => chart.applyOptions({ width: el.clientWidth });
    window.addEventListener("resize", onResize);

    let prevClose = 0;

    // Load candle data
    fetchKlines(asset, timeframe, candleLimit).then((klines) => {
      if (cancelled) return;
      cs.setData(klines.map((k) => ({ time: k.time as Time, open: k.open, high: k.high, low: k.low, close: k.close })));
      vs.setData(klines.map((k) => ({ time: k.time as Time, value: k.volume, color: k.close >= k.open ? "rgba(0,212,170,0.3)" : "rgba(255,71,87,0.3)" })));

      if (klines.length > 0) {
        const last = klines[klines.length - 1]!;
        prevClose = klines.length > 1 ? klines[klines.length - 2]!.close : last.open;
        const ch = last.close - prevClose;
        setBar({ open: last.open, high: last.high, low: last.low, close: last.close, volume: last.volume, change: ch, changePct: prevClose ? (ch / prevClose) * 100 : 0 });
      }

      // Draw active agent position on chart
      if (activePosition) {
        const pos = activePosition[asset.toUpperCase()];
        if (pos) {
          // Entry line (yellow)
          priceLines.push(cs.createPriceLine({
            price: pos.entry, color: "#facc15", lineWidth: 2, lineStyle: LineStyle.Solid,
            axisLabelVisible: true, title: `${pos.action} Entry (${pos.strategy})`,
          }));
          // SL line (red)
          priceLines.push(cs.createPriceLine({
            price: pos.sl, color: "#ff4757", lineWidth: 2, lineStyle: LineStyle.Solid,
            axisLabelVisible: true, title: `SL`,
          }));
          // TP lines (green)
          pos.tps.forEach((tp, i) => {
            priceLines.push(cs.createPriceLine({
              price: tp, color: "#00d4aa", lineWidth: 1, lineStyle: LineStyle.Dashed,
              axisLabelVisible: true, title: `TP${i + 1}`,
            }));
          });
        }
      }

      // Load indicators + liquidation heatmap
      const promises: Promise<void>[] = [];

      if (activeIndicators.size > 0) {
        const hasNonLiqHeatmap = Array.from(activeIndicators).some((id) => id !== "liq_heatmap");
        if (hasNonLiqHeatmap) {
          promises.push(
            fetchIndicators(asset, timeframe, candleLimit).then((ind) => {
              if (cancelled) return;
              drawIndicators(chart, cs, ind, activeIndicators, indicatorSeries, priceLines);
            })
          );
        }
        if (activeIndicators.has("liq_heatmap")) {
          promises.push(
            fetchLiquidationHeatmap(asset, 5).then((liqData) => {
              if (cancelled) return;
              drawLiquidationHeatmap(cs, liqData, priceLines);
            }).catch(() => {})
          );
        }
      }

      if (promises.length > 0) {
        Promise.all(promises).then(() => {
          chart.timeScale().fitContent();
          setLoading(false);
        }).catch(() => setLoading(false));
      } else {
        chart.timeScale().fitContent();
        setLoading(false);
      }
    }).catch(() => setLoading(false));

    // Live updates — WebSocket for crypto, polling for forex
    const isCryptoPair = CRYPTO_SET.has(asset.toUpperCase());
    let ws: WebSocket | null = null;
    let reconTimer: ReturnType<typeof setTimeout> | null = null;
    let forexPollTimer: ReturnType<typeof setInterval> | null = null;

    if (isCryptoPair) {
      // Binance WebSocket for crypto
      const wsUrl = `wss://stream.binance.com:9443/ws/${asset.toLowerCase()}@kline_${timeframe}`;
      function connectWs() {
        if (cancelled) return;
        ws = new WebSocket(wsUrl);
        ws.onmessage = (ev) => {
          try {
            const msg = JSON.parse(ev.data);
            if (msg.e !== "kline") return;
            const k = msg.k;
            const time = Math.floor(k.t / 1000) as Time;
            const o = parseFloat(k.o), h = parseFloat(k.h), l = parseFloat(k.l), c = parseFloat(k.c), vol = parseFloat(k.v);
            cs.update({ time, open: o, high: h, low: l, close: c });
            vs.update({ time, value: vol, color: c >= o ? "rgba(0,212,170,0.3)" : "rgba(255,71,87,0.3)" });
            const ch = c - (prevClose || o);
            setBar({ open: o, high: h, low: l, close: c, volume: vol, change: ch, changePct: prevClose ? (ch / prevClose) * 100 : 0 });
          } catch { /* */ }
        };
        ws.onclose = () => { if (!cancelled) reconTimer = setTimeout(connectWs, 3000); };
        ws.onerror = () => ws?.close();
      }
      connectWs();
    } else {
      // Forex polling — fetch latest candle every 1 second
      forexPollTimer = setInterval(() => {
        if (cancelled) return;
        fetchKlines(asset, timeframe, 2).then((klines) => {
          if (cancelled || klines.length === 0) return;
          const last = klines[klines.length - 1]!;
          const time = last.time as Time;
          cs.update({ time, open: last.open, high: last.high, low: last.low, close: last.close });
          vs.update({ time, value: last.volume, color: last.close >= last.open ? "rgba(0,212,170,0.3)" : "rgba(255,71,87,0.3)" });
          const ch = last.close - (prevClose || last.open);
          setBar({ open: last.open, high: last.high, low: last.low, close: last.close, volume: last.volume, change: ch, changePct: prevClose ? (ch / prevClose) * 100 : 0 });
        }).catch(() => {});
      }, 1000);
    }

    // Refresh indicators every 30s — clear old lines first
    const indInterval = setInterval(() => {
      if (cancelled || activeIndicators.size === 0) return;

      // Remove all old price lines
      for (const pl of priceLines) {
        try { cs.removePriceLine(pl); } catch { /* */ }
      }
      priceLines.length = 0;

      // Remove old line series
      indicatorSeries.forEach((s) => { try { chart.removeSeries(s); } catch { /* */ } });
      indicatorSeries.length = 0;

      const hasNonLiqHeatmap = Array.from(activeIndicators).some((id) => id !== "liq_heatmap");
      if (hasNonLiqHeatmap) {
        fetchIndicators(asset, timeframe, candleLimit).then((ind) => {
          if (cancelled) return;
          drawIndicators(chart, cs, ind, activeIndicators, indicatorSeries, priceLines);
        }).catch(() => {});
      }
      if (activeIndicators.has("liq_heatmap")) {
        fetchLiquidationHeatmap(asset, 5).then((liqData) => {
          if (cancelled) return;
          drawLiquidationHeatmap(cs, liqData, priceLines);
        }).catch(() => {});
      }
    }, 30_000);

    return () => {
      cancelled = true;
      clearInterval(indInterval);
      if (forexPollTimer) clearInterval(forexPollTimer);
      window.removeEventListener("resize", onResize);
      if (reconTimer) clearTimeout(reconTimer);
      ws?.close();
      chart.remove();
    };
  }, []);

  return (
    <div className="relative">
      {display && (
        <div className="absolute left-4 top-2 z-20 flex items-center gap-3 text-xs">
          <span className={`text-lg font-mono font-bold ${display.change >= 0 ? "text-bullish" : "text-bearish"}`}>{fmt(display.close)}</span>
          <span className={`font-mono ${display.change >= 0 ? "text-bullish" : "text-bearish"}`}>
            {display.change >= 0 ? "+" : ""}{fmt(display.change)} ({display.changePct >= 0 ? "+" : ""}{display.changePct.toFixed(2)}%)
          </span>
          <span className="text-gray-500">|</span>
          <span className="text-gray-400">O <span className="font-mono text-white">{fmt(display.open)}</span></span>
          <span className="text-gray-400">H <span className="font-mono text-white">{fmt(display.high)}</span></span>
          <span className="text-gray-400">L <span className="font-mono text-white">{fmt(display.low)}</span></span>
          <span className="text-gray-400">C <span className="font-mono text-white">{fmt(display.close)}</span></span>
          <span className="text-gray-400">Vol <span className="font-mono text-white">{fmtVol(display.volume)}</span></span>
        </div>
      )}
      {loading && (
        <div className="absolute inset-0 z-10 flex items-center justify-center bg-background/70">
          <div className="flex items-center gap-2 text-sm text-gray-400">
            <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>Loading...
          </div>
        </div>
      )}
      <div ref={containerRef} style={{ width: "100%" }} />
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Draw indicators on chart                                          */
/* ------------------------------------------------------------------ */

function drawIndicators(
  chart: IChartApi,
  candleSeries: ISeriesApi<"Candlestick">,
  data: IndicatorData,
  active: Set<IndicatorId>,
  seriesRefs: ISeriesApi<"Line">[],
  plRefs: ReturnType<ISeriesApi<"Candlestick">["createPriceLine"]>[] = [],
) {
  // EMA 20
  if (active.has("ema_20") && data.ema_20?.length) {
    const s = chart.addLineSeries({ color: "#f59e0b", lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
    s.setData(data.ema_20.map((p) => ({ time: p.time as Time, value: p.value })));
    seriesRefs.push(s);
  }
  // EMA 50
  if (active.has("ema_50") && data.ema_50?.length) {
    const s = chart.addLineSeries({ color: "#3b82f6", lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
    s.setData(data.ema_50.map((p) => ({ time: p.time as Time, value: p.value })));
    seriesRefs.push(s);
  }
  // EMA 200
  if (active.has("ema_200") && data.ema_200?.length) {
    const s = chart.addLineSeries({ color: "#ef4444", lineWidth: 2, priceLineVisible: false, lastValueVisible: false });
    s.setData(data.ema_200.map((p) => ({ time: p.time as Time, value: p.value })));
    seriesRefs.push(s);
  }
  // Bollinger Bands
  if (active.has("bb")) {
    if (data.bb_upper?.length) {
      const su = chart.addLineSeries({ color: "#8b5cf680", lineWidth: 1, lineStyle: LineStyle.Dashed, priceLineVisible: false, lastValueVisible: false });
      su.setData(data.bb_upper.map((p) => ({ time: p.time as Time, value: p.value })));
      seriesRefs.push(su);
    }
    if (data.bb_middle?.length) {
      const sm = chart.addLineSeries({ color: "#8b5cf640", lineWidth: 1, lineStyle: LineStyle.Dotted, priceLineVisible: false, lastValueVisible: false });
      sm.setData(data.bb_middle.map((p) => ({ time: p.time as Time, value: p.value })));
      seriesRefs.push(sm);
    }
    if (data.bb_lower?.length) {
      const sl = chart.addLineSeries({ color: "#8b5cf680", lineWidth: 1, lineStyle: LineStyle.Dashed, priceLineVisible: false, lastValueVisible: false });
      sl.setData(data.bb_lower.map((p) => ({ time: p.time as Time, value: p.value })));
      seriesRefs.push(sl);
    }
  }
  // Order Blocks — LONG/SHORT zones with clear labels
  if (active.has("order_blocks") && data.order_blocks?.length) {
    const activeOBs = data.order_blocks.filter((ob) => ob.status === "active").slice(-8);
    for (const ob of activeOBs) {
      const isLong = ob.signal === "LONG" || ob.signal === "WATCH_LONG";
      const color = isLong ? "#00d4aa" : "#ff4757";
      const label = `${ob.signal} OB`;
      // Upper boundary
      plRefs.push(candleSeries.createPriceLine({
        price: ob.high, color, lineWidth: 2, lineStyle: LineStyle.Solid,
        axisLabelVisible: true, title: label,
      }));
      // Lower boundary
      plRefs.push(candleSeries.createPriceLine({
        price: ob.low, color, lineWidth: 2, lineStyle: LineStyle.Solid,
        axisLabelVisible: false, title: "",
      }));
      // Midpoint (entry zone)
      plRefs.push(candleSeries.createPriceLine({
        price: ob.mid, color: color + "80", lineWidth: 1, lineStyle: LineStyle.Dashed,
        axisLabelVisible: false, title: `Entry ${ob.distance_pct.toFixed(1)}%`,
      }));
    }
  }
  // Fair Value Gaps — LONG/SHORT with fill status
  if (active.has("fvg") && data.fair_value_gaps?.length) {
    const activeFVGs = data.fair_value_gaps.filter((f) => !f.filled).slice(-6);
    for (const fvg of activeFVGs) {
      const isLong = fvg.signal === "LONG";
      const color = isLong ? "#22c55e" : fvg.signal === "SHORT" ? "#ef4444" : "#6b7280";
      const label = `${fvg.signal} FVG ${fvg.size_pct.toFixed(2)}%`;
      plRefs.push(candleSeries.createPriceLine({
        price: fvg.top, color, lineWidth: 1, lineStyle: LineStyle.LargeDashed,
        axisLabelVisible: true, title: label,
      }));
      plRefs.push(candleSeries.createPriceLine({
        price: fvg.bottom, color, lineWidth: 1, lineStyle: LineStyle.LargeDashed,
        axisLabelVisible: false, title: "",
      }));
    }
  }
  // Liquidation levels — with leverage labels
  if (active.has("liquidations") && data.liquidation_levels?.length) {
    for (const liq of data.liquidation_levels) {
      const isLong = liq.side === "long";
      const color = isLong ? "#ec4899" : "#06b6d4";
      const opacity = Math.max(0.3, liq.intensity / 100);
      plRefs.push(candleSeries.createPriceLine({
        price: liq.price, color: color + Math.round(opacity * 255).toString(16).padStart(2, "0"),
        lineWidth: 1, lineStyle: LineStyle.SparseDotted,
        axisLabelVisible: liq.leverage <= 25,
        title: `${liq.leverage}x ${liq.side.toUpperCase()} LIQ`,
      }));
    }
  }
}

/* ------------------------------------------------------------------ */
/*  Draw Liquidation Heatmap on chart (magma color scale)             */
/* ------------------------------------------------------------------ */

function fmtUsd(v: number): string {
  if (v >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `$${(v / 1e3).toFixed(0)}K`;
  return `$${v.toFixed(0)}`;
}

function intensityToColor(intensity: number): string {
  // Magma scale: deep purple → magenta → neon yellow
  if (intensity > 0.8) return "#facc15";  // neon yellow — extreme
  if (intensity > 0.6) return "#f97316";  // orange — very high
  if (intensity > 0.4) return "#d946ef";  // magenta — high
  if (intensity > 0.2) return "#7c3aed";  // purple — medium
  return "#2d1b69";                        // deep purple — low
}

function drawLiquidationHeatmap(
  candleSeries: ISeriesApi<"Candlestick">,
  data: LiquidationHeatmapData,
  plRefs: ReturnType<ISeriesApi<"Candlestick">["createPriceLine"]>[],
) {
  // Draw bins as price lines with magma colors
  if (data.bins && data.bins.length > 0) {
    for (const bin of data.bins) {
      if (bin.intensity < 0.1) continue;
      const color = intensityToColor(bin.intensity);
      const totalLabel = fmtUsd(bin.total_usd);
      const lineWidth = bin.intensity > 0.6 ? 3 : bin.intensity > 0.3 ? 2 : 1;

      plRefs.push(candleSeries.createPriceLine({
        price: bin.price_mid,
        color,
        lineWidth,
        lineStyle: LineStyle.Solid,
        axisLabelVisible: bin.intensity > 0.4,
        title: bin.intensity > 0.3 ? `🔥 ${totalLabel}` : "",
      }));
    }
  }

  // Draw theoretical levels with leverage labels
  if (data.theoretical_levels && data.theoretical_levels.length > 0) {
    for (const level of data.theoretical_levels) {
      const isLong = level.side === "long";
      const importance = level.leverage >= 50 ? 3 : level.leverage >= 25 ? 2 : 1;
      const color = isLong ? "#ec489980" : "#06b6d480";

      plRefs.push(candleSeries.createPriceLine({
        price: level.price,
        color,
        lineWidth: importance,
        lineStyle: level.leverage >= 50 ? LineStyle.Dashed : LineStyle.SparseDotted,
        axisLabelVisible: level.leverage >= 25,
        title: `${level.leverage}x ${isLong ? "LONG" : "SHORT"} ${fmtUsd(level.estimated_usd)}`,
      }));
    }
  }
}
