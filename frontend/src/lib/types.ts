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
  plan_score?: number | null;
  plan_failed_items_count?: number;
  plan_unknown_items_count?: number;
}

export interface IndicatorSnapshot {
  id: string;
  position_id: string;
  symbol: string;
  timeframe: Timeframe;
  anchor: "entry" | "exit" | string;
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
  plan_evaluation: TradingPlanEvaluation | null;
  transaction_timeline: PositionTransaction[];
  transaction_timeline_source: "linked" | "inferred" | "unavailable";
}

export interface PositionTransaction {
  id: string;
  raw_mexc_order_deal_id: string | null;
  mexc_deal_id: string;
  order_id: string;
  side: number;
  side_label: string;
  vol: string;
  price: string;
  fee: string;
  fee_currency: string | null;
  profit: string;
  timestamp: string;
  timestamp_ms: number;
  source: "linked" | "inferred";
}

export type TradingPlanRuleType =
  | "manual_check"
  | "allowed_symbols"
  | "required_timeframes"
  | "max_trades_per_day"
  | "max_leverage"
  | "max_risk_per_trade"
  | "min_risk_reward";

export type TradingPlanEvaluationStatus = "passed" | "failed" | "unknown" | "manual";

export interface TradingPlanItem {
  id: string;
  trading_plan_id: string;
  sort_order: number;
  title: string;
  description: string | null;
  category: string | null;
  rule_type: TradingPlanRuleType;
  enabled: boolean;
  config: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface TradingPlanItemInput {
  id?: string | null;
  sort_order: number;
  title: string;
  description?: string | null;
  category?: string | null;
  rule_type: TradingPlanRuleType;
  enabled: boolean;
  config: Record<string, unknown>;
}

export interface TradingPlan {
  id: string;
  user_id: string;
  items: TradingPlanItem[];
  created_at: string;
  updated_at: string;
}

export interface TradingPlanUpsert {
  items: TradingPlanItemInput[];
}

export type CryptoBasketSyncStatus = "idle" | "running" | "success" | "error";
export type CryptoBasketSyncRunStatus = "running" | "success" | "error" | "skipped";
export type CryptoBasketSyncRunType = "manual" | "automatic";

export interface CryptoBasketItem {
  id: string;
  basket_id: string;
  sort_order: number;
  symbol: string;
  enabled: boolean;
  sync_status: CryptoBasketSyncStatus;
  last_sync_started_at: string | null;
  last_sync_finished_at: string | null;
  last_successful_sync_at: string | null;
  last_sync_start_time_ms: number | null;
  last_sync_end_time_ms: number | null;
  last_imported: number;
  last_skipped_duplicates: number;
  last_positions_created: number;
  last_open_positions: number;
  last_closed_positions: number;
  last_warnings: string[];
  last_error: string | null;
  created_at: string;
  updated_at: string;
}

export interface CryptoBasketItemInput {
  id?: string | null;
  sort_order: number;
  symbol: string;
  enabled: boolean;
}

export interface CryptoBasket {
  id: string;
  user_id: string;
  items: CryptoBasketItem[];
  created_at: string;
  updated_at: string;
}

export interface CryptoBasketUpsert {
  items: CryptoBasketItemInput[];
}

export interface CryptoBasketSyncRun {
  id: string;
  basket_id: string;
  basket_item_id: string;
  symbol: string;
  run_type: CryptoBasketSyncRunType;
  status: CryptoBasketSyncRunStatus;
  started_at: string;
  finished_at: string | null;
  start_time_ms: number | null;
  end_time_ms: number | null;
  imported: number;
  skipped_duplicates: number;
  positions_created: number;
  open_positions: number;
  closed_positions: number;
  warnings: string[];
  error: string | null;
}

export interface CryptoBasketSyncResponse {
  basket: CryptoBasket;
  runs: CryptoBasketSyncRun[];
}

export interface TradingPlanEvaluationItem {
  item_id: string;
  sort_order: number;
  title: string;
  description: string | null;
  category: string | null;
  rule_type: TradingPlanRuleType;
  status: TradingPlanEvaluationStatus;
  message: string;
}

export interface TradingPlanEvaluation {
  score: number | null;
  passed_items_count: number;
  failed_items_count: number;
  unknown_items_count: number;
  manual_items_count: number;
  total_scored_items: number;
  items: TradingPlanEvaluationItem[];
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
  transaction_timeline?: string[];
  entry_analysis?: string[];
  exit_analysis?: string[];
  plan_compliance?: string[];
  execution_notes?: string[];
  missed_context?: string[];
  follow_up_questions?: string[];
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

export interface AiTradeQuestion {
  id: string;
  user_id: string;
  position_id: string;
  question: string;
  answer: string;
  context_json: Record<string, unknown>;
  model: string;
  created_at: string;
}
