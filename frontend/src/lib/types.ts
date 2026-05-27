export type Timeframe = "Min60" | "Hour4" | "Day1";
export type TimeframeLabel = "1H" | "4H" | "1D";
export type PositionDirection = "long" | "short";
export type PositionStatus = "open" | "closed";

export interface Position {
  id: string;
  user_id: string;
  exchange: string;
  symbol: string;
  direction: PositionDirection;
  opened_at: string;
  closed_at: string | null;
  avg_entry_price: string;
  avg_exit_price: string | null;
  total_volume: string;
  realized_pnl: string;
  total_fees: string;
  funding_fees: string;
  leverage: string | null;
  status: PositionStatus;
  raw_source: string | null;
  created_at: string;
  net_pnl?: string;
}

export interface IndicatorSnapshot {
  id: string;
  position_id: string;
  symbol: string;
  timeframe: Timeframe;
  timestamp: string;
  price: string;
  rsi_14: string | null;
  stoch_rsi_k: string | null;
  stoch_rsi_d: string | null;
  macd: string | null;
  macd_signal: string | null;
  macd_histogram: string | null;
  supertrend_value: string | null;
  supertrend_direction: "bullish" | "bearish" | "unknown" | string | null;
  atr_14: string | null;
  volume_relative: string | null;
  trend_label: string | null;
}

export interface AiTradeReview {
  id: string;
  user_id: string;
  position_id: string;
  timeframe: string;
  rule_match_score: number | null;
  risk_score: number | null;
  execution_score: number | null;
  mistake_tags: string[];
  summary: string;
  review_json: TradeReviewOutput | Record<string, unknown>;
  created_at: string;
}

export interface IndicatorSummary {
  rsi_overbought_entries: number;
  rsi_oversold_entries: number;
  supertrend_aligned_trades: number;
  supertrend_against_trades: number;
  macd_aligned_trades: number;
  macd_against_trades: number;
}

export interface SymbolPerformance {
  symbol: string;
  net_pnl: string;
  trade_count: number;
}

export interface DashboardMetrics {
  total_realized_pnl: string;
  total_fees: string;
  net_pnl: string;
  trade_count: number;
  win_rate: string;
  average_win: string;
  average_loss: string;
  profit_factor: string | null;
  long_pnl: string;
  short_pnl: string;
  best_symbols: SymbolPerformance[];
  worst_symbols: SymbolPerformance[];
  open_positions: number;
  closed_positions: number;
  indicator_summary: IndicatorSummary;
}

export interface PositionDetail {
  position: Position;
  indicator_snapshots: IndicatorSnapshot[];
  ai_review: AiTradeReview | null;
}

export interface ImportOrderDealsRequest {
  user_id: string;
  symbol: string;
  start_time_ms?: number;
  end_time_ms?: number;
}

export interface ImportOrderDealsResponse {
  imported: number;
  skipped_duplicates: number;
  symbol: string;
}

export interface ImportAndReconstructResponse extends ImportOrderDealsResponse {
  positions_created: number;
  open_positions: number;
  closed_positions: number;
  warnings: string[];
}

export interface MexcReadinessResponse {
  base_url: string;
  credentials_configured: boolean;
  public_api_reachable: boolean;
  private_read_authenticated: boolean;
  message: string;
}

export interface Candle {
  id: string;
  exchange: string;
  symbol: string;
  timeframe: Timeframe;
  timestamp: string;
  timestamp_s: number;
  open: string;
  high: string;
  low: string;
  close: string;
  volume: string;
}

export interface PositionFilters {
  symbol?: string;
  status?: PositionStatus;
  direction?: PositionDirection;
  start?: string;
  end?: string;
  timeframe?: Timeframe;
}

export interface UserTradingRules {
  max_risk_per_trade?: string | null;
  min_risk_reward?: string | null;
  allowed_timeframes?: string[] | null;
  allowed_symbols?: string[] | null;
  max_trades_per_day?: number | null;
  notes?: string | null;
}

export interface TimeframeAlignment {
  one_hour: string;
  four_hour: string;
  one_day: string;
  overall: string;
}

export interface IndicatorObservations {
  rsi: string[];
  stoch_rsi: string[];
  macd: string[];
  supertrend: string[];
}

export interface TradeReviewOutput {
  summary: string;
  timeframe_alignment: TimeframeAlignment;
  indicator_observations: IndicatorObservations;
  strengths: string[];
  weaknesses: string[];
  risk_flags: string[];
  mistake_tags: string[];
  rule_match_score: number | null;
  risk_score: number | null;
  execution_score: number | null;
  final_note: string;
}

export interface TradeReviewResponse {
  position_id: string;
  review_id: string | null;
  review: TradeReviewOutput;
}

export interface IndicatorSnapshotCalculationResponse {
  position_id: string;
  snapshots_created_or_updated: number;
  warnings: string[];
}
