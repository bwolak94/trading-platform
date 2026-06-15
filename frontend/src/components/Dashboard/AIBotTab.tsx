/**
 * AIBotTab — dedicated tab showing AI paper trading bot performance.
 * Combines agent status, active signals, open positions, equity curve,
 * learning log, and the EnhancedPaperPanel controls in one place.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useMemo, useState } from "react";
import axios from "axios";
import EnhancedPaperPanel from "./EnhancedPaperPanel";
import FuturesTestnetPanel from "./FuturesTestnetPanel";

// ─── Types ────────────────────────────────────────────────────────────────────

interface AgentStatus {
  running: boolean;
  scan_count: number;
  last_scan: string | null;
  active_signals: number;
  total_trades: number;
  wins: number;
  losses: number;
  win_rate: number;
  total_reward: number;
  avg_reward: number;
  recent_lessons: string[];
}

interface SimPerformance {
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number;
  total_pnl_pct: number;
  avg_win_pct: number;
  avg_loss_pct: number;
  profit_factor: number;
  max_drawdown_pct: number;
  sharpe_ratio: number;
  best_trade: number;
  worst_trade: number;
  open_positions: number;
  running_pnl: number;
}

interface SimStatus {
  is_running: boolean;
  session_id: string;
  open_positions: number;
  max_positions: number;
  performance: SimPerformance;
}

interface EquityPoint {
  time: string;
  equity: number;
  pnl_pct: number;
  trade_count: number;
}

interface SimPosition {
  id: string;
  symbol: string;
  direction: "LONG" | "SHORT";
  strategy: string;
  regime: string;
  confidence: number;
  entry_price: number;
  stop_loss: number;
  take_profit_1: number;
  take_profit_2: number | null;
  current_price: number;
  pnl_pct: number;
  leveraged_pnl_pct: number;
  unrealized_pnl_usdt: number;
  leverage: number;
  status: string;
  opened_at: string;
  tp1_hit: boolean;
  trailing_active: boolean;
}

interface AgentSignal {
  symbol: string;
  action: "LONG" | "SHORT";
  entry: number;
  stop_loss: number;
  tp_levels: number[];
  confidence: number;
  reasoning: string;
  strategy_name: string;
  regime: string;
  risk_reward: number;
  readiness: number;
  conditions: { label: string; met: boolean }[];
  timestamp: string;
}

// ─── API ─────────────────────────────────────────────────────────────────────

const fetchAgentStatus = async (): Promise<AgentStatus> =>
  (await axios.get("/api/v1/agent/status")).data;

const fetchSimStatus = async (): Promise<SimStatus> =>
  (await axios.get("/api/v1/simulation/status")).data;

const fetchEquityCurve = async (): Promise<{ equity_curve: EquityPoint[] }> =>
  (await axios.get("/api/v1/simulation/equity-curve")).data;

const fetchPositions = async (): Promise<{ positions: SimPosition[]; count: number }> =>
  (await axios.get("/api/v1/simulation/positions")).data;

const fetchAgentSignals = async (): Promise<Record<string, AgentSignal>> =>
  (await axios.get<{ signals: Record<string, AgentSignal> }>("/api/v1/agent/signals")).data.signals;

// ─── Equity Curve SVG ────────────────────────────────────────────────────────

function EquityCurveChart({ points }: { points: EquityPoint[] }) {
  const W = 800;
  const H = 120;
  const PAD = { top: 12, right: 16, bottom: 20, left: 48 };

  const xs = useMemo(() => {
    if (points.length < 2) return [];
    const inner = W - PAD.left - PAD.right;
    return points.map((_, i) => PAD.left + (i / (points.length - 1)) * inner);
  }, [points]);

  const { minEq, maxEq, ys } = useMemo(() => {
    if (points.length === 0) return { minEq: 100, maxEq: 100, ys: [] };
    const vals = points.map((p) => p.equity);
    const minEq = Math.min(...vals);
    const maxEq = Math.max(...vals);
    const range = maxEq - minEq || 1;
    const inner = H - PAD.top - PAD.bottom;
    const ys = vals.map((v) => PAD.top + inner - ((v - minEq) / range) * inner);
    return { minEq, maxEq, ys };
  }, [points]);

  if (points.length < 2) {
    return (
      <div className="flex h-[120px] items-center justify-center text-xs text-muted-foreground">
        Not enough data yet — close your first trade to see the curve.
      </div>
    );
  }

  const pathD = xs.map((x, i) => `${i === 0 ? "M" : "L"} ${x} ${ys[i]}`).join(" ");
  const areaD = `${pathD} L ${xs[xs.length - 1]} ${H - PAD.bottom} L ${xs[0]} ${H - PAD.bottom} Z`;
  const isUp = points[points.length - 1]!.equity >= points[0]!.equity;
  const color = isUp ? "#00d4aa" : "#ff4757";

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" preserveAspectRatio="none" aria-label="Equity curve">
      <defs>
        <linearGradient id="eqGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.25" />
          <stop offset="100%" stopColor={color} stopOpacity="0.02" />
        </linearGradient>
      </defs>
      {/* Zero baseline */}
      <line
        x1={PAD.left} y1={H - PAD.bottom}
        x2={W - PAD.right} y2={H - PAD.bottom}
        stroke="#ffffff18" strokeWidth="1"
      />
      {/* Area fill */}
      <path d={areaD} fill="url(#eqGrad)" />
      {/* Line */}
      <path d={pathD} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" />
      {/* Last price dot */}
      <circle cx={xs[xs.length - 1]} cy={ys[ys.length - 1]} r="4" fill={color} />
      {/* Min / max labels */}
      <text x={PAD.left - 4} y={PAD.top + 4} fill="#6b7280" fontSize="9" textAnchor="end">{maxEq.toFixed(0)}</text>
      <text x={PAD.left - 4} y={H - PAD.bottom} fill="#6b7280" fontSize="9" textAnchor="end">{minEq.toFixed(0)}</text>
    </svg>
  );
}

