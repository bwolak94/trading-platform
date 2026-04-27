/**
 * StreakCircuitBreakerWidget
 * Compact widget showing consecutive loss circuit breaker status.
 * Shows streak count, status badge, cooldown countdown, position scale, and manual reset.
 * Fetches from GET /api/v1/features2/streak-status
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useState } from "react";
import axios from "axios";

// --------------- Types ---------------

interface StreakData {
  can_trade: boolean;
  reason: string;
  consecutive_losses: number;
  is_triggered: boolean;
  position_scale: number;
  message: string;
  cooldown_until?: string;
  requires_manual_reset?: boolean;
}

type CircuitStatus = "NORMAL" | "CAUTION" | "TRIGGERED" | "COOLDOWN";

// --------------- Constants ---------------

const STATUS_STYLES: Record<
  CircuitStatus,
  { border: string; badge: string; text: string; bg: string }
> = {
  NORMAL: {
    border: "border-green-500/30",
    badge: "bg-green-500/20 text-green-400",
    text: "text-green-400",
    bg: "bg-green-500/5",
  },
  CAUTION: {
    border: "border-yellow-500/30",
    badge: "bg-yellow-500/20 text-yellow-400",
    text: "text-yellow-400",
    bg: "bg-yellow-500/5",
  },
  TRIGGERED: {
    border: "border-red-500",
    badge: "bg-red-500/20 text-red-400",
    text: "text-red-400",
    bg: "bg-red-500/10",
  },
  COOLDOWN: {
    border: "border-orange-500/40",
    badge: "bg-orange-500/20 text-orange-400",
    text: "text-orange-400",
    bg: "bg-orange-500/5",
  },
};

// --------------- Helpers ---------------

function deriveStatus(data: StreakData): CircuitStatus {
  if (data.is_triggered && !data.cooldown_until) return "TRIGGERED";
  if (data.cooldown_until) return "COOLDOWN";
  if (data.consecutive_losses >= 3) return "CAUTION";
  return "NORMAL";
}

async function fetchStreakStatus(): Promise<StreakData> {
  const { data } = await axios.get<StreakData>("/api/v1/features2/streak-status");
  return data;
}

async function resetCircuitBreaker(): Promise<void> {
  await axios.post("/api/v1/features2/streak-reset");
}

// --------------- Countdown hook ---------------

function useCountdown(until?: string): string {
  const [remaining, setRemaining] = useState("");

  useEffect(() => {
    if (!until) {
      setRemaining("");
      return;
    }

    const tick = () => {
      const diff = new Date(until).getTime() - Date.now();
      if (diff <= 0) {
        setRemaining("00:00:00");
        return;
      }
      const h = Math.floor(diff / 3_600_000);
      const m = Math.floor((diff % 3_600_000) / 60_000);
      const s = Math.floor((diff % 60_000) / 1_000);
      setRemaining(
        `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`,
      );
    };

    tick();
    const id = setInterval(tick, 1_000);
    return () => clearInterval(id);
  }, [until]);

  return remaining;
}

// --------------- Skeleton ---------------

function StreakSkeleton() {
  return (
    <div className="space-y-2" aria-busy="true" aria-label="Loading circuit breaker status">
      <div className="flex gap-2">
        <div className="h-8 w-28 animate-pulse rounded bg-white/5" />
        <div className="h-8 w-20 animate-pulse rounded bg-white/5" />
      </div>
      <div className="h-4 w-full animate-pulse rounded bg-white/5" />
      <div className="h-4 w-2/3 animate-pulse rounded bg-white/5" />
    </div>
  );
}

// --------------- Main Component ---------------

export default function StreakCircuitBreakerWidget() {
  const queryClient = useQueryClient();

  const { data, isLoading, isError, refetch } = useQuery<StreakData>({
    queryKey: ["streak-status"],
    queryFn: fetchStreakStatus,
    refetchInterval: 30_000,
    retry: 2,
  });

  const mutation = useMutation<void, Error>({
    mutationFn: resetCircuitBreaker,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["streak-status"] });
    },
  });

  const handleRetry = useCallback(() => {
    void refetch();
  }, [refetch]);

  const handleReset = useCallback(() => {
    mutation.mutate();
  }, [mutation]);

  const status = data ? deriveStatus(data) : "NORMAL";
  const styles = STATUS_STYLES[status];
  const countdown = useCountdown(data?.cooldown_until);

  const isTriggeredOrCooldown = status === "TRIGGERED" || status === "COOLDOWN";

  return (
    <div className={`rounded-lg border-2 ${styles.border} bg-gray-900 p-4`}>
      {/* Header */}
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-white">
          Streak Circuit Breaker
        </h2>
        <span
          className={`rounded px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide ${styles.badge}`}
          aria-label={`Circuit breaker status: ${status}`}
        >
          {status}
        </span>
      </div>

      {/* Error */}
      {isError && (
        <div className="mb-3 flex items-center justify-between rounded bg-red-500/10 px-3 py-2">
          <span className="text-xs text-red-400">Status unavailable</span>
          <button
            type="button"
            onClick={handleRetry}
            className="text-xs text-red-400 underline hover:text-red-300"
            aria-label="Retry"
          >
            Retry
          </button>
        </div>
      )}

      {isLoading && <StreakSkeleton />}

      {data && (
        <div className="space-y-3">
          {/* Triggered banner */}
          {isTriggeredOrCooldown && (
            <div
              className="rounded border border-red-500/40 bg-red-500/10 px-3 py-2 text-center"
              role="alert"
              aria-live="assertive"
            >
              <p className="text-sm font-bold text-red-400 uppercase tracking-wide">
                Circuit Breaker Active — Trading Restricted
              </p>
              {countdown && (
                <p className="mt-1 font-mono text-xl font-bold text-red-300">
                  {countdown}
                </p>
              )}
              {countdown && (
                <p className="text-[10px] text-red-400/70">cool-off remaining</p>
              )}
            </div>
          )}

          {/* Streak counter */}
          <div className={`flex items-center justify-between rounded ${styles.bg} px-3 py-2`}>
            <div>
              <p className="text-[10px] text-gray-500">Consecutive Losses</p>
              <div className="flex items-end gap-1">
                <span
                  className={`font-mono text-3xl font-bold ${styles.text}`}
                  aria-label={`${data.consecutive_losses} consecutive losses`}
                >
                  {data.consecutive_losses}
                </span>
                <span className="mb-1 text-xs text-gray-500">in a row</span>
              </div>
            </div>
            <div className="flex gap-1" aria-hidden="true">
              {[...Array(Math.max(0, Math.min(Math.floor(data.consecutive_losses ?? 0), 5)))].map((_, i) => (
                <span key={i} className="text-lg">
                  🔴
                </span>
              ))}
            </div>
          </div>

          {/* Position scale */}
          <div className="rounded border border-border bg-gray-800/60 px-3 py-2">
            <div className="flex items-center justify-between">
              <p className="text-xs text-gray-400">Position Size</p>
              <span
                className={`font-mono text-lg font-bold ${
                  data.position_scale < 1
                    ? "text-yellow-400"
                    : "text-green-400"
                }`}
              >
                {(data.position_scale * 100).toFixed(0)}%
              </span>
            </div>
            <div className="mt-1.5 h-2 w-full overflow-hidden rounded-full bg-gray-700">
              <div
                className={`h-full rounded-full transition-all duration-500 ${
                  data.position_scale < 0.5
                    ? "bg-red-500"
                    : data.position_scale < 1
                      ? "bg-yellow-500"
                      : "bg-green-500"
                }`}
                style={{ width: `${data.position_scale * 100}%` }}
                role="progressbar"
                aria-valuenow={data.position_scale * 100}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label="Position size scale"
              />
            </div>
            <p className="mt-0.5 text-[10px] text-gray-500">
              Trading at {(data.position_scale * 100).toFixed(0)}% normal size
            </p>
          </div>

          {/* Message */}
          <p className="text-xs italic text-gray-400 leading-relaxed">
            {data.message}
          </p>

          {/* Manual reset button */}
          {data.requires_manual_reset && (
            <button
              type="button"
              onClick={handleReset}
              disabled={mutation.isPending}
              className="w-full rounded border border-orange-500/40 bg-orange-500/10 px-3 py-2 text-xs font-semibold text-orange-400 hover:bg-orange-500/20 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-orange-500 disabled:opacity-60"
              aria-label="Manually reset circuit breaker"
            >
              {mutation.isPending ? "Resetting…" : "Manual Reset"}
            </button>
          )}
          {mutation.isError && (
            <p className="text-center text-xs text-red-400">Reset failed</p>
          )}
        </div>
      )}
    </div>
  );
}
