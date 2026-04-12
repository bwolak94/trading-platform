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

// --- Indicators ---

export interface IndicatorPoint {
  time: number;
  value: number;
}

export interface OrderBlockData {
  time: number;
  type: "bullish" | "bearish";
  signal: "LONG" | "SHORT" | "WATCH_LONG" | "WATCH_SHORT";
  status: "active" | "broken";
  high: number;
  low: number;
  mid: number;
  strength: number;
  distance_pct: number;
}

export interface FVGData {
  time: number;
  type: "bullish" | "bearish";
  signal: "LONG" | "SHORT" | "WATCH";
  filled: boolean;
  top: number;
  bottom: number;
  mid: number;
  size_pct: number;
}

export interface LiquidationLevel {
  price: number;
  side: "long" | "short";
  leverage: number;
  distance_pct: number;
  intensity: number;
}

export interface VolumeProfileBucket {
  price_low: number;
  price_high: number;
  price_mid: number;
  total_volume: number;
  buy_volume: number;
  sell_volume: number;
  pct_of_max: number;
}

export interface IndicatorData {
  ema_20: IndicatorPoint[];
  ema_50: IndicatorPoint[];
  ema_200: IndicatorPoint[];
  bb_upper: IndicatorPoint[];
  bb_middle: IndicatorPoint[];
  bb_lower: IndicatorPoint[];
  rsi: IndicatorPoint[];
  macd_line: IndicatorPoint[];
  macd_signal: IndicatorPoint[];
  macd_hist: IndicatorPoint[];
  order_blocks: OrderBlockData[];
  fair_value_gaps: FVGData[];
  liquidation_levels: LiquidationLevel[];
  volume_profile: VolumeProfileBucket[];
  poc: VolumeProfileBucket | null;
  current_price: number;
}

export async function fetchIndicators(
  asset: string,
  interval: string,
  limit: number = 300,
): Promise<IndicatorData> {
  const { data } = await api.get<IndicatorData>("/market/indicators", {
    params: { asset, interval, limit },
  });
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

// --- Market Klines ---

export interface KlineData {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export async function fetchKlines(
  asset: string,
  interval: string,
  limit: number = 300,
): Promise<KlineData[]> {
  const { data } = await api.get<KlineData[]>("/market/klines", {
    params: { asset, interval, limit },
  });
  return data;
}

// --- Analysis ---

export interface AnalysisResult {
  asset: string;
  timeframe: string;
  timestamp: string;
  regime: {
    regime: string;
    confidence: number;
    probabilities: Record<string, number>;
  };
  summary: {
    price: number;
    change_24h: number;
    rsi: number;
    adx: number;
    atr: number;
    atr_normalized: number;
    ema_cross: number;
    bb_position: number;
    volume_vs_avg: number;
  };
  strategies: {
    name: string;
    description: string;
    compatible_with_regime: boolean;
    supported_regimes: string[];
    signal: {
      asset: string;
      direction: string;
      confidence: number;
      entry_price: number;
      stop_loss: number;
      take_profit_1: number;
      take_profit_2: number;
      risk_reward: number;
      strategy_name: string;
      factors: { name: string; weight: number; score: number; label: string }[];
    } | null;
    reason: string | null;
  }[];
  signals: AnalysisResult["strategies"][number]["signal"][];
}

export interface LiveRegime {
  asset: string;
  regime: string;
  confidence: number;
  price: number;
  rsi: number;
  adx: number;
}

export async function runAnalysis(
  asset: string,
  timeframe: string,
  strategy?: string,
): Promise<AnalysisResult> {
  const params: Record<string, string> = { asset, timeframe };
  if (strategy) params["strategy"] = strategy;
  const { data } = await api.get<AnalysisResult>("/analyze/run", { params });
  return data;
}

export async function fetchLiveRegimes(): Promise<LiveRegime[]> {
  const { data } = await api.get<LiveRegime[]>("/analyze/regimes");
  return data;
}

// --- Chat ---

export interface ChatAnnotation {
  type: "entry" | "stop_loss" | "take_profit";
  price: number;
  label: string;
}

export interface ChatResponseData {
  message: string;
  annotations: ChatAnnotation[];
  market_context: Record<string, unknown>;
}

export async function sendChatMessage(
  message: string,
  asset: string,
  timeframe: string,
  history: { role: string; content: string }[],
): Promise<ChatResponseData> {
  const { data } = await api.post<ChatResponseData>("/chat", {
    message,
    asset,
    timeframe,
    history,
  });
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
