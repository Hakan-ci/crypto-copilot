from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.indicators import IndicatorSnapshotRead


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


class PositionDetail(BaseModel):
    position: FuturesPositionRead
    indicator_snapshots: list[IndicatorSnapshotRead]
    ai_review: AiTradeReviewRead | None = None


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


class UserTradingRules(BaseModel):
    max_risk_per_trade: Decimal | None = None
    min_risk_reward: Decimal | None = None
    allowed_timeframes: list[str] | None = None
    allowed_symbols: list[str] | None = None
    max_trades_per_day: int | None = None
    notes: str | None = None


class TradeReviewInput(BaseModel):
    position: TradeReviewPositionInput
    indicator_snapshots: list[TradeReviewIndicatorSnapshotInput]
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

    @field_validator("summary", "final_note")
    @classmethod
    def require_non_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Text fields must not be empty.")
        return value


class TradeReviewRequest(BaseModel):
    user_rules: UserTradingRules | None = None
    similar_past_trade_stats: dict[str, Any] | None = None


class TradeReviewResponse(BaseModel):
    position_id: UUID
    review_id: UUID | None = None
    review: TradeReviewOutput
