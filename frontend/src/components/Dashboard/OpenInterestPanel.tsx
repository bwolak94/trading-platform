/**
 * OpenInterestPanel — visualises Binance Futures positioning data.
 *
 * Three synchronised lightweight-charts panes:
 *   A) Price (candlestick from klines) + liquidation price lines
 *   B) OI histogram (green rising / red falling, unit $B)
 *   C) L/S ratio lines (global=blue, top trader=orange) + 1.0 baseline
 *
 * Data polled every 60 s via React Query; no WebSocket (Binance has none for OI history).
 */
import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  createChart,
  LineStyle,
  type IChartApi,
  type ISeriesApi,
  type IPriceLine,
  type SeriesMarker,
  type Time,
  type CandlestickData,
  type HistogramData,
  type LineData,
} from "lightweight-charts";
import {
  fetchPositioningSnapshot,
  fetchKlines,
  fetchOpenPositions,
  fetchClosedPositions,
} from "../../api/client";
import type { PositioningSnapshot, KlineData, SimulatedPosition } from "../../api/client";
import { useAppStore } from "../../store";
import { AssetSearchSelect } from "../ui/AssetSearchSelect";

interface OpenInterestPanelProps {
  defaultSymbol?: string;
}

const PERIODS = ["5m", "15m", "1h", "4h", "1d"] as const;
type Period = (typeof PERIODS)[number];

const PERIOD_TO_INTERVAL: Record<Period, string> = {
  "5m": "5m",
  "15m": "15m",
  "1h": "1h",
  "4h": "4h",
  "1d": "1D",
};

const baseChartOpts = {
  layout: {
    background: { color: "#0f1117" },
    textColor: "#9ca3af",
    fontFamily: "Inter, system-ui, sans-serif",
  },
  grid: {
    vertLines: { color: "#1f2937" },
    horzLines: { color: "#1f2937" },
  },
  crosshair: { mode: 1 as const },
  timeScale: {
    borderColor: "#374151",
    timeVisible: true,
    secondsVisible: false,
  },
  rightPriceScale: { borderColor: "#374151" },
  handleScroll: { mouseWheel: true, pressedMouseMove: true },
  handleScale: { mouseWheel: true, pinch: true },
} as const;

/* ── formatting helpers ─────────────────────────────────────────────────── */

function formatOI(value: number): string {
  if (value >= 1e9) return `$${(value / 1e9).toFixed(2)}B`;
  if (value >= 1e6) return `$${(value / 1e6).toFixed(1)}M`;
  return `$${value.toFixed(0)}`;
}

function ratioColor(r: number) {
  return r > 1.2 ? "text-green-400" : r < 0.8 ? "text-red-400" : "text-gray-300";
}

function fundingColor(r: number) {
  return r > 0.0001 ? "text-red-400" : r < 0 ? "text-blue-400" : "text-gray-300";
}

function oiChangeColor(p: number) {
  return p >= 0 ? "text-green-400" : "text-red-400";
}

/* ── chart instances holder ─────────────────────────────────────────────── */

interface Charts {
  price: IChartApi;
  oi: IChartApi;
  ls: IChartApi;
  candle: ISeriesApi<"Candlestick">;
  oiHist: ISeriesApi<"Histogram">;
  globalLs: ISeriesApi<"Line">;
  topLs: ISeriesApi<"Line">;
  /** Liquidation level dashed lines — managed by positioning effect */
  priceLines: IPriceLine[];
  /** Signal level lines (entry/TP/SL) — managed by signal effect */
  signalLines: IPriceLine[];
}

/* ── component ──────────────────────────────────────────────────────────── */

