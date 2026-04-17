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

export interface FibonacciLevel {
  ratio: number;
  label: string;
  price: number;
}

export interface FibonacciData {
  swing_high: number;
  swing_low: number;
  levels: FibonacciLevel[];
}

export interface SupportResistanceLevel {
  price: number;
  touches: number;
  role: "support" | "resistance";
  strength: number;
  distance_pct: number;
  color: string;
}

export interface MoneyFlowMarker {
  index: number;
  text: "$" | "$$" | "$$$";
  direction: "up" | "down";
  intensity: "medium" | "high" | "extreme";
  volume_ratio: number;
  body_atr: number;
  time?: number;
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
  stoch_k: IndicatorPoint[];
  stoch_d: IndicatorPoint[];
  dmi_stoch: IndicatorPoint[];
  scalp_signals: { time: number; type: string; price: number }[];
  ichimoku_tenkan: IndicatorPoint[];
  ichimoku_kijun: IndicatorPoint[];
  ichimoku_senkou_a: IndicatorPoint[];
  ichimoku_senkou_b: IndicatorPoint[];
  ichimoku_chikou: IndicatorPoint[];
  fibonacci: FibonacciData;
  support_resistance: SupportResistanceLevel[];
  money_flow_markers: MoneyFlowMarker[];
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

// --- Order Flow ---

export interface PriceCluster {
  price: number;
  bid_vol: number;
  ask_vol: number;
  delta: number;
  trades: number;
  imbalance: "BUY" | "SELL" | null;
}

export interface FootprintWindow {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  total_volume: number;
  delta: number;
  clusters: PriceCluster[];
}

export interface OrderFlowData {
  windows: FootprintWindow[];
  cumulative_delta: number;
  delta_history: { time: number; value: number }[];
  imbalances: { price: number; type: string; ratio: number }[];
  current_price: number;
}

export async function fetchOrderFlow(
  asset: string,
  timeframe: string = "1m",
  limit: number = 30,
): Promise<OrderFlowData> {
  const { data } = await api.get<OrderFlowData>("/market/orderflow", {
    params: { asset, timeframe, limit },
  });
  return data;
}

// --- Liquidation Heatmap ---

export interface LiquidationBin {
  price_low: number;
  price_high: number;
  price_mid: number;
  long_usd: number;
  short_usd: number;
  total_usd: number;
  count: number;
  intensity: number;
}

export interface TheoreticalLevel {
  price: number;
  leverage: number;
  side: "long" | "short";
  estimated_usd: number;
}

export interface ForcedLiquidation {
  symbol: string;
  side: string;
  price: number;
  quantity: number;
  usd_value: number;
  timestamp: number;
}

export interface LiquidationHeatmapData {
  bins: LiquidationBin[];
  recent_liquidations: ForcedLiquidation[];
  theoretical_levels: TheoreticalLevel[];
  open_interest: number;
  current_price: number;
  total_long_liq_usd: number;
  total_short_liq_usd: number;
}

export async function fetchLiquidationHeatmap(
  asset: string,
  rangePct: number = 5,
): Promise<LiquidationHeatmapData> {
  const { data } = await api.get<LiquidationHeatmapData>(
    "/market/liquidation-heatmap",
    { params: { asset, range_pct: rangePct } },
  );
  return data;
}

export async function fetchRecentLiquidations(
  asset: string,
  limit: number = 50,
): Promise<ForcedLiquidation[]> {
  const { data } = await api.get<ForcedLiquidation[]>(
    "/market/liquidations/recent",
    { params: { asset, limit } },
  );
  return data;
}

// --- Agent ---

export interface AgentSignal {
  symbol: string;
  action: "LONG" | "SHORT" | "HOLD";
  entry: number;
  stop_loss: number;
  tp_levels: number[];
  confidence: number;
  reasoning: string;
  strategy_name: string;
  regime: string;
  risk_reward: number;
  readiness: number;
  conditions: { label: string; met: boolean }[];
  ui_elements: {
    sl_box: { price_top: number; price_bottom: number; color: string; border_color: string; label: string };
    tp_boxes: { price_top: number; price_bottom: number; color: string; border_color: string; label: string }[];
    entry_line: { price: number; color: string; label: string };
    be_line: { price: number; color: string; label: string };
  };
  timestamp: string;
}

export interface AgentStatus {
  running: boolean;
  scan_count: number;
  last_scan: string;
  active_signals: number;
  total_trades: number;
  wins: number;
  losses: number;
  win_rate: number;
  total_reward: number;
  avg_reward: number;
  recent_lessons: string[];
}

export async function fetchAgentSignals(): Promise<Record<string, AgentSignal>> {
  const { data } = await api.get<{ signals: Record<string, AgentSignal> }>("/agent/signals");
  return data.signals;
}

export async function fetchAgentStatus(): Promise<AgentStatus> {
  const { data } = await api.get<AgentStatus>("/agent/status");
  return data;
}

export async function startAgent(): Promise<{ status: string }> {
  const { data } = await api.post<{ status: string }>("/agent/start");
  return data;
}

export async function stopAgent(): Promise<{ status: string }> {
  const { data } = await api.post<{ status: string }>("/agent/stop");
  return data;
}

export interface LearningData {
  strategy_performance: {
    strategy: string;
    regime: string;
    wins: number;
    losses: number;
    win_rate: number;
    total_pnl: number;
    avg_reward: number;
    confidence_multiplier: number;
    blocked: boolean;
  }[];
  confidence_multipliers: Record<string, number>;
  blocked_combos: Record<string, string>;
  best_by_regime: Record<string, string | null>;
}

export async function fetchLearningData(): Promise<LearningData> {
  const { data } = await api.get<LearningData>("/agent/learning");
  return data;
}

// --- Day Trading ---

export interface DayTradeSignal {
  symbol: string;
  action: "LONG" | "SHORT" | "HOLD";
  entry: number;
  stop_loss: number;
  tp_levels: number[];
  be_trigger: number;
  confidence: number;
  hold_time_minutes: number;
  reasoning: string;
  strategy_type: string;
  session_levels: {
    session_high: number; session_low: number;
    pdh: number; pdl: number;
    vwap: number; vwap_upper: number; vwap_lower: number;
  };
  regime: string;
  readiness: number;
  conditions: { label: string; met: boolean }[];
  ui_elements: {
    sl_box: { price_top: number; price_bottom: number; color: string; label: string };
    tp_boxes: { price_top: number; price_bottom: number; color: string; label: string }[];
    entry_line: { price: number; color: string; label: string };
    be_line: { price: number; color: string; label: string };
    vwap_line: { price: number; color: string; label: string };
    pdh_line: { price: number; label: string };
    pdl_line: { price: number; label: string };
    confidence_label: { value: number; text: string };
    hold_time_label: { value: number; text: string };
  };
  timestamp: string;
}

export async function fetchDayTradeSignals(): Promise<Record<string, DayTradeSignal>> {
  const { data } = await api.get<{ signals: Record<string, DayTradeSignal> }>("/agent/day-trading/signals");
  return data.signals;
}

export async function fetchDayTradeStatus(): Promise<Record<string, unknown>> {
  const { data } = await api.get<Record<string, unknown>>("/agent/day-trading/status");
  return data;
}

// --- Intelligence ---

export interface NewsItemData {
  title: string;
  source: string;
  url: string;
  published: string;
  sentiment: number;
  is_emergency: boolean;
  keywords: string[];
  timestamp: string;
}

export interface SentimentSnapshot {
  timestamp: string;
  global_sentiment: number;
  crypto_sentiment: number;
  forex_sentiment: number;
  emergency_active: boolean;
  emergency_reason: string;
  priority_alerts: string[];
  impact_zones: string[];
  news_count: number;
}

export interface WhaleData {
  long_short_ratios: Record<string, { ratio: number; long_pct: number; short_pct: number; bias: string }>;
  open_interest: Record<string, number>;
  retail_sentiment: Record<string, number>;
  whale_alerts: Record<string, unknown>[];
}

export async function fetchNews(limit: number = 50): Promise<{ news: NewsItemData[] }> {
  const { data } = await api.get<{ news: NewsItemData[] }>("/intelligence/news", { params: { limit } });
  return data;
}

export async function fetchSentimentSnapshot(): Promise<SentimentSnapshot> {
  const { data } = await api.get<SentimentSnapshot>("/intelligence/sentiment");
  return data;
}

export async function fetchWhaleData(): Promise<WhaleData> {
  const { data } = await api.get<WhaleData>("/intelligence/whales");
  return data;
}

// --- Pro Analysis ---

export interface ProAnalysisData {
  analysis: string;
  recommendation: {
    action: string;
    entry: number;
    stop_loss: number;
    take_profit_1: number;
    take_profit_2: number;
    take_profit_3: number;
    risk_reward: number;
    confidence: number;
    timeframe: string;
  } | null;
  market_data: Record<string, unknown>;
  probability: { long: number; short: number; components: Record<string, number> };
}

export async function sendProAnalysis(
  message: string,
  asset: string,
  timeframe: string,
  imageBase64: string | null,
  history: { role: string; content: string }[],
): Promise<ProAnalysisData> {
  const { data } = await api.post<ProAnalysisData>("/pro-analysis", {
    message, asset, timeframe, image_base64: imageBase64, history,
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
