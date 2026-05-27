from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.constants import SUPPORTED_TIMEFRAMES

TradingPlanRuleType = Literal[
    "manual_check",
    "allowed_symbols",
    "required_timeframes",
    "max_trades_per_day",
    "max_leverage",
    "max_risk_per_trade",
    "min_risk_reward",
]
TradingPlanEvaluationStatus = Literal["passed", "failed", "unknown", "manual"]

NUMERIC_LIMIT_RULE_TYPES = {
    "max_leverage",
    "max_risk_per_trade",
    "min_risk_reward",
}


class TradingPlanItemBase(BaseModel):
    sort_order: int = Field(default=0, ge=0)
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    category: str | None = Field(default=None, max_length=80)
    rule_type: TradingPlanRuleType = "manual_check"
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("title")
    @classmethod
    def require_non_empty_title(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Trading plan item title must not be empty.")
        return stripped

    @field_validator("description", "category")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @model_validator(mode="after")
    def validate_config(self) -> Self:
        config = dict(self.config or {})
        if self.rule_type == "allowed_symbols":
            symbols = _optional_string_list(config, "symbols")
            if symbols is not None:
                config["symbols"] = [symbol.upper() for symbol in symbols]
        elif self.rule_type == "required_timeframes":
            timeframes = _optional_string_list(config, "timeframes")
            if timeframes is not None:
                invalid_timeframes = [
                    timeframe for timeframe in timeframes if timeframe not in SUPPORTED_TIMEFRAMES
                ]
                if invalid_timeframes:
                    raise ValueError(
                        f"Unsupported timeframe(s): {', '.join(sorted(set(invalid_timeframes)))}"
                    )
                config["timeframes"] = timeframes
        elif self.rule_type == "max_trades_per_day":
            limit = _optional_decimal(config, "limit")
            if limit is not None:
                if limit != limit.to_integral_value():
                    raise ValueError("max_trades_per_day limit must be an integer.")
                config["limit"] = int(limit)
        elif self.rule_type in NUMERIC_LIMIT_RULE_TYPES:
            limit = _optional_decimal(config, "limit")
            if limit is not None:
                config["limit"] = str(limit)
        self.config = config
        return self


class TradingPlanItemUpsert(TradingPlanItemBase):
    id: UUID | None = None


class TradingPlanItemRead(TradingPlanItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    trading_plan_id: UUID
    created_at: datetime
    updated_at: datetime


class TradingPlanUpsert(BaseModel):
    items: list[TradingPlanItemUpsert] = Field(default_factory=list)


class TradingPlanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    items: list[TradingPlanItemRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class TradingPlanReviewItem(BaseModel):
    title: str
    description: str | None = None
    category: str | None = None
    rule_type: TradingPlanRuleType
    enabled: bool
    config: dict[str, Any]
    sort_order: int


class TradingPlanReviewContext(BaseModel):
    items: list[TradingPlanReviewItem]


class TradingPlanEvaluationItem(BaseModel):
    item_id: UUID
    sort_order: int
    title: str
    description: str | None = None
    category: str | None = None
    rule_type: TradingPlanRuleType
    status: TradingPlanEvaluationStatus
    message: str


class TradingPlanEvaluation(BaseModel):
    score: int | None = Field(default=None, ge=0, le=100)
    passed_items_count: int
    failed_items_count: int
    unknown_items_count: int
    manual_items_count: int
    total_scored_items: int
    items: list[TradingPlanEvaluationItem]


def _optional_string_list(config: dict[str, Any], key: str) -> list[str] | None:
    raw_value = config.get(key)
    if raw_value is None or raw_value == "":
        return None
    if not isinstance(raw_value, list):
        raise ValueError(f"{key} must be a list.")
    values = [str(item).strip() for item in raw_value if str(item).strip()]
    return values


def _optional_decimal(config: dict[str, Any], key: str) -> Decimal | None:
    raw_value = config.get(key)
    if raw_value is None or raw_value == "":
        return None
    try:
        value = Decimal(str(raw_value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{key} must be numeric.") from exc
    if not value.is_finite():
        raise ValueError(f"{key} must be finite.")
    if value < Decimal("0"):
        raise ValueError(f"{key} must not be negative.")
    return value
