/**
 * Portfolio P&L Heatmap
 * Tile grid — one tile per open position, colored by unrealized P&L.
 * Tile size proportional to position age (larger = longer held).
 */

import { useQuery } from "@tanstack/react-query";
import { fetchOpenPositions } from "../../api/client";
import type { SimulatedPosition } from "../../api/client";
import { fmtPct, fmtPrice } from "../../lib/format";

function pnlColor(pnl: number): string {
  if (pnl >= 5) return "bg-bullish/80 border-bullish";
  if (pnl >= 2) return "bg-bullish/50 border-bullish/60";
  if (pnl >= 0.5) return "bg-bullish/30 border-bullish/40";
  if (pnl >= -0.5) return "bg-gray-700/60 border-border";
  if (pnl >= -2) return "bg-bearish/30 border-bearish/40";
  if (pnl >= -5) return "bg-bearish/50 border-bearish/60";
  return "bg-bearish/80 border-bearish";
}

function pnlText(pnl: number): string {
  if (pnl >= 2) return "text-white font-bold";
  if (pnl <= -2) return "text-white font-bold";
  return "text-gray-200";
}

function PositionTile({ pos }: { pos: SimulatedPosition }) {
  const pnl = pos.pnl_pct ?? 0;
  const ageHours = (Date.now() - new Date(pos.opened_at).getTime()) / 3_600_000;
  // Tile grows from 80px to 160px based on age (max 24h)
  const sizePx = Math.round(80 + Math.min(ageHours / 24, 1) * 80);

  return (
    <div
      className={`flex flex-col items-center justify-center rounded border p-2 transition-all ${pnlColor(pnl)}`}
      style={{ width: sizePx, height: sizePx, minWidth: 80, minHeight: 80 }}
      role="gridcell"
      aria-label={`${pos.symbol} ${pos.direction} P&L ${fmtPct(pnl, { showSign: true })}`}
      title={`Entry: ${fmtPrice(pos.entry_price)} | Current: ${fmtPrice(pos.current_price)}`}
    >
      <span className="truncate text-center text-[10px] text-gray-400">
        {pos.symbol.replace("USDT", "")}
      </span>
      <span className={`font-mono text-sm ${pnlText(pnl)}`}>
        {fmtPct(pnl, { showSign: true, decimals: 1 })}
      </span>
      <span className="text-[9px] text-gray-500">
        {pos.direction === "LONG" ? "▲" : "▼"} {pos.strategy?.slice(0, 6)}
      </span>
    </div>
  );
}

function PnLLegend() {
  const steps = [
    { color: "bg-bearish/80", label: "<−5%" },
    { color: "bg-bearish/50", label: "−2%" },
    { color: "bg-gray-700/60", label: "~0%" },
    { color: "bg-bullish/30", label: "+0.5%" },
    { color: "bg-bullish/80", label: ">+5%" },
  ];
  return (
    <div className="flex items-center gap-1.5 text-[10px] text-gray-500" aria-label="P&L color legend">
      <span>P&L:</span>
      {steps.map(({ color, label }) => (
        <div key={label} className="flex items-center gap-1">
          <div className={`h-3 w-3 rounded-sm ${color}`} aria-hidden="true" />
          <span>{label}</span>
        </div>
      ))}
    </div>
  );
}

export function PortfolioPnLHeatmap() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["open-positions-heatmap"],
    queryFn: fetchOpenPositions,
    refetchInterval: 15_000,
    retry: false,
  });

  const positions = data?.positions ?? [];
  const totalPnL = positions.reduce((s, p) => s + (p.pnl_pct ?? 0), 0);
  const winners = positions.filter((p) => (p.pnl_pct ?? 0) > 0).length;

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-white">Portfolio P&L Heatmap</h2>
        {positions.length > 0 && (
          <div className="flex items-center gap-3 text-xs">
            <span className="text-gray-500">
              {winners}/{positions.length} winning
            </span>
            <span className={`font-mono font-bold ${totalPnL >= 0 ? "text-bullish" : "text-bearish"}`}>
              Σ {fmtPct(totalPnL, { showSign: true })}
            </span>
          </div>
        )}
      </div>

      {isError && (
        <p className="mb-3 text-xs text-bearish">Unable to load positions</p>
      )}

      {isLoading && (
        <div className="flex flex-wrap gap-2">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-20 w-20 animate-pulse rounded bg-white/5" />
          ))}
        </div>
      )}

      {!isLoading && positions.length === 0 && (
        <div className="flex flex-col items-center justify-center py-8 text-gray-600">
          <svg className="mb-2 h-8 w-8 opacity-40" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
              d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z"
            />
          </svg>
          <p className="text-sm">No open positions</p>
          <p className="text-xs">Start the bot to see live positions here</p>
        </div>
      )}

      {!isLoading && positions.length > 0 && (
        <div
          className="flex flex-wrap gap-2"
          role="grid"
          aria-label={`${positions.length} open positions`}
        >
          {positions.map((pos) => (
            <PositionTile key={pos.id} pos={pos} />
          ))}
        </div>
      )}

      {positions.length > 0 && (
        <div className="mt-3">
          <PnLLegend />
          <p className="mt-1 text-[9px] text-gray-600">
            Tile size proportional to position age. Hover for entry/current price.
          </p>
        </div>
      )}
    </div>
  );
}
