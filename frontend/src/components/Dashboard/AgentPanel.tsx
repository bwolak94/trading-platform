import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchAgentSignals,
  fetchAgentStatus,
  fetchLearningData,
  startAgent,
  stopAgent,
} from "../../api/client";
import type { AgentSignal } from "../../api/client";
import { DayTradeHUD } from "./DayTradeHUD";
import { EquityCurve } from "./EquityCurve";
import { StrategyStats } from "./StrategyStats";

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

// --------------- Alpha Freshness helpers ---------------

/** Returns a Tailwind bar color class based on freshness score 0-100. */
function getFreshnessBarColor(freshness: number): string {
  if (freshness >= 75) return "bg-green-500";
  if (freshness >= 25) return "bg-amber-500";
  return "bg-red-500";
}

/** Returns a Tailwind text color class based on freshness score 0-100. */
function getFreshnessTextColor(freshness: number): string {
  if (freshness >= 75) return "text-green-400";
  if (freshness >= 25) return "text-amber-400";
  return "text-red-400";
}

/** Returns a human-readable freshness label. */
function getFreshnessLabel(freshness: number): string {
  if (freshness >= 75) return "Fresh";
  if (freshness >= 25) return "Aging";
  return "Stale";
}

/**
 * Compute freshness (0-100) from a signal timestamp ISO string.
 * < 2h   → 100..75 range  (Fresh)
 * 2-8h   → 75..25 range   (Aging)
 * > 8h   → < 25           (Stale, approaches 0 at 16h+)
 */
function computeFreshnessFromTimestamp(timestamp: string): number {
  const ageMs = Date.now() - new Date(timestamp).getTime();
  const ageHours = ageMs / 3_600_000;
  if (ageHours < 2) return Math.round(100 - (ageHours / 2) * 25); // 100 → 75
  if (ageHours < 8) return Math.round(75 - ((ageHours - 2) / 6) * 50); // 75 → 25
  return Math.max(0, Math.round(25 - ((ageHours - 8) / 8) * 25)); // 25 → 0
}

// --------------- Alpha decay endpoint types ---------------

interface AlphaDecayEntry {
  strategy: string;
  signal_age_hours: number;
  freshness: number;
}

interface AlphaDecayResponse {
  strategies: AlphaDecayEntry[];
}

// --------------- AlphaFreshnessPanel ---------------

interface StrategyFreshness {
  name: string;
  freshness: number;
}

interface AlphaFreshnessPanelProps {
  /** Fallback: derive freshness from live signals if endpoint unavailable */
  signalEntries: [string, AgentSignal][];
}

