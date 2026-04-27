/**
 * C1: Breakeven Stop Panel
 *
 * Shows open positions that have reached 1R profit and should have their
 * stop moved to breakeven.  Backend calculates which positions qualify;
 * frontend shows the alert so the trader can act.
 */

import { useQuery } from "@tanstack/react-query";

interface BreakevenAlert {
  position_id: string;
  asset: string;
  direction: string;
  entry_price: number;
  current_price: number;
  r_multiple: number;
  stop_loss: number;
  breakeven_price: number;
  action_needed: boolean;
}

async function fetchBreakevenAlerts(): Promise<BreakevenAlert[]> {
  const resp = await fetch("/api/v1/risk/breakeven-alerts");
  if (!resp.ok) throw new Error("Failed to fetch breakeven alerts");
  return resp.json();
}

export function BreakevenStopPanel() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["breakeven-alerts"],
    queryFn: fetchBreakevenAlerts,
    staleTime: 30_000,
    refetchInterval: 60_000,
  });

  const actionRequired = (data ?? []).filter((a) => a.action_needed);

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-gray-200">Breakeven Stop Alerts</h3>
          <p className="text-xs text-gray-400">
            Positions at 1R+ profit — move stop to breakeven
          </p>
        </div>
        {actionRequired.length > 0 && (
          <span className="rounded bg-amber-500/20 px-2 py-0.5 text-xs font-semibold text-amber-400">
            {actionRequired.length} action{actionRequired.length !== 1 ? "s" : ""}
          </span>
        )}
      </div>

      {isLoading && (
        <div className="flex h-28 items-center justify-center text-xs text-gray-500">Loading…</div>
      )}
      {isError && (
        <div className="flex h-28 items-center justify-center text-xs text-bearish">
          Failed to load alerts
        </div>
      )}

      {!isLoading && !isError && data && data.length === 0 && (
        <div className="flex h-28 items-center justify-center text-xs text-gray-500">
          No positions at 1R+ yet
        </div>
      )}

      {!isLoading && !isError && data && data.length > 0 && (
        <div className="space-y-2">
          {data.map((alert) => (
            <div
              key={alert.position_id}
              className={`rounded border p-3 ${
                alert.action_needed
                  ? "border-amber-500/40 bg-amber-500/5"
                  : "border-border bg-background/40"
              }`}
            >
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-semibold text-gray-200">{alert.asset}</span>
                <span className={`text-xs font-semibold ${alert.direction === "LONG" ? "text-bullish" : "text-bearish"}`}>
                  {alert.direction}
                </span>
                <span className="text-xs text-amber-400 font-mono">
                  {alert.r_multiple.toFixed(2)}R
                </span>
              </div>
              <div className="grid grid-cols-3 gap-2 text-[10px] text-gray-400">
                <div>
                  <div>Entry</div>
                  <div className="font-mono text-gray-300">${alert.entry_price.toLocaleString()}</div>
                </div>
                <div>
                  <div>Current</div>
                  <div className="font-mono text-gray-300">${alert.current_price.toLocaleString()}</div>
                </div>
                <div>
                  <div>Move SL to</div>
                  <div className="font-mono text-bullish">${alert.breakeven_price.toLocaleString()}</div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
