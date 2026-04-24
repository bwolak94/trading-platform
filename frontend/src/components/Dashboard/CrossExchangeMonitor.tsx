/**
 * CrossExchangeMonitor
 * Real-time cross-exchange price spread monitor.
 * Fetches from GET /api/v1/features/cross-exchange/{symbol} — refreshes every 15 seconds.
 */

import { useQuery } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import axios from "axios";

// --------------- Types ---------------

interface CrossExchangeData {
  symbol: string;
  prices: Record<string, number>;
  max_spread_pct: number;
  leading_exchange: string;
  lagging_exchange: string;
  spread_alert: boolean;
  signal: string;
}

// --------------- Constants ---------------

const SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"];
const EXCHANGES = ["Binance", "OKX", "Bybit"];
const SPREAD_ALERT_THRESHOLD = 0.15;

// --------------- Helpers ---------------

function formatPrice(price: number): string {
  if (price >= 10000) return `$${price.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
  if (price >= 100) return `$${price.toFixed(2)}`;
  return `$${price.toFixed(4)}`;
}

function getSpreadColor(spreadPct: number): string {
  if (spreadPct > SPREAD_ALERT_THRESHOLD) return "text-red-400";
  if (spreadPct > 0.05) return "text-yellow-400";
  return "text-green-400";
}

function getSignalStyle(signal: string): string {
  const s = signal.toUpperCase();
  if (s.includes("BUY") || s.includes("BULL") || s.includes("LONG")) return "text-green-400";
  if (s.includes("SELL") || s.includes("BEAR") || s.includes("SHORT")) return "text-red-400";
  return "text-gray-400";
}

async function fetchCrossExchange(symbol: string): Promise<CrossExchangeData> {
  const { data } = await axios.get<CrossExchangeData>(
    `/api/v1/features/cross-exchange/${symbol}`
  );
  return data;
}

// --------------- Skeleton ---------------

function CrossExchangeSkeleton() {
  return (
    <div className="space-y-3" aria-busy="true" aria-label="Loading cross-exchange data">
      <div className="h-6 w-48 animate-pulse rounded bg-white/5" />
      <div className="h-24 animate-pulse rounded bg-white/5" />
      <div className="h-4 w-3/4 animate-pulse rounded bg-white/5" />
    </div>
  );
}

// --------------- Main Component ---------------

export default function CrossExchangeMonitor() {
  const [symbol, setSymbol] = useState("BTCUSDT");

  const { data, isLoading, isError, refetch, dataUpdatedAt } = useQuery<CrossExchangeData>({
    queryKey: ["cross-exchange", symbol],
    queryFn: () => fetchCrossExchange(symbol),
    refetchInterval: 15_000,
    retry: 2,
  });

  const handleRefetch = useCallback(() => { void refetch(); }, [refetch]);
  const lastUpdated = dataUpdatedAt ? new Date(dataUpdatedAt).toLocaleTimeString() : null;

  const signalColor = data ? getSignalStyle(data.signal) : "";

  // Compute per-exchange spreads relative to average
  const avgPrice = data
    ? Object.values(data.prices).reduce((sum, p) => sum + p, 0) /
      Math.max(Object.values(data.prices).length, 1)
    : 0;

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-white">Cross-Exchange Monitor</h2>
          {lastUpdated && (
            <p className="mt-0.5 text-xs text-gray-500">
              Updated: {lastUpdated}{" "}
              <span className="text-blue-400">(15s)</span>
            </p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <select
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            className="rounded border border-border bg-gray-800 px-2 py-1 text-xs text-gray-300 focus:outline-none focus:ring-1 focus:ring-blue-500"
            aria-label="Select symbol"
          >
            {SYMBOLS.map((s) => (
              <option key={s} value={s}>{s.replace("USDT", "")}</option>
            ))}
          </select>
          <button
            type="button"
            onClick={handleRefetch}
            className="rounded border border-border bg-gray-800 px-2 py-1 text-xs text-gray-400 hover:text-white transition-colors"
            aria-label="Refresh cross-exchange data"
          >
            Refresh
          </button>
        </div>
      </div>

      {/* Spread alert banner */}
      {data?.spread_alert && (
        <div
          className="mb-3 rounded border border-red-500/40 bg-red-500/10 px-3 py-2 text-center"
          role="alert"
          aria-live="polite"
        >
          <p className="text-sm font-bold text-red-400 uppercase tracking-wide">
            VOLATILITY INCOMING
          </p>
          <p className="text-xs text-red-300">
            Spread alert: {data.max_spread_pct.toFixed(3)}% — large cross-exchange divergence detected
          </p>
        </div>
      )}

      {/* Error */}
      {isError && (
        <div className="mb-3 flex items-center justify-between rounded bg-red-500/10 px-3 py-2">
          <span className="text-xs text-red-400">Failed to load exchange data</span>
          <button type="button" onClick={handleRefetch} className="text-xs text-red-400 underline hover:text-red-300">
            Retry
          </button>
        </div>
      )}

      {isLoading && <CrossExchangeSkeleton />}

      {data && (
        <div className="space-y-4">
          {/* Exchange price table */}
          <div className="overflow-x-auto rounded border border-border">
            <table className="w-full text-xs" aria-label="Cross-exchange prices">
              <thead>
                <tr className="border-b border-border bg-gray-800/40">
                  <th className="px-3 py-2 text-left font-medium text-gray-500">Exchange</th>
                  <th className="px-3 py-2 text-right font-medium text-gray-500">Price</th>
                  <th className="px-3 py-2 text-right font-medium text-gray-500">vs Avg</th>
                  <th className="px-3 py-2 text-right font-medium text-gray-500">Role</th>
                </tr>
              </thead>
              <tbody>
                {EXCHANGES.map((exchange) => {
                  const price = data.prices[exchange] ?? data.prices[exchange.toLowerCase()] ?? 0;
                  const spreadPct = avgPrice > 0 ? ((price - avgPrice) / avgPrice) * 100 : 0;
                  const spreadColor = getSpreadColor(Math.abs(spreadPct));
                  const isLeading = exchange.toLowerCase() === data.leading_exchange.toLowerCase();
                  const isLagging = exchange.toLowerCase() === data.lagging_exchange.toLowerCase();

                  return (
                    <tr
                      key={exchange}
                      className={`border-b border-border/50 last:border-0 ${isLeading ? "bg-blue-500/5" : ""}`}
                    >
                      <td className="px-3 py-2">
                        <span className={`font-medium ${isLeading ? "text-blue-400" : "text-gray-300"}`}>
                          {exchange}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-right font-mono font-semibold text-white">
                        {price > 0 ? formatPrice(price) : "—"}
                      </td>
                      <td className={`px-3 py-2 text-right font-mono ${spreadColor}`}>
                        {price > 0
                          ? `${spreadPct >= 0 ? "+" : ""}${spreadPct.toFixed(3)}%`
                          : "—"}
                      </td>
                      <td className="px-3 py-2 text-right">
                        {isLeading && (
                          <span className="rounded bg-blue-500/20 px-1.5 py-0.5 text-[10px] text-blue-400">
                            LEADER
                          </span>
                        )}
                        {isLagging && (
                          <span className="rounded bg-gray-700 px-1.5 py-0.5 text-[10px] text-gray-400">
                            LAGGING
                          </span>
                        )}
                        {!isLeading && !isLagging && (
                          <span className="text-[10px] text-gray-600">—</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Max spread + signal */}
          <div className="grid grid-cols-2 gap-2">
            <div className="rounded bg-gray-800/60 px-3 py-2">
              <p className="text-[10px] text-gray-500">Max Spread</p>
              <p className={`font-mono text-sm font-bold ${getSpreadColor(data.max_spread_pct)}`}>
                {data.max_spread_pct.toFixed(3)}%
              </p>
            </div>
            <div className="rounded bg-gray-800/60 px-3 py-2">
              <p className="text-[10px] text-gray-500">Signal</p>
              <p className={`text-sm font-bold ${signalColor}`}>{data.signal}</p>
            </div>
          </div>

          {/* Alert threshold note */}
          <p className="text-[10px] text-gray-600">
            Alert triggered when spread &gt; {SPREAD_ALERT_THRESHOLD}% | Leading exchange = smart money flow
          </p>
        </div>
      )}
    </div>
  );
}
