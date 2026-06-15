/**
 * C2: Time-Based Stop Exit Tracker
 *
 * Flags positions open longer than N hours without reaching TP.
 * Configurable N per asset.  Research shows time stops reduce max adverse excursion.
 */

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

interface TimeStopAlert {
  position_id: string;
  asset: string;
  direction: string;
  open_hours: number;
  time_limit_hours: number;
  unrealized_pnl_pct: number;
  urgency: "WARNING" | "CRITICAL";
}

async function fetchTimeStopAlerts(limitHours: number): Promise<TimeStopAlert[]> {
  const resp = await fetch(`/api/v1/risk/time-stop-alerts?limit_hours=${limitHours}`);
  if (!resp.ok) throw new Error("Failed to fetch time stop alerts");
  return resp.json();
}

export function TimeStopPanel() {
  const [limitHours, setLimitHours] = useState(24);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["time-stop-alerts", limitHours],
    queryFn: () => fetchTimeStopAlerts(limitHours),
    staleTime: 60_000,
    refetchInterval: 120_000,
  });

  const criticals = (data ?? []).filter((a) => a.urgency === "CRITICAL");
  const warnings = (data ?? []).filter((a) => a.urgency === "WARNING");

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-gray-200">Time Stop Tracker</h3>
          <p className="text-xs text-gray-400">Positions exceeding hold-time limit</p>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-xs text-gray-500" htmlFor="time-limit">Limit (h)</label>
          <select
            id="time-limit"
            value={limitHours}
            onChange={(e) => { setLimitHours(Number(e.target.value)); }}
            className="rounded border border-border bg-background px-1.5 py-0.5 text-xs text-gray-300"
          >
            {[8, 12, 24, 48, 72].map((h) => (
              <option key={h} value={h}>{h}h</option>
            ))}
          </select>
        </div>
      </div>

      <div className="mb-2 flex gap-3 text-xs">
        <span className="text-bearish font-semibold">Critical: {criticals.length}</span>
        <span className="text-amber-400 font-semibold">Warning: {warnings.length}</span>
      </div>

      {isLoading && (
        <div className="flex h-28 items-center justify-center text-xs text-gray-500">Loading…</div>
      )}
      {isError && (
        <div className="flex h-28 items-center justify-center text-xs text-bearish">
          Failed to load alerts
        </div>
      )}

      {!isLoading && !isError && (
        <div className="space-y-2 max-h-64 overflow-y-auto">
          {(data ?? []).length === 0 ? (
            <div className="py-6 text-center text-xs text-gray-500">
              No positions exceeding {limitHours}h
            </div>
          ) : (
            (data ?? []).map((alert) => (
              <div
                key={alert.position_id}
                className={`rounded border p-3 ${
                  alert.urgency === "CRITICAL"
                    ? "border-bearish/40 bg-bearish/5"
                    : "border-amber-500/30 bg-amber-500/5"
                }`}
              >
                <div className="flex justify-between text-xs">
                  <span className="font-semibold text-gray-200">{alert.asset}</span>
                  <span className={`font-semibold ${alert.direction === "LONG" ? "text-bullish" : "text-bearish"}`}>
                    {alert.direction}
                  </span>
                </div>
                <div className="mt-1 grid grid-cols-3 gap-1 text-[10px] text-gray-400">
                  <div>Open: <span className="text-gray-300">{alert.open_hours.toFixed(1)}h</span></div>
                  <div>Limit: <span className="text-gray-300">{alert.time_limit_hours}h</span></div>
                  <div>
                    P&L:{" "}
                    <span className={alert.unrealized_pnl_pct >= 0 ? "text-bullish" : "text-bearish"}>
                      {alert.unrealized_pnl_pct >= 0 ? "+" : ""}
                      {alert.unrealized_pnl_pct.toFixed(2)}%
                    </span>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
