/**
 * Liquidation Cascade Risk Panel
 * Shows cascade probability and scenario table for a selected symbol,
 * using GET /api/v1/market/liquidation-cascade/{symbol}.
 */

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import axios from "axios";
import { fmtPct } from "../../lib/format";

type Severity = "LOW" | "MEDIUM" | "HIGH" | "EXTREME";

interface CascadeScenario {
  price_move_pct: number;
  target_price: number;
  direction: "DOWN" | "UP";
  liquidations_usd: number;
  cascade_multiplier: number;
  effective_liquidations_usd: number;
  pct_of_oi: number;
  severity: Severity;
}

interface CascadeData {
  symbol: string;
  current_price: number;
  open_interest_usd: number;
  scenarios: CascadeScenario[];
  nearest_cascade_level: number | null;
  cascade_probability_24h: number;
  downside_risk_pct: number;
  upside_risk_pct: number;
}

const SEVERITY_STYLE: Record<Severity, { bg: string; text: string; bar: string }> = {
  LOW: { bg: "bg-bullish/10", text: "text-bullish", bar: "bg-bullish" },
  MEDIUM: { bg: "bg-amber-400/10", text: "text-amber-400", bar: "bg-amber-400" },
  HIGH: { bg: "bg-orange-500/10", text: "text-orange-400", bar: "bg-orange-500" },
  EXTREME: { bg: "bg-bearish/15", text: "text-bearish", bar: "bg-bearish" },
};

const SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"];

async function fetchCascade(symbol: string): Promise<CascadeData> {
  const { data } = await axios.get<CascadeData>(`/api/v1/market/liquidation-cascade/${symbol}`);
  return data;
}

function CascadeMeter({ probability }: { probability: number }) {
  const pct = Math.round(probability * 100);
  const color = pct >= 60 ? "text-bearish" : pct >= 30 ? "text-amber-400" : "text-bullish";
  const barColor = pct >= 60 ? "bg-bearish" : pct >= 30 ? "bg-amber-400" : "bg-bullish";
  return (
    <div className="flex items-center gap-3">
      <div className="h-2 flex-1 overflow-hidden rounded-full bg-background">
        <div
          className={`h-full rounded-full transition-all duration-500 ${barColor}`}
          style={{ width: `${pct}%` }}
          role="progressbar"
          aria-valuenow={pct}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`Cascade probability: ${pct}%`}
        />
      </div>
      <span className={`w-12 text-right font-mono text-sm font-bold ${color}`}>{pct}%</span>
    </div>
  );
}

export function LiquidationCascadePanel() {
  const [symbol, setSymbol] = useState("BTCUSDT");

  const { data, isLoading, isError } = useQuery({
    queryKey: ["liquidation-cascade", symbol],
    queryFn: () => fetchCascade(symbol),
    refetchInterval: 30_000,
    retry: false,
  });

  // Show only downside scenarios for the table (most critical risk direction)
  const downScenarios = data?.scenarios
    .filter((s) => s.direction === "DOWN")
    .slice(0, 5) ?? [];

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-white">Liquidation Cascade Risk</h2>
        <select
          value={symbol}
          onChange={(e) => { setSymbol(e.target.value); }}
          className="rounded border border-border bg-background px-2 py-1 text-xs text-gray-300 focus:outline-none focus:ring-1 focus:ring-accent"
          aria-label="Select asset"
        >
          {SYMBOLS.map((s) => (
            <option key={s} value={s}>{s.replace("USDT", "")}</option>
          ))}
        </select>
      </div>

      {isError && (
        <p className="mb-3 rounded bg-bearish/10 px-3 py-2 text-xs text-bearish">
          Cascade data unavailable
        </p>
      )}

      {isLoading ? (
        <div className="space-y-2">
          <div className="h-8 animate-pulse rounded bg-white/5" />
          {[...Array(3)].map((_, i) => <div key={i} className="h-5 animate-pulse rounded bg-white/5" />)}
        </div>
      ) : data && (
        <>
          {/* 24h probability meter */}
          <div className="mb-4 rounded border border-border/50 p-3">
            <div className="mb-2 flex items-center justify-between text-xs">
              <span className="font-medium text-gray-300">24h Cascade Probability</span>
              {data.nearest_cascade_level && (
                <span className="text-gray-500">
                  Trigger: ${data.nearest_cascade_level.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                </span>
              )}
            </div>
            <CascadeMeter probability={data.cascade_probability_24h} />
          </div>

          {/* Directional risk summary */}
          <div className="mb-4 grid grid-cols-2 gap-2 text-xs">
            <div className="rounded bg-bearish/10 px-3 py-2 text-center">
              <p className="text-gray-500">Downside OI Risk</p>
              <p className="font-mono font-bold text-bearish">
                {fmtPct(data.downside_risk_pct * 100, { decimals: 1 })}
              </p>
            </div>
            <div className="rounded bg-bullish/10 px-3 py-2 text-center">
              <p className="text-gray-500">Upside OI Risk</p>
              <p className="font-mono font-bold text-bullish">
                {fmtPct(data.upside_risk_pct * 100, { decimals: 1 })}
              </p>
            </div>
          </div>

          {/* Scenario table */}
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border/50">
                  <th className="pb-1.5 text-left font-medium text-gray-500">Move</th>
                  <th className="pb-1.5 text-right font-medium text-gray-500">Liq. $</th>
                  <th className="pb-1.5 text-right font-medium text-gray-500">×</th>
                  <th className="pb-1.5 text-right font-medium text-gray-500">Severity</th>
                </tr>
              </thead>
              <tbody>
                {downScenarios.map((s) => {
                  const st = SEVERITY_STYLE[s.severity];
                  return (
                    <tr key={s.price_move_pct} className="border-b border-border/20">
                      <td className="py-1 text-bearish">
                        {fmtPct(s.price_move_pct, { showSign: true })}
                      </td>
                      <td className="py-1 text-right font-mono text-gray-300">
                        ${(s.effective_liquidations_usd / 1_000_000).toFixed(1)}M
                      </td>
                      <td className="py-1 text-right font-mono text-gray-400">
                        {s.cascade_multiplier.toFixed(2)}x
                      </td>
                      <td className="py-1 text-right">
                        <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${st.bg} ${st.text}`}>
                          {s.severity}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
