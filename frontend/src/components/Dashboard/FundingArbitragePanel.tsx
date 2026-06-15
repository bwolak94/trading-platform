/**
 * Funding Rate Arbitrage Scanner
 * Shows extreme funding rates as arbitrage opportunities
 */

import { useQuery } from "@tanstack/react-query";
import { useCallback } from "react";
import axios from "axios";

interface ArbitrageOpportunity {
  symbol: string;
  funding_rate: number;
  annualized_rate_pct: number;
  receiving_direction: "LONG" | "SHORT";
  signal_strength: "EXTREME" | "HIGH" | "MODERATE";
  next_funding_time: string | null;
}

interface FundingArbitrageResponse {
  opportunities: ArbitrageOpportunity[];
  updated_at: string;
}

async function fetchFundingArbitrage(): Promise<FundingArbitrageResponse> {
  const { data } = await axios.get<FundingArbitrageResponse>(
    "/api/v1/market/funding-arbitrage",
  );
  return data;
}

type SignalStrength = ArbitrageOpportunity["signal_strength"];

const STRENGTH_STYLES: Record<
  SignalStrength,
  { badge: string; row: string }
> = {
  EXTREME: {
    badge: "bg-bearish/10 text-bearish border-bearish/30",
    row: "border-bearish/20",
  },
  HIGH: {
    badge: "bg-amber-400/10 text-amber-400 border-amber-400/30",
    row: "border-amber-400/20",
  },
  MODERATE: {
    badge: "bg-gray-500/10 text-gray-400 border-gray-500/30",
    row: "border-border/20",
  },
};

function SkeletonRow() {
  return (
    <tr className="border-b border-border/20">
      {[...Array(5)].map((_, i) => (
        <td key={i} className="py-2 px-2">
          <div className="h-3 w-full animate-pulse rounded bg-white/5" />
        </td>
      ))}
    </tr>
  );
}

interface FundingArbitrageProps {
  onViewChart?: (symbol: string) => void;
}

export function FundingArbitragePanel({ onViewChart }: FundingArbitrageProps) {
  const { data, isLoading, isError, dataUpdatedAt } = useQuery({
    queryKey: ["funding-arbitrage"],
    queryFn: fetchFundingArbitrage,
    refetchInterval: 60_000,
    retry: false,
  });

  const opportunities = data?.opportunities ?? [];
  const lastUpdated = dataUpdatedAt
    ? new Date(dataUpdatedAt).toLocaleTimeString()
    : null;

  const handleViewChart = useCallback(
    (symbol: string) => {
      onViewChart?.(symbol);
    },
    [onViewChart],
  );

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-white">Funding Rate Arbitrage</h2>
          {lastUpdated && (
            <p className="mt-0.5 text-xs text-gray-500">Updated: {lastUpdated}</p>
          )}
        </div>
        {isError && (
          <span className="rounded bg-bearish/10 px-2 py-0.5 text-xs text-bearish">
            Offline
          </span>
        )}
      </div>

      {/* Legend */}
      <div className="mb-3 flex gap-3 text-[10px] text-gray-500">
        <span>
          <span className="text-bearish font-bold">EXTREME</span> = &gt;0.1%
        </span>
        <span>
          <span className="text-amber-400 font-bold">HIGH</span> = 0.05–0.1%
        </span>
        <span>
          <span className="font-bold">MOD</span> = &lt;0.05%
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-border/50">
              <th className="pb-1.5 text-left font-medium text-gray-500">Symbol</th>
              <th className="pb-1.5 text-right font-medium text-gray-500">Rate</th>
              <th className="pb-1.5 text-right font-medium text-gray-500">Ann.</th>
              <th className="pb-1.5 text-center font-medium text-gray-500">Receives</th>
              <th className="pb-1.5 text-center font-medium text-gray-500">Strength</th>
              <th className="pb-1.5 text-right font-medium text-gray-500" />
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              [...Array(5)].map((_, i) => <SkeletonRow key={i} />)
            ) : opportunities.length === 0 ? (
              <tr>
                <td colSpan={6} className="py-6 text-center text-gray-500">
                  No notable arbitrage opportunities
                </td>
              </tr>
            ) : (
              opportunities
                .sort((a, b) => Math.abs(b.funding_rate) - Math.abs(a.funding_rate))
                .map((opp) => {
                  const styles = STRENGTH_STYLES[opp.signal_strength];
                  const rateColor =
                    opp.funding_rate > 0 ? "text-bullish" : "text-bearish";

                  return (
                    <tr
                      key={opp.symbol}
                      className={`border-b ${styles.row} hover:bg-white/3`}
                    >
                      <td className="py-2 pr-2 font-medium text-gray-200">
                        {opp.symbol.replace("USDT", "")}
                      </td>
                      <td className={`py-2 text-right ${rateColor}`}>
                        {opp.funding_rate >= 0 ? "+" : ""}
                        {(opp.funding_rate * 100).toFixed(4)}%
                      </td>
                      <td className={`py-2 text-right ${rateColor}`}>
                        {opp.annualized_rate_pct.toFixed(1)}%
                      </td>
                      <td className="py-2 text-center">
                        <span
                          className={
                            opp.receiving_direction === "LONG"
                              ? "text-bullish"
                              : "text-bearish"
                          }
                        >
                          {opp.receiving_direction}
                        </span>
                      </td>
                      <td className="py-2 text-center">
                        <span
                          className={`rounded border px-1.5 py-0.5 text-[9px] font-bold ${styles.badge}`}
                        >
                          {opp.signal_strength}
                        </span>
                      </td>
                      <td className="py-2 pl-2 text-right">
                        {onViewChart && (
                          <button
                            type="button"
                            onClick={() => { handleViewChart(opp.symbol); }}
                            className="rounded border border-border px-1.5 py-0.5 text-[10px] text-gray-400 transition-colors hover:border-accent hover:text-white"
                            aria-label={`View ${opp.symbol} chart`}
                          >
                            Chart
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
