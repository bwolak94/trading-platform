/**
 * Portfolio Stress Test Scenarios Panel
 * Simulates portfolio performance under historical crash scenarios
 */

import { useMutation, useQuery } from "@tanstack/react-query";
import axios from "axios";

interface StressScenario {
  name: string;
  description: string;
  estimated_loss_pct: number;
  recovery_time_days: number | null;
  max_drawdown_pct: number;
  simulated: boolean;
}

interface StressTestResponse {
  scenarios: StressScenario[];
  portfolio_value: number;
  last_run: string | null;
}

const PREDEFINED_SCENARIOS = [
  "2020 COVID Crash",
  "2022 LUNA Collapse",
  "2021 China Ban",
  "FTX Collapse",
];

async function fetchStressTest(): Promise<StressTestResponse> {
  const { data } = await axios.get<StressTestResponse>("/api/v1/risk/stress", {
    params: { scenarios: PREDEFINED_SCENARIOS.join(",") },
  });
  return data;
}

async function runStressTest(): Promise<StressTestResponse> {
  const { data } = await axios.post<StressTestResponse>("/api/v1/risk/stress", {
    scenarios: PREDEFINED_SCENARIOS,
  });
  return data;
}

type SeverityLevel = "high" | "medium" | "low";

function getSeverity(lossPct: number): SeverityLevel {
  const abs = Math.abs(lossPct);
  if (abs > 20) return "high";
  if (abs > 10) return "medium";
  return "low";
}

const SEVERITY_STYLES: Record<SeverityLevel, { dot: string; badge: string; text: string }> = {
  high: {
    dot: "bg-bearish",
    badge: "bg-bearish/10 text-bearish border-bearish/30",
    text: "text-bearish",
  },
  medium: {
    dot: "bg-amber-400",
    badge: "bg-amber-400/10 text-amber-400 border-amber-400/30",
    text: "text-amber-400",
  },
  low: {
    dot: "bg-bullish",
    badge: "bg-bullish/10 text-bullish border-bullish/30",
    text: "text-bullish",
  },
};

function ScenarioSkeleton() {
  return (
    <div className="space-y-3">
      {[...Array(4)].map((_, i) => (
        <div key={i} className="h-20 animate-pulse rounded-lg bg-white/5" />
      ))}
    </div>
  );
}

function ScenarioCard({ scenario }: { scenario: StressScenario }) {
  const severity = getSeverity(scenario.estimated_loss_pct);
  const styles = SEVERITY_STYLES[severity];
  const severityLabel = severity === "high" ? "HIGH" : severity === "medium" ? "MEDIUM" : "LOW";

  return (
    <div className={`rounded-lg border p-3 ${styles.badge}`}>
      <div className="mb-2 flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className={`mt-0.5 h-2 w-2 shrink-0 rounded-full ${styles.dot}`} />
          <span className="text-sm font-medium text-white">{scenario.name}</span>
        </div>
        <span className={`shrink-0 rounded border px-1.5 py-0.5 text-[10px] font-bold ${styles.badge}`}>
          {severityLabel}
        </span>
      </div>
      {scenario.description && (
        <p className="mb-2 text-xs text-gray-400">{scenario.description}</p>
      )}
      <div className="grid grid-cols-3 gap-2 text-xs">
        <div>
          <p className="text-gray-500">Est. Loss</p>
          <p className={`font-semibold ${styles.text}`}>
            {scenario.estimated_loss_pct.toFixed(1)}%
          </p>
        </div>
        <div>
          <p className="text-gray-500">Max DD</p>
          <p className="font-semibold text-bearish">{scenario.max_drawdown_pct.toFixed(1)}%</p>
        </div>
        <div>
          <p className="text-gray-500">Recovery</p>
          <p className="font-semibold text-gray-300">
            {scenario.recovery_time_days != null
              ? `${scenario.recovery_time_days}d`
              : "Unknown"}
          </p>
        </div>
      </div>
    </div>
  );
}

export function StressTestScenariosPanel() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["stress-test"],
    queryFn: fetchStressTest,
    retry: false,
  });

  const mutation = useMutation({
    mutationFn: runStressTest,
    onSuccess: () => { void refetch(); },
  });

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-white">Stress Test Scenarios</h2>
          {data?.last_run && (
            <p className="mt-0.5 text-xs text-gray-500">
              Last run: {new Date(data.last_run).toLocaleString()}
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={() => mutation.mutate()}
          disabled={mutation.isPending}
          className="flex items-center gap-1.5 rounded border border-border bg-surface px-3 py-1.5 text-xs font-medium text-gray-300 transition-colors hover:border-accent hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
          aria-label="Run stress test simulation"
        >
          {mutation.isPending ? (
            <>
              <svg
                className="h-3 w-3 animate-spin"
                fill="none"
                viewBox="0 0 24 24"
                aria-hidden="true"
              >
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8v8z"
                />
              </svg>
              Simulating…
            </>
          ) : (
            "Run Simulation"
          )}
        </button>
      </div>

      {isError && !data && (
        <div className="mb-3 rounded bg-bearish/10 px-3 py-2 text-xs text-bearish">
          Stress test data unavailable
        </div>
      )}

      {mutation.isError && (
        <div className="mb-3 rounded bg-bearish/10 px-3 py-2 text-xs text-bearish">
          Simulation failed — check backend connection
        </div>
      )}

      {isLoading ? (
        <ScenarioSkeleton />
      ) : (
        <div className="space-y-2">
          {data?.scenarios.map((scenario) => (
            <ScenarioCard key={scenario.name} scenario={scenario} />
          ))}
          {!data?.scenarios?.length && (
            <p className="py-6 text-center text-xs text-gray-500">
              No scenarios loaded. Click "Run Simulation" to begin.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
