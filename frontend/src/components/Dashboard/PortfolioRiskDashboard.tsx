/**
 * PortfolioRiskDashboard
 * Unified portfolio risk view with all open positions and real-time risk metrics.
 * Shows positions table, portfolio heat bar, correlation warnings, and kill switch gauge.
 */

import { useQuery } from "@tanstack/react-query";
import { useCallback } from "react";
import axios from "axios";

// --------------- Types ---------------

interface Position {
  id: string;
  symbol: string;
  direction: string;
  entry_price: number;
  current_price: number;
  unrealized_pnl_pct: number;
  stop_loss: number;
  distance_to_sl_pct: number;
  funding_rate: number;
  quantity: number;
  notional_usd: number;
}

interface PortfolioHeat {
  capital_at_risk_pct: number;
  kill_switch_threshold_pct: number;
  correlation_warnings: CorrelationWarning[];
}

interface CorrelationWarning {
  symbol_a: string;
  symbol_b: string;
  correlation: number;
}

interface CircuitBreaker {
  can_trade: boolean;
  is_triggered: boolean;
  consecutive_losses: number;
  position_scale: number;
  message: string;
}

// --------------- Fetch helpers ---------------

async function fetchPositions(): Promise<Position[]> {
  const { data } = await axios.get<Position[]>("/api/v1/simulation/positions");
  return data;
}

async function fetchPortfolioHeat(): Promise<PortfolioHeat> {
  const { data } = await axios.get<PortfolioHeat>("/api/v1/risk-advanced/portfolio");
  return data;
}

async function fetchCircuitBreaker(): Promise<CircuitBreaker> {
  const { data } = await axios.get<CircuitBreaker>("/api/v1/features2/streak-status");
  return data;
}

// --------------- Sub-components ---------------

function SkeletonRow() {
  return (
    <tr>
      {[...Array(7)].map((_, i) => (
        <td key={i} className="px-3 py-2">
          <div className="h-3 w-full animate-pulse rounded bg-white/5" />
        </td>
      ))}
    </tr>
  );
}

function HeatBar({ pct, threshold }: { pct: number; threshold: number }) {
  const fraction = Math.min(pct / threshold, 1);
  const color =
    fraction >= 0.9
      ? "bg-red-500"
      : fraction >= 0.65
        ? "bg-yellow-500"
        : "bg-green-500";

  return (
    <div className="mb-4">
      <div className="mb-1 flex items-center justify-between text-xs">
        <span className="font-semibold text-gray-300">Portfolio Heat</span>
        <span
          className={
            fraction >= 0.9
              ? "font-bold text-red-400"
              : fraction >= 0.65
                ? "font-bold text-yellow-400"
                : "font-bold text-green-400"
          }
        >
          {pct.toFixed(1)}% of capital at risk
        </span>
      </div>
      <div
        className="h-3 w-full overflow-hidden rounded-full bg-gray-700"
        role="progressbar"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={threshold}
        aria-label="Portfolio capital at risk"
      >
        <div
          className={`h-full rounded-full transition-all duration-500 ${color}`}
          style={{ width: `${fraction * 100}%` }}
        />
      </div>
      <div className="mt-0.5 flex justify-end text-[10px] text-gray-500">
        Kill switch at {threshold}%
      </div>
    </div>
  );
}

function KillSwitchGauge({
  pct,
  threshold,
}: {
  pct: number;
  threshold: number;
}) {
  const proximity = Math.min((pct / threshold) * 100, 100);
  const isProximate = proximity >= 75;

  return (
    <div className="rounded border border-border bg-gray-800/60 px-3 py-2">
      <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-gray-500">
        Kill Switch Proximity
      </p>
      <div className="flex items-center gap-2">
        <div className="relative h-2 flex-1 overflow-hidden rounded-full bg-gray-700">
          <div
            className={`h-full rounded-full transition-all duration-500 ${
              proximity >= 90
                ? "animate-pulse bg-red-500"
                : isProximate
                  ? "bg-orange-500"
                  : "bg-green-500"
            }`}
            style={{ width: `${proximity}%` }}
          />
        </div>
        <span
          className={`w-10 text-right text-xs font-mono font-bold ${
            proximity >= 90
              ? "text-red-400"
              : isProximate
                ? "text-orange-400"
                : "text-green-400"
          }`}
        >
          {proximity.toFixed(0)}%
        </span>
      </div>
    </div>
  );
}

// --------------- Main Component ---------------

