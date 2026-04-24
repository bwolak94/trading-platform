/**
 * CarryOptimizerPanel
 * Shows top carry trade opportunities ranked by annual yield.
 * Fetches from GET /api/v1/features2/carry-optimizer
 */

import { useQuery } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import axios from "axios";

// --------------- Types ---------------

interface CarryOpportunity {
  symbol: string;
  funding_8h_pct: number;
  annual_yield_pct: number;
  monthly_pct: number;
  position: string;
  risk_adjusted: number;
  volatility_pct?: number;
  net_yield_pct?: number;
  funding_flipped?: boolean;
}

interface CarryResponse {
  opportunities: CarryOpportunity[];
  portfolio_yield_pct: number;
  updated_at: string;
}

// --------------- Fetch helper ---------------

async function fetchCarryOptimizer(): Promise<CarryResponse> {
  const { data } = await axios.get<CarryResponse>(
    "/api/v1/features2/carry-optimizer",
  );
  return data;
}

// --------------- Helpers ---------------

function getYieldColor(annualYield: number): string {
  if (annualYield >= 20) return "text-green-400";
  if (annualYield >= 10) return "text-yellow-400";
  return "text-gray-400";
}

function getRiskAdjColor(score: number): string {
  if (score >= 0.7) return "text-green-400";
  if (score >= 0.4) return "text-yellow-400";
  return "text-red-400";
}

// --------------- Skeleton ---------------

function CarrySkeleton() {
  return (
    <div className="space-y-2" aria-busy="true" aria-label="Loading carry opportunities">
      {[...Array(3)].map((_, i) => (
        <div key={i} className="h-12 animate-pulse rounded border border-gray-700 bg-white/5" />
      ))}
      <div className="h-14 animate-pulse rounded border border-gray-700 bg-white/5" />
    </div>
  );
}

// --------------- Expanded detail row ---------------

function DetailRow({ opp }: { opp: CarryOpportunity }) {
  return (
    <div className="mt-1 rounded bg-gray-800/60 px-3 py-2 text-[10px] space-y-1">
      <div className="flex justify-between">
        <span className="text-gray-500">Volatility</span>
        <span className="font-mono text-gray-300">
          {opp.volatility_pct != null
            ? `${opp.volatility_pct.toFixed(2)}%`
            : "N/A"}
        </span>
      </div>
      <div className="flex justify-between">
        <span className="text-gray-500">Net yield (after costs)</span>
        <span className="font-mono text-gray-300">
          {opp.net_yield_pct != null
            ? `${opp.net_yield_pct.toFixed(2)}%`
            : "N/A"}
        </span>
      </div>
      {opp.funding_flipped && (
        <div className="flex items-center gap-1 text-orange-400 font-semibold">
          <span aria-hidden="true">⚠</span>
          <span>Funding flipped — consider unwinding</span>
        </div>
      )}
    </div>
  );
}

// --------------- Main Component ---------------

