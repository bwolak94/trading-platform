import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchAgentSignals,
  fetchAgentStatus,
  startAgent,
  stopAgent,
} from "../../api/client";
import type { AgentSignal } from "../../api/client";
import { DayTradeHUD } from "./DayTradeHUD";

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
        onClick={() => (running ? stopMutation.mutate() : startMutation.mutate())}
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

export function AgentPanel() {
  const { data: signals } = useQuery({
    queryKey: ["agent-signals"],
    queryFn: fetchAgentSignals,
    refetchInterval: 10_000,
  });

  const entries = signals ? Object.entries(signals) : [];

  return (
    <div className="space-y-6">
      <StatusHeader />
      <PerformanceStats />

      {/* Signals grid */}
      <div>
        <h3 className="mb-3 text-sm font-semibold text-white">Active Signals</h3>
        {entries.length === 0 ? (
          <p className="rounded-lg border border-border bg-surface p-6 text-center text-sm text-gray-500">
            No active signals. The agent will generate signals during market scans.
          </p>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {entries.map(([sym, sig]) => (
              <SignalCard key={sym} symbol={sym} signal={sig} />
            ))}
          </div>
        )}
      </div>

      <LearningLog />

      {/* Day Trading HUD */}
      <div className="mt-8">
        <h2 className="mb-4 text-lg font-bold text-white">Day Trading HUD (M1/M5/M15)</h2>
        <DayTradeHUD />
      </div>
    </div>
  );
}
