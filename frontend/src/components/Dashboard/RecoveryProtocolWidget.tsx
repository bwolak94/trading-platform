/**
 * RecoveryProtocolWidget
 * Shows current drawdown recovery protocol stage and active trading rules.
 * Fetches from GET /api/v1/features/recovery-protocol?drawdown_pct={dd}
 */

import { useQuery } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import axios from "axios";

// --------------- Types ---------------

interface RecoveryStage {
  stage_name: string;
  position_scale: number;
  min_confidence: number;
  allowed_strategies: string[];
  max_trades_per_day: number;
  description: string;
  dd_min_pct: number;
  dd_max_pct: number;
}

interface RecoveryData {
  current_drawdown_pct: number;
  stage: RecoveryStage;
  action: string;
  message: string;
}

// --------------- Constants ---------------

type StageName = "NORMAL" | "CAUTION" | "DEFENSIVE" | "EMERGENCY" | "KILL_SWITCH";

const STAGE_STYLES: Record<
  StageName,
  { border: string; badge: string; text: string; bar: string; bg: string }
> = {
  NORMAL: {
    border: "border-green-500",
    badge: "bg-green-500/20 text-green-400",
    text: "text-green-400",
    bar: "bg-green-500",
    bg: "bg-green-500/5",
  },
  CAUTION: {
    border: "border-yellow-500",
    badge: "bg-yellow-500/20 text-yellow-400",
    text: "text-yellow-400",
    bar: "bg-yellow-500",
    bg: "bg-yellow-500/5",
  },
  DEFENSIVE: {
    border: "border-orange-500",
    badge: "bg-orange-500/20 text-orange-400",
    text: "text-orange-400",
    bar: "bg-orange-500",
    bg: "bg-orange-500/5",
  },
  EMERGENCY: {
    border: "border-red-500",
    badge: "bg-red-500/20 text-red-400",
    text: "text-red-400",
    bar: "bg-red-500",
    bg: "bg-red-500/5",
  },
  KILL_SWITCH: {
    border: "border-red-900",
    badge: "bg-red-900/40 text-red-300",
    text: "text-red-300",
    bar: "bg-red-900",
    bg: "bg-red-900/10",
  },
};

const DEFAULT_STYLE = STAGE_STYLES.NORMAL;

function getStageStyle(stageName: string) {
  const normalized = stageName.toUpperCase().replace(/ /g, "_") as StageName;
  return STAGE_STYLES[normalized] ?? DEFAULT_STYLE;
}

async function fetchRecoveryProtocol(drawdownPct: number): Promise<RecoveryData> {
  const { data } = await axios.get<RecoveryData>("/api/v1/features/recovery-protocol", {
    params: { drawdown_pct: drawdownPct },
  });
  return data;
}

// --------------- Skeleton ---------------

function RecoverySkeleton() {
  return (
    <div className="space-y-3" aria-busy="true" aria-label="Loading recovery protocol data">
      <div className="h-8 w-32 animate-pulse rounded bg-white/5" />
      <div className="h-12 animate-pulse rounded bg-white/5" />
      <div className="h-24 animate-pulse rounded bg-white/5" />
      <div className="h-4 animate-pulse rounded bg-white/5" />
    </div>
  );
}

// --------------- Main Component ---------------

