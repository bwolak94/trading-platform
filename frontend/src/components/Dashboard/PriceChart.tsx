import {
  type IChartApi,
  type ISeriesApi,
  type CandlestickData,
  type HistogramData,
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
  fetchNews,
  type LiquidationHeatmapData,
  type IndicatorData,
  type NewsItemData,
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
    label: "Heatmap",
    items: [
      { id: "vol_heatmap", label: "Volume Heatmap", color: "#ff6b00" },
    ],
  },
  {
    label: "Ichimoku",
    items: [
      { id: "ichimoku", label: "Ichimoku Cloud", color: "#f97316" },
    ],
  },
  {
    label: "Volatility",
    items: [
      { id: "bb", label: "Bollinger Bands", color: "#8b5cf6" },
      { id: "vwap", label: "VWAP", color: "#a78bfa" },
    ],
  },
  {
    label: "Fibonacci / S&R",
    items: [
      { id: "fibonacci", label: "Fibonacci Levels", color: "#eab308" },
      { id: "support_resistance", label: "Auto S/R", color: "#06b6d4" },
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
    label: "Flow",
    items: [
      { id: "money_flow", label: "$ Money Flow", color: "#22c55e" },
      { id: "rsi_scalp", label: "RSI Scalp Signals", color: "#22d3ee" },
    ],
  },
  {
    label: "Levels",
    items: [
      { id: "liquidations", label: "Liquidation Levels", color: "#ec4899" },
      { id: "liq_heatmap", label: "Liquidation Heatmap", color: "#facc15" },
    ],
  },
  {
    label: "Sessions",
    items: [
      { id: "sessions", label: "Trading Sessions", color: "#60a5fa" },
    ],
  },
  {
    label: "News",
    items: [
      { id: "news", label: "News Impact", color: "#a78bfa" },
    ],
  },
] as { label: string; items: { id: IndicatorId; label: string; color: string }[] }[];

type IndicatorId = "ema_20" | "ema_50" | "ema_200" | "bb" | "vwap" | "order_blocks" | "fvg" | "liquidations" | "liq_heatmap" | "rsi_scalp" | "ichimoku" | "fibonacci" | "support_resistance" | "money_flow" | "vol_heatmap" | "sessions" | "news";

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
  defaultAsset?: string;
  defaultTimeframe?: string;
}

