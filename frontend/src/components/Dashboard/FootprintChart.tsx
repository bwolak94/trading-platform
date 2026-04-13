import { useCallback, useEffect, useRef, useState } from "react";
import {
  fetchOrderFlow,
  type OrderFlowData,
  type FootprintWindow,
  type PriceCluster,
} from "../../api/client";

// --- Constants ---

const BG_COLOR = "#0d1117";
const TEXT_COLOR = "#8b949e";
const GRID_COLOR = "#1b2028";
const CELL_COLORS = {
  low: "#1a1f36",
  medium: "#1e3a5f",
  high: "#06b6d4",
  extreme: "#00d4aa",
};
const IMBALANCE_BUY_COLOR = "#00d4aa";
const IMBALANCE_SELL_COLOR = "#ff4757";
const DELTA_POSITIVE_COLOR = "#00d4aa";
const DELTA_NEGATIVE_COLOR = "#ff4757";
const CUMULATIVE_LINE_COLOR = "#06b6d4";

const DEFAULT_COL_WIDTH = 80;
const MIN_ROW_HEIGHT = 14;
const MAX_ROW_HEIGHT = 40;
const DEFAULT_ROW_HEIGHT = 20;
const DELTA_HIST_HEIGHT = 60;
const PRICE_AXIS_WIDTH = 70;
const HEADER_HEIGHT = 0;
const FONT_SMALL = "9px monospace";

const ASSETS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"];
const TIMEFRAMES = ["1m", "5m", "15m", "1h"];

// --- Helpers ---

function formatNumber(n: number): string {
  if (Math.abs(n) >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (Math.abs(n) >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  if (Math.abs(n) >= 1) return n.toFixed(0);
  return n.toFixed(2);
}

function formatPrice(p: number): string {
  if (p >= 1000) return p.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 });
  if (p >= 1) return p.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return p.toLocaleString("en-US", { minimumFractionDigits: 4, maximumFractionDigits: 4 });
}

function volumeToColor(vol: number, maxVol: number): string {
  if (maxVol === 0) return CELL_COLORS.low;
  const ratio = vol / maxVol;
  if (ratio > 0.75) return CELL_COLORS.extreme;
  if (ratio > 0.5) return CELL_COLORS.high;
  if (ratio > 0.25) return CELL_COLORS.medium;
  return CELL_COLORS.low;
}

function getTickSize(windows: FootprintWindow[]): number {
  // Derive tick size from the clusters in the first window with data
  for (const w of windows) {
    if (w.clusters.length >= 2) {
      const sorted = [...w.clusters].sort((a, b) => a.price - b.price);
      const first = sorted[0];
      const second = sorted[1];
      if (!first || !second) continue;
      const diff = second.price - first.price;
      if (diff > 0) return diff;
    }
  }
  return 1;
}

// --- Component ---