function AlphaFreshnessPanel({ signalEntries }: AlphaFreshnessPanelProps) {
  const { data, isError } = useQuery<AlphaDecayResponse>({
    queryKey: ["alpha-decay"],
    queryFn: async () => {
      const res = await fetch("/api/v1/analytics/alpha-decay");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json() as Promise<AlphaDecayResponse>;
    },
    retry: false,
    staleTime: 30_000,
    refetchInterval: 60_000,
  });

  // Build strategy list: prefer API data, fall back to computing from signal timestamps
  const strategies: StrategyFreshness[] = (() => {
    if (data?.strategies && data.strategies.length > 0) {
      return data.strategies.map((s) => ({
        name: s.strategy,
        freshness: s.freshness,
      }));
    }
    if (isError || !data) {
      // Derive from signal timestamps grouped by strategy name
      const byStrategy = new Map<string, number[]>();
      for (const [, sig] of signalEntries) {
        const key = sig.strategy_name ?? "Unknown";
        const freshness = computeFreshnessFromTimestamp(sig.timestamp);
        const existing = byStrategy.get(key) ?? [];
        byStrategy.set(key, [...existing, freshness]);
      }
      return [...byStrategy.entries()].map(([name, values]) => ({
        name,
        freshness: Math.round(values.reduce((a, b) => a + b, 0) / values.length),
      }));
    }
    return [];
  })();

  if (strategies.length === 0) return null;

  return (
    <div className="mt-3 rounded-lg border border-border bg-surface p-3">
      <h4 className="text-xs font-medium text-gray-400 mb-2">Alpha Freshness</h4>
      <div className="space-y-1.5" role="list" aria-label="Strategy freshness indicators">
        {strategies.map((s) => (
          <div
            key={s.name}
            className="flex items-center justify-between"
            role="listitem"
          >
            <span className="text-xs text-gray-300 truncate max-w-[120px]" title={s.name}>
              {s.name}
            </span>
            <div className="flex items-center gap-2 ml-2">
              <div
                className="w-20 h-1.5 bg-surface rounded-full overflow-hidden"
                role="progressbar"
                aria-valuenow={s.freshness}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label={`${s.name} freshness: ${s.freshness}%`}
              >
                <div
                  className={`h-full rounded-full transition-all duration-500 ${getFreshnessBarColor(s.freshness)}`}
                  style={{ width: `${s.freshness}%` }}
                />
              </div>
              <span className={`text-xs font-medium min-w-[32px] text-right ${getFreshnessTextColor(s.freshness)}`}>
                {getFreshnessLabel(s.freshness)}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// --------------- Sub-components ---------------

function StatusHeader() {
  const queryClient = useQueryClient();

  const { data: status } = useQuery({
    queryKey: ["agent-status"],
    queryFn: fetchAgentStatus,
    refetchInterval: 10_000,
  });

  const startMutation = useMutation({
    mutationFn: startAgent,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["agent-status"] });
    },
  });

  const stopMutation = useMutation({
    mutationFn: stopAgent,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["agent-status"] });
    },
  });

  const running = status?.running ?? false;
  const busy = startMutation.isPending || stopMutation.isPending;

  return (
    <div className="flex flex-wrap items-center justify-between gap-4 rounded-lg border border-border bg-surface p-4">
      <div className="flex items-center gap-3">
        <span
          className={`inline-block h-3 w-3 rounded-full ${running ? "bg-green-500 shadow-[0_0_6px_rgba(34,197,94,0.6)]" : "bg-red-500"}`}
          aria-label={running ? "Agent is running" : "Agent is stopped"}
        />
        <span className="text-lg font-semibold text-white">
          AI Agent — {running ? "Running" : "Stopped"}
        </span>
      </div>

      <div className="flex items-center gap-6 text-sm text-gray-400">
        <span>Scans: {status?.scan_count ?? 0}</span>
        <span>Last scan: {status?.last_scan ? formatTime(status.last_scan) : "N/A"}</span>
        <span>Active signals: {status?.active_signals ?? 0}</span>
      </div>

      <button
        onClick={() => { running ? stopMutation.mutate() : startMutation.mutate(); }}
        disabled={busy}
        aria-label={running ? "Stop the AI agent" : "Start the AI agent"}
        className={`rounded px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50 ${
          running
            ? "bg-red-600 text-white hover:bg-red-700"
            : "bg-green-600 text-white hover:bg-green-700"
        }`}
      >
        {busy ? "..." : running ? "Stop Agent" : "Start Agent"}
      </button>
    </div>
  );
}

// --------------- RR Visualization ---------------

function RiskRewardViz({ signal }: { signal: AgentSignal }) {
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
      style={{ height: 180 }}
      aria-label="Risk/Reward visualization"
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
              borderTop: `1px solid ${tp.border_color || "#22c55e"}`,
              borderBottom: `1px solid ${tp.border_color || "#22c55e"}`,
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
          borderTop: `1px solid ${ui_elements.sl_box.border_color || "#ef4444"}`,
          borderBottom: `1px solid ${ui_elements.sl_box.border_color || "#ef4444"}`,
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
            borderColor: ui_elements.be_line.color || "#9ca3af",
          }}
        >
          <span>{ui_elements.be_line.label} ${formatNumber(ui_elements.be_line.price)}</span>
        </div>
      )}
    </div>
  );
}

// --------------- Signal Card ---------------

