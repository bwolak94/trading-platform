import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { UseQueryResult, UseMutationResult } from "@tanstack/react-query";
import {
  fetchActiveSignals,
  fetchLiveRegimes,
  fetchIndicators,
  fetchKlines,
  runAnalysis,
  fetchBacktestResults,
  fetchSettings,
  updateSettings,
} from "../api/client";
import type {
  IndicatorData,
  KlineData,
  AnalysisResult,
  LiveRegime,
} from "../api/client";
import type {
  SignalListResponse,
  BacktestResult,
  UserSettings,
} from "../types";

/** Active trading signals, auto-refreshed every 30s */
export function useActiveSignals(): UseQueryResult<SignalListResponse> {
  return useQuery({
    queryKey: ["signals", "active"],
    queryFn: fetchActiveSignals,
    refetchInterval: 30_000,
  });
}

/** Live regime data for all assets, auto-refreshed every 30s */
export function useRegimes(): UseQueryResult<LiveRegime[]> {
  return useQuery({
    queryKey: ["regimes", "live"],
    queryFn: fetchLiveRegimes,
    refetchInterval: 30_000,
  });
}

/** Technical indicators for a given asset/timeframe, stale after 15s */
export function useIndicators(
  asset: string,
  timeframe: string,
  count = 300,
): UseQueryResult<IndicatorData> {
  return useQuery({
    queryKey: ["indicators", asset, timeframe, count],
    queryFn: () => fetchIndicators(asset, timeframe, count),
    staleTime: 15_000,
    enabled: Boolean(asset && timeframe),
  });
}

/** OHLCV kline data for a given asset/timeframe, stale after 15s */
export function useKlines(
  asset: string,
  timeframe: string,
  count = 300,
): UseQueryResult<KlineData[]> {
  return useQuery({
    queryKey: ["klines", asset, timeframe, count],
    queryFn: () => fetchKlines(asset, timeframe, count),
    staleTime: 15_000,
    enabled: Boolean(asset && timeframe),
  });
}

/** Mutation to trigger an analysis run */
export function useRunAnalysis(): UseMutationResult<
  AnalysisResult,
  Error,
  { asset: string; timeframe: string; strategy?: string }
> {
  return useMutation({
    mutationFn: ({ asset, timeframe, strategy }) =>
      runAnalysis(asset, timeframe, strategy),
  });
}

/** All backtest results */
export function useBacktestResults(): UseQueryResult<BacktestResult[]> {
  return useQuery({
    queryKey: ["backtestResults"],
    queryFn: fetchBacktestResults,
  });
}

/** Current user settings */
export function useSettings(): UseQueryResult<UserSettings> {
  return useQuery({
    queryKey: ["settings"],
    queryFn: fetchSettings,
  });
}

/** Mutation to update user settings, invalidates settings cache on success */
export function useUpdateSettings(): UseMutationResult<
  UserSettings,
  Error,
  Partial<UserSettings>
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: updateSettings,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["settings"] });
    },
  });
}