export default function CarryOptimizerPanel() {
  const [expandedSymbol, setExpandedSymbol] = useState<string | null>(null);

  const { data, isLoading, isError, refetch } = useQuery<CarryResponse>({
    queryKey: ["carry-optimizer"],
    queryFn: fetchCarryOptimizer,
    refetchInterval: 5 * 60_000, // 5 minutes
    retry: 2,
  });

  const handleRetry = useCallback(() => {
    void refetch();
  }, [refetch]);

  const toggleExpand = useCallback((symbol: string) => {
    setExpandedSymbol((prev) => (prev === symbol ? null : symbol));
  }, []);

  const top3 = data?.opportunities.slice(0, 3) ?? [];

  return (
    <div className="rounded-lg border border-border bg-gray-900 p-4">
      {/* Header */}
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-white">
            Carry Trade Opportunities
          </h2>
          {data?.updated_at && (
            <p className="text-[10px] text-gray-500">
              Updated{" "}
              {new Date(data.updated_at).toLocaleTimeString([], {
                hour: "2-digit",
                minute: "2-digit",
              })}
              {" · "}refresh 5m
            </p>
          )}
        </div>
      </div>

      {/* Error */}
      {isError && (
        <div className="mb-3 flex items-center justify-between rounded bg-red-500/10 px-3 py-2">
          <span className="text-xs text-red-400">
            Failed to load carry opportunities
          </span>
          <button
            type="button"
            onClick={handleRetry}
            className="text-xs text-red-400 underline hover:text-red-300"
            aria-label="Retry loading carry opportunities"
          >
            Retry
          </button>
        </div>
      )}

      {isLoading && <CarrySkeleton />}

      {data && (
        <div className="space-y-3">
          {/* Opportunities table */}
          <div className="overflow-x-auto rounded border border-border">
            <table className="w-full min-w-[480px] text-xs">
              <thead>
                <tr className="border-b border-border bg-gray-800/80">
                  <th className="px-3 py-2 text-left font-semibold text-gray-400">
                    Symbol
                  </th>
                  <th className="px-3 py-2 text-right font-semibold text-gray-400">
                    8h Rate
                  </th>
                  <th className="px-3 py-2 text-right font-semibold text-gray-400">
                    Annual
                  </th>
                  <th className="px-3 py-2 text-right font-semibold text-gray-400">
                    Monthly
                  </th>
                  <th className="px-3 py-2 text-right font-semibold text-gray-400">
                    Position
                  </th>
                  <th className="px-3 py-2 text-right font-semibold text-gray-400">
                    Risk Adj
                  </th>
                </tr>
              </thead>
              <tbody>
                {top3.length === 0 && (
                  <tr>
                    <td
                      colSpan={6}
                      className="px-3 py-6 text-center text-gray-500"
                    >
                      No opportunities available
                    </td>
                  </tr>
                )}
                {top3.map((opp) => (
                  <>
                    <tr
                      key={opp.symbol}
                      className="cursor-pointer border-b border-border/50 hover:bg-gray-800/40"
                      onClick={() => toggleExpand(opp.symbol)}
                      role="button"
                      aria-expanded={expandedSymbol === opp.symbol}
                      aria-label={`Toggle details for ${opp.symbol}`}
                      tabIndex={0}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          toggleExpand(opp.symbol);
                        }
                      }}
                    >
                      <td className="px-3 py-2">
                        <div className="flex items-center gap-1.5">
                          {opp.funding_flipped && (
                            <span
                              className="text-orange-400"
                              title="Funding flipped — consider unwinding"
                              aria-label="Warning: funding flipped"
                            >
                              ⚠
                            </span>
                          )}
                          <span className="font-semibold text-white">
                            {opp.symbol}
                          </span>
                        </div>
                      </td>
                      <td
                        className={`px-3 py-2 text-right font-mono ${
                          opp.funding_8h_pct >= 0
                            ? "text-green-400"
                            : "text-red-400"
                        }`}
                      >
                        {opp.funding_8h_pct >= 0 ? "+" : ""}
                        {opp.funding_8h_pct.toFixed(4)}%
                      </td>
                      <td
                        className={`px-3 py-2 text-right font-mono font-bold ${getYieldColor(opp.annual_yield_pct)}`}
                      >
                        {opp.annual_yield_pct.toFixed(1)}%
                      </td>
                      <td className="px-3 py-2 text-right font-mono text-gray-300">
                        {opp.monthly_pct.toFixed(2)}%
                      </td>
                      <td className="px-3 py-2 text-right">
                        <span
                          className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${
                            opp.position === "LONG"
                              ? "bg-green-500/15 text-green-400"
                              : "bg-red-500/15 text-red-400"
                          }`}
                        >
                          {opp.position}
                        </span>
                      </td>
                      <td
                        className={`px-3 py-2 text-right font-mono font-bold ${getRiskAdjColor(opp.risk_adjusted)}`}
                      >
                        {opp.risk_adjusted.toFixed(2)}
                      </td>
                    </tr>
                    {expandedSymbol === opp.symbol && (
                      <tr key={`${opp.symbol}-detail`}>
                        <td colSpan={6} className="px-3 pb-2">
                          <DetailRow opp={opp} />
                        </td>
                      </tr>
                    )}
                  </>
                ))}
              </tbody>
            </table>
          </div>

          {/* Portfolio yield summary */}
          <div className="rounded border border-green-500/30 bg-green-500/10 px-4 py-3">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-500">
                  Estimated Portfolio Yield
                </p>
                <p className="text-xs text-gray-400">
                  Based on top carry positions combined
                </p>
              </div>
              <span className="font-mono text-2xl font-bold text-green-400">
                +{data.portfolio_yield_pct.toFixed(2)}%
                <span className="ml-1 text-xs text-gray-500">/yr</span>
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
