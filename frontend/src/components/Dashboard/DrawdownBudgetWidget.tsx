/**
 * Monthly Drawdown Budget Tracker
 * Shows remaining risk budget and position sizing multiplier
 */

import { useQuery } from "@tanstack/react-query";
import axios from "axios";

interface DrawdownBudgetData {
  monthly_budget_pct: number;
  consumed_pct: number;
  remaining_pct: number;
  position_size_multiplier: number;
  budget_reset_date: string;
  recommendation: string;
}

async function fetchDrawdownBudget(): Promise<DrawdownBudgetData> {
  const { data } = await axios.get<DrawdownBudgetData>("/api/v1/risk/drawdown-budget");
  return data;
}

type BudgetStatus = "safe" | "caution" | "critical";

function getBudgetStatus(consumedPct: number, totalBudget: number): BudgetStatus {
  const fraction = consumedPct / totalBudget;
  if (fraction >= 0.75) return "critical";
  if (fraction >= 0.5) return "caution";
  return "safe";
}

const STATUS_STYLES: Record<BudgetStatus, { arc: string; label: string; bg: string }> = {
  safe: { arc: "#22c55e", label: "text-bullish", bg: "bg-bullish/10" },
  caution: { arc: "#f59e0b", label: "text-amber-400", bg: "bg-amber-400/10" },
  critical: { arc: "#ef4444", label: "text-bearish", bg: "bg-bearish/10" },
};

function ArcGauge({
  fraction,
  status,
}: {
  fraction: number;
  status: BudgetStatus;
}) {
  const clamped = Math.min(1, Math.max(0, fraction));
  const styles = STATUS_STYLES[status];

  // SVG arc: use a semi-circle (180 degrees)
  const cx = 60;
  const cy = 60;
  const r = 46;
  const startAngle = Math.PI; // 180deg = left
  const endAngle = 0; // 0deg = right (going counter-clockwise for top arc)

  // Convert fraction to angle (0 = left, 1 = right, going through top)
  const angle = Math.PI - clamped * Math.PI; // from PI to 0
  const x1 = cx + r * Math.cos(Math.PI);
  const y1 = cy + r * Math.sin(Math.PI);
  const x2 = cx + r * Math.cos(angle);
  const y2 = cy + r * Math.sin(angle);

  const largeArc = clamped > 0.5 ? 1 : 0;
  const trackX1 = cx + r * Math.cos(startAngle);
  const trackY1 = cy + r * Math.sin(startAngle);
  const trackX2 = cx + r * Math.cos(endAngle);
  const trackY2 = cy + r * Math.sin(endAngle);

  return (
    <svg viewBox="0 0 120 70" className="w-32" aria-hidden="true">
      {/* Background arc */}
      <path
        d={`M ${trackX1} ${trackY1} A ${r} ${r} 0 0 1 ${trackX2} ${trackY2}`}
        fill="none"
        stroke="rgba(255,255,255,0.05)"
        strokeWidth="10"
        strokeLinecap="round"
      />
      {/* Progress arc */}
      {clamped > 0 && (
        <path
          d={`M ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2}`}
          fill="none"
          stroke={styles.arc}
          strokeWidth="10"
          strokeLinecap="round"
          style={{ transition: "all 0.5s ease" }}
        />
      )}
    </svg>
  );
}

function getDaysUntilReset(resetDate: string): number {
  const reset = new Date(resetDate);
  const now = new Date();
  return Math.max(
    0,
    Math.ceil((reset.getTime() - now.getTime()) / (1000 * 60 * 60 * 24)),
  );
}

export function DrawdownBudgetWidget() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["drawdown-budget"],
    queryFn: fetchDrawdownBudget,
    refetchInterval: 60_000,
    retry: false,
  });

  const consumedFraction = data
    ? data.consumed_pct / data.monthly_budget_pct
    : 0;
  const status = data
    ? getBudgetStatus(data.consumed_pct, data.monthly_budget_pct)
    : "safe";
  const statusStyles = STATUS_STYLES[status];
  const daysUntilReset = data ? getDaysUntilReset(data.budget_reset_date) : null;

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-3 text-sm font-semibold text-white">Drawdown Budget</h2>

      {isError && (
        <div className="mb-3 rounded bg-bearish/10 px-3 py-2 text-xs text-bearish">
          Budget data unavailable
        </div>
      )}

      {isLoading ? (
        <div className="flex flex-col items-center gap-3">
          <div className="h-20 w-32 animate-pulse rounded bg-white/5" />
          <div className="w-full space-y-2">
            {[...Array(3)].map((_, i) => (
              <div key={i} className="h-3 w-full animate-pulse rounded bg-white/5" />
            ))}
          </div>
        </div>
      ) : data ? (
        <>
          {/* Arc gauge + labels */}
          <div className="mb-4 flex flex-col items-center">
            <ArcGauge fraction={consumedFraction} status={status} />
            <div className="mt-1 text-center">
              <p className={`text-2xl font-bold ${statusStyles.label}`}>
                {data.remaining_pct.toFixed(1)}%
              </p>
              <p className="text-xs text-gray-500">remaining budget</p>
            </div>
          </div>

          {/* Stats */}
          <div className="mb-4 grid grid-cols-3 gap-2 text-xs">
            <div className="rounded bg-white/5 p-2 text-center">
              <p className="text-gray-500">Budget</p>
              <p className="font-semibold text-gray-200">{data.monthly_budget_pct}%</p>
            </div>
            <div className="rounded bg-white/5 p-2 text-center">
              <p className="text-gray-500">Consumed</p>
              <p className={`font-semibold ${statusStyles.label}`}>
                {data.consumed_pct.toFixed(1)}%
              </p>
            </div>
            <div className="rounded bg-white/5 p-2 text-center">
              <p className="text-gray-500">Multiplier</p>
              <p
                className={`font-bold ${
                  data.position_size_multiplier < 1 ? "text-amber-400" : "text-bullish"
                }`}
              >
                {data.position_size_multiplier.toFixed(1)}x
              </p>
            </div>
          </div>

          {/* Recommendation */}
          <div className={`mb-3 rounded px-3 py-2 text-xs ${statusStyles.bg}`}>
            <span className={statusStyles.label}>Recommendation: </span>
            <span className="text-gray-300">{data.recommendation}</span>
          </div>

          {/* Reset date */}
          {daysUntilReset !== null && (
            <p className="text-center text-xs text-gray-500">
              Budget resets in {daysUntilReset} day{daysUntilReset !== 1 ? "s" : ""} —{" "}
              {new Date(data.budget_reset_date).toLocaleDateString([], {
                month: "short",
                day: "numeric",
              })}
            </p>
          )}
        </>
      ) : null}
    </div>
  );
}