export function PriceChart({ onAssetChange, activePosition, compact, defaultAsset, defaultTimeframe }: PriceChartProps = {}) {
  const [asset, setAsset] = useState<Asset>(() => {
    if (defaultAsset && ALL_ASSETS.some((a) => a.value === defaultAsset)) return defaultAsset as Asset;
    return "BTCUSDT";
  });
  const [tf, setTf] = useState<Timeframe>(() => {
    if (defaultTimeframe && TIMEFRAMES.includes(defaultTimeframe as Timeframe)) return defaultTimeframe as Timeframe;
    return "1h";
  });
  const [count, setCount] = useState<CandleCountOption>(300);
  const [activeIndicators, setActiveIndicators] = useState<Set<IndicatorId>>(new Set(["ema_20", "ema_50"]));
  const [showIndicatorPanel, setShowIndicatorPanel] = useState(false);
  const [heikinAshi, setHeikinAshi] = useState(false);

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
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-2 py-2 sm:px-4">
        <div className="flex flex-wrap items-center gap-2">
          <select value={asset} onChange={(e) => { const v = e.target.value as Asset; setAsset(v); onAssetChange?.(v, tf); }}
            className="min-h-[44px] rounded border border-border bg-background px-3 py-1.5 text-sm font-semibold text-white focus:outline-none"
            aria-label="Select pair">
            {ALL_ASSETS.map((a) => <option key={a.value} value={a.value}>{a.label}</option>)}
          </select>

          <div className="flex flex-wrap gap-0.5">
            {TIMEFRAMES.map((t) => (
              <button key={t} type="button" onClick={() => { setTf(t); onAssetChange?.(asset, t); }}
                className={`min-h-[44px] min-w-[44px] rounded px-2.5 py-1 text-xs font-medium ${tf === t ? "bg-accent text-white" : "bg-background text-gray-400 hover:text-white"}`}
                aria-label={`${t} timeframe`}>{t.toUpperCase()}</button>
            ))}
          </div>

          <span className="hidden text-gray-600 sm:inline">|</span>

          <div className="flex flex-wrap gap-0.5">
            {CANDLE_COUNTS.map((c) => (
              <button key={c} type="button" onClick={() => setCount(c)}
                className={`min-h-[44px] min-w-[44px] rounded px-2 py-1 text-xs ${count === c ? "bg-accent text-white" : "bg-background text-gray-400 hover:text-white"}`}
                aria-label={`${c} candles`}>{c}</button>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Heikin-Ashi toggle */}
          <button type="button" onClick={() => setHeikinAshi((prev) => !prev)}
            className={`min-h-[44px] min-w-[44px] rounded px-2.5 py-1.5 text-xs font-bold transition-colors ${heikinAshi ? "bg-accent text-white" : "bg-background text-gray-400 hover:text-white"}`}
            aria-label={heikinAshi ? "Disable Heikin-Ashi candles" : "Enable Heikin-Ashi candles"}
            aria-pressed={heikinAshi}
            title="Heikin-Ashi">
            HA
          </button>

        {/* Indicators toggle button */}
        <button type="button" onClick={() => setShowIndicatorPanel(!showIndicatorPanel)}
          className={`min-h-[44px] flex items-center gap-1.5 rounded px-3 py-1.5 text-xs font-medium ${showIndicatorPanel ? "bg-accent text-white" : "bg-background text-gray-400 hover:text-white"}`}
          aria-label="Toggle indicators panel">
          <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
          </svg>
          Indicators ({activeIndicators.size})
        </button>
        </div>
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
                      className={`min-h-[44px] flex items-center gap-1.5 rounded border px-2.5 py-1 text-xs transition-colors ${
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
      <ChartCanvas key={`${asset}-${tf}-${count}-${indicatorKey}-${heikinAshi}`}
        asset={asset} timeframe={tf} candleLimit={count}
        activeIndicators={activeIndicators} activePosition={activePosition} compact={compact} heikinAshi={heikinAshi} />

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

/** Transform OHLCV data to Heikin-Ashi candles */
function toHeikinAshi(klines: { time: number; open: number; high: number; low: number; close: number; volume: number }[]): { time: number; open: number; high: number; low: number; close: number; volume: number }[] {
  if (klines.length === 0) return [];
  const result: { time: number; open: number; high: number; low: number; close: number; volume: number }[] = [];
  for (let i = 0; i < klines.length; i++) {
    const k = klines[i]!;
    const haClose = (k.open + k.high + k.low + k.close) / 4;
    const haOpen = i === 0
      ? (k.open + k.close) / 2
      : (result[i - 1]!.open + result[i - 1]!.close) / 2;
    const haHigh = Math.max(k.high, haOpen, haClose);
    const haLow = Math.min(k.low, haOpen, haClose);
    result.push({ time: k.time, open: haOpen, high: haHigh, low: haLow, close: haClose, volume: k.volume });
  }
  return result;
}

function ChartCanvas({ asset, timeframe, candleLimit, activeIndicators, activePosition, compact, heikinAshi }: {
  asset: string; timeframe: string; candleLimit: number; activeIndicators: Set<IndicatorId>;
  activePosition?: Record<string, { type: string; entry: number; sl: number; tps: number[]; action: string; strategy: string; confidence: number }>;
  compact?: boolean;
  heikinAshi?: boolean;
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

    const hasVolHeatmap = activeIndicators.has("vol_heatmap");
    const hasSessions = activeIndicators.has("sessions");

    // Responsive chart height: use smaller height on mobile
    const isMobile = el.clientWidth < 768;
    const chartHeight = compact ? (isMobile ? 250 : 350) : (isMobile ? 300 : 500);

    const chart = createChart(el, {
      width: el.clientWidth, height: chartHeight,
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

    const onResize = () => {
      const mobile = el.clientWidth < 768;
      const h = compact ? (mobile ? 250 : 350) : (mobile ? 300 : 500);
      chart.applyOptions({ width: el.clientWidth, height: h });
    };
    window.addEventListener("resize", onResize);

    let prevClose = 0;
    let heatmapCleanupRef: (() => void) | null = null;
    let sessionsCleanupRef: (() => void) | null = null;

    // Load candle data
    fetchKlines(asset, timeframe, candleLimit).then((rawKlines) => {
      if (cancelled) return;
      const klines = heikinAshi ? toHeikinAshi(rawKlines) : rawKlines;
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

      // Volume Heatmap — thermal overlay on chart
      if (hasVolHeatmap && klines.length > 0) {
        heatmapCleanupRef = setupVolumeHeatmap(chart, cs, klines, el, chartHeight);
      }

      // Trading Sessions — colored background overlay
      if (hasSessions && klines.length > 0) {
        sessionsCleanupRef = setupSessionsOverlay(chart, klines, el, chartHeight);
      }

      // Load indicators + liquidation heatmap
      const promises: Promise<void>[] = [];

      if (activeIndicators.size > 0) {
        const hasNonLiqHeatmap = Array.from(activeIndicators).some((id) => id !== "liq_heatmap" && id !== "vol_heatmap" && id !== "sessions" && id !== "news");
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
        if (activeIndicators.has("news")) {
          promises.push(
            fetchNews(100).then(({ news }) => {
              if (cancelled || news.length === 0) return;
              drawNewsMarkers(cs, news, klines);
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

      const hasNonLiqHeatmap = Array.from(activeIndicators).some((id) => id !== "liq_heatmap" && id !== "vol_heatmap" && id !== "sessions" && id !== "news");
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
      if (activeIndicators.has("news")) {
        fetchKlines(asset, timeframe, candleLimit).then((refreshedKlines) => {
          if (cancelled) return;
          fetchNews(100).then(({ news }) => {
            if (cancelled || news.length === 0) return;
            drawNewsMarkers(cs, news, refreshedKlines);
          }).catch(() => {});
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
      heatmapCleanupRef?.();
      sessionsCleanupRef?.();
      chart.remove();
    };
  }, []);

  return (
    <div className="relative">
      {display && (
        <div className="absolute left-2 top-2 z-20 flex flex-wrap items-center gap-1.5 text-xs sm:left-4 sm:gap-3">
          <span className={`text-sm font-mono font-bold sm:text-lg ${display.change >= 0 ? "text-bullish" : "text-bearish"}`}>{fmt(display.close)}</span>
          <span className={`font-mono ${display.change >= 0 ? "text-bullish" : "text-bearish"}`}>
            {display.change >= 0 ? "+" : ""}{fmt(display.change)} ({display.changePct >= 0 ? "+" : ""}{display.changePct.toFixed(2)}%)
          </span>
          <span className="hidden text-gray-500 sm:inline">|</span>
          <span className="hidden text-gray-400 sm:inline">O <span className="font-mono text-white">{fmt(display.open)}</span></span>
          <span className="hidden text-gray-400 sm:inline">H <span className="font-mono text-white">{fmt(display.high)}</span></span>
          <span className="hidden text-gray-400 sm:inline">L <span className="font-mono text-white">{fmt(display.low)}</span></span>
          <span className="hidden text-gray-400 sm:inline">C <span className="font-mono text-white">{fmt(display.close)}</span></span>
          <span className="hidden text-gray-400 sm:inline">Vol <span className="font-mono text-white">{fmtVol(display.volume)}</span></span>
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
  // VWAP with upper/lower bands
  if (active.has("vwap")) {
    if (data.vwap?.length) {
      const sv = chart.addLineSeries({ color: "#a78bfa", lineWidth: 2, priceLineVisible: false, lastValueVisible: false });
      sv.setData(data.vwap.map((p) => ({ time: p.time as Time, value: p.value })));
      seriesRefs.push(sv);
    }
    if (data.vwap_upper_1?.length) {
      const su = chart.addLineSeries({ color: "#a78bfa60", lineWidth: 1, lineStyle: LineStyle.Dashed, priceLineVisible: false, lastValueVisible: false });
      su.setData(data.vwap_upper_1.map((p) => ({ time: p.time as Time, value: p.value })));
      seriesRefs.push(su);
    }
    if (data.vwap_lower_1?.length) {
      const slv = chart.addLineSeries({ color: "#a78bfa60", lineWidth: 1, lineStyle: LineStyle.Dashed, priceLineVisible: false, lastValueVisible: false });
      slv.setData(data.vwap_lower_1.map((p) => ({ time: p.time as Time, value: p.value })));
      seriesRefs.push(slv);
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
  // RSI Scalping BUY/SELL signals — only last 3 clean signals
  if (active.has("rsi_scalp") && data.scalp_signals?.length) {
    for (const sig of data.scalp_signals.slice(-3)) {
      const isBuy = sig.type === "BUY";
      plRefs.push(candleSeries.createPriceLine({
        price: sig.price,
        color: isBuy ? "#22d3ee" : "#f43f5e",
        lineWidth: 2,
        lineStyle: isBuy ? LineStyle.Dashed : LineStyle.Dashed,
        axisLabelVisible: true,
        title: `${sig.type} (RSI Scalp)`,
      }));
    }
  }

  // Ichimoku Cloud
  if (active.has("ichimoku")) {
    // Tenkan-sen (orange)
    if (data.ichimoku_tenkan?.length) {
      const s = chart.addLineSeries({ color: "#f97316", lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
      s.setData(data.ichimoku_tenkan.map((p) => ({ time: p.time as Time, value: p.value })));
      seriesRefs.push(s);
    }
    // Kijun-sen (blue)
    if (data.ichimoku_kijun?.length) {
      const s = chart.addLineSeries({ color: "#3b82f6", lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
      s.setData(data.ichimoku_kijun.map((p) => ({ time: p.time as Time, value: p.value })));
      seriesRefs.push(s);
    }
    // Senkou Span A (green dashed)
    if (data.ichimoku_senkou_a?.length) {
      const s = chart.addLineSeries({ color: "#22c55e80", lineWidth: 1, lineStyle: LineStyle.Dashed, priceLineVisible: false, lastValueVisible: false });
      s.setData(data.ichimoku_senkou_a.map((p) => ({ time: p.time as Time, value: p.value })));
      seriesRefs.push(s);
    }
    // Senkou Span B (red dashed)
    if (data.ichimoku_senkou_b?.length) {
      const s = chart.addLineSeries({ color: "#ef444480", lineWidth: 1, lineStyle: LineStyle.Dashed, priceLineVisible: false, lastValueVisible: false });
      s.setData(data.ichimoku_senkou_b.map((p) => ({ time: p.time as Time, value: p.value })));
      seriesRefs.push(s);
    }
    // Chikou Span (purple dotted)
    if (data.ichimoku_chikou?.length) {
      const s = chart.addLineSeries({ color: "#a855f780", lineWidth: 1, lineStyle: LineStyle.Dotted, priceLineVisible: false, lastValueVisible: false });
      s.setData(data.ichimoku_chikou.map((p) => ({ time: p.time as Time, value: p.value })));
      seriesRefs.push(s);
    }
  }

  // Fibonacci Levels — horizontal lines with color gradient (gold to red)
  if (active.has("fibonacci") && data.fibonacci?.levels?.length) {
    const fibColors: Record<string, string> = {
      "0.0%": "#6b7280", "23.6%": "#eab308", "38.2%": "#f59e0b",
      "50.0%": "#f97316", "61.8%": "#ef4444", "78.6%": "#dc2626",
      "88.6%": "#b91c1c", "100.0%": "#6b7280",
    };
    for (const level of data.fibonacci.levels) {
      const color = fibColors[level.label] ?? "#eab308";
      plRefs.push(candleSeries.createPriceLine({
        price: level.price,
        color: color + "90",
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: `Fib ${level.label}`,
      }));
    }
  }

  // Auto Support / Resistance — colored by role, style by strength
  if (active.has("support_resistance") && data.support_resistance?.length) {
    const srLevels = data.support_resistance.slice(-12);
    for (const sr of srLevels) {
      const isResistance = sr.role === "resistance";
      const color = isResistance ? "#ef4444" : "#3b82f6";
      const lineWidth = sr.strength > 0.6 ? 2 : 1;
      plRefs.push(candleSeries.createPriceLine({
        price: sr.price,
        color: color + (sr.strength > 0.6 ? "cc" : "80"),
        lineWidth,
        lineStyle: sr.strength > 0.4 ? LineStyle.Solid : LineStyle.Dashed,
        axisLabelVisible: sr.strength > 0.3,
        title: `${isResistance ? "R" : "S"} (${sr.touches}x)`,
      }));
    }
  }

  // $ Money Flow Markers — series markers on candles
  if (active.has("money_flow") && data.money_flow_markers?.length) {
    const markers: SeriesMarker<Time>[] = data.money_flow_markers
      .filter((m) => m.time != null)
      .map((m) => ({
        time: m.time as Time,
        position: m.direction === "up" ? "aboveBar" as const : "belowBar" as const,
        color: m.direction === "up" ? "#22c55e" : "#ef4444",
        shape: "circle" as const,
        text: m.text,
      }));
    if (markers.length > 0) {
      candleSeries.setMarkers(markers);
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

/* ------------------------------------------------------------------ */
/*  Volume Heatmap — thermal color overlay behind candles              */
/* ------------------------------------------------------------------ */

interface HeatCell {
  time: number;
  priceLow: number;
  priceHigh: number;
  intensity: number;
}

function thermalColor(intensity: number): string {
  // Thermal scale matching TradingMaster: dark red → red → orange → yellow → green → cyan
  const a = Math.min(0.92, Math.max(0.25, intensity * 0.95 + 0.1));
  if (intensity < 0.08) return `rgba(30, 5, 5, ${a})`;
  if (intensity < 0.16) return `rgba(80, 12, 8, ${a})`;
  if (intensity < 0.24) return `rgba(130, 22, 5, ${a})`;
  if (intensity < 0.32) return `rgba(170, 40, 0, ${a})`;
  if (intensity < 0.40) return `rgba(200, 70, 0, ${a})`;
  if (intensity < 0.48) return `rgba(220, 110, 0, ${a})`;
  if (intensity < 0.56) return `rgba(235, 160, 0, ${a})`;
  if (intensity < 0.64) return `rgba(240, 210, 0, ${a})`;
  if (intensity < 0.72) return `rgba(200, 235, 0, ${a})`;
  if (intensity < 0.80) return `rgba(120, 230, 40, ${a})`;
  if (intensity < 0.88) return `rgba(0, 220, 100, ${a})`;
  if (intensity < 0.95) return `rgba(0, 220, 180, ${a})`;
  return `rgba(0, 235, 235, ${a})`;
}

function computeHeatmapCells(
  klines: { time: number; open: number; high: number; low: number; close: number; volume: number }[],
  numBins: number = 60,
): HeatCell[] {
  if (klines.length < 2) return [];

  let priceMin = Infinity;
  let priceMax = -Infinity;
  for (const k of klines) {
    if (k.low < priceMin) priceMin = k.low;
    if (k.high > priceMax) priceMax = k.high;
  }
  const range = priceMax - priceMin;
  if (range <= 0) return [];

  const binSize = range / numBins;
  const lookback = Math.min(30, Math.floor(klines.length / 3));

  // Rolling volume profile: for each candle, accumulate volume from lookback window
  // This creates a dense, continuous heatmap like TradingMaster
  const profileBins = new Float64Array(numBins); // reusable accumulator
  const cells: HeatCell[] = [];
  let globalMax = 0;

  for (let i = 0; i < klines.length; i++) {
    // Reset accumulator
    profileBins.fill(0);

    // Accumulate volume from lookback window
    const windowStart = Math.max(0, i - lookback);
    for (let j = windowStart; j <= i; j++) {
      const k = klines[j]!;
      const startBin = Math.max(0, Math.floor((k.low - priceMin) / binSize));
      const endBin = Math.min(numBins - 1, Math.floor((k.high - priceMin) / binSize));
      const numTouched = endBin - startBin + 1;
      if (numTouched <= 0) continue;

      const bodyLow = Math.min(k.open, k.close);
      const bodyHigh = Math.max(k.open, k.close);

      // Decay: more recent candles contribute more
      const age = i - j;
      const decay = 1.0 - age / (lookback + 1) * 0.6;

      for (let b = startBin; b <= endBin; b++) {
        const bMid = priceMin + (b + 0.5) * binSize;
        const inBody = bMid >= bodyLow && bMid <= bodyHigh;
        const weight = inBody ? 2.0 : 0.5;
        profileBins[b]! += (k.volume / numTouched) * weight * decay;
      }
    }

    // Find local max for this column
    let colMax = 0;
    for (let b = 0; b < numBins; b++) {
      if (profileBins[b]! > colMax) colMax = profileBins[b]!;
    }
    if (colMax > globalMax) globalMax = colMax;

    // Store all non-zero bins for this time column
    const time = klines[i]!.time;
    for (let b = 0; b < numBins; b++) {
      if (profileBins[b]! > 0) {
        cells.push({
          time,
          priceLow: priceMin + b * binSize,
          priceHigh: priceMin + (b + 1) * binSize,
          intensity: profileBins[b]!, // normalize later
        });
      }
    }
  }

  // Normalize all cells by global max
  if (globalMax > 0) {
    for (const cell of cells) {
      cell.intensity = cell.intensity / globalMax;
    }
  }

  return cells;
}

/* ------------------------------------------------------------------ */
/*  Trading Sessions — colored background overlay by market session    */
/* ------------------------------------------------------------------ */

interface SessionDefinition {
  readonly name: string;
  readonly startHour: number;
  readonly startMinute: number;
  readonly endHour: number;
  readonly endMinute: number;
  readonly color: string;
  readonly labelColor: string;
}

const TRADING_SESSIONS: readonly SessionDefinition[] = [
  { name: "Tokyo", startHour: 0, startMinute: 0, endHour: 9, endMinute: 0, color: "rgba(250, 204, 21, 0.06)", labelColor: "#facc15" },
  { name: "London", startHour: 8, startMinute: 0, endHour: 16, endMinute: 30, color: "rgba(34, 197, 94, 0.06)", labelColor: "#22c55e" },
  { name: "NYSE", startHour: 13, startMinute: 30, endHour: 20, endMinute: 0, color: "rgba(96, 165, 250, 0.06)", labelColor: "#60a5fa" },
] as const;

function getSessionsForTimestamp(utcHour: number, utcMinute: number): SessionDefinition[] {
  const timeInMinutes = utcHour * 60 + utcMinute;
  const result: SessionDefinition[] = [];
  for (const s of TRADING_SESSIONS) {
    const start = s.startHour * 60 + s.startMinute;
    const end = s.endHour * 60 + s.endMinute;
    if (timeInMinutes >= start && timeInMinutes < end) {
      result.push(s);
    }
  }
  return result;
}

function setupSessionsOverlay(
  chart: IChartApi,
  klines: { time: number; open: number; high: number; low: number; close: number; volume: number }[],
  container: HTMLDivElement,
  chartHeight: number,
): () => void {
  if (klines.length === 0) return () => {};

  const overlay = document.createElement("canvas");
  overlay.style.position = "absolute";
  overlay.style.top = "0";
  overlay.style.left = "0";
  overlay.style.pointerEvents = "none";
  overlay.style.zIndex = "5";
  container.style.position = "relative";
  container.appendChild(overlay);

  // Pre-compute session assignments for each candle timestamp
  const candleSessions: { time: number; sessions: SessionDefinition[] }[] = klines.map((k) => {
    const date = new Date(k.time * 1000);
    const utcH = date.getUTCHours();
    const utcM = date.getUTCMinutes();
    return { time: k.time, sessions: getSessionsForTimestamp(utcH, utcM) };
  });

  const sortedTimes = klines.map((k) => k.time);

  let rafId = 0;

  function render(): void {
    const dpr = window.devicePixelRatio || 1;
    const w = container.clientWidth;
    const h = chartHeight;

    overlay.width = Math.round(w * dpr);
    overlay.height = Math.round(h * dpr);
    overlay.style.width = w + "px";
    overlay.style.height = h + "px";

    const ctx = overlay.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, overlay.width, overlay.height);
    ctx.scale(dpr, dpr);

    // Calculate bar width from adjacent candles
    let barW = 10;
    for (let i = 0; i < sortedTimes.length - 1; i++) {
      const x0 = chart.timeScale().timeToCoordinate(sortedTimes[i]! as Time);
      const x1 = chart.timeScale().timeToCoordinate(sortedTimes[i + 1]! as Time);
      if (x0 !== null && x1 !== null) {
        barW = Math.max(4, Math.abs(x1 - x0));
        break;
      }
    }

    // Track session label positions to draw them once per visible session block
    const drawnLabels = new Map<string, boolean>();

    for (const entry of candleSessions) {
      if (entry.sessions.length === 0) continue;

      const x = chart.timeScale().timeToCoordinate(entry.time as Time);
      if (x === null) continue;

      // Draw background column for each active session (they blend additively)
      for (const session of entry.sessions) {
        ctx.fillStyle = session.color;
        ctx.fillRect(x - barW / 2, 0, barW + 1, h);
      }

      // Draw session label at the top for the primary (latest-starting) session
      const primary = entry.sessions[entry.sessions.length - 1]!;
      const labelKey = `${primary.name}-${Math.floor(entry.time / 86400)}`;
      if (!drawnLabels.has(labelKey)) {
        drawnLabels.set(labelKey, true);
        ctx.save();
        ctx.font = "bold 9px Inter, sans-serif";
        ctx.fillStyle = primary.labelColor + "70";
        ctx.textAlign = "left";
        ctx.fillText(primary.name, x - barW / 2 + 2, 12);
        ctx.restore();
      }
    }

    // Draw legend in top-right corner
    ctx.save();
    const legendX = w - 170;
    const legendY = 14;
    ctx.font = "10px Inter, sans-serif";
    for (let i = 0; i < TRADING_SESSIONS.length; i++) {
      const s = TRADING_SESSIONS[i]!;
      const y = legendY + i * 14;
      ctx.fillStyle = s.labelColor + "60";
      ctx.fillRect(legendX, y - 6, 8, 8);
      ctx.fillStyle = "#8b949e";
      const startStr = `${String(s.startHour).padStart(2, "0")}:${String(s.startMinute).padStart(2, "0")}`;
      const endStr = `${String(s.endHour).padStart(2, "0")}:${String(s.endMinute).padStart(2, "0")}`;
      ctx.fillText(`${s.name} (${startStr}-${endStr} UTC)`, legendX + 12, y + 1);
    }
    ctx.restore();
  }

  function scheduleRender(): void {
    cancelAnimationFrame(rafId);
    rafId = requestAnimationFrame(render);
  }

  setTimeout(scheduleRender, 100);
  setTimeout(scheduleRender, 400);
  setTimeout(scheduleRender, 1000);

  chart.timeScale().subscribeVisibleLogicalRangeChange(scheduleRender);

  const resizeObs = new ResizeObserver(scheduleRender);
  resizeObs.observe(container);

  const syncTimer = setInterval(scheduleRender, 500);

  return () => {
    cancelAnimationFrame(rafId);
    clearInterval(syncTimer);
    try { chart.timeScale().unsubscribeVisibleLogicalRangeChange(scheduleRender); } catch { /* */ }
    resizeObs.disconnect();
    overlay.remove();
  };
}

function setupVolumeHeatmap(
  chart: IChartApi,
  candleSeries: ISeriesApi<"Candlestick">,
  klines: { time: number; open: number; high: number; low: number; close: number; volume: number }[],
  container: HTMLDivElement,
  chartHeight: number,
): () => void {
  const cells = computeHeatmapCells(klines, 50);
  if (cells.length === 0) return () => {};

  // Overlay canvas on top of the chart inside the container div
  const overlay = document.createElement("canvas");
  overlay.style.position = "absolute";
  overlay.style.top = "0";
  overlay.style.left = "0";
  overlay.style.pointerEvents = "none";
  overlay.style.zIndex = "10";
  container.style.position = "relative";
  container.appendChild(overlay);

  const sortedTimes = Array.from(new Set(cells.map((c) => c.time))).sort((a, b) => a - b);

  let rafId = 0;

  function render() {
    const dpr = window.devicePixelRatio || 1;
    const w = container.clientWidth;
    const h = chartHeight;

    overlay.width = Math.round(w * dpr);
    overlay.height = Math.round(h * dpr);
    overlay.style.width = w + "px";
    overlay.style.height = h + "px";

    const ctx = overlay.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, overlay.width, overlay.height);

    // Bar width from two adjacent visible times — extend slightly for overlap
    let barW = 10;
    for (let i = 0; i < sortedTimes.length - 1; i++) {
      const x0 = chart.timeScale().timeToCoordinate(sortedTimes[i]! as Time);
      const x1 = chart.timeScale().timeToCoordinate(sortedTimes[i + 1]! as Time);
      if (x0 !== null && x1 !== null) {
        barW = Math.max(4, Math.abs(x1 - x0) * 1.1); // 10% wider for seamless fill
        break;
      }
    }

    // Draw cells in CSS pixels, let canvas scaling handle DPI
    ctx.scale(dpr, dpr);

    for (const cell of cells) {
      const x = chart.timeScale().timeToCoordinate(cell.time as Time);
      if (x === null) continue;

      const y1 = candleSeries.priceToCoordinate(cell.priceHigh);
      const y2 = candleSeries.priceToCoordinate(cell.priceLow);
      if (y1 === null || y2 === null) continue;

      const top = Math.min(y1, y2);
      const cellH = Math.abs(y2 - y1);
      if (cellH < 0.5) continue;

      ctx.fillStyle = thermalColor(cell.intensity);
      ctx.fillRect(x - barW / 2, top, barW, Math.max(cellH, 1));
    }
  }

  function scheduleRender() {
    cancelAnimationFrame(rafId);
    rafId = requestAnimationFrame(render);
  }

  // Staggered initial renders
  setTimeout(scheduleRender, 100);
  setTimeout(scheduleRender, 400);
  setTimeout(scheduleRender, 1000);

  // Re-render on pan/zoom
  chart.timeScale().subscribeVisibleLogicalRangeChange(scheduleRender);

  // Re-render on resize
  const resizeObs = new ResizeObserver(scheduleRender);
  resizeObs.observe(container);

  // Periodic sync for price auto-scale
  const syncTimer = setInterval(scheduleRender, 300);

  return () => {
    cancelAnimationFrame(rafId);
    clearInterval(syncTimer);
    try { chart.timeScale().unsubscribeVisibleLogicalRangeChange(scheduleRender); } catch { /* */ }
    resizeObs.disconnect();
    overlay.remove();
  };
}

/* ------------------------------------------------------------------ */
/*  News Impact Markers — overlay news events on chart timeline        */
/* ------------------------------------------------------------------ */

function drawNewsMarkers(
  candleSeries: ISeriesApi<"Candlestick">,
  news: NewsItemData[],
  klines: { time: number; open: number; high: number; low: number; close: number; volume: number }[],
): void {
  if (klines.length === 0 || news.length === 0) return;

  const candleTimes = klines.map((k) => k.time).sort((a, b) => a - b);
  const firstTime = candleTimes[0]!;
  const lastTime = candleTimes[candleTimes.length - 1]!;

  /** Snap a unix timestamp to the nearest candle time via binary search */
  function snapToCandle(timestamp: number): number | null {
    if (timestamp < firstTime - 86400 || timestamp > lastTime + 86400) return null;
    let lo = 0;
    let hi = candleTimes.length - 1;
    while (lo < hi) {
      const mid = (lo + hi) >>> 1;
      if (candleTimes[mid]! < timestamp) lo = mid + 1;
      else hi = mid;
    }
    const best = lo > 0 && Math.abs(candleTimes[lo - 1]! - timestamp) < Math.abs(candleTimes[lo]! - timestamp)
      ? candleTimes[lo - 1]!
      : candleTimes[lo]!;
    return best;
  }

  function sentimentCategory(sentiment: number): "bullish" | "bearish" | "neutral" {
    if (sentiment > 0.2) return "bullish";
    if (sentiment < -0.2) return "bearish";
    return "neutral";
  }

  // Group news by snapped candle time — keep the most impactful per candle
  const grouped = new Map<number, { sentiment: "bullish" | "bearish" | "neutral"; title: string; sentimentValue: number }>();

  for (const item of news) {
    const rawTs = item.timestamp
      ? new Date(item.timestamp).getTime()
      : new Date(item.published).getTime();
    if (Number.isNaN(rawTs)) continue;
    const ts = Math.floor(rawTs / 1000);
    const snapped = snapToCandle(ts);
    if (snapped === null) continue;

    const cat = sentimentCategory(item.sentiment);
    const existing = grouped.get(snapped);
    if (!existing || Math.abs(item.sentiment) > Math.abs(existing.sentimentValue)) {
      grouped.set(snapped, { sentiment: cat, title: item.title, sentimentValue: item.sentiment });
    }
  }

  const markers: SeriesMarker<Time>[] = Array.from(grouped.entries())
    .sort(([a], [b]) => a - b)
    .map(([time, data]) => {
      const shape = data.sentiment === "bullish"
        ? "arrowUp" as const
        : data.sentiment === "bearish"
          ? "arrowDown" as const
          : "circle" as const;

      const color = data.sentiment === "bullish"
        ? "#22c55e"
        : data.sentiment === "bearish"
          ? "#ef4444"
          : "#9ca3af";

      const position = data.sentiment === "bearish" ? "aboveBar" as const : "belowBar" as const;

      const truncatedTitle = data.title.length > 30 ? data.title.slice(0, 27) + "..." : data.title;

      return {
        time: time as Time,
        position,
        color,
        shape,
        text: truncatedTitle,
      };
    });

  if (markers.length > 0) {
    candleSeries.setMarkers(markers);
  }
}