export function OpenInterestPanel({ defaultSymbol = "BTCUSDT" }: OpenInterestPanelProps) {
  const [symbol, setSymbol] = useState(defaultSymbol);
  const [period, setPeriod] = useState<Period>("1h");

  const { activeSignals } = useAppStore();

  const priceRef = useRef<HTMLDivElement>(null);
  const oiRef = useRef<HTMLDivElement>(null);
  const lsRef = useRef<HTMLDivElement>(null);
  const charts = useRef<Charts | null>(null);

  // ── Queries ────────────────────────────────────────────────────────────
  const { data: positioning, dataUpdatedAt } = useQuery<PositioningSnapshot>({
    queryKey: ["positioning", symbol, period],
    queryFn: () => fetchPositioningSnapshot(symbol, period, 100),
    refetchInterval: 60_000,
    staleTime: 30_000,
    retry: 2,
  });

  const { data: klines } = useQuery<KlineData[]>({
    queryKey: ["klines-oi", symbol, period],
    queryFn: () => fetchKlines(symbol, PERIOD_TO_INTERVAL[period], 100),
    refetchInterval: 60_000,
    staleTime: 30_000,
    retry: 2,
  });

  const { data: openPositionsData } = useQuery({
    queryKey: ["open-positions-oi"],
    queryFn: fetchOpenPositions,
    refetchInterval: 30_000,
    staleTime: 15_000,
  });

  const { data: closedPositionsData } = useQuery({
    queryKey: ["closed-positions-oi"],
    queryFn: () => fetchClosedPositions({ limit: 100 }),
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

  // ── Create charts once on mount ────────────────────────────────────────
  useEffect(() => {
    if (!priceRef.current || !oiRef.current || !lsRef.current) return;

    const price = createChart(priceRef.current, { ...baseChartOpts, height: 240 });
    const oi = createChart(oiRef.current, { ...baseChartOpts, height: 140 });
    const ls = createChart(lsRef.current, { ...baseChartOpts, height: 120 });

    const candle = price.addCandlestickSeries({
      upColor: "#22c55e",
      downColor: "#ef4444",
      borderUpColor: "#22c55e",
      borderDownColor: "#ef4444",
      wickUpColor: "#22c55e",
      wickDownColor: "#ef4444",
    });

    const oiHist = oi.addHistogramSeries({
      color: "#22c55e",
      priceFormat: {
        type: "custom",
        formatter: (v: number) => `${v.toFixed(2)}B`,
        minMove: 0.01,
      },
    });

    const globalLs = ls.addLineSeries({ color: "#3b82f6", lineWidth: 2, title: "Global" });
    const topLs = ls.addLineSeries({ color: "#f97316", lineWidth: 2, title: "Top" });

    globalLs.createPriceLine({
      price: 1.0,
      color: "#4b5563",
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      axisLabelVisible: false,
      title: "",
    });

    charts.current = { price, oi, ls, candle, oiHist, globalLs, topLs, priceLines: [], signalLines: [] };

    // ── Crosshair sync ──────────────────────────────────────────────────
    type AnySeries =
      | ISeriesApi<"Candlestick">
      | ISeriesApi<"Histogram">
      | ISeriesApi<"Line">;

    function syncCrosshair(src: IChartApi, targets: { chart: IChartApi; series: AnySeries }[]) {
      src.subscribeCrosshairMove((p) => {
        targets.forEach(({ chart, series }) => {
          if (p.time) chart.setCrosshairPosition(0, p.time as Time, series);
          else chart.clearCrosshairPosition();
        });
      });
    }

    syncCrosshair(price, [{ chart: oi, series: oiHist }, { chart: ls, series: globalLs }]);
    syncCrosshair(oi, [{ chart: price, series: candle }, { chart: ls, series: globalLs }]);
    syncCrosshair(ls, [{ chart: price, series: candle }, { chart: oi, series: oiHist }]);

    // ── Time range sync ─────────────────────────────────────────────────
    function syncRange(src: IChartApi, others: IChartApi[]) {
      src.timeScale().subscribeVisibleLogicalRangeChange((range) => {
        if (range) others.forEach((o) => o.timeScale().setVisibleLogicalRange(range));
      });
    }

    syncRange(price, [oi, ls]);
    syncRange(oi, [price, ls]);
    syncRange(ls, [price, oi]);

    return () => {
      price.remove();
      oi.remove();
      ls.remove();
      charts.current = null;
    };
  }, []);

  // ── Clear all series data immediately when symbol or period changes ────
  // This prevents stale BTC candles from showing while ETH data is loading.
  useEffect(() => {
    const c = charts.current;
    if (!c) return;
    try {
      c.candle.setData([]);
      c.candle.setMarkers([]);
      c.oiHist.setData([]);
      c.globalLs.setData([]);
      c.topLs.setData([]);
      c.priceLines.forEach((pl) => { try { c.candle.removePriceLine(pl); } catch { /* ignore */ } });
      c.priceLines = [];
      c.signalLines.forEach((pl) => { try { c.candle.removePriceLine(pl); } catch { /* ignore */ } });
      c.signalLines = [];
    } catch {
      /* ignore */
    }
  }, [symbol, period]);

  // ── Update candles when klines arrive ────────────────────────────────
  // symbol + period are included so this effect re-fires even when the
  // query returns the same cached reference after a period switch-back.
  useEffect(() => {
    const c = charts.current;
    if (!c || !klines || klines.length === 0) return;

    const data: CandlestickData[] = klines.map((k) => ({
      time: k.time as Time,
      open: k.open,
      high: k.high,
      low: k.low,
      close: k.close,
    }));

    try {
      c.candle.setData(data);
      c.price.timeScale().fitContent();
    } catch {
      /* ignore stale-series errors on rapid switches */
    }
  }, [klines, symbol, period]);

  // ── Update OI / LS / liquidation lines when positioning arrives ───────
  // symbol + period included for the same cache-reference reason as above.
  useEffect(() => {
    const c = charts.current;
    if (!c || !positioning) return;

    const { oi_history, ls_history, top_trader_history, liquidation_levels } = positioning;

    // OI histogram
    if (oi_history.length > 0) {
      const data: HistogramData[] = oi_history.map((pt, i) => ({
        time: Math.floor(pt.timestamp / 1000) as Time,
        value: pt.open_interest_value / 1e9,
        color:
          i === 0 || pt.open_interest_value >= oi_history[i - 1]!.open_interest_value
            ? "#22c55e"
            : "#ef4444",
      }));
      try {
        c.oiHist.setData(data);
        c.oi.timeScale().fitContent();
      } catch {
        /* ignore */
      }
    }

    // Global L/S ratio
    if (ls_history.length > 0) {
      const data: LineData[] = ls_history.map((pt) => ({
        time: Math.floor(pt.timestamp / 1000) as Time,
        value: pt.long_short_ratio,
      }));
      try {
        c.globalLs.setData(data);
      } catch {
        /* ignore */
      }
    }

    // Top trader L/S ratio
    if (top_trader_history.length > 0) {
      const data: LineData[] = top_trader_history.map((pt) => ({
        time: Math.floor(pt.timestamp / 1000) as Time,
        value: pt.long_short_ratio,
      }));
      try {
        c.topLs.setData(data);
        c.ls.timeScale().fitContent();
      } catch {
        /* ignore */
      }
    }

    // Remove stale liquidation lines, then add fresh ones
    c.priceLines.forEach((pl) => {
      try { c.candle.removePriceLine(pl); } catch { /* ignore */ }
    });
    c.priceLines = [];

    liquidation_levels.forEach((lv) => {
      try {
        const pl = c.candle.createPriceLine({
          price: lv.price,
          color: lv.side === "long" ? "#ef4444" : "#22c55e",
          lineWidth: 1,
          lineStyle: LineStyle.Dashed,
          title: `${lv.side.toUpperCase()} ${lv.leverage}x`,
          axisLabelVisible: true,
        });
        c.priceLines.push(pl);
      } catch {
        /* ignore */
      }
    });
  }, [positioning, symbol, period]);

  // ── Overlay active signal levels (entry / TP1 / TP2 / SL) on price chart ─
  // Signals are filtered to the current symbol. Both "BTCUSDT" and "BTC/USDT"
  // asset formats are handled. Lines are refreshed whenever signals or symbol change.
  useEffect(() => {
    const c = charts.current;
    if (!c) return;

    // Remove previous signal lines
    c.signalLines.forEach((pl) => { try { c.candle.removePriceLine(pl); } catch { /* ignore */ } });
    c.signalLines = [];

    // Normalise both "BTCUSDT" and "BTC/USDT" → "BTCUSDT" for comparison
    const normalise = (s: string) => s.replace("/", "").toUpperCase();
    const sym = normalise(symbol);

    const relevant = activeSignals.filter(
      (s) => normalise(s.asset) === sym && s.status === "ACTIVE",
    );

    relevant.forEach((sig) => {
      const levels: { price: number; color: string; title: string; style: LineStyle }[] = [
        {
          price: sig.entry_price,
          color: "#f59e0b",   // amber — entry
          title: `${sig.direction} Entry`,
          style: LineStyle.Solid,
        },
        {
          price: sig.take_profit_1,
          color: "#22c55e",   // green — TP1
          title: "TP1",
          style: LineStyle.Dashed,
        },
        {
          price: sig.take_profit_2,
          color: "#16a34a",   // dark green — TP2
          title: "TP2",
          style: LineStyle.Dashed,
        },
        {
          price: sig.stop_loss,
          color: "#ef4444",   // red — stop loss
          title: "SL",
          style: LineStyle.Dashed,
        },
      ];

      levels.forEach(({ price, color, title, style }) => {
        if (!price || price <= 0) return;
        try {
          const pl = c.candle.createPriceLine({
            price,
            color,
            lineWidth: 1,
            lineStyle: style,
            title,
            axisLabelVisible: true,
          });
          c.signalLines.push(pl);
        } catch {
          /* ignore */
        }
      });

    });
  }, [activeSignals, symbol]);

  // ── Simulated position markers + open position level lines ────────────
  useEffect(() => {
    const c = charts.current;
    if (!c) return;

    const normalise = (s: string) => s.replace("/", "").toUpperCase();
    const sym = normalise(symbol);

    const openList: SimulatedPosition[] = (openPositionsData?.positions ?? []).filter(
      (p) => normalise(p.symbol) === sym,
    );
    const closedList: SimulatedPosition[] = (closedPositionsData?.positions ?? []).filter(
      (p) => normalise(p.symbol) === sym,
    );

    // ── Markers on the candle chart ─────────────────────────────────────
    const markers: SeriesMarker<Time>[] = [];

    // Open position entries
    openList.forEach((pos) => {
      const t = Math.floor(new Date(pos.opened_at).getTime() / 1000) as Time;
      markers.push({
        time: t,
        position: pos.direction === "LONG" ? "belowBar" : "aboveBar",
        color: pos.direction === "LONG" ? "#22c55e" : "#ef4444",
        shape: pos.direction === "LONG" ? "arrowUp" : "arrowDown",
        text: `${pos.direction} Open`,
        size: 2,
      });
    });

    // Closed position entries + exits
    closedList.forEach((pos) => {
      const openT = Math.floor(new Date(pos.opened_at).getTime() / 1000) as Time;
      markers.push({
        time: openT,
        position: pos.direction === "LONG" ? "belowBar" : "aboveBar",
        color: pos.direction === "LONG" ? "#22c55e99" : "#ef444499",
        shape: pos.direction === "LONG" ? "arrowUp" : "arrowDown",
        text: `${pos.direction}`,
        size: 1,
      });

      if (pos.closed_at) {
        const closeT = Math.floor(new Date(pos.closed_at).getTime() / 1000) as Time;
        const profitable = (pos.pnl_pct ?? 0) >= 0;
        markers.push({
          time: closeT,
          position: pos.direction === "LONG" ? "aboveBar" : "belowBar",
          color: profitable ? "#22c55e" : "#ef4444",
          shape: "circle",
          text: `${profitable ? "+" : ""}${(pos.pnl_pct ?? 0).toFixed(1)}%`,
          size: 1,
        });
      }
    });

    // lightweight-charts requires markers sorted by time ascending
    markers.sort((a, b) => (a.time as number) - (b.time as number));

    try {
      c.candle.setMarkers(markers);
    } catch {
      /* ignore if series not ready */
    }

    // ── Price lines for OPEN positions (entry / SL / TP) ────────────────
    // Remove previous position level lines (signalLines array is reused here)
    c.signalLines.forEach((pl) => { try { c.candle.removePriceLine(pl); } catch { /* ignore */ } });
    c.signalLines = [];

    openList.forEach((pos) => {
      const levels: { price: number | null; color: string; title: string }[] = [
        { price: pos.entry_price, color: "#f59e0b", title: `${pos.direction} Entry` },
        { price: pos.stop_loss,   color: "#ef4444", title: "Stop Loss" },
        { price: pos.take_profit_1, color: "#22c55e", title: "TP1" },
        { price: pos.take_profit_2, color: "#16a34a", title: "TP2" },
      ];
      levels.forEach(({ price, color, title }) => {
        if (!price || price <= 0) return;
        try {
          const pl = c.candle.createPriceLine({
            price,
            color,
            lineWidth: 1,
            lineStyle: LineStyle.Dashed,
            title,
            axisLabelVisible: true,
          });
          c.signalLines.push(pl);
        } catch { /* ignore */ }
      });
    });
  }, [openPositionsData, closedPositionsData, symbol, klines]);

  const updatedAt = dataUpdatedAt
    ? new Date(dataUpdatedAt).toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      })
    : "—";

  /* ── render ─────────────────────────────────────────────────────────── */
  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-3">
        <AssetSearchSelect
          value={symbol}
          onChange={(v) => setSymbol(v)}
          aria-label="Select asset for positioning view"
          includeForex={false}
        />

        <div
          className="flex overflow-hidden rounded border border-border"
          role="group"
          aria-label="Select period"
        >
          {PERIODS.map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => setPeriod(p)}
              aria-pressed={period === p}
              className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                period === p
                  ? "bg-accent text-white"
                  : "bg-surface text-gray-400 hover:text-gray-200"
              }`}
            >
              {p}
            </button>
          ))}
        </div>

        <span className="ml-auto text-xs text-gray-500">Last updated: {updatedAt}</span>
      </div>

      {/* Stats row */}
      {positioning && (
        <div className="flex flex-wrap gap-6 rounded-lg border border-border bg-surface px-4 py-3">
          <StatBadge label="OI" value={formatOI(positioning.current_oi_value)} />
          <StatBadge
            label="OI 24h"
            value={`${positioning.oi_change_24h_pct >= 0 ? "+" : ""}${positioning.oi_change_24h_pct.toFixed(1)}%`}
            valueClassName={oiChangeColor(positioning.oi_change_24h_pct)}
          />
          <StatBadge
            label="Global L/S"
            value={positioning.global_ls_ratio.toFixed(2)}
            valueClassName={ratioColor(positioning.global_ls_ratio)}
          />
          <StatBadge
            label="Top Trader"
            value={positioning.top_trader_ratio.toFixed(2)}
            valueClassName={ratioColor(positioning.top_trader_ratio)}
          />
          <StatBadge
            label="Funding"
            value={`${(positioning.funding_rate * 100).toFixed(4)}%`}
            valueClassName={fundingColor(positioning.funding_rate)}
          />
        </div>
      )}

      {/* Charts */}
      <div className="overflow-hidden rounded-lg border border-border">
        <div className="border-b border-border px-3 py-1.5">
          <span className="text-xs font-medium text-gray-400">
            Price
            {positioning?.current_price
              ? ` · $${positioning.current_price.toLocaleString(undefined, {
                  minimumFractionDigits: 2,
                  maximumFractionDigits: 2,
                })}`
              : ""}
            {positioning && positioning.liquidation_levels.length > 0
              ? ` · ${positioning.liquidation_levels.length} liq. levels`
              : ""}
          </span>
          {/* Open position indicator */}
          {(openPositionsData?.positions ?? []).some(
            (p) => p.symbol.replace("/", "").toUpperCase() === symbol,
          ) && (
            <span className="ml-3 inline-flex items-center gap-2 text-[10px] text-gray-400">
              <span className="inline-block h-2 w-2 rounded-full bg-[#f59e0b]" />
              {(openPositionsData?.positions ?? []).filter(
                (p) => p.symbol.replace("/", "").toUpperCase() === symbol,
              ).length}{" "}
              open position(s)
              <span className="text-[#f59e0b]">— Entry</span>
              <span className="text-[#22c55e]">— TP</span>
              <span className="text-[#ef4444]">— SL</span>
            </span>
          )}
        </div>
        <div ref={priceRef} />

        <div className="border-b border-t border-border px-3 py-1.5">
          <span className="text-xs font-medium text-gray-400">Open Interest ($B)</span>
        </div>
        <div ref={oiRef} />

        <div className="border-t border-border px-3 py-1.5">
          <span className="text-xs font-medium text-gray-400">
            Long / Short Ratio{" "}
            <span className="text-blue-400">— Global</span>{" "}
            <span className="text-orange-400">— Top Trader</span>
          </span>
        </div>
        <div ref={lsRef} />
      </div>
    </div>
  );
}

/* ── StatBadge ──────────────────────────────────────────────────────────── */

interface StatBadgeProps {
  label: string;
  value: string;
  valueClassName?: string;
}

function StatBadge({ label, value, valueClassName = "text-white" }: StatBadgeProps) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] uppercase tracking-wide text-gray-500">{label}</span>
      <span className={`text-sm font-semibold tabular-nums ${valueClassName}`}>{value}</span>
    </div>
  );
}