function SignalCard({ symbol, signal }: { symbol: string; signal: AgentSignal }) {
  const isLong = signal.action === "LONG";
  const dirColor = isLong ? "bg-green-600" : signal.action === "SHORT" ? "bg-red-600" : "bg-gray-600";

  return (
    <div className="rounded-lg border border-border bg-surface p-4" aria-label={`Signal card for ${symbol}`}>
      {/* Header */}
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-lg font-bold text-white">{symbol}</span>
          <span className={`rounded px-2 py-0.5 text-xs font-semibold text-white ${dirColor}`}>
            {signal.action}
          </span>
        </div>
        <span className="rounded bg-[#1f2937] px-2 py-0.5 text-xs text-gray-300">
          {signal.strategy_name}
        </span>
      </div>

      {/* Confidence bar */}
      <div className="mb-3">
        <div className="mb-1 flex items-center justify-between text-xs text-gray-400">
          <span>Confidence</span>
          <span>{(signal.confidence * 100).toFixed(1)}%</span>
        </div>
        <div className="h-2 w-full overflow-hidden rounded-full bg-[#1f2937]" aria-label={`Confidence ${(signal.confidence * 100).toFixed(1)} percent`}>
          <div
            className="h-full rounded-full bg-blue-500 transition-all"
            style={{ width: `${signal.confidence * 100}%` }}
          />
        </div>
      </div>

      {/* Price levels grid */}
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
        <div className="text-gray-400">R/R</div>
        <div className="text-right text-white">{signal.risk_reward.toFixed(2)}</div>
      </div>

      {/* Regime badge */}
      <div className="mb-3 flex items-center gap-2">
        <span className="rounded bg-purple-900/50 px-2 py-0.5 text-xs text-purple-300">
          {signal.regime}
        </span>
      </div>

      {/* Readiness + conditions */}
      <div className="mb-3">
        <div className="mb-1 flex items-center justify-between text-xs text-gray-400">
          <span>Readiness</span>
          <span>{(signal.readiness * 100).toFixed(0)}%</span>
        </div>
        <div className="h-2 w-full overflow-hidden rounded-full bg-[#1f2937]" aria-label={`Readiness ${(signal.readiness * 100).toFixed(0)} percent`}>
          <div
            className="h-full rounded-full bg-amber-500 transition-all"
            style={{ width: `${signal.readiness * 100}%` }}
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
      <RiskRewardViz signal={signal} />

      {/* Reasoning */}
      <p className="mt-3 text-xs leading-relaxed text-gray-400">{signal.reasoning}</p>

      {/* Timestamp */}
      <div className="mt-2 text-right text-[10px] text-gray-500">
        {formatTime(signal.timestamp)}
      </div>
    </div>
  );
}

// --------------- Performance Stats ---------------