export function FootprintChart() {
  const [asset, setAsset] = useState("BTCUSDT");
  const [timeframe, setTimeframe] = useState("1m");
  const [data, setData] = useState<OrderFlowData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [rowHeight, setRowHeight] = useState(DEFAULT_ROW_HEIGHT);
  const [scrollX, setScrollX] = useState(0);
  const [tooltip, setTooltip] = useState<{
    x: number;
    y: number;
    cluster: PriceCluster;
    window: FootprintWindow;
  } | null>(null);

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const isDragging = useRef(false);
  const lastDragX = useRef(0);

  // Fetch data
  const loadData = useCallback(() => {
    fetchOrderFlow(asset, timeframe, 30)
      .then((d) => {
        setData(d);
        setError(null);
        setLoading(false);
      })
      .catch((err: unknown) => {
        const message = err instanceof Error ? err.message : "Failed to fetch order flow data";
        setError(message);
        setLoading(false);
      });
  }, [asset, timeframe]);

  useEffect(() => {
    setLoading(true);
    setScrollX(0);
    loadData();
  }, [loadData]);

  // Auto-refresh every 5 seconds
  useEffect(() => {
    const timer = setInterval(loadData, 5_000);
    return () => clearInterval(timer);
  }, [loadData]);

  // Get all price levels and max volume for color scaling
  const getChartMetrics = useCallback(
    (orderData: OrderFlowData) => {
      let minPrice = Infinity;
      let maxPrice = -Infinity;
      let maxClusterVol = 0;
      let maxDelta = 0;

      for (const w of orderData.windows) {
        for (const c of w.clusters) {
          minPrice = Math.min(minPrice, c.price);
          maxPrice = Math.max(maxPrice, c.price);
          maxClusterVol = Math.max(maxClusterVol, c.bid_vol + c.ask_vol);
        }
        maxDelta = Math.max(maxDelta, Math.abs(w.delta));
      }

      const tickSize = getTickSize(orderData.windows);
      return { minPrice, maxPrice, maxClusterVol, maxDelta, tickSize };
    },
    [],
  );

  // Draw canvas
  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container || !data || data.windows.length === 0) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const rect = container.getBoundingClientRect();
    const canvasW = rect.width;
    const canvasH = rect.height;

    canvas.width = canvasW * dpr;
    canvas.height = canvasH * dpr;
    canvas.style.width = `${canvasW}px`;
    canvas.style.height = `${canvasH}px`;
    ctx.scale(dpr, dpr);

    // Clear
    ctx.fillStyle = BG_COLOR;
    ctx.fillRect(0, 0, canvasW, canvasH);

    const { minPrice, maxPrice, maxClusterVol, maxDelta, tickSize } =
      getChartMetrics(data);
    if (minPrice === Infinity) return;

    const mainChartHeight = canvasH - DELTA_HIST_HEIGHT - HEADER_HEIGHT;
    const priceLevels = Math.ceil((maxPrice - minPrice) / tickSize) + 1;
    const totalContentHeight = priceLevels * rowHeight;
    const colWidth = DEFAULT_COL_WIDTH;
    const totalContentWidth =
      data.windows.length * colWidth + PRICE_AXIS_WIDTH;
    const chartAreaWidth = canvasW - PRICE_AXIS_WIDTH;

    // Clamp scrollX
    const maxScrollX = Math.max(0, totalContentWidth - canvasW);
    const clampedScrollX = Math.max(0, Math.min(scrollX, maxScrollX));

    // Vertical offset to center content
    const verticalOffset = Math.max(
      0,
      (mainChartHeight - totalContentHeight) / 2,
    );

    // --- Draw price axis ---
    ctx.save();
    ctx.fillStyle = "#0f1318";
    ctx.fillRect(0, HEADER_HEIGHT, PRICE_AXIS_WIDTH, mainChartHeight);

    ctx.font = FONT_SMALL;
    ctx.fillStyle = TEXT_COLOR;
    ctx.textAlign = "right";
    ctx.textBaseline = "middle";

    for (let i = 0; i < priceLevels; i++) {
      const price = maxPrice - i * tickSize;
      const y = HEADER_HEIGHT + verticalOffset + i * rowHeight + rowHeight / 2;
      if (y >= HEADER_HEIGHT && y <= HEADER_HEIGHT + mainChartHeight) {
        ctx.fillText(formatPrice(price), PRICE_AXIS_WIDTH - 6, y);
        // Grid line
        ctx.strokeStyle = GRID_COLOR;
        ctx.lineWidth = 0.5;
        ctx.beginPath();
        ctx.moveTo(PRICE_AXIS_WIDTH, y);
        ctx.lineTo(canvasW, y);
        ctx.stroke();
      }
    }
    ctx.restore();

    // --- Draw footprint cells ---
    ctx.save();
    ctx.beginPath();
    ctx.rect(
      PRICE_AXIS_WIDTH,
      HEADER_HEIGHT,
      chartAreaWidth,
      mainChartHeight,
    );
    ctx.clip();

    for (let wi = 0; wi < data.windows.length; wi++) {
      const w = data.windows[wi] as FootprintWindow | undefined;
      if (!w) continue;
      const colX =
        PRICE_AXIS_WIDTH + wi * colWidth - clampedScrollX;

      // Skip if off-screen
      if (colX + colWidth < PRICE_AXIS_WIDTH || colX > canvasW) continue;

      // Column separator
      ctx.strokeStyle = GRID_COLOR;
      ctx.lineWidth = 0.5;
      ctx.beginPath();
      ctx.moveTo(colX, HEADER_HEIGHT);
      ctx.lineTo(colX, HEADER_HEIGHT + mainChartHeight);
      ctx.stroke();

      // Build a map of price -> cluster for quick lookup
      const clusterMap = new Map<number, PriceCluster>();
      for (const c of w.clusters) {
        clusterMap.set(c.price, c);
      }

      // Draw each price level cell
      for (let i = 0; i < priceLevels; i++) {
        const price = maxPrice - i * tickSize;
        const cellY = HEADER_HEIGHT + verticalOffset + i * rowHeight;
        const cluster = clusterMap.get(price);

        if (!cluster) continue;
        if (cellY + rowHeight < HEADER_HEIGHT || cellY > HEADER_HEIGHT + mainChartHeight) continue;

        const totalVol = cluster.bid_vol + cluster.ask_vol;

        // Cell background (heatmap)
        ctx.fillStyle = volumeToColor(totalVol, maxClusterVol);
        ctx.fillRect(colX + 1, cellY + 1, colWidth - 2, rowHeight - 2);

        // Imbalance border
        if (cluster.imbalance) {
          ctx.strokeStyle =
            cluster.imbalance === "BUY"
              ? IMBALANCE_BUY_COLOR
              : IMBALANCE_SELL_COLOR;
          ctx.lineWidth = 2;
          ctx.strokeRect(colX + 1, cellY + 1, colWidth - 2, rowHeight - 2);
        }

        // Text: "bid | ask"
        if (rowHeight >= 14) {
          ctx.font = FONT_SMALL;
          ctx.textBaseline = "middle";
          const textY = cellY + rowHeight / 2;
          const midX = colX + colWidth / 2;

          // Bid volume (left, red-ish)
          ctx.fillStyle = "#ff6b6b";
          ctx.textAlign = "right";
          ctx.fillText(formatNumber(cluster.bid_vol), midX - 3, textY);

          // Separator
          ctx.fillStyle = TEXT_COLOR;
          ctx.textAlign = "center";
          ctx.fillText("|", midX, textY);

          // Ask volume (right, green-ish)
          ctx.fillStyle = "#51cf66";
          ctx.textAlign = "left";
          ctx.fillText(formatNumber(cluster.ask_vol), midX + 3, textY);
        }
      }

      // Time label at bottom of column
      const timeLabel = new Date(w.time * 1000).toLocaleTimeString("en-US", {
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      });
      ctx.font = FONT_SMALL;
      ctx.fillStyle = TEXT_COLOR;
      ctx.textAlign = "center";
      ctx.textBaseline = "top";
      ctx.fillText(
        timeLabel,
        colX + colWidth / 2,
        HEADER_HEIGHT + mainChartHeight - 14,
      );
    }
    ctx.restore();

    // --- Draw delta histogram ---
    const deltaY = HEADER_HEIGHT + mainChartHeight;
    ctx.fillStyle = "#0f1318";
    ctx.fillRect(0, deltaY, canvasW, DELTA_HIST_HEIGHT);

    // Separator line
    ctx.strokeStyle = "#2d333b";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(0, deltaY);
    ctx.lineTo(canvasW, deltaY);
    ctx.stroke();

    const deltaMid = deltaY + DELTA_HIST_HEIGHT / 2;
    const deltaMaxBarH = DELTA_HIST_HEIGHT / 2 - 4;

    ctx.save();
    ctx.beginPath();
    ctx.rect(PRICE_AXIS_WIDTH, deltaY, chartAreaWidth, DELTA_HIST_HEIGHT);
    ctx.clip();

    for (let wi = 0; wi < data.windows.length; wi++) {
      const w = data.windows[wi] as FootprintWindow | undefined;
      if (!w) continue;
      const colX = PRICE_AXIS_WIDTH + wi * colWidth - clampedScrollX;
      if (colX + colWidth < PRICE_AXIS_WIDTH || colX > canvasW) continue;

      const barHeight =
        maxDelta > 0
          ? (Math.abs(w.delta) / maxDelta) * deltaMaxBarH
          : 0;
      const barColor = w.delta >= 0 ? DELTA_POSITIVE_COLOR : DELTA_NEGATIVE_COLOR;

      ctx.fillStyle = barColor;
      ctx.globalAlpha = 0.7;
      if (w.delta >= 0) {
        ctx.fillRect(
          colX + 4,
          deltaMid - barHeight,
          colWidth - 8,
          barHeight,
        );
      } else {
        ctx.fillRect(colX + 4, deltaMid, colWidth - 8, barHeight);
      }
      ctx.globalAlpha = 1;

      // Delta value text
      if (colWidth >= 50) {
        ctx.font = FONT_SMALL;
        ctx.fillStyle = barColor;
        ctx.textAlign = "center";
        ctx.textBaseline = w.delta >= 0 ? "bottom" : "top";
        ctx.fillText(
          formatNumber(w.delta),
          colX + colWidth / 2,
          w.delta >= 0 ? deltaMid - barHeight - 1 : deltaMid + barHeight + 1,
        );
      }
    }

    // Zero line
    ctx.strokeStyle = TEXT_COLOR;
    ctx.lineWidth = 0.5;
    ctx.beginPath();
    ctx.moveTo(PRICE_AXIS_WIDTH, deltaMid);
    ctx.lineTo(canvasW, deltaMid);
    ctx.stroke();

    // --- Cumulative delta line overlay ---
    if (data.delta_history.length > 1) {
      const deltaHist = data.delta_history;
      let minCd = Infinity;
      let maxCd = -Infinity;
      for (const d of deltaHist) {
        minCd = Math.min(minCd, d.value);
        maxCd = Math.max(maxCd, d.value);
      }
      const cdRange = maxCd - minCd || 1;

      ctx.strokeStyle = CUMULATIVE_LINE_COLOR;
      ctx.lineWidth = 1.5;
      ctx.globalAlpha = 0.6;
      ctx.beginPath();

      for (let i = 0; i < data.windows.length && i < deltaHist.length; i++) {
        const point = deltaHist[i];
        if (!point) continue;
        const cx =
          PRICE_AXIS_WIDTH +
          i * colWidth +
          colWidth / 2 -
          clampedScrollX;
        const cy =
          deltaY +
          DELTA_HIST_HEIGHT -
          4 -
          ((point.value - minCd) / cdRange) *
            (DELTA_HIST_HEIGHT - 8);
        if (i === 0) ctx.moveTo(cx, cy);
        else ctx.lineTo(cx, cy);
      }
      ctx.stroke();
      ctx.globalAlpha = 1;
    }

    ctx.restore();

    // --- Price axis label for delta section ---
    ctx.font = FONT_SMALL;
    ctx.fillStyle = TEXT_COLOR;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.save();
    ctx.translate(10, deltaY + DELTA_HIST_HEIGHT / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.fillText("Delta", 0, 0);
    ctx.restore();
  }, [data, rowHeight, scrollX, getChartMetrics]);

  // Redraw on state changes
  useEffect(() => {
    draw();
  }, [draw]);

  // Resize observer
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const observer = new ResizeObserver(() => {
      draw();
    });
    observer.observe(container);
    return () => observer.disconnect();
  }, [draw]);

  // Mouse wheel => zoom row height
  const handleWheel = useCallback(
    (e: React.WheelEvent<HTMLCanvasElement>) => {
      e.preventDefault();
      if (e.ctrlKey || e.metaKey) {
        // Zoom
        setRowHeight((prev) => {
          const next = prev - Math.sign(e.deltaY) * 2;
          return Math.max(MIN_ROW_HEIGHT, Math.min(MAX_ROW_HEIGHT, next));
        });
      } else {
        // Horizontal scroll
        setScrollX((prev) => Math.max(0, prev + e.deltaX + e.deltaY));
      }
    },
    [],
  );

  // Drag to scroll
  const handleMouseDown = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    isDragging.current = true;
    lastDragX.current = e.clientX;
  }, []);

  const handleMouseMove = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      if (isDragging.current) {
        const dx = lastDragX.current - e.clientX;
        lastDragX.current = e.clientX;
        setScrollX((prev) => Math.max(0, prev + dx));
        setTooltip(null);
        return;
      }

      // Tooltip on hover
      if (!data || !canvasRef.current || !containerRef.current) return;

      const rect = canvasRef.current.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      const canvasH = rect.height;
      const mainChartHeight = canvasH - DELTA_HIST_HEIGHT - HEADER_HEIGHT;

      const { minPrice, maxPrice, tickSize } = getChartMetrics(data);
      if (minPrice === Infinity) return;

      const priceLevels = Math.ceil((maxPrice - minPrice) / tickSize) + 1;
      const totalContentHeight = priceLevels * rowHeight;
      const verticalOffset = Math.max(0, (mainChartHeight - totalContentHeight) / 2);

      // Which column?
      const clampedSx = Math.max(0, scrollX);
      const colIndex = Math.floor(
        (mx - PRICE_AXIS_WIDTH + clampedSx) / DEFAULT_COL_WIDTH,
      );
      // Which row?
      const rowIndex = Math.floor(
        (my - HEADER_HEIGHT - verticalOffset) / rowHeight,
      );
      const price = maxPrice - rowIndex * tickSize;

      if (
        colIndex >= 0 &&
        colIndex < data.windows.length &&
        mx > PRICE_AXIS_WIDTH &&
        my > HEADER_HEIGHT &&
        my < HEADER_HEIGHT + mainChartHeight
      ) {
        const w = data.windows[colIndex];
        if (!w) { setTooltip(null); return; }
        const cluster = w.clusters.find((c) => c.price === price);
        if (cluster) {
          setTooltip({ x: e.clientX - rect.left, y: e.clientY - rect.top, cluster, window: w });
          return;
        }
      }
      setTooltip(null);
    },
    [data, rowHeight, scrollX, getChartMetrics],
  );

  const handleMouseUp = useCallback(() => {
    isDragging.current = false;
  }, []);

  const handleMouseLeave = useCallback(() => {
    isDragging.current = false;
    setTooltip(null);
  }, []);

  // Imbalance summary
  const imbalanceSummary =
    data && data.imbalances.length > 0
      ? {
          buyCount: data.imbalances.filter((im) => im.type === "BUY").length,
          sellCount: data.imbalances.filter((im) => im.type === "SELL").length,
        }
      : null;

  return (
    <div className="rounded-lg border border-border bg-surface">
      {/* Header with controls */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-3">
        <div className="flex items-center gap-3">
          <h2 className="text-sm font-bold text-white">Footprint Chart</h2>

          {/* Asset selector */}
          <select
            value={asset}
            onChange={(e) => setAsset(e.target.value)}
            className="rounded border border-border bg-background px-2 py-1 text-xs text-white focus:outline-none focus:ring-1 focus:ring-accent"
            aria-label="Select asset"
          >
            {ASSETS.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>

          {/* Timeframe selector */}
          <div className="flex gap-1">
            {TIMEFRAMES.map((tf) => (
              <button
                key={tf}
                onClick={() => setTimeframe(tf)}
                className={`rounded px-2 py-1 text-xs font-medium transition-colors ${
                  timeframe === tf
                    ? "bg-accent/20 text-accent"
                    : "text-gray-400 hover:bg-background hover:text-white"
                }`}
                aria-label={`Set timeframe to ${tf}`}
              >
                {tf}
              </button>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-4">
          {/* Cumulative delta */}
          {data && (
            <div className="flex items-center gap-2">
              <span className="text-xs text-gray-400">Cum. Delta:</span>
              <span
                className={`text-sm font-bold font-mono ${
                  data.cumulative_delta >= 0
                    ? "text-bullish"
                    : "text-bearish"
                }`}
              >
                {data.cumulative_delta >= 0 ? "+" : ""}
                {formatNumber(data.cumulative_delta)}
              </span>
            </div>
          )}

          {/* Current price */}
          {data && (
            <div className="flex items-center gap-2">
              <span className="text-xs text-gray-400">Price:</span>
              <span className="text-sm font-bold font-mono text-white">
                ${formatPrice(data.current_price)}
              </span>
            </div>
          )}

          {/* Zoom info */}
          <span className="text-[10px] text-gray-500">
            Scroll: wheel | Zoom: Ctrl+wheel
          </span>
        </div>
      </div>

      {/* Canvas area */}
      <div
        ref={containerRef}
        className="relative"
        style={{ height: "480px" }}
      >
        {loading && !data && (
          <div className="flex h-full items-center justify-center">
            <div className="flex items-center gap-2 text-sm text-gray-400">
              <svg
                className="h-4 w-4 animate-spin"
                viewBox="0 0 24 24"
                fill="none"
                aria-hidden="true"
              >
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                />
              </svg>
              Loading order flow data...
            </div>
          </div>
        )}

        {error && !data && (
          <div className="flex h-full items-center justify-center">
            <p className="text-sm text-bearish">{error}</p>
          </div>
        )}

        {data && (
          <canvas
            ref={canvasRef}
            className="h-full w-full cursor-crosshair"
            onWheel={handleWheel}
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            onMouseLeave={handleMouseLeave}
            aria-label="Footprint chart canvas showing order flow data with bid and ask volumes at each price level"
          />
        )}

        {/* Tooltip */}
        {tooltip && (
          <div
            className="pointer-events-none absolute z-10 rounded border border-border bg-background px-3 py-2 text-xs shadow-lg"
            style={{
              left: Math.min(
                tooltip.x + 12,
                (containerRef.current?.clientWidth ?? 300) - 180,
              ),
              top: Math.min(
                tooltip.y + 12,
                (containerRef.current?.clientHeight ?? 300) - 120,
              ),
            }}
          >
            <div className="mb-1 font-bold text-white">
              ${formatPrice(tooltip.cluster.price)}
            </div>
            <div className="flex items-center gap-2">
              <span className="text-[#ff6b6b]">
                Bid: {formatNumber(tooltip.cluster.bid_vol)}
              </span>
              <span className="text-[#51cf66]">
                Ask: {formatNumber(tooltip.cluster.ask_vol)}
              </span>
            </div>
            <div className="mt-1 text-gray-400">
              Delta:{" "}
              <span
                className={
                  tooltip.cluster.delta >= 0
                    ? "text-bullish"
                    : "text-bearish"
                }
              >
                {tooltip.cluster.delta >= 0 ? "+" : ""}
                {formatNumber(tooltip.cluster.delta)}
              </span>
            </div>
            <div className="text-gray-400">
              Trades: {tooltip.cluster.trades.toLocaleString()}
            </div>
            {tooltip.cluster.imbalance && (
              <div
                className={`mt-1 font-bold ${
                  tooltip.cluster.imbalance === "BUY"
                    ? "text-bullish"
                    : "text-bearish"
                }`}
              >
                {tooltip.cluster.imbalance} IMBALANCE
              </div>
            )}
          </div>
        )}
      </div>

      {/* Imbalance summary bar */}
      {imbalanceSummary && (
        <div className="flex items-center gap-4 border-t border-border px-4 py-2">
          <span className="text-xs text-gray-400">Imbalances:</span>
          <span className="flex items-center gap-1 text-xs">
            <span
              className="inline-block h-2 w-2 rounded-full"
              style={{ backgroundColor: IMBALANCE_BUY_COLOR }}
            />
            <span className="text-bullish font-mono">
              {imbalanceSummary.buyCount} BUY
            </span>
          </span>
          <span className="flex items-center gap-1 text-xs">
            <span
              className="inline-block h-2 w-2 rounded-full"
              style={{ backgroundColor: IMBALANCE_SELL_COLOR }}
            />
            <span className="text-bearish font-mono">
              {imbalanceSummary.sellCount} SELL
            </span>
          </span>
        </div>
      )}
    </div>
  );
}