export default function RecoveryProtocolWidget() {
  const [drawdownPct, setDrawdownPct] = useState(5);

  const { data, isLoading, isError, refetch, dataUpdatedAt } = useQuery<RecoveryData>({
    queryKey: ["recovery-protocol", drawdownPct],
    queryFn: () => fetchRecoveryProtocol(drawdownPct),
    refetchInterval: 60_000,
    retry: 2,
  });

  const handleRefetch = useCallback(() => { void refetch(); }, [refetch]);
  const lastUpdated = dataUpdatedAt ? new Date(dataUpdatedAt).toLocaleTimeString() : null;

  const style = data?.stage ? getStageStyle(data.stage.stage_name) : DEFAULT_STYLE;

  // Progress within stage range
  const stageFraction = data?.stage
    ? Math.min(
        (data.current_drawdown_pct - data.stage.dd_min_pct) /
          Math.max(data.stage.dd_max_pct - data.stage.dd_min_pct, 0.01),
        1
      )
    : 0;

  const isKillSwitch = data?.stage?.stage_name.toUpperCase().includes("KILL") ?? false;

  return (
    <div className={`rounded-lg border ${style.border} bg-surface p-4`}>
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-white">Recovery Protocol</h2>
          {lastUpdated && (
            <p className="mt-0.5 text-xs text-gray-500">Updated: {lastUpdated}</p>
          )}
        </div>
        <div className="flex items-center gap-2">
          {/* Manual drawdown input */}
          <div className="flex items-center gap-1">
            <label htmlFor="drawdown-input" className="text-[10px] text-gray-500">DD%</label>
            <input
              id="drawdown-input"
              type="number"
              min={0}
              max={100}
              step={0.5}
              value={drawdownPct}
              onChange={(e) => { setDrawdownPct(parseFloat(e.target.value) || 0); }}
              className="w-16 rounded border border-border bg-gray-800 px-2 py-1 text-xs text-gray-300 focus:outline-none focus:ring-1 focus:ring-blue-500"
              aria-label="Current drawdown percentage"
            />
          </div>
          <button
            type="button"
            onClick={handleRefetch}
            className="rounded border border-border bg-gray-800 px-2 py-1 text-xs text-gray-400 hover:text-white transition-colors"
            aria-label="Refresh recovery protocol"
          >
            Check
          </button>
        </div>
      </div>

      {/* Error */}
      {isError && (
        <div className="mb-3 flex items-center justify-between rounded bg-red-500/10 px-3 py-2">
          <span className="text-xs text-red-400">Failed to load recovery data</span>
          <button type="button" onClick={handleRefetch} className="text-xs text-red-400 underline hover:text-red-300">
            Retry
          </button>
        </div>
      )}

      {isLoading && <RecoverySkeleton />}

      {data?.stage && (
        <div className="space-y-4">
          {/* Kill switch banner */}
          {isKillSwitch && (
            <div
              className="rounded border border-red-900 bg-red-900/30 px-3 py-2 text-center"
              role="alert"
              aria-live="assertive"
            >
              <p className="text-sm font-bold text-red-300 uppercase tracking-wide">
                KILL SWITCH ACTIVE — NO TRADING
              </p>
            </div>
          )}

          {/* Stage badge + drawdown */}
          <div className={`flex items-center justify-between rounded-lg border ${style.border} ${style.bg} px-4 py-3`}>
            <div>
              <span className={`rounded px-2 py-0.5 text-xs font-bold uppercase tracking-wide ${style.badge}`}>
                {data.stage.stage_name}
              </span>
              <p className="mt-1 text-[10px] text-gray-400 italic">{data.stage.description}</p>
            </div>
            <div className="text-right">
              <p className={`font-mono text-2xl font-bold ${style.text}`}>
                {data.current_drawdown_pct.toFixed(1)}%
              </p>
              <p className="text-[10px] text-gray-500">drawdown</p>
            </div>
          </div>

          {/* Stage progress bar */}
          <div>
            <div className="mb-1 flex items-center justify-between text-[10px] text-gray-500">
              <span>{data.stage.dd_min_pct}% DD</span>
              <span>Stage threshold progress</span>
              <span>{data.stage.dd_max_pct}% DD</span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-gray-700">
              <div
                className={`h-full rounded-full transition-all duration-500 ${style.bar}`}
                style={{ width: `${stageFraction * 100}%` }}
                role="progressbar"
                aria-valuenow={data.current_drawdown_pct}
                aria-valuemin={data.stage.dd_min_pct}
                aria-valuemax={data.stage.dd_max_pct}
                aria-label="Drawdown within stage threshold"
              />
            </div>
          </div>

          {/* Active rules */}
          <div className="rounded border border-border bg-gray-800/60 px-3 py-3 space-y-2">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-500">
              Active Trading Rules
            </p>
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div>
                <p className="text-gray-500">Position Size</p>
                <p className={`font-mono font-bold ${data.stage.position_scale < 1 ? "text-yellow-400" : "text-green-400"}`}>
                  {data.stage.position_scale.toFixed(1)}x
                </p>
              </div>
              <div>
                <p className="text-gray-500">Min Confidence</p>
                <p className="font-mono font-bold text-gray-200">{data.stage.min_confidence}%</p>
              </div>
              <div>
                <p className="text-gray-500">Max Trades/Day</p>
                <p className="font-mono font-bold text-gray-200">{data.stage.max_trades_per_day}</p>
              </div>
            </div>
            <div>
              <p className="mb-1 text-[10px] text-gray-500">Allowed Strategies</p>
              <div className="flex flex-wrap gap-1">
                {data.stage.allowed_strategies.length > 0
                  ? data.stage.allowed_strategies.map((strategy) => (
                      <span
                        key={strategy}
                        className="rounded bg-blue-500/15 px-1.5 py-0.5 text-[10px] text-blue-400"
                      >
                        {strategy}
                      </span>
                    ))
                  : (
                    <span className="text-[10px] text-red-400 font-bold">NONE — Trading Suspended</span>
                  )
                }
              </div>
            </div>
          </div>

          {/* Action + message */}
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-semibold uppercase tracking-wide text-gray-500">Action:</span>
              <span className={`text-xs font-medium ${style.text}`}>{data.action}</span>
            </div>
            <p className="text-xs text-gray-400 italic leading-relaxed">{data.message}</p>
          </div>
        </div>
      )}
    </div>
  );
}
