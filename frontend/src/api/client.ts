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
  vwap: IndicatorPoint[];
  vwap_upper_1: IndicatorPoint[];
  vwap_lower_1: IndicatorPoint[];
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

// --- Correlations ---

export interface CorrelationData {
  symbols: string[];
  matrix: number[][];
  timeframe: string;
  lookback_days: number;
}

export async function fetchCorrelations(
  symbols?: string,
  timeframe?: string,
  lookback_days?: number,
): Promise<CorrelationData> {
  const params: Record<string, string | number> = {};
  if (symbols) params["symbols"] = symbols;
  if (timeframe) params["timeframe"] = timeframe;
  if (lookback_days) params["lookback_days"] = lookback_days;
  const { data } = await api.get<CorrelationData>("/market/correlations", { params });
  return data;
}

// --- Funding Rates ---

export interface FundingRateData {
  symbol: string;
  funding_rate: number;
  next_funding_time: string;
  mark_price: number;
  index_price: number;
}

export async function fetchFundingRates(
  symbols?: string,
): Promise<FundingRateData[]> {
  const params: Record<string, string> = {};
  if (symbols) params["symbols"] = symbols;
  const { data } = await api.get<FundingRateData[]>("/market/funding-rates", { params });
  return data;
}

// --- Funding Rates (enhanced) ---

export interface FundingRateEntry {
  symbol: string;
  funding_rate: number;
  next_funding_time: number;
}

export interface FundingRatesData {
  rates: FundingRateEntry[];
  extreme_longs: FundingRateEntry[];  // rate > 0.1%
  extreme_shorts: FundingRateEntry[]; // rate < -0.05%
}

export async function fetchFundingRatesEnhanced(): Promise<FundingRatesData> {
  const { data } = await api.get<{ rates: FundingRateData[] }>("/market/funding-rates");
  const raw = data.rates ?? [];
  const rates: FundingRateEntry[] = raw.map((r) => ({
    symbol: r.symbol,
    funding_rate: r.funding_rate,
    next_funding_time: typeof r.next_funding_time === "string"
      ? new Date(r.next_funding_time).getTime()
      : (r.next_funding_time as unknown as number),
  }));
  return {
    rates,
    extreme_longs: rates.filter((r) => r.funding_rate > 0.001),
    extreme_shorts: rates.filter((r) => r.funding_rate < -0.0005),
  };
}

// --- Order Book ---

export interface OrderBookLevel {
  price: string;
  qty: string;
}

export interface OrderBookData {
  bids: [string, string][];
  asks: [string, string][];
  spread: number;
  best_bid: number;
  best_ask: number;
  timestamp: number;
  symbol: string;
}

export async function fetchOrderBook(
  symbol: string,
  limit: number = 100,
): Promise<OrderBookData> {
  const { data } = await api.get<OrderBookData>("/market/orderbook", {
    params: { symbol, limit },
  });
  return data;
}

// --- Symbols ---

export interface SymbolOption {
  label: string;  // e.g. "BTC/USDT"
  value: string;  // e.g. "BTCUSDT"
}

export interface AllSymbolsResponse {
  crypto: SymbolOption[];
  forex: SymbolOption[];
  total: number;
}

export async function fetchAllSymbols(): Promise<AllSymbolsResponse> {
  const { data } = await api.get<AllSymbolsResponse>("/market/symbols");
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

// --- Simulation (Paper Trading) ---

export interface SimulatedPosition {
  id: string;
  symbol: string;
  direction: "LONG" | "SHORT";
  strategy: string;
  regime: string;
  confidence: number;
  entry_price: number;
  stop_loss: number;
  take_profit_1: number;
  take_profit_2: number | null;
  take_profit_3: number | null;
  current_price: number;
  exit_price: number | null;
  pnl_pct: number;
  status: string;
  exit_reason: string | null;
  opened_at: string;
  closed_at: string | null;
  mae_pct: number | null;
  mfe_pct: number | null;
  tags: string[] | null;
  notes: string | null;
}

// --- Trade Journal ---

export interface UpdatePositionNotesRequest {
  tags?: string[];
  notes?: string;
}

export const updatePositionNotes = (
  positionId: number,
  data: UpdatePositionNotesRequest,
): Promise<void> =>
  fetch(`/api/v1/simulation/positions/${positionId}/notes`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  }).then((r) => {
    if (!r.ok) throw new Error("Failed to update notes");
  });

export interface SimulationPerformance {
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number;
  total_pnl_pct: number;
  avg_win_pct: number;
  avg_loss_pct: number;
  profit_factor: number;
  max_drawdown_pct: number;
  sharpe_ratio: number;
  best_trade: number;
  worst_trade: number;
  open_positions: number;
  running_pnl: number;
}

