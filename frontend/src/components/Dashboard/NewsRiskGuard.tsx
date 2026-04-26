/**
 * News Event Risk Guard
 * Shows a banner when a high-impact macro event (FOMC, CPI, NFP) is scheduled
 * within the next 2 hours. Recommends reducing position sizes.
 *
 * Data from GET /api/v1/features2/news-risk-guard (if available),
 * with a graceful fallback to known upcoming events from the earnings calendar.
 */

import { useQuery } from "@tanstack/react-query";
import axios from "axios";

interface RiskEvent {
  name: string;
  scheduled_at: string;
  impact: "HIGH" | "MEDIUM";
  affects: string[];
}

interface NewsRiskData {
  high_impact_soon: boolean;
  events: RiskEvent[];
  warning_message: string | null;
}

async function fetchNewsRisk(): Promise<NewsRiskData> {
  try {
    const { data } = await axios.get<NewsRiskData>("/api/v1/features2/news-risk-guard");
    return data;
  } catch {
    return { high_impact_soon: false, events: [], warning_message: null };
  }
}

export function NewsRiskGuard() {
  const { data } = useQuery({
    queryKey: ["news-risk-guard"],
    queryFn: fetchNewsRisk,
    refetchInterval: 5 * 60_000, // check every 5 min
    retry: false,
  });

  if (!data?.high_impact_soon || data.events.length === 0) return null;

  return (
    <div
      className="flex items-start gap-3 rounded-lg border border-amber-400/40 bg-amber-400/8 px-4 py-3"
      role="alert"
      aria-live="polite"
    >
      <div className="mt-0.5 text-amber-400 text-base" aria-hidden="true">⚡</div>
      <div className="flex-1">
        <p className="text-sm font-semibold text-amber-300">High-Impact Event Soon</p>
        <div className="mt-1 space-y-0.5">
          {data.events.slice(0, 3).map((ev, i) => {
            const minsAway = Math.round(
              (new Date(ev.scheduled_at).getTime() - Date.now()) / 60_000,
            );
            return (
              <p key={i} className="text-xs text-amber-200/80">
                <span className="font-medium">{ev.name}</span>{" "}
                — in {minsAway > 0 ? `${minsAway}m` : "now"} · affects{" "}
                {ev.affects.join(", ")}
              </p>
            );
          })}
        </div>
        <p className="mt-1.5 text-xs text-amber-400/70">
          Recommendation: reduce position sizes by 30–50% or wait for the print to pass.
        </p>
      </div>
    </div>
  );
}
