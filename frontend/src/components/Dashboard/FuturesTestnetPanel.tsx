/**
 * FuturesTestnetPanel — Option A
 * Places and monitors real orders on Binance Futures Testnet (fake money).
 * Requires BINANCE_TESTNET_API_KEY + BINANCE_TESTNET_API_SECRET on the backend.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import axios from "axios";

// ------------------------------------------------------------------ //
// Types
// ------------------------------------------------------------------ //

interface TestnetStatus {
  configured: boolean;
  connected?: boolean;
  balance_usdt?: number;
  available_usdt?: number;
  unrealized_pnl?: number;
  error?: string;
  message?: string;
  setup_url?: string;
}

interface TestnetPosition {
  symbol: string;
  direction: "LONG" | "SHORT";
  size: number;
  entry_price: number;
  mark_price: number;
  liquidation_price: number;
  leverage: number;
  unrealized_pnl: number;
  pnl_pct: number;
  margin_type: string;
}

interface TestnetOrder {
  order_id: number;
  symbol: string;
  side: string;
  type: string;
  price: number;
  orig_qty: number;
  executed_qty: number;
  status: string;
  reduce_only: boolean;
}

interface OpenFromSignalForm {
  symbol: string;
  direction: "LONG" | "SHORT";
  entry_price: string;
  stop_loss: string;
  take_profit_1: string;
  take_profit_2: string;
  leverage: number;
  usdt_size: number;
}

// ------------------------------------------------------------------ //
// API helpers
// ------------------------------------------------------------------ //

const api = axios.create({ baseURL: "/api/v1/futures-testnet" });

const fetchStatus = async (): Promise<TestnetStatus> =>
  (await api.get("/status")).data;

const fetchPositions = async (): Promise<{ positions: TestnetPosition[]; count: number }> =>
  (await api.get("/positions")).data;

const fetchOrders = async (): Promise<{ orders: TestnetOrder[]; count: number }> =>
  (await api.get("/orders")).data;

// ------------------------------------------------------------------ //
// Component
// ------------------------------------------------------------------ //

export default function FuturesTestnetPanel() {
  const qc = useQueryClient();
  const [activeTab, setActiveTab] = useState<"positions" | "orders" | "open">("positions");
  const [form, setForm] = useState<OpenFromSignalForm>({
    symbol: "BTCUSDT",
    direction: "LONG",
    entry_price: "",
    stop_loss: "",
    take_profit_1: "",
    take_profit_2: "",
    leverage: 5,
    usdt_size: 100,
  });

  const { data: status } = useQuery({
    queryKey: ["testnet-status"],
    queryFn: fetchStatus,
    refetchInterval: 30_000,
  });

  const { data: posData, isLoading: posLoading } = useQuery({
    queryKey: ["testnet-positions"],
    queryFn: fetchPositions,
    refetchInterval: 5_000,
    enabled: status?.connected === true,
  });

  const { data: orderData } = useQuery({
    queryKey: ["testnet-orders"],
    queryFn: fetchOrders,
    refetchInterval: 10_000,
    enabled: status?.connected === true,
  });

  const openMutation = useMutation({
    mutationFn: async (f: OpenFromSignalForm) => {
      const body: Record<string, unknown> = {
        symbol: f.symbol,
        direction: f.direction,
        leverage: f.leverage,
        usdt_size: f.usdt_size,
      };
      if (f.entry_price) body.entry_price = parseFloat(f.entry_price);
      if (f.stop_loss) body.stop_loss = parseFloat(f.stop_loss);
      if (f.take_profit_1) body.take_profit_1 = parseFloat(f.take_profit_1);
      if (f.take_profit_2) body.take_profit_2 = parseFloat(f.take_profit_2);
      return (await api.post("/from-signal", body)).data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["testnet-positions"] });
      qc.invalidateQueries({ queryKey: ["testnet-orders"] });
      qc.invalidateQueries({ queryKey: ["testnet-status"] });
    },
  });

  const closeMutation = useMutation({
    mutationFn: async (symbol: string) =>
      (await api.post(`/position/close?symbol=${symbol}`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["testnet-positions"] }),
  });

  const cancelOrderMutation = useMutation({
    mutationFn: async ({ symbol, orderId }: { symbol: string; orderId: number }) =>
      (await api.delete(`/order/${orderId}?symbol=${symbol}`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["testnet-orders"] }),
  });

  const handleFormChange = useCallback(
    (field: keyof OpenFromSignalForm, value: string | number) => {
      setForm((prev) => ({ ...prev, [field]: value }));
    },
    [],
  );

  // ---------------------------------------------------------------- //
  // Not configured
  // ---------------------------------------------------------------- //

  if (status && !status.configured) {
    return (
      <div className="rounded-lg border border-yellow-500/30 bg-yellow-500/5 p-5">
        <h3 className="mb-2 text-sm font-semibold text-yellow-400">
          Binance Futures Testnet — Setup Required
        </h3>
        <p className="mb-3 text-xs text-gray-400">
          Get free testnet API keys, then set them as environment variables on the backend.
        </p>
        <ol className="mb-4 space-y-1 text-xs text-gray-300">
          <li>1. Register at <span className="font-mono text-yellow-300">testnet.binancefuture.com</span></li>
          <li>2. Go to API Management → generate keys</li>
          <li>3. Set <span className="font-mono">BINANCE_TESTNET_API_KEY</span></li>
          <li>4. Set <span className="font-mono">BINANCE_TESTNET_API_SECRET</span></li>
          <li>5. Restart the backend</li>
        </ol>
        <p className="text-xs text-gray-500">Testnet uses fake USDT — no real money at risk.</p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-yellow-400" />
          <h3 className="text-sm font-semibold text-white">Binance Futures Testnet</h3>
          <span className="rounded border border-yellow-500/30 px-1.5 py-0.5 text-[10px] font-bold text-yellow-400">
            TESTNET
          </span>
        </div>
        {status?.connected && (
          <div className="flex gap-4 text-xs text-gray-400">
            <span>Balance: <span className="font-mono text-white">${status.balance_usdt?.toFixed(2)}</span></span>
            <span>Available: <span className="font-mono text-green-400">${status.available_usdt?.toFixed(2)}</span></span>
            <span className={`font-mono ${(status.unrealized_pnl ?? 0) >= 0 ? "text-green-400" : "text-red-400"}`}>
              PnL: {(status.unrealized_pnl ?? 0) >= 0 ? "+" : ""}{status.unrealized_pnl?.toFixed(2)} USDT
            </span>
          </div>
        )}
      </div>

      {/* Tabs */}
      <div className="mb-4 flex gap-1 border-b border-border">
        {(["positions", "orders", "open"] as const).map((tab) => (
          <button
            key={tab}
            type="button"
            onClick={() => setActiveTab(tab)}
            className={`px-3 py-1.5 text-xs font-medium capitalize transition-colors ${
              activeTab === tab
                ? "border-b-2 border-yellow-400 text-yellow-400"
                : "text-gray-500 hover:text-gray-300"
            }`}
          >
            {tab === "open" ? "Open Position" : tab}
            {tab === "positions" && posData?.count ? (
              <span className="ml-1 rounded bg-yellow-400/20 px-1 text-[10px] text-yellow-400">
                {posData.count}
              </span>
            ) : null}
          </button>
        ))}
      </div>

      {/* Positions tab */}
      {activeTab === "positions" && (
        <div>
          {posLoading && <p className="text-xs text-gray-500">Loading positions…</p>}
          {!posLoading && !posData?.positions.length && (
            <p className="text-center text-xs text-gray-600 py-6">No open testnet positions</p>
          )}
          <div className="space-y-2">
            {posData?.positions.map((pos) => (
              <div
                key={pos.symbol}
                className="rounded border border-border bg-background p-3"
              >
                <div className="mb-2 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-sm font-bold text-white">{pos.symbol}</span>
                    <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${
                      pos.direction === "LONG" ? "bg-green-500/20 text-green-400" : "bg-red-500/20 text-red-400"
                    }`}>
                      {pos.direction}
                    </span>
                    <span className="text-[10px] text-gray-500">{pos.leverage}×</span>
                    <span className="text-[10px] text-gray-500">{pos.margin_type}</span>
                  </div>
                  <button
                    type="button"
                    onClick={() => closeMutation.mutate(pos.symbol)}
                    disabled={closeMutation.isPending}
                    className="rounded border border-red-500/50 px-2 py-0.5 text-[10px] text-red-400 hover:bg-red-500/10 disabled:opacity-50"
                  >
                    Close
                  </button>
                </div>
                <div className="grid grid-cols-3 gap-2 text-xs">
                  <div>
                    <span className="text-gray-500">Entry</span>
                    <p className="font-mono text-white">{pos.entry_price.toLocaleString()}</p>
                  </div>
                  <div>
                    <span className="text-gray-500">Mark</span>
                    <p className="font-mono text-white">{pos.mark_price.toLocaleString()}</p>
                  </div>
                  <div>
                    <span className="text-gray-500">Liq.</span>
                    <p className="font-mono text-orange-400">{pos.liquidation_price.toLocaleString()}</p>
                  </div>
                  <div>
                    <span className="text-gray-500">Size</span>
                    <p className="font-mono text-white">{pos.size}</p>
                  </div>
                  <div>
                    <span className="text-gray-500">PnL USD</span>
                    <p className={`font-mono font-bold ${pos.unrealized_pnl >= 0 ? "text-green-400" : "text-red-400"}`}>
                      {pos.unrealized_pnl >= 0 ? "+" : ""}{pos.unrealized_pnl.toFixed(2)}
                    </p>
                  </div>
                  <div>
                    <span className="text-gray-500">PnL %</span>
                    <p className={`font-mono font-bold ${pos.pnl_pct >= 0 ? "text-green-400" : "text-red-400"}`}>
                      {pos.pnl_pct >= 0 ? "+" : ""}{pos.pnl_pct.toFixed(2)}%
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Orders tab */}
      {activeTab === "orders" && (
        <div>
          {!orderData?.orders.length && (
            <p className="text-center text-xs text-gray-600 py-6">No open orders</p>
          )}
          <div className="space-y-1">
            {orderData?.orders.map((order) => (
              <div key={order.order_id} className="flex items-center justify-between rounded border border-border bg-background px-3 py-2">
                <div className="flex items-center gap-2 text-xs">
                  <span className="font-mono font-bold text-white">{order.symbol}</span>
                  <span className={`${order.side === "BUY" ? "text-green-400" : "text-red-400"}`}>{order.side}</span>
                  <span className="text-gray-500">{order.type}</span>
                  <span className="font-mono text-gray-300">
                    qty={order.orig_qty} {order.price > 0 ? `@ ${order.price.toLocaleString()}` : "MKT"}
                  </span>
                  {order.reduce_only && <span className="text-[10px] text-orange-400">REDUCE</span>}
                </div>
                <button
                  type="button"
                  onClick={() => cancelOrderMutation.mutate({ symbol: order.symbol, orderId: order.order_id })}
                  disabled={cancelOrderMutation.isPending}
                  className="text-[10px] text-red-400 hover:text-red-300 disabled:opacity-50"
                >
                  Cancel
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Open position tab */}
      {activeTab === "open" && (
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-[10px] text-gray-500">Symbol</label>
              <input
                type="text"
                value={form.symbol}
                onChange={(e) => handleFormChange("symbol", e.target.value.toUpperCase())}
                className="w-full rounded border border-border bg-background px-2 py-1.5 text-xs font-mono text-white focus:outline-none focus:ring-1 focus:ring-yellow-500"
                placeholder="BTCUSDT"
              />
            </div>
            <div>
              <label className="mb-1 block text-[10px] text-gray-500">Direction</label>
              <div className="flex gap-1">
                {(["LONG", "SHORT"] as const).map((d) => (
                  <button
                    key={d}
                    type="button"
                    onClick={() => handleFormChange("direction", d)}
                    className={`flex-1 rounded py-1.5 text-xs font-bold transition-colors ${
                      form.direction === d
                        ? d === "LONG" ? "bg-green-500/20 text-green-400 border border-green-500/50" : "bg-red-500/20 text-red-400 border border-red-500/50"
                        : "border border-border text-gray-500 hover:text-gray-300"
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
              <label className="mb-1 block text-[10px] text-gray-500">Entry Price (blank = market)</label>
              <input
                type="number"
                value={form.entry_price}
                onChange={(e) => handleFormChange("entry_price", e.target.value)}
                className="w-full rounded border border-border bg-background px-2 py-1.5 text-xs font-mono text-white focus:outline-none focus:ring-1 focus:ring-yellow-500"
                placeholder="Market"
              />
            </div>
            <div>
              <label className="mb-1 block text-[10px] text-gray-500">Stop Loss</label>
              <input
                type="number"
                value={form.stop_loss}
                onChange={(e) => handleFormChange("stop_loss", e.target.value)}
                className="w-full rounded border border-border bg-background px-2 py-1.5 text-xs font-mono text-white focus:outline-none focus:ring-1 focus:ring-yellow-500"
                placeholder="Stop price"
              />
            </div>
            <div>
              <label className="mb-1 block text-[10px] text-gray-500">Take Profit 1 (50%)</label>
              <input
                type="number"
                value={form.take_profit_1}
                onChange={(e) => handleFormChange("take_profit_1", e.target.value)}
                className="w-full rounded border border-border bg-background px-2 py-1.5 text-xs font-mono text-white focus:outline-none focus:ring-1 focus:ring-yellow-500"
                placeholder="TP1 price"
              />
            </div>
            <div>
              <label className="mb-1 block text-[10px] text-gray-500">Take Profit 2 (50%)</label>
              <input
                type="number"
                value={form.take_profit_2}
                onChange={(e) => handleFormChange("take_profit_2", e.target.value)}
                className="w-full rounded border border-border bg-background px-2 py-1.5 text-xs font-mono text-white focus:outline-none focus:ring-1 focus:ring-yellow-500"
                placeholder="TP2 price (optional)"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 flex justify-between text-[10px] text-gray-500">
                <span>Leverage</span>
                <span className="text-yellow-400 font-bold">{form.leverage}×</span>
              </label>
              <input
                type="range"
                min={1}
                max={50}
                value={form.leverage}
                onChange={(e) => handleFormChange("leverage", parseInt(e.target.value))}
                className="w-full accent-yellow-400"
              />
              <div className="flex justify-between text-[9px] text-gray-600">
                <span>1×</span><span>10×</span><span>25×</span><span>50×</span>
              </div>
            </div>
            <div>
              <label className="mb-1 block text-[10px] text-gray-500">Size (USDT)</label>
              <input
                type="number"
                value={form.usdt_size}
                onChange={(e) => handleFormChange("usdt_size", parseFloat(e.target.value))}
                className="w-full rounded border border-border bg-background px-2 py-1.5 text-xs font-mono text-white focus:outline-none focus:ring-1 focus:ring-yellow-500"
                min={10}
              />
              <p className="mt-0.5 text-[10px] text-gray-600">
                Notional: ${(form.usdt_size * form.leverage).toFixed(0)} USDT
              </p>
            </div>
          </div>

          {openMutation.isError && (
            <p className="rounded bg-red-500/10 px-2 py-1 text-xs text-red-400">
              {(openMutation.error as Error).message}
            </p>
          )}
          {openMutation.isSuccess && (
            <p className="rounded bg-green-500/10 px-2 py-1 text-xs text-green-400">
              Position opened on testnet!
            </p>
          )}

          <button
            type="button"
            onClick={() => openMutation.mutate(form)}
            disabled={openMutation.isPending || !form.symbol}
            className={`w-full rounded py-2 text-sm font-bold transition-colors disabled:opacity-50 ${
              form.direction === "LONG"
                ? "bg-green-500/20 text-green-400 hover:bg-green-500/30 border border-green-500/50"
                : "bg-red-500/20 text-red-400 hover:bg-red-500/30 border border-red-500/50"
            }`}
          >
            {openMutation.isPending ? "Opening…" : `Open ${form.direction} on Testnet`}
          </button>
        </div>
      )}
    </div>
  );
}
