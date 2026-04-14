import { useQuery } from "@tanstack/react-query";
import {
  fetchDayTradeSignals,
  fetchDayTradeStatus,
} from "../../api/client";
import type { DayTradeSignal } from "../../api/client";

function formatNumber(n: number): string {
  return n.toLocaleString("en-US", { maximumFractionDigits: 2 });
}

function formatTime(iso: string): string {
  if (!iso) return "N/A";
  const d = new Date(iso);
  return d.toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

const STRATEGY_COLORS: Record<string, string> = {
  liquidity_sweep: "bg-orange-600",
  ob_bounce: "bg-blue-600",
  vwap_reversion: "bg-purple-600",
  delta_divergence: "bg-cyan-600",
};

// --------------- Status Bar ---------------

function DayTradeStatusBar() {
  const { data: status } = useQuery({
    queryKey: ["day-trade-status"],
    queryFn: fetchDayTradeStatus,
    refetchInterval: 10_000,
  });

  const running = (status?.running as boolean) ?? false;
  const scanCount = (status?.scan_count as number) ?? 0;
  const lastScan = (status?.last_scan as string) ?? "";
  const activeSignals = (status?.active_signals as number) ?? 0;
  const blocked = (status?.blocked_symbols as Record<string, string>) ?? {};
  const blockedKeys = Object.keys(blocked);

  return (
    <div
      className="flex flex-wrap items-center justify-between gap-4 rounded-lg border border-border bg-surface p-3"
      aria-label="Day trading engine status"
    >
      <div className="flex items-center gap-3">
        <span
          className={`inline-block h-2.5 w-2.5 rounded-full ${running ? "bg-green-500 shadow-[0_0_6px_rgba(34,197,94,0.6)]" : "bg-red-500"}`}
          aria-label={running ? "Day trading engine running" : "Day trading engine stopped"}
        />
        <span className="text-sm font-semibold text-white">
          Day Trade Scanner — {running ? "Active" : "Inactive"}
        </span>
      </div>

      <div className="flex items-center gap-5 text-xs text-gray-400">
        <span>Scans: {scanCount}</span>
        <span>Last: {lastScan ? formatTime(lastScan) : "N/A"}</span>
        <span>Active: {activeSignals}</span>
        {blockedKeys.length > 0 && (
          <span className="text-yellow-400">
            Blocked: {blockedKeys.join(", ")}
          </span>
        )}
      </div>
    </div>
  );
}

// --------------- RR Visualization ---------------

function DayTradeRRViz({ signal }: { signal: DayTradeSignal }) {
  const { entry, stop_loss, tp_levels, ui_elements } = signal;
  const allPrices = [entry, stop_loss, ...tp_levels];
  const maxPrice = Math.max(...allPrices);
  const minPrice = Math.min(...allPrices);
  const range = maxPrice - minPrice || 1;

  const priceToPct = (p: number) => ((maxPrice - p) / range) * 100;

  const entryPct = priceToPct(entry);
  const slPct = priceToPct(stop_loss);
  const slTop = Math.min(entryPct, slPct);
  const slHeight = Math.abs(slPct - entryPct);

  return (
    <div
      className="relative w-full rounded border border-border bg-[#161b22]"
      style={{ height: 160 }}
      aria-label="Day trade risk/reward visualization"
    >
      {/* TP zones */}
      {ui_elements.tp_boxes.map((tp, i) => {
        const top = priceToPct(tp.price_top);
        const bottom = priceToPct(tp.price_bottom);
        return (
          <div
            key={i}
            className="absolute left-0 right-0 flex items-center justify-between px-2 text-[10px] text-white"
            style={{
              top: `${Math.min(top, bottom)}%`,
              height: `${Math.abs(bottom - top)}%`,
              backgroundColor: tp.color || "rgba(34,197,94,0.25)",
              borderTop: "1px solid #00d4aa",
              borderBottom: "1px solid #00d4aa",
            }}
          >
            <span>{tp.label}</span>
            <span>${formatNumber(tp.price_top)}</span>
          </div>
        );
      })}

      {/* SL zone */}
      <div
        className="absolute left-0 right-0 flex items-center justify-between px-2 text-[10px] text-white"
        style={{
          top: `${slTop}%`,
          height: `${slHeight}%`,
          backgroundColor: ui_elements.sl_box.color || "rgba(239,68,68,0.25)",
          borderTop: "1px solid #ff4757",
          borderBottom: "1px solid #ff4757",
        }}
      >
        <span>{ui_elements.sl_box.label}</span>
        <span>${formatNumber(stop_loss)}</span>
      </div>

      {/* Entry line */}
      <div
        className="absolute left-0 right-0 flex items-center justify-between px-2 text-[10px] font-bold text-yellow-300"
        style={{
          top: `${entryPct}%`,
          height: 2,
          backgroundColor: ui_elements.entry_line.color || "#eab308",
        }}
      >
        <span>{ui_elements.entry_line.label}</span>
        <span>${formatNumber(entry)}</span>
      </div>

      {/* BE line */}
      {ui_elements.be_line.price > 0 && (
        <div
          className="absolute left-0 right-0 border-t border-dashed px-2 text-[10px] text-gray-300"
          style={{
            top: `${priceToPct(ui_elements.be_line.price)}%`,
            borderColor: ui_elements.be_line.color || "#3b82f6",
          }}
        >
          <span>{ui_elements.be_line.label} ${formatNumber(ui_elements.be_line.price)}</span>
        </div>
      )}

      {/* VWAP line */}
      <div
        className="absolute left-0 right-0 border-t border-dashed px-2 text-[10px] text-purple-300"
        style={{
          top: `${priceToPct(ui_elements.vwap_line.price)}%`,
          borderColor: "#a855f7",
        }}
      >
        <span>{ui_elements.vwap_line.label}</span>
      </div>
    </div>
  );
}

// --------------- Signal Card ---------------

function DayTradeCard({ symbol, signal }: { symbol: string; signal: DayTradeSignal }) {
  const isLong = signal.action === "LONG";
  const dirColor = isLong ? "bg-green-600" : signal.action === "SHORT" ? "bg-red-600" : "bg-gray-600";
  const stratBg = STRATEGY_COLORS[signal.strategy_type] ?? "bg-gray-600";

  return (
    <div
      className="rounded-lg border border-border bg-surface p-4"
      aria-label={`Day trade signal card for ${symbol}`}
    >
      {/* Header */}
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-lg font-bold text-white">{symbol}</span>
          <span className={`rounded px-2 py-0.5 text-xs font-semibold text-white ${dirColor}`}>
            {signal.action}
          </span>
          <span className="rounded bg-[#1f2937] px-2 py-0.5 text-[10px] text-gray-300">
            {signal.confidence}%
          </span>
          <span className="rounded bg-[#1f2937] px-2 py-0.5 text-[10px] text-gray-300">
            ~{signal.hold_time_minutes}m
          </span>
        </div>
        <span className={`rounded px-2 py-0.5 text-[10px] font-semibold text-white ${stratBg}`}>
          {signal.strategy_type.replace(/_/g, " ")}
        </span>
      </div>

      {/* Confidence bar */}
      <div className="mb-3">
        <div className="mb-1 flex items-center justify-between text-xs text-gray-400">
          <span>Confidence</span>
          <span>{signal.confidence}%</span>
        </div>
        <div
          className="h-2 w-full overflow-hidden rounded-full bg-[#1f2937]"
          aria-label={`Confidence ${signal.confidence} percent`}
        >
          <div
            className="h-full rounded-full bg-blue-500 transition-all"
            style={{ width: `${signal.confidence}%` }}
          />
        </div>
      </div>

      {/* Price levels */}
      <div className="mb-3 grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
        <div className="text-gray-400">Entry</div>
        <div className="text-right text-white">${formatNumber(signal.entry)}</div>
        <div className="text-gray-400">Stop Loss</div>
        <div className="text-right text-red-400">${formatNumber(signal.stop_loss)}</div>
        {signal.tp_levels.map((tp, i) => (
          <div key={i} className="contents">
            <div className="text-gray-400">TP{i + 1}</div>
            <div className="text-right text-green-400">${formatNumber(tp)}</div>
          </div>
        ))}
        <div className="text-gray-400">BE Trigger</div>
        <div className="text-right text-blue-400">${formatNumber(signal.be_trigger)}</div>
      </div>

      {/* Session Levels */}
      <div className="mb-3">
        <h4 className="mb-1 text-xs font-semibold text-gray-300">Session Levels</h4>
        <div className="grid grid-cols-2 gap-x-4 gap-y-0.5 text-xs">
          <span className="text-gray-500">VWAP</span>
          <span className="text-right text-purple-300">${formatNumber(signal.session_levels.vwap)}</span>
          <span className="text-gray-500">VWAP Upper</span>
          <span className="text-right text-purple-400">${formatNumber(signal.session_levels.vwap_upper)}</span>
          <span className="text-gray-500">VWAP Lower</span>
          <span className="text-right text-purple-400">${formatNumber(signal.session_levels.vwap_lower)}</span>
          <span className="text-gray-500">PDH</span>
          <span className="text-right text-orange-300">${formatNumber(signal.session_levels.pdh)}</span>
          <span className="text-gray-500">PDL</span>
          <span className="text-right text-orange-300">${formatNumber(signal.session_levels.pdl)}</span>
          <span className="text-gray-500">Session High</span>
          <span className="text-right text-gray-300">${formatNumber(signal.session_levels.session_high)}</span>
          <span className="text-gray-500">Session Low</span>
          <span className="text-right text-gray-300">${formatNumber(signal.session_levels.session_low)}</span>
        </div>
      </div>

      {/* Conditions checklist */}
      <div className="mb-3">
        <div className="mb-1 flex items-center justify-between text-xs text-gray-400">
          <span>Readiness</span>
          <span>{signal.readiness}%</span>
        </div>
        <div
          className="h-2 w-full overflow-hidden rounded-full bg-[#1f2937]"
          aria-label={`Readiness ${signal.readiness} percent`}
        >
          <div
            className="h-full rounded-full bg-amber-500 transition-all"
            style={{ width: `${signal.readiness}%` }}
          />
        </div>
        <ul className="mt-2 space-y-0.5 text-xs" aria-label="Conditions checklist">
          {signal.conditions.map((c, i) => (
            <li key={i} className={c.met ? "text-green-400" : "text-red-400"}>
              {c.met ? "\u2713" : "\u2717"} {c.label}
            </li>
          ))}
        </ul>
      </div>

      {/* RR Visualization */}
      <DayTradeRRViz signal={signal} />

      {/* Reasoning */}
      <p className="mt-3 text-xs leading-relaxed text-gray-400">{signal.reasoning}</p>

      {/* Timestamp */}
      <div className="mt-2 text-right text-[10px] text-gray-500">
        {formatTime(signal.timestamp)}
      </div>
    </div>
  );
}

// --------------- Main HUD ---------------

export function DayTradeHUD() {
  const { data: signals } = useQuery({
    queryKey: ["day-trade-signals"],
    queryFn: fetchDayTradeSignals,
    refetchInterval: 10_000,
  });

  const entries = signals ? Object.entries(signals) : [];

  return (
    <div className="space-y-4" aria-label="Day Trading HUD">
      <DayTradeStatusBar />

      {entries.length === 0 ? (
        <p className="rounded-lg border border-border bg-surface p-6 text-center text-sm text-gray-500">
          No active day trade signals. The engine scans M1/M5/M15 every 30 seconds.
        </p>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {entries.map(([sym, sig]) => (
            <DayTradeCard key={sym} symbol={sym} signal={sig} />
          ))}
        </div>
      )}
    </div>
  );
}
