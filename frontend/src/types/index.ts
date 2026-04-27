export type MarketRegime =
  | "TREND_BULL"
  | "TREND_BEAR"
  | "CONSOLIDATION"
  | "HIGH_VOL_CHOPPY";

export type SignalDirection = "LONG" | "SHORT" | "NEUTRAL";

export type SignalStatus =
  | "ACTIVE"
  | "TP1_HIT"
  | "TP2_HIT"
  | "SL_HIT"
  | "EXPIRED"
  | "CANCELLED";

export interface SignalFactor {
  name: string;
  weight: number;
  score: number;
  label: string;
}

export interface Signal {
  id: string;
  asset: string;
  direction: SignalDirection;
  confidence: number;
  regime: MarketRegime;
  entry_price: number;
  stop_loss: number;
  take_profit_1: number;
  take_profit_2: number;
  risk_reward: number;
  position_size_pct: number | null;
  technical_score: number | null;
  onchain_score: number | null;
  sentiment_score: number | null;
  macro_score: number | null;
  factors: SignalFactor[];
  status: SignalStatus;
  expires_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface SignalListResponse {
  data: Signal[];
  meta: {
    total: number;
    limit: number;
    offset: number;
  };
}

export interface RegimeData {
  asset: string;
  regime: MarketRegime;
  confidence: number;
  started_at: string;
  ended_at: string | null;
  metadata: Record<string, unknown> | null;
}

export interface SentimentData {
  asset: string;
  source: string;
  score: number;
  volume: number | null;
  period_start: string;
  period_end: string;
}

export interface OnChainEvent {
  asset: string;
  event_type: string;
  amount: number;
  amount_usd: number | null;
  direction: string | null;
  source: string | null;
  timestamp: string;
}

export interface UserSettings {
  user_id: string;
  capital: number | null;
  risk_per_trade_pct: number;
  max_drawdown_pct: number;
  telegram_chat_id: string | null;
  enabled_assets: string[];
  system_status: "ACTIVE" | "PAUSED";
  notifications_enabled: boolean;
}

export interface BacktestRequest {
  strategy: string;
  asset: string;
  timeframe: string;
  from_date: string;
  to_date: string;
  initial_capital: number;
  risk_per_trade_pct: number;
}

export interface BacktestResult {
  id: string;
  strategy_name: string;
  asset: string;
  timeframe: string;
  period_start: string;
  period_end: string;
  win_rate: number | null;
  profit_factor: number | null;
  max_drawdown: number | null;
  sharpe_ratio: number | null;
  calmar_ratio: number | null;
  total_trades: number | null;
  prob_ruin_20pct: number | null;
  prob_ruin_30pct: number | null;
  equity_curve: { date: string; equity: number }[] | null;
  created_at: string;
}

export interface SystemStatus {
  status: string;
  websocket_clients: number;
  system_status: "ACTIVE" | "PAUSED";
  drawdown_pct: number;
}

export interface RiskSummary {
  system_status: "ACTIVE" | "PAUSED";
  drawdown_pct: number;
  max_drawdown_pct: number;
  capital: number;
  risk_per_trade_pct: number;
  kill_switch_active: boolean;
  streak: { wins: number; losses: number };
}

/** Discriminated union of all WebSocket message types. */
export type WSMessage =
  | { type: "NEW_SIGNAL"; payload: Pick<Signal, "asset" | "direction" | "confidence" | "entry_price"> & { strategy: string } }
  | { type: "REGIME_CHANGE"; payload: { asset: string; regime: MarketRegime; confidence: number } }
  | { type: "KILL_SWITCH_TRIGGERED"; payload: { drawdown_pct: number; reason: string } }
  | { type: "SUBSCRIBED"; payload: { channels: string[] } }
  | { type: "UNSUBSCRIBED"; payload: { channels: string[] } };