function PerformanceStats() {
  const { data: status } = useQuery({
    queryKey: ["agent-status"],
    queryFn: fetchAgentStatus,
    refetchInterval: 10_000,
  });

  if (!status) return null;

  const stats = [
    { label: "Total Trades", value: formatNumber(status.total_trades) },
    { label: "Wins", value: formatNumber(status.wins) },
    { label: "Losses", value: formatNumber(status.losses) },
    { label: "Win Rate", value: `${(status.win_rate * 100).toFixed(1)}%` },
    { label: "Total Reward", value: `${status.total_reward >= 0 ? "+" : ""}${formatNumber(status.total_reward)}R` },
    { label: "Avg Reward", value: `${status.avg_reward >= 0 ? "+" : ""}${status.avg_reward.toFixed(2)}R` },
  ];

  return (
    <div className="rounded-lg border border-border bg-surface p-4" aria-label="Performance statistics">
      <h3 className="mb-3 text-sm font-semibold text-white">Performance</h3>
      <div className="grid grid-cols-3 gap-4 sm:grid-cols-6">
        {stats.map((s) => (
          <div key={s.label} className="text-center">
            <div className="text-lg font-bold text-white">{s.value}</div>
            <div className="text-[11px] text-gray-400">{s.label}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

// --------------- Learning Log ---------------

function LearningLog() {
  const { data: status } = useQuery({
    queryKey: ["agent-status"],
    queryFn: fetchAgentStatus,
    refetchInterval: 10_000,
  });

  const lessons = status?.recent_lessons ?? [];

  return (
    <div className="rounded-lg border border-border bg-surface p-4" aria-label="Learning log">
      <h3 className="mb-3 text-sm font-semibold text-white">Recent Lessons</h3>
      {lessons.length === 0 ? (
        <p className="text-xs text-gray-500">No lessons yet.</p>
      ) : (
        <ul className="max-h-40 space-y-2 overflow-y-auto pr-1">
          {lessons.slice(0, 5).map((lesson, i) => (
            <li key={i} className="rounded bg-[#161b22] px-3 py-2 text-xs leading-relaxed text-gray-300">
              {lesson}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// --------------- Main Panel ---------------

function LearningDashboard() {
  const { data: learning } = useQuery({
    queryKey: ["learning-data"],
    queryFn: fetchLearningData,
    refetchInterval: 15_000,
  });

  if (!learning) return null;

  const perf = learning.strategy_performance;
  const blocked = Object.entries(learning.blocked_combos);

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h3 className="mb-3 text-sm font-semibold text-white">AI Learning Dashboard</h3>

      {/* Best strategy per regime */}
      <div className="mb-3 flex flex-wrap gap-2">
        {Object.entries(learning.best_by_regime).map(([regime, strat]) => (
          <div key={regime} className="rounded bg-background px-2 py-1 text-xs">
            <span className="text-gray-500">{regime}: </span>
            <span className={strat ? "text-bullish font-semibold" : "text-gray-600"}>{strat ?? "No data"}</span>
          </div>
        ))}
      </div>

      {/* Confidence multipliers */}
      <div className="mb-3">
        <span className="mb-1 block text-xs text-gray-500">Confidence Multipliers (Learned)</span>
        <div className="flex flex-wrap gap-2">
          {Object.entries(learning.confidence_multipliers).map(([strat, mult]) => (
            <span key={strat} className={`rounded px-2 py-0.5 text-xs font-mono ${
              mult > 1.1 ? "bg-bullish/20 text-bullish" : mult < 0.8 ? "bg-bearish/20 text-bearish" : "bg-background text-gray-400"
            }`}>
              {strat}: {mult}x
            </span>
          ))}
        </div>
      </div>

      {/* Blocked combos */}
      {blocked.length > 0 && (
        <div className="mb-3">
          <span className="mb-1 block text-xs text-bearish">Blocked (Learning Penalty)</span>
          {blocked.map(([combo, until]) => (
            <div key={combo} className="rounded bg-bearish/10 px-2 py-1 text-xs text-bearish">
              {combo} — until {new Date(until).toLocaleTimeString()}
            </div>
          ))}
        </div>
      )}

      {/* Strategy performance table */}
      {perf.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="text-gray-500">
              <tr>
                <th className="pb-1 pr-3">Strategy</th>
                <th className="pb-1 pr-3">Regime</th>
                <th className="pb-1 pr-2">W</th>
                <th className="pb-1 pr-2">L</th>
                <th className="pb-1 pr-3">WR%</th>
                <th className="pb-1 pr-3">PnL%</th>
                <th className="pb-1 pr-3">Mult</th>
                <th className="pb-1">Status</th>
              </tr>
            </thead>
            <tbody>
              {perf.map((p, i) => (
                <tr key={i} className="border-t border-border">
                  <td className="py-1 pr-3 text-white">{p.strategy}</td>
                  <td className="py-1 pr-3 text-gray-400">{p.regime}</td>
                  <td className="py-1 pr-2 text-bullish">{p.wins}</td>
                  <td className="py-1 pr-2 text-bearish">{p.losses}</td>
                  <td className={`py-1 pr-3 font-mono ${p.win_rate >= 50 ? "text-bullish" : "text-bearish"}`}>{p.win_rate}%</td>
                  <td className={`py-1 pr-3 font-mono ${p.total_pnl >= 0 ? "text-bullish" : "text-bearish"}`}>{p.total_pnl > 0 ? "+" : ""}{p.total_pnl}%</td>
                  <td className={`py-1 pr-3 font-mono ${p.confidence_multiplier > 1 ? "text-bullish" : p.confidence_multiplier < 0.8 ? "text-bearish" : "text-gray-400"}`}>{p.confidence_multiplier}x</td>
                  <td className="py-1">{p.blocked ? <span className="text-bearish">BLOCKED</span> : <span className="text-gray-500">OK</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {perf.length === 0 && <p className="text-xs text-gray-500">No trades completed yet — learning data will appear after trades close.</p>}
    </div>
  );
}

export function AgentPanel() {
  const { data: signals } = useQuery({
    queryKey: ["agent-signals"],
    queryFn: fetchAgentSignals,
    refetchInterval: 10_000,
  });

  const entries: [string, AgentSignal][] = signals ? Object.entries(signals) : [];

  return (
    <div className="space-y-6">
      {/* === Swing Trading Section === */}
      <h2 className="text-lg font-bold text-white border-b border-border pb-2">Swing Trading Agent (4H)</h2>
      <StatusHeader />
      <PerformanceStats />

      <div>
        <h3 className="mb-3 text-sm font-semibold text-white">Swing Trade Signals</h3>
        {entries.length === 0 ? (
          <p className="rounded-lg border border-border bg-surface p-6 text-center text-sm text-gray-500">
            No active swing signals.
          </p>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {entries.map(([sym, sig]) => (
              <SignalCard key={sym} symbol={sym} signal={sig} />
            ))}
          </div>
        )}
      </div>

      {/* Alpha Freshness */}
      <AlphaFreshnessPanel signalEntries={entries} />

      <LearningLog />

      {/* === Day Trading Section === */}
      <h2 className="text-lg font-bold text-white border-b border-border pb-2 mt-8">Day Trading Agent (M1/M5/M15)</h2>
      <DayTradeHUD />

      {/* === AI Learning Dashboard === */}
      <h2 className="text-lg font-bold text-white border-b border-border pb-2 mt-8">AI Learning Engine</h2>
      <LearningDashboard />

      {/* === Equity Curve === */}
      <h2 className="text-lg font-bold text-white border-b border-border pb-2 mt-8">Equity Curve</h2>
      <EquityCurve />

      {/* === Strategy Performance Stats === */}
      <h2 className="text-lg font-bold text-white border-b border-border pb-2 mt-8">Strategy Performance</h2>
      <StrategyStats />
    </div>
  );
}
