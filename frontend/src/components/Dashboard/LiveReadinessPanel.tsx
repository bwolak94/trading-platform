import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchSimulationPerformance } from "../../api/client";

// ------------------------------------------------------------------ //
// Types & constants                                                    //
// ------------------------------------------------------------------ //

interface PerfData {
  total_trades: number;
  win_rate: number;
  sharpe_ratio: number;
  max_drawdown_pct: number;
  profit_factor: number;
}

interface ChecklistItem {
  id: string;
  label: string;
  description: string;
  passes: (p: PerfData) => boolean;
  fmt: (p: PerfData) => string;
  target: string;
}

const CHECKLIST: ChecklistItem[] = [
  {
    id: "trades",
    label: "Minimum Trades",
    description: "At least 100 completed trades for statistical significance",
    passes: (p) => p.total_trades >= 100,
    fmt: (p) => `${p.total_trades} trades`,
    target: "\u2265 100",
  },
  {
    id: "winrate",
    label: "Win Rate",
    description: "Win rate above 55% demonstrates edge",
    passes: (p) => p.win_rate >= 0.55,
    fmt: (p) => `${(p.win_rate * 100).toFixed(1)}%`,
    target: "\u2265 55%",
  },
  {
    id: "sharpe",
    label: "Sharpe Ratio",
    description: "Risk-adjusted return above 1.0",
    passes: (p) => p.sharpe_ratio >= 1.0,
    fmt: (p) => p.sharpe_ratio.toFixed(2),
    target: "\u2265 1.0",
  },
  {
    id: "drawdown",
    label: "Max Drawdown",
    description: "Maximum drawdown below 15%",
    passes: (p) => p.max_drawdown_pct < 15,
    fmt: (p) => `${p.max_drawdown_pct.toFixed(1)}%`,
    target: "< 15%",
  },
  {
    id: "profit_factor",
    label: "Profit Factor",
    description: "Gross profits exceed gross losses by 1.5\u00d7",
    passes: (p) => p.profit_factor >= 1.5,
    fmt: (p) => p.profit_factor.toFixed(2),
    target: "\u2265 1.5",
  },
];

const GO_LIVE_STEPS: { step: number; text: string }[] = [
  { step: 1, text: "Export positions CSV for review" },
  { step: 2, text: "Test strategy on smaller account first" },
  { step: 3, text: "Configure proper exchange API keys" },
  {
    step: 4,
    text: "Set conservative position sizes for first 2 weeks",
  },
  {
    step: 5,
    text: "Monitor for 30 days before full deployment",
  },
];

// ------------------------------------------------------------------ //
// HowToGoLive expandable section                                      //
// ------------------------------------------------------------------ //

function HowToGoLive() {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="rounded-lg border border-border/50 bg-surface/20">
      <button
        type="button"
        onClick={() => { setExpanded((p) => !p); }}
        className="flex w-full items-center justify-between px-4 py-3 text-sm font-medium text-foreground hover:bg-surface/40"
        aria-expanded={expanded}
        aria-controls="go-live-steps"
      >
        <span>How to go live</span>
        <span
          className={`text-xs text-muted-foreground transition-transform duration-200 ${expanded ? "rotate-180" : ""}`}
          aria-hidden="true"
        >
          &#9660;
        </span>
      </button>

      {expanded && (
        <ol
          id="go-live-steps"
          className="flex flex-col gap-2 border-t border-border/40 px-4 pb-4 pt-3"
          aria-label="Steps to go live"
        >
          {GO_LIVE_STEPS.map(({ step, text }) => (
            <li key={step} className="flex items-start gap-3">
              <span className="flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full bg-accent/20 text-[11px] font-bold text-accent">
                {step}
              </span>
              <span className="text-xs text-muted-foreground">{text}</span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ //
// LiveReadinessPanel                                                  //
// ------------------------------------------------------------------ //

export function LiveReadinessPanel() {
  const { data: perf, isLoading } = useQuery({
    queryKey: ["sim-performance"],
    queryFn: fetchSimulationPerformance,
    refetchInterval: 30_000,
  });

  if (isLoading || !perf) {
    return (
      <div className="flex flex-col gap-4 rounded-xl border border-border bg-background p-5">
        <h2 className="text-base font-semibold text-foreground">
          Ready for Live?
        </h2>
        <div className="flex h-32 items-center justify-center text-sm text-muted-foreground">
          Loading performance data...
        </div>
      </div>
    );
  }

  const results = CHECKLIST.map((item) => ({
    ...item,
    passed: item.passes(perf),
    currentValue: item.fmt(perf),
  }));

  const passedCount = results.filter((r) => r.passed).length;
  const readinessPct = (passedCount / results.length) * 100;
  const isReady = passedCount === results.length;

  return (
    <div className="flex flex-col gap-4 rounded-xl border border-border bg-background p-5">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-base font-semibold text-foreground">
            Ready for Live Trading?
          </h2>
          <p className="text-xs text-muted-foreground">
            Paper trading performance checklist
          </p>
        </div>
        <div className="flex flex-col items-end gap-1">
          <span
            className={`text-sm font-bold ${isReady ? "text-green-400" : "text-amber-400"}`}
          >
            {passedCount}/{results.length} passed
          </span>
          <div
            className="h-1.5 w-24 overflow-hidden rounded-full bg-border/50"
            role="progressbar"
            aria-valuenow={passedCount}
            aria-valuemin={0}
            aria-valuemax={results.length}
            aria-label={`${passedCount} of ${results.length} criteria passed`}
          >
            <div
              className={`h-full rounded-full transition-all duration-500 ${isReady ? "bg-green-400" : "bg-amber-400"}`}
              style={{ width: `${readinessPct}%` }}
            />
          </div>
        </div>
      </div>

      {/* Ready banner with animation */}
      {isReady && (
        <div
          className="animate-pulse rounded-lg border border-green-500/40 bg-green-500/10 px-4 py-3 text-center text-sm font-semibold text-green-400"
          role="status"
          aria-live="polite"
        >
          &#10003; Ready for Live Trading
        </div>
      )}

      {/* Criteria rows */}
      <div className="flex flex-col gap-2">
        {results.map((item) => (
          <div
            key={item.id}
            className={`flex items-center gap-3 rounded-lg border px-3 py-2 ${
              item.passed
                ? "border-green-500/20 bg-green-500/5"
                : "border-border/50 bg-surface/30"
            }`}
          >
            <div
              className={`flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full text-xs ${
                item.passed
                  ? "bg-green-500/20 text-green-400"
                  : "bg-border/50 text-muted-foreground"
              }`}
              aria-label={item.passed ? "Passed" : "Not yet passed"}
            >
              {item.passed ? "\u2713" : "\u25cb"}
            </div>
            <div className="flex min-w-0 flex-1 items-center justify-between gap-2">
              <div className="min-w-0">
                <p
                  className={`text-sm font-medium ${item.passed ? "text-foreground" : "text-muted-foreground"}`}
                >
                  {item.label}
                </p>
                <p className="truncate text-xs text-muted-foreground">
                  {item.description}
                </p>
              </div>
              <div className="flex-shrink-0 text-right">
                <p
                  className={`font-mono text-sm font-semibold ${item.passed ? "text-green-400" : "text-amber-400"}`}
                >
                  {item.currentValue}
                </p>
                <p className="text-xs text-muted-foreground">
                  target: {item.target}
                </p>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* How to go live */}
      <HowToGoLive />
    </div>
  );
}