export interface SimulationStatus {
  is_running: boolean;
  session_id: string;
  open_positions: number;
  max_positions: number;
  performance: SimulationPerformance;
}

export interface BotSession {
  id: string;
  started_at: string | null;
  ended_at: string | null;
  is_active: boolean;
  total_trades: number;
  winning_trades: number;
  total_pnl_pct: number;
  max_drawdown_pct: number;
  sharpe_ratio: number | null;
  win_rate: number;
}

export async function fetchSimulationStatus(): Promise<SimulationStatus> {
  const { data } = await api.get<SimulationStatus>("/simulation/status");
  return data;
}

export async function fetchOpenPositions(): Promise<{
  positions: SimulatedPosition[];
  count: number;
  session_id: string;
  is_running: boolean;
}> {
  const { data } = await api.get("/simulation/positions");
  return data;
}

export async function fetchClosedPositions(params?: {
  limit?: number;
  offset?: number;
}): Promise<{ positions: SimulatedPosition[]; total: number; limit: number; offset: number }> {
  const { data } = await api.get("/simulation/positions/closed", { params });
  return data;
}

export async function fetchSimulationPerformance(): Promise<SimulationPerformance> {
  const { data } = await api.get<SimulationPerformance>("/simulation/performance");
  return data;
}

export async function fetchSessionHistory(limit: number = 10): Promise<{ sessions: BotSession[] }> {
  const { data } = await api.get("/simulation/performance/history", { params: { limit } });
  return data;
}

export async function startSimulation(): Promise<{ status: string; session_id: string }> {
  const { data } = await api.post("/simulation/start");
  return data;
}

export async function stopSimulation(): Promise<{ status: string }> {
  const { data } = await api.post("/simulation/stop");
  return data;
}

// --- Notification History ---

export interface NotificationRecord {
  id: string;
  chat_id: string;
  message_type: string;
  asset: string | null;
  direction: string | null;
  confidence: number | null;
  strategy: string | null;
  entry_price: number | null;
  stop_loss: number | null;
  take_profit_1: number | null;
  outcome: string | null;
  pnl_pct: number | null;
  message_text: string;
  sent_at: string | null;
}

export interface NotificationPerformance {
  total_signals: number;
  win_rate: number;
  breakdown: Record<string, { count: number; avg_pnl: number }>;
}

export async function fetchNotificationHistory(params?: {
  limit?: number;
  offset?: number;
  chat_id?: string;
  message_type?: string;
}): Promise<{ notifications: NotificationRecord[]; total: number; limit: number; offset: number }> {
  const { data } = await api.get("/notifications/history", { params });
  return data;
}

export async function fetchNotificationPerformance(): Promise<NotificationPerformance> {
  const { data } = await api.get<NotificationPerformance>("/notifications/performance");
  return data;
}

// --- Signal Markers ---

export interface SignalMarker {
  time: number;
  direction: "LONG" | "SHORT";
  price: number;
  confidence: number;
  strategy: string;
  symbol: string;
}

export async function fetchSignalMarkersForSymbol(
  symbol: string,
  limit = 50,
): Promise<{ signals: SignalMarker[] }> {
  const { data } = await api.get<{ signals: SignalMarker[] }>(
    `/signals/history?symbol=${symbol}&limit=${limit}`,
  );
  return data;
}

// --- Equity Curve ---

export interface EquityPoint {
  time: string;
  equity: number;
  pnl_pct: number;
  trade_count: number;
}

export interface EquityCurveData {
  equity_curve: EquityPoint[];
  session_id: string | null;
  is_running: boolean;
}

export async function fetchEquityCurve(): Promise<EquityCurveData> {
  const { data } = await api.get<EquityCurveData>("/simulation/equity-curve");
  return data;
}

// --- Fear & Greed ---

export interface FearGreedData {
  value: number;
  value_classification: string;
  timestamp: string;
  cached_at: string;
  error?: string;
}

export async function fetchFearGreed(): Promise<FearGreedData> {
  const { data } = await api.get<FearGreedData>("/market/fear-greed");
  return data;
}

// --- Strategy Heatmap ---

export interface HeatmapCell {
  strategy: string;
  regime: string;
  win_rate: number;
  total_trades: number;
  wins: number;
}

export interface StrategyHeatmapData {
  heatmap: HeatmapCell[];
  strategies: string[];
  regimes: string[];
  total_positions: number;
}

