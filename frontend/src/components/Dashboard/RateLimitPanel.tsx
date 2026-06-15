/**
 * E1: API Rate Limit Panel
 *
 * Shows remaining Binance API weight per minute.
 * Red warning when > 80% consumed.
 */

import { useQuery } from "@tanstack/react-query";

interface RateLimitStatus {
  binance_weight_used: number | null;
  binance_weight_limit: number;
  warning: boolean;
  timestamp: string;
}

async function fetchRateLimitStatus(): Promise<RateLimitStatus> {
  const resp = await fetch("/api/v1/monitoring/rate-limits");
  if (!resp.ok) throw new Error("Failed to fetch rate limit status");
  return resp.json();
}

export function RateLimitPanel() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["rate-limits"],
    queryFn: fetchRateLimitStatus,
    staleTime: 30_000,
    refetchInterval: 30_000,
  });

  const used = data?.binance_weight_used ?? null;
  const limit = data?.binance_weight_limit ?? 1200;
  const pct = used !== null ? (used / limit) * 100 : null;
  const warning = data?.warning ?? false;

  return (
    <div className={`rounded-lg border p-4 ${warning ? "border-bearish/50 bg-bearish/5" : "border-border bg-surface"}`}>
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-gray-200">API Rate Limits</h3>
          <p className="text-xs text-gray-400">Binance weight consumption / minute</p>
        </div>
        {warning && (
          <span className="rounded bg-bearish/20 px-2 py-0.5 text-xs font-semibold text-bearish">
            HIGH USAGE
          </span>
        )}
      </div>

      {isLoading && (
        <div className="flex h-16 items-center justify-center text-xs text-gray-500">Loading…</div>
      )}
      {isError && (
        <div className="flex h-16 items-center justify-center text-xs text-gray-500">
          Status unavailable
        </div>
      )}

      {!isLoading && !isError && (
        <div>
          <div className="mb-2 flex justify-between text-xs">
            <span className="text-gray-400">Binance API Weight</span>
            <span className={`font-semibold ${warning ? "text-bearish" : "text-bullish"}`}>
              {used !== null ? `${used} / ${limit}` : "Unknown"}
            </span>
          </div>
          {pct !== null && (
            <div className="h-2 w-full overflow-hidden rounded-full bg-gray-800">
              <div
                className={`h-full rounded-full transition-all ${warning ? "bg-bearish" : pct > 60 ? "bg-amber-500" : "bg-bullish"}`}
                style={{ width: `${pct}%` }}
                role="progressbar"
                aria-valuenow={pct}
                aria-valuemin={0}
                aria-valuemax={100}
              />
            </div>
          )}
          {data?.timestamp && (
            <div className="mt-2 text-right text-[10px] text-gray-500">
              Updated {new Date(data.timestamp).toLocaleTimeString()}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
