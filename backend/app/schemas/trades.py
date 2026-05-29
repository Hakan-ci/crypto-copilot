from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.constants import SUPPORTED_TIMEFRAMES
from app.schemas.indicators import IndicatorSnapshotRead
from app.schemas.trading_plan import TradingPlanEvaluation, TradingPlanReviewContext

DEFAULT_REVIEW_TIMEFRAME = "Hour4"


class FuturesPositionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    exchange: str
    symbol: str
    direction: Literal["long", "short"]
    opened_at: datetime
    closed_at: datetime | None = None
    avg_entry_price: Decimal
    avg_exit_price: Decimal | None = None
    total_volume: Decimal
    realized_pnl: Decimal
    total_fees: Decimal
    funding_fees: Decimal
    leverage: Decimal | None = None
    status: Literal["open", "closed"]
    raw_source: str | None = None
    created_at: datetime


class PositionListItem(FuturesPositionRead):
    net_pnl: Decimal
    plan_score: int | None = Field(default=None, ge=0, le=100)
    plan_failed_items_count: int = 0
    plan_unknown_items_count: int = 0


class IndicatorSummary(BaseModel):
    rsi_overbought_entries: int
    rsi_oversold_entries: int
    supertrend_aligned_trades: int
    supertrend_against_trades: int
    macd_aligned_trades: int
    macd_against_trades: int


class SymbolPerformance(BaseModel):
    symbol: str
    net_pnl: Decimal
    trade_count: int


class DashboardAnalytics(BaseModel):
    total_realized_pnl: Decimal
    total_fees: Decimal
    net_pnl: Decimal
    trade_count: int
    win_rate: Decimal
    average_win: Decimal
    average_loss: Decimal
    profit_factor: Decimal | None
    long_pnl: Decimal
    short_pnl: Decimal
    best_symbols: list[SymbolPerformance]
    worst_symbols: list[SymbolPerformance]
    open_positions: int
    closed_positions: int
    indicator_summary: IndicatorSummary


class AiTradeReviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    position_id: UUID
    timeframe: str
    rule_match_score: int | None = None
    risk_score: int | None = None
    execution_score: int | None = None
    mistake_tags: list[str]
    summary: str
    review_json: dict[str, Any]
    created_at: datetime


class PositionTransactionRead(BaseModel):
    id: UUID
    raw_mexc_order_deal_id: UUID | None = None
    mexc_deal_id: str
    order_id: str
    side: int
    side_label: str
    vol: Decimal
    price: Decimal
    fee: Decimal
    fee_currency: str | None = None
    profit: Decimal
    timestamp: datetime
    timestamp_ms: int
    source: Literal["linked", "inferred"]


class PositionTradeMetadataRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    position_id: UUID
    planned_stop_loss_price: Decimal | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class PositionTradeMetadataUpsert(BaseModel):
    planned_stop_loss_price: Decimal | None = Field(default=None, ge=0)
    notes: str | None = None

    @field_validator("notes")
    @classmethod
    def normalize_notes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class PositionDetail(BaseModel):
    position: FuturesPositionRead
    indicator_snapshots: list[IndicatorSnapshotRead]
    ai_review: AiTradeReviewRead | None = None
    plan_evaluation: TradingPlanEvaluation | None = None
    trade_metadata: PositionTradeMetadataRead | None = None
    transaction_timeline: list[PositionTransactionRead] = Field(default_factory=list)
    transaction_timeline_source: Literal["linked", "inferred", "unavailable"] = "unavailable"


class ReconstructionReport(BaseModel):
    positions_created: int
    open_positions: int
    closed_positions: int
    warnings: list[str]


class TradeReviewPositionInput(BaseModel):
    symbol: str
    direction: Literal["long", "short"]
    opened_at: datetime
    closed_at: datetime | None = None
    avg_entry_price: Decimal
    avg_exit_price: Decimal | None = None
    realized_pnl: Decimal
    total_fees: Decimal
    status: Literal["open", "closed"]


