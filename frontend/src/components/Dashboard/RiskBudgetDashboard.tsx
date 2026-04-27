/**
 * C7: Risk Budget Dashboard
 *
 * Live view of four risk gauges:
 *   - Daily loss budget used %
 *   - Per-asset exposure %
 *   - Correlated exposure %
 *   - Drawdown budget remaining %
 */

import { useQuery } from "@tanstack/react-query";

interface RiskBudgetData {
  daily_loss_used_pct: number;
  daily_loss_limit_pct: number;
  max_single_asset_exposure_pct: number;
  current_max_exposure_pct: number;
  correlated_exposure_pct: number;
  correlated_exposure_limit_pct: number;
  drawdown_remaining_pct: number;
  drawdown_limit_pct: number;
}

async function fetchRiskBudget(): Promise<RiskBudgetData> {
  const resp = await fetch("/api/v1/risk/budget");
  if (!resp.ok) throw new Error("Failed to fetch risk budget");
  return resp.json();
}

interface GaugeProps {
  label: string;
  used: number;
  limit: number;
  inverted?: boolean; // for "remaining" metrics where high is good
}

function Gauge({ label, used, limit, inverted = false }: GaugeProps) {
  const pct = limit > 0 ? Math.min((used / limit) * 100, 100) : 0;
  const danger = inverted ? pct < 30 : pct > 80;
  const warn = inverted ? pct < 50 : pct > 60;

  const barColor = danger
    ? "bg-bearish"
    : warn
    ? "bg-amber-500"
    : "bg-bullish";

  return (
    <div className="rounded border border-border bg-background/50 p-3">
      <div className="mb-1 flex justify-between text-xs">
        <span className="text-gray-400">{label}</span>
        <span className={`font-semibold ${danger ? "text-bearish" : warn ? "text-amber-400" : "text-bullish"}`}>
          {inverted ? `${used.toFixed(1)}% left` : `${pct.toFixed(0)}%`}
        </span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-gray-800">
        <div
          className={`h-full rounded-full transition-all duration-500 ${barColor}`}
          style={{ width: `${inverted ? 100 - pct : pct}%` }}
          role="progressbar"
          aria-valuenow={pct}
          aria-valuemin={0}
          aria-valuemax={100}
        />
      </div>
      <div className="mt-1 text-[10px] text-gray-500">
        {inverted
          ? `${used.toFixed(1)}% / ${limit.toFixed(1)}% limit`
          : `${used.toFixed(1)}% used of ${limit.toFixed(1)}% limit`}
      </div>
    </div>
  );
}

export function RiskBudgetDashboard() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["risk-budget"],
    queryFn: fetchRiskBudget,
    staleTime: 30_000,
    refetchInterval: 60_000,
  });

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h3 className="mb-3 text-sm font-semibold text-gray-200">Risk Budget</h3>

      {isLoading && (
        <div className="flex h-40 items-center justify-center text-xs text-gray-500">Loading…</div>
      )}
      {isError && (
        <div className="flex h-40 items-center justify-center text-xs text-bearish">
          Failed to load risk data
        </div>
      )}

      {!isLoading && !isError && data && (
        <div className="grid grid-cols-2 gap-3">
          <Gauge
            label="Daily Loss Budget"
            used={data.daily_loss_used_pct}
            limit={data.daily_loss_limit_pct}
          />
          <Gauge
            label="Max Asset Exposure"
            used={data.current_max_exposure_pct}
            limit={data.max_single_asset_exposure_pct}
          />
          <Gauge
            label="Correlated Exposure"
            used={data.correlated_exposure_pct}
            limit={data.correlated_exposure_limit_pct}
          />
          <Gauge
            label="Drawdown Remaining"
            used={data.drawdown_remaining_pct}
            limit={data.drawdown_limit_pct}
            inverted
          />
        </div>
      )}
    </div>
  );
}