export async function fetchStrategyHeatmap(): Promise<StrategyHeatmapData> {
  const { data } = await api.get<StrategyHeatmapData>("/simulation/strategy-heatmap");
  return data;
}

// --- Attribution ---

export interface AttributionEntry {
  key: string;
  total_pnl: number;
  trades: number;
  win_rate: number;
}

export interface AttributionData {
  by_strategy: AttributionEntry[];
  by_regime: AttributionEntry[];
  by_symbol: AttributionEntry[];
  total_closed_trades: number;
}

export async function fetchAttribution(): Promise<AttributionData> {
  const { data } = await api.get<AttributionData>("/simulation/attribution");
  return data;
}

// --- R-Multiple ---

export interface RMultipleData {
  distribution: { r: number; count: number }[];
  avg_r: number;
  expectancy: number;
  win_rate: number;
  avg_win_r: number;
  avg_loss_r: number;
  total_trades: number;
}

export async function fetchRMultiple(): Promise<RMultipleData> {
  const { data } = await api.get<RMultipleData>("/simulation/r-multiple");
  return data;
}

// --- BTC Dominance ---

export interface BtcDominanceData {
  btc_dominance: number;
  total_market_cap_usd: number;
  total_volume_24h_usd: number;
  market_cap_change_24h_pct: number;
  active_cryptocurrencies: number;
  cached_at: string;
  error?: string;
}

export async function fetchBtcDominance(): Promise<BtcDominanceData> {
  const { data } = await api.get<BtcDominanceData>("/market/btc-dominance");
  return data;
}

// --- Market Breadth ---

export interface MarketBreadthData {
  above_ema20_pct: number;
  above_ema50_pct: number;
  above_ema200_pct: number;
  total_symbols: number;
  scanned_symbols: number;
  cached_at: string;
}

export async function fetchMarketBreadth(): Promise<MarketBreadthData> {
  const { data } = await api.get<MarketBreadthData>("/market/breadth");
  return data;
}

// --- Momentum Rankings ---

export interface MomentumEntry {
  symbol: string;
  score: number;
  direction: "LONG" | "SHORT" | "NEUTRAL";
  tf_scores: Record<string, number>;
}

export interface MomentumRankData {
  rankings: MomentumEntry[];
  count: number;
}

export async function fetchMomentumRank(topN: number = 20): Promise<MomentumRankData> {
  const { data } = await api.get<MomentumRankData>("/market/momentum-rank", {
    params: { top_n: topN },
  });
  return data;
}

// --- Signal History ---

export interface SignalHistoryEntry {
  id: string;
  asset: string;
  direction: string;
  confidence: number;
  entry_price: number;
  stop_loss: number;
  take_profit_1: number;
  strategy_name: string;
  status: string;
  created_at: string;
}

export interface SignalHistoryResponse {
  data: SignalHistoryEntry[];
  total: number;
  limit: number;
  offset: number;
}

export async function fetchSignalHistory(params?: {
  asset?: string;
  direction?: string;
  strategy?: string;
  limit?: number;
  offset?: number;
}): Promise<SignalHistoryResponse> {
  const { data } = await api.get<SignalHistoryResponse>("/signals", { params: { ...params, limit: params?.limit ?? 50 } });
  return data;
}

// --- Trade Duration Distribution ---

export interface TradeDurationData {
  buckets: string[];
  by_strategy: Record<string, Record<string, number>>;
}

export async function fetchTradeDuration(): Promise<TradeDurationData> {
  const { data } = await api.get<TradeDurationData>("/simulation/trade-duration");
  return data;
}

// --- Entry Timing Heatmap ---

export interface TimingCell {
  hour: number;
  day: number;
  win_rate: number | null;
  total_trades: number;
}

export interface EntryTimingData {
  matrix: TimingCell[];
  days: string[];
}

export async function fetchEntryTimingHeatmap(): Promise<EntryTimingData> {
  const { data } = await api.get<EntryTimingData>("/simulation/entry-timing-heatmap");
  return data;
}

// --- Macro Overlay ---

export interface MacroData {
  dxy_price: number | null;
  dxy_change_pct: number | null;
  us10y_yield: number | null;
  us10y_change_pct: number | null;
  spx_price: number | null;
  spx_change_pct: number | null;
  btc_correlation_dxy: number | null;
  last_updated: number;
}

export async function fetchMacroData(): Promise<MacroData> {
  const { data } = await api.get<MacroData>("/market/macro");
  return data;
}

// --- Sector Momentum ---

export interface SectorMomentumEntry {
  sector: string;
  momentum_score: number;
  avg_1d_change: number;
  avg_7d_change: number;
  top_performers: string[];
  symbol_count: number;
}