class TradeReviewIndicatorSnapshotInput(BaseModel):
    timeframe: str
    anchor: Literal["entry", "exit"] = "entry"
    rsi_14: Decimal | None = None
    stoch_rsi_k: Decimal | None = None
    stoch_rsi_d: Decimal | None = None
    macd: Decimal | None = None
    macd_signal: Decimal | None = None
    macd_histogram: Decimal | None = None
    supertrend_value: Decimal | None = None
    supertrend_direction: str | None = None
    atr_14: Decimal | None = None
    volume_relative: Decimal | None = None
    trend_label: str | None = None
    candlestick_patterns: list[str] = Field(default_factory=list)


class UserTradingRules(BaseModel):
    max_risk_per_trade: Decimal | None = None
    min_risk_reward: Decimal | None = None
    allowed_timeframes: list[str] | None = None
    allowed_symbols: list[str] | None = None
    max_trades_per_day: int | None = None
    notes: str | None = None


class TradeReviewInput(BaseModel):
    review_timeframe: str = DEFAULT_REVIEW_TIMEFRAME
    position: TradeReviewPositionInput
    indicator_snapshots: list[TradeReviewIndicatorSnapshotInput]
    transaction_timeline: list[PositionTransactionRead] = Field(default_factory=list)
    transaction_timeline_source: Literal["linked", "inferred", "unavailable"] = "unavailable"
    trade_metadata: PositionTradeMetadataRead | None = None
    trading_plan: TradingPlanReviewContext | None = None
    plan_evaluation: TradingPlanEvaluation | None = None
    rule_evidence: list[dict[str, Any]] = Field(default_factory=list)
    user_rules: UserTradingRules | None = None
    similar_past_trade_stats: dict[str, Any] | None = None


class TimeframeAlignment(BaseModel):
    one_hour: str
    four_hour: str
    one_day: str
    overall: str


class IndicatorObservations(BaseModel):
    rsi: list[str]
    stoch_rsi: list[str]
    macd: list[str]
    supertrend: list[str]


class TradingPlanRuleResult(BaseModel):
    title: str
    status: Literal["followed", "not_followed"]
    reason: str

    @field_validator("title", "reason")
    @classmethod
    def require_non_empty_rule_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Rule result text fields must not be empty.")
        return stripped


class TradeReviewOutput(BaseModel):
    summary: str
    timeframe_alignment: TimeframeAlignment
    indicator_observations: IndicatorObservations
    strengths: list[str]
    weaknesses: list[str]
    risk_flags: list[str]
    mistake_tags: list[str]
    rule_match_score: int | None = Field(default=None, ge=0, le=100)
    risk_score: int | None = Field(default=None, ge=0, le=100)
    execution_score: int | None = Field(default=None, ge=0, le=100)
    final_note: str
    transaction_timeline: list[str] = Field(default_factory=list)
    entry_analysis: list[str] = Field(default_factory=list)
    exit_analysis: list[str] = Field(default_factory=list)
    plan_compliance: list[str] = Field(default_factory=list)
    execution_notes: list[str] = Field(default_factory=list)
    missed_context: list[str] = Field(default_factory=list)
    follow_up_questions: list[str] = Field(default_factory=list)
    abandoned_rules: list[str] = Field(default_factory=list)
    rule_violations: list[str] = Field(default_factory=list)
    trading_plan_rule_results: list[TradingPlanRuleResult] = Field(default_factory=list)

    @field_validator("summary", "final_note")
    @classmethod
    def require_non_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Text fields must not be empty.")
        return value


class TradeReviewRequest(BaseModel):
    review_timeframe: str = DEFAULT_REVIEW_TIMEFRAME
    user_rules: UserTradingRules | None = None
    similar_past_trade_stats: dict[str, Any] | None = None

    @field_validator("review_timeframe")
    @classmethod
    def validate_review_timeframe(cls, value: str) -> str:
        if value not in SUPPORTED_TIMEFRAMES:
            raise ValueError(f"Unsupported review timeframe: {value}")
        return value


class TradeReviewResponse(BaseModel):
    position_id: UUID
    review_id: UUID | None = None
    review: TradeReviewOutput


class AiTradeQuestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    position_id: UUID
    question: str
    answer: str
    context_json: dict[str, Any]
    model: str
    created_at: datetime


class AiTradeQuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)

    @field_validator("question")
    @classmethod
    def require_non_empty_question(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Question must not be empty.")
        return stripped
