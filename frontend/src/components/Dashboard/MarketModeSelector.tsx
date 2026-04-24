/**
 * MarketModeSelector
 * Primary control for selecting the active market mode.
 * 4 large mode buttons + AUTO toggle. Calling POST /api/v1/features2/market-mode on change.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import axios from "axios";

// --------------- Types ---------------

type ModeId =
  | "TRENDING"
  | "RANGING"
  | "HIGH_VOLATILITY"
  | "ACCUMULATION"
  | "AUTO";

interface ModeStatus {
  active_mode: ModeId;
  set_by: "user" | "auto";
  auto_detected: ModeId;
}

interface ModeConfig {
  id: ModeId;
  label: string;
  color: string;
  desc: string;
}

// --------------- Constants ---------------

const MODES: ModeConfig[] = [
  {
    id: "TRENDING",
    label: "Trending",
    color: "blue",
    desc: "Follow momentum",
  },
  {
    id: "RANGING",
    label: "Ranging",
    color: "purple",
    desc: "Mean reversion",
  },
  {
    id: "HIGH_VOLATILITY",
    label: "High Vol",
    color: "red",
    desc: "Defensive mode",
  },
  {
    id: "ACCUMULATION",
    label: "Accumulation",
    color: "yellow",
    desc: "Await breakout",
  },
];

const MODE_STYLES: Record<
  string,
  { border: string; bg: string; activeBg: string; text: string; dot: string }
> = {
  blue: {
    border: "border-blue-500",
    bg: "border-gray-700 hover:border-blue-500/50",
    activeBg: "border-blue-500 bg-blue-500/15",
    text: "text-blue-400",
    dot: "bg-blue-500",
  },
  purple: {
    border: "border-purple-500",
    bg: "border-gray-700 hover:border-purple-500/50",
    activeBg: "border-purple-500 bg-purple-500/15",
    text: "text-purple-400",
    dot: "bg-purple-500",
  },
  red: {
    border: "border-red-500",
    bg: "border-gray-700 hover:border-red-500/50",
    activeBg: "border-red-500 bg-red-500/15",
    text: "text-red-400",
    dot: "bg-red-500",
  },
  yellow: {
    border: "border-yellow-500",
    bg: "border-gray-700 hover:border-yellow-500/50",
    activeBg: "border-yellow-500 bg-yellow-500/15",
    text: "text-yellow-400",
    dot: "bg-yellow-500",
  },
  gray: {
    border: "border-gray-500",
    bg: "border-gray-700 hover:border-gray-500/50",
    activeBg: "border-gray-500 bg-gray-500/15",
    text: "text-gray-400",
    dot: "bg-gray-500",
  },
};

// --------------- Fetch helpers ---------------

async function fetchModeStatus(): Promise<ModeStatus> {
  const { data } = await axios.get<ModeStatus>("/api/v1/features2/market-mode");
  return data;
}

async function setMarketMode(mode: ModeId): Promise<ModeStatus> {
  const { data } = await axios.post<ModeStatus>("/api/v1/features2/market-mode", {
    mode,
  });
  return data;
}

// --------------- Main Component ---------------

export default function MarketModeSelector() {
  const queryClient = useQueryClient();

  const { data, isLoading, isError, refetch } = useQuery<ModeStatus>({
    queryKey: ["market-mode"],
    queryFn: fetchModeStatus,
    refetchInterval: 60_000,
    retry: 2,
  });

  const mutation = useMutation<ModeStatus, Error, ModeId>({
    mutationFn: setMarketMode,
    onSuccess: (updated) => {
      queryClient.setQueryData(["market-mode"], updated);
    },
  });

  const handleSelect = useCallback(
    (mode: ModeId) => {
      mutation.mutate(mode);
    },
    [mutation],
  );

  const handleRetry = useCallback(() => {
    void refetch();
  }, [refetch]);

  const activeMode = data?.active_mode ?? null;
  const isAutoMode = activeMode === "AUTO";
  const setBy = data?.set_by ?? "auto";
  const autoDetected = data?.auto_detected;

  return (
    <div className="rounded-lg border border-border bg-gray-900 p-4">
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-white">Market Mode</h2>
          <p className="mt-0.5 text-[10px] text-gray-500">
            {setBy === "user" ? (
              <span className="text-blue-400">Set manually by user</span>
            ) : (
              <span className="text-gray-400">
                Auto-detected
                {autoDetected ? `: ${autoDetected}` : ""}
              </span>
            )}
          </p>
        </div>
        {mutation.isPending && (
          <span className="text-[10px] text-gray-500 animate-pulse">
            Applying...
          </span>
        )}
        {mutation.isError && (
          <span className="text-[10px] text-red-400">Failed to set mode</span>
        )}
      </div>

      {/* Error state */}
      {isError && (
        <div className="mb-3 flex items-center justify-between rounded bg-red-500/10 px-3 py-2">
          <span className="text-xs text-red-400">Failed to load mode</span>
          <button
            type="button"
            onClick={handleRetry}
            className="text-xs text-red-400 underline hover:text-red-300"
            aria-label="Retry loading market mode"
          >
            Retry
          </button>
        </div>
      )}

      {/* Loading skeleton */}
      {isLoading && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {[...Array(4)].map((_, i) => (
            <div
              key={i}
              className="h-20 animate-pulse rounded-lg border border-gray-700 bg-white/5"
            />
          ))}
        </div>
      )}

      {/* Mode buttons */}
      {!isLoading && (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4" role="radiogroup" aria-label="Market mode selection">
            {MODES.map((mode) => {
              const styles = MODE_STYLES[mode.color] ?? MODE_STYLES["gray"]!;
              const isActive = activeMode === mode.id && !isAutoMode;
              return (
                <button
                  key={mode.id}
                  type="button"
                  role="radio"
                  aria-checked={isActive}
                  onClick={() => handleSelect(mode.id)}
                  disabled={mutation.isPending}
                  className={`relative flex flex-col items-center justify-center rounded-lg border-2 px-4 py-4 text-center transition-all duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 disabled:opacity-60 ${
                    isActive ? styles.activeBg : styles.bg
                  }`}
                  aria-label={`Set market mode to ${mode.label}: ${mode.desc}`}
                >
                  {isActive && (
                    <span
                      className={`absolute right-2 top-2 h-2 w-2 rounded-full ${styles.dot}`}
                      aria-hidden="true"
                    />
                  )}
                  <span
                    className={`text-base font-bold ${
                      isActive ? styles.text : "text-gray-300"
                    }`}
                  >
                    {mode.label}
                  </span>
                  <span className="mt-1 text-[10px] text-gray-500">
                    {mode.desc}
                  </span>
                </button>
              );
            })}
          </div>

          {/* AUTO toggle */}
          <div className="mt-3 flex items-center justify-between rounded-lg border border-gray-700 bg-gray-800/60 px-4 py-2">
            <div>
              <span
                className={`font-semibold text-sm ${
                  isAutoMode ? "text-gray-300" : "text-gray-500"
                }`}
              >
                AUTO
              </span>
              <span className="ml-2 text-xs text-gray-500">
                Let AI detect & switch mode automatically
              </span>
            </div>
            <button
              type="button"
              role="switch"
              aria-checked={isAutoMode}
              onClick={() => handleSelect("AUTO")}
              disabled={mutation.isPending}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 disabled:opacity-60 ${
                isAutoMode ? "bg-blue-600" : "bg-gray-700"
              }`}
              aria-label="Toggle auto mode"
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
                  isAutoMode ? "translate-x-6" : "translate-x-1"
                }`}
              />
            </button>
          </div>
        </>
      )}
    </div>
  );
}
