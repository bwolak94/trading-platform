/**
 * EnhancedPaperPanel — Option B
 * Manual paper trading with realistic leverage, fees (0.04% taker),
 * funding rate (every 8h), and liquidation price tracking.
 * No real money, no API keys required.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import axios from "axios";

// ------------------------------------------------------------------ //
// Types
// ------------------------------------------------------------------ //

interface PaperPosition {
  id: string;
  symbol: string;
  direction: "LONG" | "SHORT";
  strategy: string;
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
  position_size_usdt: number;
  margin_usdt: number;
  fee_paid_pct: number;
  funding_charged_pct: number;
  liquidation_price: number;
  distance_to_liquidation_pct: number | null;
  mae_pct: number;
  mfe_pct: number;
  trailing_active: boolean;
  trailing_stop: number;
  tp1_hit: boolean;
  remaining_size_pct: number;
  opened_at: string;
  status: string;
}

interface SimStatus {
  is_running: boolean;
  open_positions: number;
  performance: {
    total_trades: number;
    winning_trades: number;
    win_rate: number;
    total_pnl_pct: number;
    max_drawdown_pct: number;
  };
}

interface FundingEntry {
  symbol: string;
  direction: string;
  funding_rate_pct: number;
  charged_at: string;
  total_charged_pct: number;
}

interface ManualForm {
  symbol: string;
  direction: "LONG" | "SHORT";
  entry_price: string;
  stop_loss: string;
  take_profit_1: string;
  take_profit_2: string;
  leverage: number;
  position_size_usdt: number;
}

// ------------------------------------------------------------------ //
// API helpers
// ------------------------------------------------------------------ //

const api = axios.create({ baseURL: "/api/v1/simulation" });

const fetchStatus = async (): Promise<SimStatus> =>
  (await api.get("/status")).data;

const fetchPositions = async (): Promise<{ positions: PaperPosition[]; count: number }> =>
  (await api.get("/positions")).data;

const fetchFunding = async (): Promise<{ history: FundingEntry[] }> =>
  (await api.get("/funding-history?limit=30")).data;

// ------------------------------------------------------------------ //
// Sub-components
// ------------------------------------------------------------------ //

function PnlBadge({ value, suffix = "%" }: { value: number; suffix?: string }) {
  const color = value > 0 ? "text-green-400" : value < 0 ? "text-red-400" : "text-gray-400";
  return (
    <span className={`font-mono font-bold ${color}`}>
      {value > 0 ? "+" : ""}{value.toFixed(2)}{suffix}
    </span>
  );
}

function LiquidationBar({ distancePct }: { distancePct: number | null }) {
  if (distancePct === null) return null;
  const danger = distancePct < 5;
  const warn = distancePct < 15;
  const color = danger ? "bg-red-500" : warn ? "bg-orange-400" : "bg-green-500";
  const width = Math.min(100, 100 - distancePct * 2);
  return (
    <div className="mt-1">
      <div className="flex justify-between text-[9px] text-gray-500 mb-0.5">
        <span>Liq. distance</span>
        <span className={danger ? "text-red-400 font-bold" : warn ? "text-orange-400" : "text-gray-400"}>
          {distancePct.toFixed(1)}% away
        </span>
      </div>
      <div className="h-1 w-full rounded-full bg-surface overflow-hidden">
        <div className={`h-full rounded-full transition-all ${color}`} style={{ width: `${width}%` }} />
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ //
// Main component
// ------------------------------------------------------------------ //

export default function EnhancedPaperPanel() {
  const qc = useQueryClient();
  const [activeTab, setActiveTab] = useState<"positions" | "manual" | "funding" | "stats">("positions");
  const [form, setForm] = useState<ManualForm>({
    symbol: "BTCUSDT",
    direction: "LONG",
    entry_price: "",
    stop_loss: "",
    take_profit_1: "",
    take_profit_2: "",
    leverage: 5,
    position_size_usdt: 200,
  });

  const { data: status } = useQuery({
    queryKey: ["paper-status"],
    queryFn: fetchStatus,
    refetchInterval: 5_000,
  });

  const { data: posData, isLoading: posLoading } = useQuery({
    queryKey: ["paper-positions"],
    queryFn: fetchPositions,
    refetchInterval: 3_000,
  });

  const { data: fundingData } = useQuery({
    queryKey: ["paper-funding"],
    queryFn: fetchFunding,
    refetchInterval: 60_000,
    enabled: activeTab === "funding",
  });

  const openMutation = useMutation({
    mutationFn: async (f: ManualForm) =>
      (await api.post("/position/manual", {
        symbol: f.symbol,
        direction: f.direction,
        entry_price: parseFloat(f.entry_price),
        stop_loss: parseFloat(f.stop_loss),
        take_profit_1: parseFloat(f.take_profit_1),
        take_profit_2: f.take_profit_2 ? parseFloat(f.take_profit_2) : undefined,
        leverage: f.leverage,
        position_size_usdt: f.position_size_usdt,
      })).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["paper-positions"] });
      qc.invalidateQueries({ queryKey: ["paper-status"] });
      setActiveTab("positions");
    },
  });

  const closeMutation = useMutation({
    mutationFn: async (id: string) =>
      (await api.post(`/position/${id}/close`)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["paper-positions"] });
      qc.invalidateQueries({ queryKey: ["paper-status"] });
    },
  });

  const startMutation = useMutation({
    mutationFn: async () => (await api.post("/start")).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["paper-status"] }),
  });

  const handleChange = useCallback((field: keyof ManualForm, value: string | number) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  }, []);

  const perf = status?.performance;
  const openPositions = posData?.positions ?? [];
  const totalUnrealizedPnl = openPositions.reduce((acc, p) => acc + p.unrealized_pnl_usdt, 0);

  // Estimated fee for current form
  const formNotional = form.position_size_usdt * form.leverage;
  const estimatedFee = formNotional * 0.0004 * 2; // entry + exit

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={`h-2 w-2 rounded-full ${status?.is_running ? "bg-green-400 animate-pulse" : "bg-gray-600"}`} />
          <h3 className="text-sm font-semibold text-white">Enhanced Paper Trading</h3>
          <span className="rounded border border-purple-500/30 px-1.5 py-0.5 text-[10px] font-bold text-purple-400">
            PAPER
          </span>
        </div>
        <div className="flex items-center gap-3 text-xs">
          {perf && (
            <>
              <span className="text-gray-500">WR: <span className="text-white">{(perf.win_rate * 100).toFixed(0)}%</span></span>
              <span className="text-gray-500">Trades: <span className="text-white">{perf.total_trades}</span></span>
              <span className="text-gray-500">PnL: <PnlBadge value={perf.total_pnl_pct} /></span>
            </>
          )}
          {!status?.is_running && (
            <button
              type="button"
              onClick={() => { startMutation.mutate(); }}
              disabled={startMutation.isPending}
              className="rounded border border-green-500/50 px-2 py-0.5 text-[10px] text-green-400 hover:bg-green-500/10"
            >
              Start Engine
            </button>
          )}
        </div>
      </div>

      {/* Portfolio summary bar */}
      {openPositions.length > 0 && (
        <div className="mb-4 rounded border border-border bg-background p-2 flex items-center gap-4 text-xs">
          <span className="text-gray-500">Open: <span className="text-white font-bold">{openPositions.length}</span></span>
          <span className="text-gray-500">
            Unrealized: <PnlBadge value={totalUnrealizedPnl} suffix=" USDT" />
          </span>
          <span className="text-gray-500">
            Margin used: <span className="font-mono text-white">
              ${openPositions.reduce((acc, p) => acc + p.margin_usdt, 0).toFixed(2)}
            </span>
          </span>
        </div>
      )}

      {/* Tabs */}
      <div className="mb-4 flex gap-1 border-b border-border">
        {(["positions", "manual", "funding", "stats"] as const).map((tab) => (
          <button
            key={tab}
            type="button"
            onClick={() => { setActiveTab(tab); }}
            className={`px-3 py-1.5 text-xs font-medium transition-colors ${
              activeTab === tab
                ? "border-b-2 border-purple-400 text-purple-400"
                : "text-gray-500 hover:text-gray-300"
            }`}
          >
            {tab === "manual" ? "Manual Open" : tab.charAt(0).toUpperCase() + tab.slice(1)}
            {tab === "positions" && openPositions.length > 0 && (
              <span className="ml-1 rounded bg-purple-400/20 px-1 text-[10px] text-purple-400">
                {openPositions.length}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Positions */}
      {activeTab === "positions" && (
        <div className="space-y-3">
          {posLoading && <p className="text-xs text-gray-500">Loading…</p>}
          {!posLoading && openPositions.length === 0 && (
            <p className="text-center text-xs text-gray-600 py-6">
              No open paper positions. Use "Manual Open" or let the engine scan for signals.
            </p>
          )}
          {openPositions.map((pos) => (
            <div key={pos.id} className="rounded border border-border bg-background p-3">
              <div className="mb-2 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-sm font-bold text-white">{pos.symbol}</span>
                  <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${
                    pos.direction === "LONG" ? "bg-green-500/20 text-green-400" : "bg-red-500/20 text-red-400"
                  }`}>
                    {pos.direction}
                  </span>
                  <span className="text-[10px] text-purple-300">{pos.leverage}×</span>
                  <span className="text-[10px] text-gray-500">{pos.strategy}</span>
                </div>
                <button
                  type="button"
                  onClick={() => { closeMutation.mutate(pos.id); }}
                  disabled={closeMutation.isPending}
                  className="rounded border border-red-500/50 px-2 py-0.5 text-[10px] text-red-400 hover:bg-red-500/10 disabled:opacity-50"
                >
                  Close
                </button>
              </div>

              {/* PnL row */}
              <div className="mb-2 grid grid-cols-4 gap-2 text-xs">
                <div>
                  <span className="text-gray-500 text-[10px]">Raw PnL</span>
                  <p><PnlBadge value={pos.pnl_pct} /></p>
                </div>
                <div>
                  <span className="text-gray-500 text-[10px]">Lev. PnL</span>
                  <p className="font-bold"><PnlBadge value={pos.leveraged_pnl_pct} /></p>
                </div>
                <div>
                  <span className="text-gray-500 text-[10px]">USDT PnL</span>
                  <p><PnlBadge value={pos.unrealized_pnl_usdt} suffix=" $" /></p>
                </div>
                <div>
                  <span className="text-gray-500 text-[10px]">Margin</span>
                  <p className="font-mono text-xs text-white">${pos.margin_usdt.toFixed(2)}</p>
                </div>
              </div>

              {/* Prices row */}
              <div className="mb-2 grid grid-cols-4 gap-2 text-xs">
                <div>
                  <span className="text-gray-500 text-[10px]">Entry</span>
                  <p className="font-mono text-white">{pos.entry_price.toLocaleString()}</p>
                </div>
                <div>
                  <span className="text-gray-500 text-[10px]">Current</span>
                  <p className="font-mono text-white">{pos.current_price > 0 ? pos.current_price.toLocaleString() : "—"}</p>
                </div>
                <div>
                  <span className="text-gray-500 text-[10px]">Stop Loss</span>
                  <p className="font-mono text-red-400">{pos.stop_loss.toLocaleString()}</p>
                </div>
                <div>
                  <span className="text-gray-500 text-[10px]">Liq. Price</span>
                  <p className={`font-mono ${pos.distance_to_liquidation_pct !== null && pos.distance_to_liquidation_pct < 10 ? "text-red-400 font-bold" : "text-orange-400"}`}>
                    {pos.liquidation_price > 0 ? pos.liquidation_price.toLocaleString() : "—"}
                  </p>
                </div>
              </div>

              {/* Liquidation distance bar */}
              <LiquidationBar distancePct={pos.distance_to_liquidation_pct} />

              {/* Costs row */}
              <div className="mt-2 flex gap-3 text-[10px] text-gray-500">
                <span>Fees: <span className="text-orange-400">{pos.fee_paid_pct.toFixed(3)}%</span></span>
                <span>Funding: <span className={pos.funding_charged_pct > 0 ? "text-orange-400" : "text-green-400"}>
                  {pos.funding_charged_pct > 0 ? "+" : ""}{pos.funding_charged_pct.toFixed(3)}%
                </span></span>
                <span>MAE: <span className="text-red-400">{pos.mae_pct.toFixed(2)}%</span></span>
                <span>MFE: <span className="text-green-400">+{pos.mfe_pct.toFixed(2)}%</span></span>
                {pos.tp1_hit && <span className="text-yellow-400">TP1 ✓</span>}
                {pos.trailing_active && <span className="text-blue-400">Trailing {pos.trailing_stop.toLocaleString()}</span>}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Manual open form */}
      {activeTab === "manual" && (
        <div className="space-y-3">
          <p className="text-xs text-gray-500">
            Open a paper position with simulated leverage. Fees (0.04% taker) and funding rate (every 8h) are applied automatically.
          </p>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-[10px] text-gray-500">Symbol</label>
              <input
                type="text"
                value={form.symbol}
                onChange={(e) => { handleChange("symbol", e.target.value.toUpperCase()); }}
                className="w-full rounded border border-border bg-background px-2 py-1.5 text-xs font-mono text-white focus:outline-none focus:ring-1 focus:ring-purple-500"
              />
            </div>
            <div>
              <label className="mb-1 block text-[10px] text-gray-500">Direction</label>
              <div className="flex gap-1">
                {(["LONG", "SHORT"] as const).map((d) => (
                  <button
                    key={d}
                    type="button"
                    onClick={() => { handleChange("direction", d); }}
                    className={`flex-1 rounded py-1.5 text-xs font-bold transition-colors border ${
                      form.direction === d
                        ? d === "LONG" ? "bg-green-500/20 text-green-400 border-green-500/50" : "bg-red-500/20 text-red-400 border-red-500/50"
                        : "border-border text-gray-500 hover:text-gray-300"
                    }`}
                  >
                    {d}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-[10px] text-gray-500">Entry Price</label>
              <input
                type="number"
                value={form.entry_price}
                onChange={(e) => { handleChange("entry_price", e.target.value); }}
                className="w-full rounded border border-border bg-background px-2 py-1.5 text-xs font-mono text-white focus:outline-none focus:ring-1 focus:ring-purple-500"
                placeholder="e.g. 67500"
              />
            </div>
            <div>
              <label className="mb-1 block text-[10px] text-gray-500">Stop Loss</label>
              <input
                type="number"
                value={form.stop_loss}
                onChange={(e) => { handleChange("stop_loss", e.target.value); }}
                className="w-full rounded border border-border bg-background px-2 py-1.5 text-xs font-mono text-white focus:outline-none focus:ring-1 focus:ring-purple-500"
                placeholder="e.g. 65000"
              />
            </div>
            <div>
              <label className="mb-1 block text-[10px] text-gray-500">Take Profit 1</label>
              <input
                type="number"
                value={form.take_profit_1}
                onChange={(e) => { handleChange("take_profit_1", e.target.value); }}
                className="w-full rounded border border-border bg-background px-2 py-1.5 text-xs font-mono text-white focus:outline-none focus:ring-1 focus:ring-purple-500"
                placeholder="e.g. 70000"
              />
            </div>
            <div>
              <label className="mb-1 block text-[10px] text-gray-500">Take Profit 2 (optional)</label>
              <input
                type="number"
                value={form.take_profit_2}
                onChange={(e) => { handleChange("take_profit_2", e.target.value); }}
                className="w-full rounded border border-border bg-background px-2 py-1.5 text-xs font-mono text-white focus:outline-none focus:ring-1 focus:ring-purple-500"
                placeholder="e.g. 73000"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 flex justify-between text-[10px] text-gray-500">
                <span>Leverage</span>
                <span className="font-bold text-purple-400">{form.leverage}×</span>
              </label>
              <input
                type="range"
                min={1}
                max={50}
                step={1}
                value={form.leverage}
                onChange={(e) => { handleChange("leverage", parseInt(e.target.value)); }}
                className="w-full accent-purple-400"
              />
              <div className="flex justify-between text-[9px] text-gray-600 mt-0.5">
                <span>1×</span><span>10×</span><span>25×</span><span>50×</span>
              </div>
            </div>
            <div>
              <label className="mb-1 block text-[10px] text-gray-500">Position Size (USDT)</label>
              <input
                type="number"
                value={form.position_size_usdt}
                onChange={(e) => { handleChange("position_size_usdt", parseFloat(e.target.value)); }}
                className="w-full rounded border border-border bg-background px-2 py-1.5 text-xs font-mono text-white focus:outline-none focus:ring-1 focus:ring-purple-500"
                min={10}
              />
            </div>
          </div>

          {/* Cost preview */}
          <div className="rounded border border-border bg-background p-2 text-xs space-y-1">
            <div className="flex justify-between text-gray-500">
              <span>Margin required</span>
              <span className="font-mono text-white">${form.position_size_usdt.toFixed(2)}</span>
            </div>
            <div className="flex justify-between text-gray-500">
              <span>Notional value</span>
              <span className="font-mono text-white">${formNotional.toFixed(2)}</span>
            </div>
            <div className="flex justify-between text-gray-500">
              <span>Est. entry+exit fees (0.04%×2)</span>
              <span className="font-mono text-orange-400">-${estimatedFee.toFixed(3)}</span>
            </div>
            {form.entry_price && form.stop_loss && (
              <div className="flex justify-between text-gray-500">
                <span>Max loss (incl. leverage)</span>
                <span className="font-mono text-red-400">
                  -${(Math.abs(parseFloat(form.entry_price) - parseFloat(form.stop_loss)) / parseFloat(form.entry_price) * form.position_size_usdt * form.leverage).toFixed(2)}
                </span>
              </div>
            )}
          </div>

          {openMutation.isError && (
            <p className="rounded bg-red-500/10 px-2 py-1 text-xs text-red-400">
              {(openMutation.error).message}
            </p>
          )}

          <button
            type="button"
            onClick={() => { openMutation.mutate(form); }}
            disabled={openMutation.isPending || !form.entry_price || !form.stop_loss || !form.take_profit_1}
            className={`w-full rounded py-2 text-sm font-bold transition-colors disabled:opacity-50 border ${
              form.direction === "LONG"
                ? "bg-green-500/20 text-green-400 hover:bg-green-500/30 border-green-500/50"
                : "bg-red-500/20 text-red-400 hover:bg-red-500/30 border-red-500/50"
            }`}
          >
            {openMutation.isPending ? "Opening…" : `Paper ${form.direction} ${form.leverage}× — $${form.position_size_usdt}`}
          </button>
        </div>
      )}

      {/* Funding history */}
      {activeTab === "funding" && (
        <div>
          <p className="mb-3 text-xs text-gray-500">
            Funding rates are charged to leveraged positions every 8 hours.
            Longs pay when positive; shorts receive.
          </p>
          {!fundingData?.history.length && (
            <p className="text-center text-xs text-gray-600 py-6">No funding charges yet (applied every 8h to open leveraged positions)</p>
          )}
          <div className="space-y-1">
            {fundingData?.history.map((entry, i) => (
              <div key={i} className="flex items-center justify-between rounded border border-border bg-background px-3 py-1.5 text-xs">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-white">{entry.symbol}</span>
                  <span className={entry.direction === "LONG" ? "text-green-400" : "text-red-400"}>{entry.direction}</span>
                  <span className="text-gray-500">{new Date(entry.charged_at).toLocaleTimeString()}</span>
                </div>
                <div className="flex items-center gap-3 font-mono">
                  <span className={entry.funding_rate_pct > 0 ? "text-orange-400" : "text-green-400"}>
                    {entry.direction === "LONG" ? "-" : "+"}{entry.funding_rate_pct.toFixed(4)}%
                  </span>
                  <span className="text-gray-600">total: {entry.total_charged_pct.toFixed(4)}%</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Stats tab */}
      {activeTab === "stats" && perf && (
        <div className="grid grid-cols-2 gap-3">
          {[
            { label: "Total Trades", value: perf.total_trades, mono: false },
            { label: "Win Rate", value: `${(perf.win_rate * 100).toFixed(1)}%`, mono: true },
            { label: "Total PnL", value: `${perf.total_pnl_pct > 0 ? "+" : ""}${perf.total_pnl_pct.toFixed(2)}%`, mono: true, color: perf.total_pnl_pct >= 0 ? "text-green-400" : "text-red-400" },
            { label: "Max Drawdown", value: `-${perf.max_drawdown_pct.toFixed(2)}%`, mono: true, color: "text-red-400" },
          ].map(({ label, value, mono, color }) => (
            <div key={label} className="rounded border border-border bg-background p-3">
              <p className="text-[10px] text-gray-500">{label}</p>
              <p className={`text-lg font-bold ${color ?? "text-white"} ${mono ? "font-mono" : ""}`}>{value}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