export default function PortfolioRiskDashboard() {
  const {
    data: positions,
    isLoading: positionsLoading,
    isError: positionsError,
    refetch: refetchPositions,
  } = useQuery<Position[]>({
    queryKey: ["portfolio-positions"],
    queryFn: fetchPositions,
    refetchInterval: 30_000,
    retry: 2,
  });

  const { data: heat } = useQuery<PortfolioHeat>({
    queryKey: ["portfolio-heat"],
    queryFn: fetchPortfolioHeat,
    refetchInterval: 30_000,
    retry: 2,
  });

  const { data: circuit } = useQuery<CircuitBreaker>({
    queryKey: ["streak-status"],
    queryFn: fetchCircuitBreaker,
    refetchInterval: 30_000,
    retry: 2,
  });

  const handleRetry = useCallback(() => {
    void refetchPositions();
  }, [refetchPositions]);

  const totalPnlPct =
    positions && positions.length > 0
      ? positions.reduce((acc, p) => acc + p.unrealized_pnl_pct, 0) /
        positions.length
      : 0;

  return (
    <div className="rounded-lg border border-border bg-gray-900 p-4">
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-white">
            Portfolio Risk Dashboard
          </h2>
          <p className="text-[10px] text-gray-500">
            {positions?.length ?? 0} open position
            {(positions?.length ?? 0) !== 1 ? "s" : ""} · auto-refresh 30s
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={`text-xs font-mono font-bold ${
              totalPnlPct >= 0 ? "text-green-400" : "text-red-400"
            }`}
          >
            {totalPnlPct >= 0 ? "+" : ""}
            {totalPnlPct.toFixed(2)}% avg P&L
          </span>
          {circuit && !circuit.can_trade && (
            <span className="animate-pulse rounded bg-red-500/20 px-2 py-0.5 text-[10px] font-bold uppercase text-red-400">
              Circuit Breaker Active
            </span>
          )}
        </div>
      </div>

      {/* Portfolio heat bar */}
      {heat && (
        <HeatBar
          pct={heat.capital_at_risk_pct}
          threshold={heat.kill_switch_threshold_pct}
        />
      )}

      {/* Correlation warnings */}
      {heat && heat.correlation_warnings.length > 0 && (
        <div className="mb-4 rounded border border-yellow-500/30 bg-yellow-500/10 px-3 py-2">
          <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-yellow-400">
            Correlation Warnings
          </p>
          {heat.correlation_warnings.map((w) => (
            <p key={`${w.symbol_a}-${w.symbol_b}`} className="text-xs text-yellow-300">
              {w.symbol_a} / {w.symbol_b} are{" "}
              <span className="font-bold">{(w.correlation * 100).toFixed(0)}%</span>{" "}
              correlated — concentrated risk
            </p>
          ))}
        </div>
      )}

      {/* Error state */}
      {positionsError && (
        <div className="mb-3 flex items-center justify-between rounded bg-red-500/10 px-3 py-2">
          <span className="text-xs text-red-400">Failed to load positions</span>
          <button
            type="button"
            onClick={handleRetry}
            className="text-xs text-red-400 underline hover:text-red-300"
            aria-label="Retry loading positions"
          >
            Retry
          </button>
        </div>
      )}

      {/* Positions table */}
      <div className="mb-4 overflow-x-auto rounded border border-border">
        <table className="w-full min-w-[640px] text-xs">
          <thead>
            <tr className="border-b border-border bg-gray-800/80">
              <th className="px-3 py-2 text-left font-semibold text-gray-400">
                Symbol
              </th>
              <th className="px-3 py-2 text-left font-semibold text-gray-400">
                Dir
              </th>
              <th className="px-3 py-2 text-right font-semibold text-gray-400">
                Entry
              </th>
              <th className="px-3 py-2 text-right font-semibold text-gray-400">
                P&L %
              </th>
              <th className="px-3 py-2 text-right font-semibold text-gray-400">
                SL Dist
              </th>
              <th className="px-3 py-2 text-right font-semibold text-gray-400">
                Funding/8h
              </th>
              <th className="px-3 py-2 text-right font-semibold text-gray-400">
                Notional
              </th>
            </tr>
          </thead>
          <tbody>
            {positionsLoading &&
              [...Array(3)].map((_, i) => <SkeletonRow key={i} />)}

            {!positionsLoading &&
              positions &&
              positions.length === 0 && (
                <tr>
                  <td
                    colSpan={7}
                    className="px-3 py-6 text-center text-gray-500"
                  >
                    No open positions
                  </td>
                </tr>
              )}

            {positions?.map((pos) => {
              const criticalSL = Math.abs(pos.distance_to_sl_pct) < 1;
              return (
                <tr
                  key={pos.id}
                  className="border-b border-border/50 hover:bg-gray-800/40"
                >
                  <td className="px-3 py-2 font-semibold text-white">
                    {pos.symbol}
                  </td>
                  <td className="px-3 py-2">
                    <span
                      className={`rounded px-1.5 py-0.5 text-[10px] font-bold uppercase ${
                        pos.direction === "LONG"
                          ? "bg-green-500/20 text-green-400"
                          : "bg-red-500/20 text-red-400"
                      }`}
                    >
                      {pos.direction}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-gray-300">
                    {pos.entry_price.toLocaleString()}
                  </td>
                  <td
                    className={`px-3 py-2 text-right font-mono font-bold ${
                      pos.unrealized_pnl_pct >= 0
                        ? "text-green-400"
                        : "text-red-400"
                    }`}
                  >
                    {pos.unrealized_pnl_pct >= 0 ? "+" : ""}
                    {pos.unrealized_pnl_pct.toFixed(2)}%
                  </td>
                  <td
                    className={`px-3 py-2 text-right font-mono ${
                      criticalSL
                        ? "animate-pulse font-bold text-red-500"
                        : "text-gray-300"
                    }`}
                  >
                    {Math.abs(pos.distance_to_sl_pct).toFixed(2)}%
                  </td>
                  <td
                    className={`px-3 py-2 text-right font-mono ${
                      pos.funding_rate > 0.01
                        ? "text-red-400"
                        : pos.funding_rate < -0.005
                          ? "text-green-400"
                          : "text-gray-400"
                    }`}
                  >
                    {pos.funding_rate >= 0 ? "+" : ""}
                    {(pos.funding_rate * 100).toFixed(4)}%
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-gray-300">
                    ${pos.notional_usd.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Kill switch gauge */}
      {heat && (
        <KillSwitchGauge
          pct={heat.capital_at_risk_pct}
          threshold={heat.kill_switch_threshold_pct}
        />
      )}
    </div>
  );
}