// ─── Stat Tile ───────────────────────────────────────────────────────────────

function StatTile({
  label, value, sub, color = "text-white",
}: {
  label: string; value: string; sub?: string; color?: string;
}) {
  return (
    <div className="rounded-lg border border-border/40 bg-surface/60 px-4 py-3">
      <p className="mb-0.5 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">{label}</p>
      <p className={`text-xl font-bold tabular-nums ${color}`}>{value}</p>
      {sub && <p className="mt-0.5 text-[10px] text-muted-foreground">{sub}</p>}
    </div>
  );
}

// ─── Position row ─────────────────────────────────────────────────────────────

function PositionRow({ pos }: { pos: SimPosition }) {
  const isLong = pos.direction === "LONG";
  const pnl = pos.pnl_pct ?? 0;
  const pnlColor = pnl > 0 ? "text-bullish" : pnl < 0 ? "text-bearish" : "text-muted-foreground";
  return (
    <tr className="border-b border-border/20 hover:bg-white/[0.02] transition-colors">
      <td className="py-2 pr-3 text-xs font-medium text-white">{pos.symbol.replace("/", "")}</td>
      <td className="pr-3">
        <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${
          isLong ? "bg-bullish/15 text-bullish" : "bg-bearish/15 text-bearish"
        }`}>
          {pos.direction}
        </span>
      </td>
      <td className="pr-3 text-[10px] text-muted-foreground">{pos.strategy.replace("_", " ")}</td>
      <td className="pr-3 text-[10px] text-muted-foreground">{pos.entry_price.toFixed(4)}</td>
      <td className={`pr-3 text-xs font-semibold tabular-nums ${pnlColor}`}>
        {pnl > 0 ? "+" : ""}{pnl.toFixed(2)}%
      </td>
      <td className="pr-3 text-[10px] text-muted-foreground">{pos.confidence}%</td>
      <td className="text-[10px] text-muted-foreground">{pos.tp1_hit ? "✓ TP1" : pos.trailing_active ? "Trail" : "—"}</td>
    </tr>
  );
}

// ─── Signal Card ─────────────────────────────────────────────────────────────

function SignalCard({ signal }: { signal: AgentSignal }) {
  const isLong = signal.action === "LONG";
  const condMet = signal.conditions.filter((c) => c.met).length;
  const condTotal = signal.conditions.length;
  const readinessPct = condTotal > 0 ? (condMet / condTotal) * 100 : signal.readiness;
  return (
    <div className="rounded-lg border border-border/40 bg-surface/50 p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <span className="text-sm font-semibold text-white">{signal.symbol}</span>
        <span className={`rounded px-2 py-0.5 text-[10px] font-bold ${
          isLong ? "bg-bullish/20 text-bullish" : "bg-bearish/20 text-bearish"
        }`}>
          {signal.action}
        </span>
      </div>
      <div className="mb-2 grid grid-cols-3 gap-1 text-[10px]">
        <div>
          <span className="text-muted-foreground">Entry</span>
          <p className="font-medium text-white">{signal.entry.toLocaleString(undefined, { maximumFractionDigits: 4 })}</p>
        </div>
        <div>
          <span className="text-muted-foreground">SL</span>
          <p className="font-medium text-bearish">{signal.stop_loss.toLocaleString(undefined, { maximumFractionDigits: 4 })}</p>
        </div>
        <div>
          <span className="text-muted-foreground">TP1</span>
          <p className="font-medium text-bullish">
            {signal.tp_levels[0]?.toLocaleString(undefined, { maximumFractionDigits: 4 }) ?? "—"}
          </p>
        </div>
      </div>
      {/* Confidence + readiness bars */}
      <div className="space-y-1">
        <div className="flex items-center gap-2">
          <span className="w-14 shrink-0 text-[9px] text-muted-foreground">Confidence</span>
          <div className="h-1.5 flex-1 rounded-full bg-white/10">
            <div
              className="h-full rounded-full bg-accent"
              style={{ width: `${signal.confidence}%` }}
            />
          </div>
          <span className="w-7 text-right text-[9px] text-muted-foreground">{signal.confidence.toFixed(0)}%</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-14 shrink-0 text-[9px] text-muted-foreground">Readiness</span>
          <div className="h-1.5 flex-1 rounded-full bg-white/10">
            <div
              className={`h-full rounded-full ${readinessPct >= 75 ? "bg-bullish" : readinessPct >= 50 ? "bg-amber-400" : "bg-bearish"}`}
              style={{ width: `${readinessPct}%` }}
            />
          </div>
          <span className="w-7 text-right text-[9px] text-muted-foreground">{condMet}/{condTotal}</span>
        </div>
      </div>
      <p className="mt-2 text-[9px] text-muted-foreground">{signal.strategy_name.replace(/_/g, " ")} · {signal.regime}</p>
    </div>
  );
}

// ─── Inner sub-tabs ──────────────────────────────────────────────────────────

type BotSubTab = "overview" | "positions" | "signals" | "paper" | "testnet";

const SUB_TABS: { id: BotSubTab; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "positions", label: "Open Positions" },
  { id: "signals", label: "AI Signals" },
  { id: "paper", label: "Paper Controls" },
  { id: "testnet", label: "Binance Testnet" },
];

// ─── Main component ──────────────────────────────────────────────────────────

export function AIBotTab() {
  const qc = useQueryClient();
  const [subTab, setSubTab] = useState<BotSubTab>("overview");
  const [posFilter, setPosFilter] = useState<"all" | "LONG" | "SHORT">("all");
  const [posSortKey, setPosSortKey] = useState<"pnl_pct" | "confidence" | "opened_at">("pnl_pct");

  const agentQ = useQuery({ queryKey: ["agent-status"], queryFn: fetchAgentStatus, refetchInterval: 10_000 });
  const simQ = useQuery({ queryKey: ["sim-status"], queryFn: fetchSimStatus, refetchInterval: 10_000 });
  const equityQ = useQuery({ queryKey: ["equity-curve"], queryFn: fetchEquityCurve, refetchInterval: 30_000 });
  const posQ = useQuery({ queryKey: ["sim-positions"], queryFn: fetchPositions, refetchInterval: 15_000 });
  const signalsQ = useQuery({ queryKey: ["agent-signals"], queryFn: fetchAgentSignals, refetchInterval: 15_000 });

  const handleRefreshAll = useCallback(() => {
    void qc.invalidateQueries({ queryKey: ["agent-status"] });
    void qc.invalidateQueries({ queryKey: ["sim-status"] });
    void qc.invalidateQueries({ queryKey: ["equity-curve"] });
    void qc.invalidateQueries({ queryKey: ["sim-positions"] });
    void qc.invalidateQueries({ queryKey: ["agent-signals"] });
  }, [qc]);

  const startMut = useMutation({ mutationFn: () => axios.post("/api/v1/simulation/start"), onSuccess: handleRefreshAll });
  const stopMut = useMutation({ mutationFn: () => axios.post("/api/v1/simulation/stop"), onSuccess: handleRefreshAll });

  const agent = agentQ.data;
  const sim = simQ.data;
  const perf = sim?.performance;
  const equityPts = equityQ.data?.equity_curve ?? [];

  const allPositions = posQ.data?.positions ?? [];
  const filteredPositions = useMemo(() => {
    const base = posFilter === "all" ? allPositions : allPositions.filter((p) => p.direction === posFilter);
    return [...base].sort((a, b) => {
      if (posSortKey === "pnl_pct") return b.pnl_pct - a.pnl_pct;
      if (posSortKey === "confidence") return b.confidence - a.confidence;
      return b.opened_at.localeCompare(a.opened_at);
    });
  }, [allPositions, posFilter, posSortKey]);

  const signalsMap = signalsQ.data ?? {};
  const signalsList = Object.values(signalsMap);

  const isRunning = sim?.is_running ?? false;
  const openCount = sim?.open_positions ?? 0;
  const totalPnl = perf?.total_pnl_pct ?? 0;
  const winRate = perf ? perf.win_rate * 100 : 0;
  const sharpe = perf?.sharpe_ratio ?? 0;
  const mdd = perf?.max_drawdown_pct ?? 0;
  const profitFactor = perf?.profit_factor ?? 0;

  return (
    <div className="space-y-4">

      {/* ── Header bar ─────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border/40 bg-surface/60 px-4 py-3">
        <div className="flex items-center gap-3">
          {/* Status dot */}
          <span
            className={`inline-flex h-2.5 w-2.5 rounded-full ${isRunning ? "animate-pulse bg-bullish" : "bg-muted-foreground"}`}
            aria-label={isRunning ? "Bot running" : "Bot stopped"}
          />
          <div>
            <p className="text-sm font-semibold text-white">
              AI Paper Trading Bot
              <span className={`ml-2 text-[10px] font-medium ${isRunning ? "text-bullish" : "text-muted-foreground"}`}>
                {isRunning ? "RUNNING" : "STOPPED"}
              </span>
            </p>
            <p className="text-[10px] text-muted-foreground">
              {agent?.scan_count ?? 0} scans · last{" "}
              {agent?.last_scan ? new Date(agent.last_scan).toLocaleTimeString() : "—"}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleRefreshAll}
            className="rounded border border-border/50 px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:text-white"
            aria-label="Refresh bot data"
          >
            Refresh
          </button>
          {isRunning ? (
            <button
              type="button"
              onClick={() => { stopMut.mutate(); }}
              disabled={stopMut.isPending}
              className="rounded border border-bearish/50 bg-bearish/10 px-4 py-1.5 text-xs font-medium text-bearish transition-colors hover:bg-bearish/20 disabled:opacity-50"
              aria-label="Stop bot"
            >
              Stop Bot
            </button>
          ) : (
            <button
              type="button"
              onClick={() => { startMut.mutate(); }}
              disabled={startMut.isPending}
              className="rounded border border-bullish/50 bg-bullish/10 px-4 py-1.5 text-xs font-medium text-bullish transition-colors hover:bg-bullish/20 disabled:opacity-50"
              aria-label="Start bot"
            >
              Start Bot
            </button>
          )}
        </div>
      </div>

      {/* ── KPI tiles ──────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <StatTile
          label="Total PnL"
          value={`${totalPnl >= 0 ? "+" : ""}${totalPnl.toFixed(2)}%`}
          sub={`Running: +${(perf?.running_pnl ?? 0).toFixed(2)}%`}
          color={totalPnl >= 0 ? "text-bullish" : "text-bearish"}
        />
        <StatTile
          label="Win Rate"
          value={`${winRate.toFixed(1)}%`}
          sub={`${perf?.winning_trades ?? 0}W / ${perf?.losing_trades ?? 0}L`}
          color={winRate >= 50 ? "text-bullish" : "text-bearish"}
        />
        <StatTile
          label="Open Positions"
          value={String(openCount)}
          sub={`Max ${sim?.max_positions ?? 100}`}
        />
        <StatTile
          label="Sharpe Ratio"
          value={sharpe.toFixed(2)}
          sub="Risk-adjusted return"
          color={sharpe >= 1 ? "text-bullish" : "text-muted-foreground"}
        />
        <StatTile
          label="Profit Factor"
          value={profitFactor.toFixed(2)}
          sub="Gross win / gross loss"
          color={profitFactor >= 1.5 ? "text-bullish" : "text-muted-foreground"}
        />
        <StatTile
          label="Max Drawdown"
          value={`-${mdd.toFixed(2)}%`}
          sub={`Best ${(perf?.best_trade ?? 0).toFixed(2)}%`}
          color={mdd > 20 ? "text-bearish" : "text-muted-foreground"}
        />
      </div>

      {/* ── Sub-tabs ───────────────────────────────────────────────── */}
      <div className="flex gap-0.5 overflow-x-auto rounded-lg border border-border/40 bg-surface/30 p-1" role="tablist" aria-label="Bot sub-navigation">
        {SUB_TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={subTab === t.id}
            onClick={() => { setSubTab(t.id); }}
            className={`min-h-[36px] shrink-0 rounded px-4 py-1.5 text-xs font-medium transition-colors ${
              subTab === t.id
                ? "bg-accent/20 text-white"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {t.label}
            {t.id === "positions" && openCount > 0 && (
              <span className="ml-1.5 rounded-full bg-accent/30 px-1.5 py-0.5 text-[9px] text-accent">
                {openCount}
              </span>
            )}
            {t.id === "signals" && signalsList.length > 0 && (
              <span className="ml-1.5 rounded-full bg-amber-500/20 px-1.5 py-0.5 text-[9px] text-amber-400">
                {signalsList.length}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* ── Overview sub-tab ───────────────────────────────────────── */}
      {subTab === "overview" && (
        <div className="space-y-4">

          {/* Equity Curve */}
          <div className="rounded-xl border border-border/40 bg-surface/60 p-4">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-white">Equity Curve</h3>
              <span className="text-[10px] text-muted-foreground">
                {equityPts.length} closed trades · start $100
              </span>
            </div>
            <EquityCurveChart points={equityPts} />
          </div>

          {/* Two-column: stats + learning log */}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">

            {/* Detailed stats */}
            <div className="rounded-xl border border-border/40 bg-surface/60 p-4">
              <h3 className="mb-3 text-sm font-semibold text-white">Trade Statistics</h3>
              <div className="space-y-2 text-xs">
                {[
                  ["Total closed trades", perf?.total_trades ?? 0],
                  ["Avg win", `+${(perf?.avg_win_pct ?? 0).toFixed(2)}%`],
                  ["Avg loss", `${(perf?.avg_loss_pct ?? 0).toFixed(2)}%`],
                  ["Best trade", `+${(perf?.best_trade ?? 0).toFixed(2)}%`],
                  ["Worst trade", `${(perf?.worst_trade ?? 0).toFixed(2)}%`],
                  ["Active signals", agent?.active_signals ?? 0],
                  ["Agent total trades", agent?.total_trades ?? 0],
                  ["Agent wins / losses", `${agent?.wins ?? 0} / ${agent?.losses ?? 0}`],
                ].map(([label, val]) => (
                  <div key={String(label)} className="flex items-center justify-between border-b border-border/10 pb-1.5">
                    <span className="text-muted-foreground">{label}</span>
                    <span className="font-medium text-white tabular-nums">{String(val)}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* AI Learning Log */}
            <div className="rounded-xl border border-border/40 bg-surface/60 p-4">
              <h3 className="mb-3 text-sm font-semibold text-white">
                AI Learning Log
                <span className="ml-2 text-[10px] font-normal text-muted-foreground">Recent lessons</span>
              </h3>
              {(agent?.recent_lessons ?? []).length === 0 ? (
                <p className="text-xs text-muted-foreground">No lessons yet — close some trades first.</p>
              ) : (
                <div className="space-y-2">
                  {(agent?.recent_lessons ?? []).map((lesson, i) => {
                    const isWin = lesson.includes("TP") || lesson.includes("profit") || lesson.includes("worked");
                    return (
                      <div
                        key={i}
                        className={`rounded border-l-2 pl-3 py-1 text-[11px] leading-relaxed ${
                          isWin ? "border-bullish/60 bg-bullish/5 text-bullish/90" : "border-bearish/60 bg-bearish/5 text-bearish/90"
                        }`}
                      >
                        {lesson}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── Positions sub-tab ──────────────────────────────────────── */}
      {subTab === "positions" && (
        <div className="rounded-xl border border-border/40 bg-surface/60 p-4">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <h3 className="text-sm font-semibold text-white">
              Open Positions
              <span className="ml-2 text-[10px] text-muted-foreground">{openCount} active</span>
            </h3>
            <div className="flex items-center gap-2">
              {/* Filter */}
              <div className="flex gap-1" role="group" aria-label="Filter positions by direction">
                {(["all", "LONG", "SHORT"] as const).map((f) => (
                  <button
                    key={f}
                    type="button"
                    onClick={() => { setPosFilter(f); }}
                    className={`rounded px-2.5 py-1 text-[10px] font-medium transition-colors ${
                      posFilter === f
                        ? f === "LONG" ? "bg-bullish/20 text-bullish" : f === "SHORT" ? "bg-bearish/20 text-bearish" : "bg-white/10 text-white"
                        : "text-muted-foreground hover:text-white"
                    }`}
                  >
                    {f === "all" ? "All" : f}
                  </button>
                ))}
              </div>
              {/* Sort */}
              <select
                value={posSortKey}
                onChange={(e) => { setPosSortKey(e.target.value as typeof posSortKey); }}
                className="rounded border border-border/50 bg-surface px-2 py-1 text-[10px] text-muted-foreground focus:outline-none"
                aria-label="Sort positions"
              >
                <option value="pnl_pct">Sort by PnL</option>
                <option value="confidence">Sort by Confidence</option>
                <option value="opened_at">Sort by Time</option>
              </select>
            </div>
          </div>

          {filteredPositions.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">No open positions.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[500px]">
                <thead>
                  <tr className="border-b border-border/30">
                    {["Symbol", "Dir", "Strategy", "Entry", "PnL", "Conf", "Status"].map((h) => (
                      <th key={h} className="pb-2 pr-3 text-left text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filteredPositions.map((pos) => (
                    <PositionRow key={pos.id} pos={pos} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ── Signals sub-tab ────────────────────────────────────────── */}
      {subTab === "signals" && (
        <div>
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-white">
              Active AI Signals
              <span className="ml-2 text-[10px] text-muted-foreground">{signalsList.length} live</span>
            </h3>
            <p className="text-[10px] text-muted-foreground">Auto-refreshes every 15s</p>
          </div>
          {signalsList.length === 0 ? (
            <div className="rounded-xl border border-border/40 bg-surface/40 py-12 text-center">
              <p className="text-sm text-muted-foreground">No active signals. The bot is scanning…</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {signalsList.map((sig) => (
                <SignalCard key={sig.symbol} signal={sig} />
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── Paper Controls sub-tab ─────────────────────────────────── */}
      {subTab === "paper" && <EnhancedPaperPanel />}

      {/* ── Binance Testnet sub-tab ────────────────────────────────── */}
      {subTab === "testnet" && <FuturesTestnetPanel />}

    </div>
  );
}