export interface SectorMomentumData {
  sectors: SectorMomentumEntry[];
}

export async function fetchSectorMomentum(): Promise<SectorMomentumData> {
  const { data } = await api.get<SectorMomentumData>("/market/sector-momentum");
  return data;
}

// --- Long/Short Ratio ---

export interface LongShortRatioPoint {
  timestamp: number;
  long_short_ratio: number;
  long_account: number;
  short_account: number;
}

export interface LongShortData {
  symbol: string;
  data: LongShortRatioPoint[];
  current_ratio: number;
  sentiment: "extreme_long" | "long" | "neutral" | "short" | "extreme_short";
}

export async function fetchLongShortRatio(symbol: string): Promise<LongShortData> {
  const { data } = await api.get<{
    symbol: string;
    data: LongShortRatioPoint[];
    extreme_long: boolean;
    extreme_short: boolean;
  }>(`/market/long-short-ratio/${symbol}`);

  const latest = data.data[data.data.length - 1];
  const ratio = latest?.long_short_ratio ?? 1;
  const longPct = (latest?.long_account ?? 0.5) * 100;

  let sentiment: LongShortData["sentiment"] = "neutral";
  if (data.extreme_long || longPct > 75) sentiment = "extreme_long";
  else if (longPct > 60) sentiment = "long";
  else if (data.extreme_short || longPct < 25) sentiment = "extreme_short";
  else if (longPct < 40) sentiment = "short";

  return {
    symbol: data.symbol,
    data: data.data,
    current_ratio: ratio,
    sentiment,
  };
}

// --- News Velocity ---

export interface NewsVelocityEntry {
  symbol: string;
  count: number;
}

export interface NewsVelocityData {
  velocity: NewsVelocityEntry[];
  total_articles: number;
}

export async function fetchNewsVelocity(): Promise<NewsVelocityData> {
  const { data } = await api.get<NewsVelocityData>("/market/news-velocity");
  return data;
}

// --- Monte Carlo VaR ---

export interface MonteCarloVarData {
  var_95: number;
  var_99: number;
  expected_return: number;
  worst_case: number;
  best_case: number;
  median: number;
  simulations: number;
  horizon: number;
  confidence?: number;
  error?: string;
}

export const fetchMonteCarloVar = (
  simulations = 1000,
  horizon = 20,
): Promise<MonteCarloVarData> =>
  api
    .get<MonteCarloVarData>("/simulation/monte-carlo-var", {
      params: { simulations, horizon },
    })
    .then((r) => r.data);

// --- Stablecoin Supply Ratio ---

export interface StablecoinRatioData {
  ssr: number;
  usdt_market_cap: number;
  usdc_market_cap: number;
  stable_total: number;
  total_market_cap: number;
  signal: "bullish" | "neutral_bullish" | "neutral" | "bearish" | "unknown";
  interpretation: string;
  cached_at: string;
  error?: string;
}

export async function fetchStablecoinRatio(): Promise<StablecoinRatioData> {
  const { data } = await api.get<StablecoinRatioData>("/market/stablecoin-ratio");
  return data;
}

// --- Open Interest & Positioning ---

export interface OIHistoryPoint {
  timestamp: number;
  open_interest: number;
  open_interest_value: number;
}

export interface PositioningSnapshot {
  symbol: string;
  period: string;
  current_price: number;
  current_oi: number;
  current_oi_value: number;
  oi_change_24h_pct: number;
  global_ls_ratio: number;
  top_trader_ratio: number;
  funding_rate: number;
  oi_history: OIHistoryPoint[];
  ls_history: LongShortRatioPoint[];
  top_trader_history: LongShortRatioPoint[];
  liquidation_levels: LiquidationLevel[];
}

export interface TopTraderRatioData {
  symbol: string;
  position_ratio: LongShortRatioPoint[];
  account_ratio: LongShortRatioPoint[];
  current_position_ratio: number;
  current_account_ratio: number;
  longs_dominant: boolean;
}

export async function fetchPositioningSnapshot(
  symbol: string,
  period = "1h",
  limit = 100,
): Promise<PositioningSnapshot> {
  const { data } = await api.get<PositioningSnapshot>(`/market/positioning/${symbol}`, {
    params: { period, limit },
  });
  return data;
}

export async function fetchTopTraderRatio(
  symbol: string,
  period = "1h",
  limit = 50,
): Promise<TopTraderRatioData> {
  const { data } = await api.get<TopTraderRatioData>(`/market/top-trader-ratio/${symbol}`, {
    params: { period, limit },
  });
  return data;
}
