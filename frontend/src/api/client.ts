import axios from "axios";
import type {
  BacktestRequest,
  BacktestResult,
  OnChainEvent,
  RegimeData,
  SentimentData,
  Signal,
  SignalListResponse,
  SystemStatus,
  UserSettings,
} from "../types";

const api = axios.create({
  baseURL: "/api/v1",
  headers: { "Content-Type": "application/json" },
});

// --- Signals ---

export async function fetchSignals(params?: {
  asset?: string;
  direction?: string;
  status?: string;
  from?: string;
  limit?: number;
  offset?: number;
}): Promise<SignalListResponse> {
  const { data } = await api.get<SignalListResponse>("/signals", { params });
  return data;
}

export async function fetchActiveSignals(): Promise<SignalListResponse> {
  const { data } = await api.get<SignalListResponse>("/signals/active");
  return data;
}

export async function fetchSignalById(id: string): Promise<Signal> {
  const { data } = await api.get<Signal>(`/signals/${id}`);
  return data;
}

// --- Market ---

export async function fetchRegimes(): Promise<RegimeData[]> {
  const { data } = await api.get<RegimeData[]>("/market/regime");
  return data;
}

export async function fetchAssetRegime(asset: string): Promise<RegimeData> {
  const { data } = await api.get<RegimeData>(`/market/regime/${asset}`);
  return data;
}

export async function fetchSentiment(): Promise<SentimentData[]> {
  const { data } = await api.get<SentimentData[]>("/market/sentiment");
  return data;
}

export async function fetchOnChainEvents(): Promise<OnChainEvent[]> {
  const { data } = await api.get<OnChainEvent[]>("/market/onchain");
  return data;
}

// --- Backtest ---

export async function runBacktest(
  request: BacktestRequest,
): Promise<{ status: string; task_id: string }> {
  const { data } = await api.post<{ status: string; task_id: string }>(
    "/backtest/run",
    request,
  );
  return data;
}

export async function fetchBacktestResults(): Promise<BacktestResult[]> {
  const { data } = await api.get<BacktestResult[]>("/backtest/results");
  return data;
}

export async function fetchBacktestResult(id: string): Promise<BacktestResult> {
  const { data } = await api.get<BacktestResult>(`/backtest/results/${id}`);
  return data;
}

// --- Settings ---

export async function fetchSettings(): Promise<UserSettings> {
  const { data } = await api.get<UserSettings>("/settings");
  return data;
}

export async function updateSettings(
  updates: Partial<UserSettings>,
): Promise<UserSettings> {
  const { data } = await api.patch<UserSettings>("/settings", updates);
  return data;
}

export async function resetKillSwitch(): Promise<UserSettings> {
  const { data } = await api.post<UserSettings>("/settings/reset-killswitch");
  return data;
}

// --- System ---

export async function fetchSystemStatus(): Promise<SystemStatus> {
  const { data } = await api.get<SystemStatus>("/status");
  return data;
}

export async function fetchHealth(): Promise<{ status: string }> {
  const { data } = await api.get<{ status: string }>("/health");
  return data;
}
