/**
 * Mobile Essential View — optimized for small screens (< 768px).
 *
 * Shows only the most critical trading information:
 *   - Market regime banner
 *   - Top 3 signals as compact rows
 *   - Portfolio P&L summary
 *
 * Hidden on md+ breakpoints via Tailwind's `md:hidden` class.
 * Rendered only when mobile mode is active or on small viewports.
 */

import type { Signal, MarketRegime, SignalDirection } from "../../types";

// --------------- Helpers ---------------

const REGIME_BG: Record<MarketRegime, string> = {
  TREND_BULL: "bg-bullish/10 border border-bullish/30 text-bullish",
  TREND_BEAR: "bg-bearish/10 border border-bearish/30 text-bearish",
  CONSOLIDATION: "bg-yellow-500/10 border border-yellow-500/30 text-yellow-400",
  HIGH_VOL_CHOPPY: "bg-warning/10 border border-warning/30 text-warning",
};

function getRegimeBg(regime: string): string {
  return REGIME_BG[regime as MarketRegime] ?? "bg-gray-700/20 border border-border text-gray-400";
}

const DIRECTION_COLOR: Record<SignalDirection, string> = {
  LONG: "text-bullish",
  SHORT: "text-bearish",
  NEUTRAL: "text-gray-400",
};

const DIRECTION_ICON: Record<SignalDirection, string> = {
  LONG: "▲",
  SHORT: "▼",
  NEUTRAL: "—",
};

function formatPrice(price: number): string {
  if (price >= 1000) return `$${(price / 1000).toFixed(2)}k`;
  if (price >= 1) return `$${price.toFixed(2)}`;
  return `$${price.toFixed(4)}`;
}

// --------------- MobileSignalRow ---------------

interface MobileSignalRowProps {
  signal: Signal;
}

function MobileSignalRow({ signal }: MobileSignalRowProps) {
  const dirColor = DIRECTION_COLOR[signal.direction] ?? "text-gray-400";
  const dirIcon = DIRECTION_ICON[signal.direction] ?? "—";

  return (
    <div
      className="flex items-center justify-between rounded-lg bg-surface border border-border px-3 py-2.5"
      role="article"
      aria-label={`${signal.asset} ${signal.direction} signal`}
    >
      {/* Asset + direction */}
      <div className="flex items-center gap-2 min-w-0">
        <span className={`text-xs font-bold shrink-0 ${dirColor}`} aria-hidden="true">
          {dirIcon}
        </span>
        <div className="min-w-0">
          <p className="font-mono text-sm font-semibold text-white truncate">{signal.asset}</p>
          <p className={`text-[10px] font-medium ${dirColor}`}>{signal.direction}</p>
        </div>
      </div>

      {/* Entry price */}
      <div className="text-center px-2">
        <p className="text-[10px] text-gray-500">Entry</p>
        <p className="font-mono text-xs text-white">{formatPrice(signal.entry_price)}</p>
      </div>

      {/* Confidence */}
      <div className="text-right shrink-0">
        <p className="text-[10px] text-gray-500">Confidence</p>
        <div className="flex items-center gap-1.5 justify-end">
          <div className="w-12 h-1 bg-background rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full ${signal.direction === "LONG" ? "bg-bullish" : "bg-bearish"}`}
              style={{ width: `${Math.min(signal.confidence, 100)}%` }}
              role="progressbar"
              aria-valuenow={signal.confidence}
              aria-valuemin={0}
              aria-valuemax={100}
            />
          </div>
          <span className={`font-mono text-xs font-bold ${dirColor}`}>
            {signal.confidence.toFixed(0)}%
          </span>
        </div>
      </div>
    </div>
  );
}

// --------------- MobileEssentialViewProps ---------------

interface MobileEssentialViewProps {
  signals: Signal[];
  regime: string;
  /** Portfolio P&L percentage, positive or negative */
  equityPct: number;
}

// --------------- MobileEssentialView ---------------

export function MobileEssentialView({ signals, regime, equityPct }: MobileEssentialViewProps) {
  const topSignals = signals.slice(0, 3);
  const isPositive = equityPct >= 0;

  return (
    <div
      className="flex flex-col gap-3 p-3 md:hidden"
      role="region"
      aria-label="Mobile essential trading view"
    >
      {/* Regime Banner */}
      <div
        className={`rounded-lg p-3 text-center ${getRegimeBg(regime)}`}
        role="status"
        aria-live="polite"
        aria-label={`Current market regime: ${regime.replace(/_/g, " ")}`}
      >
        <p className="text-xs opacity-70 mb-0.5">Market Regime</p>
        <p className="text-base font-bold tracking-wide">{regime.replace(/_/g, " ")}</p>
      </div>

      {/* Top 3 Signals */}
      <section aria-labelledby="mobile-signals-heading">
        <h3
          id="mobile-signals-heading"
          className="text-xs font-medium text-gray-400 mb-2 uppercase tracking-wide"
        >
          Top Signals
        </h3>
        {topSignals.length === 0 ? (
          <p className="text-xs text-gray-500 text-center py-4 rounded-lg border border-border bg-surface">
            No active signals
          </p>
        ) : (
          <div className="space-y-2">
            {topSignals.map((signal) => (
              <MobileSignalRow key={signal.id} signal={signal} />
            ))}
          </div>
        )}
        {signals.length > 3 && (
          <p className="text-[10px] text-gray-500 text-right mt-1">
            +{signals.length - 3} more signal{signals.length - 3 !== 1 ? "s" : ""}
          </p>
        )}
      </section>

      {/* Equity Summary */}
      <div
        className="rounded-lg bg-surface border border-border p-3"
        role="status"
        aria-label={`Portfolio P&L: ${isPositive ? "+" : ""}${equityPct.toFixed(2)} percent`}
      >
        <p className="text-xs text-gray-400 mb-0.5">Portfolio P&L</p>
        <p className={`text-xl font-bold font-mono ${isPositive ? "text-green-400" : "text-red-400"}`}>
          {isPositive ? "+" : ""}
          {equityPct.toFixed(2)}%
        </p>
      </div>
    </div>
  );
}
