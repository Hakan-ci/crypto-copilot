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
    "indicator_condition",
    "candlestick_pattern",
    "stop_loss",
]
TradingPlanEvaluationStatus = Literal["passed", "failed", "unknown", "manual"]

SUPPORTED_INDICATOR_RULE_FIELDS = {
    "rsi_14",
    "stoch_rsi_k",
    "stoch_rsi_d",
    "macd",
    "macd_signal",
    "macd_histogram",
    "supertrend_direction",
    "trend_label",
    "atr_14",
    "volume_relative",
}
NUMERIC_INDICATOR_FIELDS = {
    "rsi_14",
    "stoch_rsi_k",
    "stoch_rsi_d",
    "macd",
    "macd_signal",
    "macd_histogram",
    "atr_14",
    "volume_relative",
}
SUPPORTED_INDICATOR_OPERATORS = {"lt", "lte", "gt", "gte", "eq", "neq", "in", "not_in"}
SUPPORTED_CANDLESTICK_PATTERNS = {
    "doji",
    "hammer",
    "shooting_star",
    "bullish_engulfing",
    "bearish_engulfing",
    "morning_star",
    "evening_star",
}
SUPPORTED_ANCHORS = {"entry", "exit"}
SUPPORTED_DIRECTION_SCOPES = {"all", "long", "short"}
SUPPORTED_PATTERN_MATCH_MODES = {"any", "all"}

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
        elif self.rule_type == "indicator_condition":
            timeframe = _required_string(config, "timeframe")
            if timeframe not in SUPPORTED_TIMEFRAMES:
                raise ValueError(f"Unsupported timeframe: {timeframe}")
            anchor = _optional_string(config, "anchor") or "entry"
            if anchor not in SUPPORTED_ANCHORS:
                raise ValueError(f"Unsupported anchor: {anchor}")
            direction_scope = _optional_string(config, "direction_scope") or "all"
            if direction_scope not in SUPPORTED_DIRECTION_SCOPES:
                raise ValueError(f"Unsupported direction scope: {direction_scope}")
            indicator = _required_string(config, "indicator")
            if indicator not in SUPPORTED_INDICATOR_RULE_FIELDS:
                raise ValueError(f"Unsupported indicator: {indicator}")
            operator = _required_string(config, "operator")
            if operator not in SUPPORTED_INDICATOR_OPERATORS:
                raise ValueError(f"Unsupported operator: {operator}")
            value = config.get("value")
            if value is None or value == "":
                raise ValueError("Indicator condition value is required.")
            if indicator in NUMERIC_INDICATOR_FIELDS:
                if operator not in {"lt", "lte", "gt", "gte", "eq", "neq"}:
                    raise ValueError(f"Operator {operator} is not supported for {indicator}.")
                config["value"] = str(_decimal_value(value, "value"))
            elif operator not in {"eq", "neq", "in", "not_in"}:
                raise ValueError(f"Operator {operator} is not supported for {indicator}.")
            config["timeframe"] = timeframe
            config["anchor"] = anchor
            config["direction_scope"] = direction_scope
            config["indicator"] = indicator
            config["operator"] = operator
        elif self.rule_type == "candlestick_pattern":
            timeframe = _required_string(config, "timeframe")
            if timeframe not in SUPPORTED_TIMEFRAMES:
                raise ValueError(f"Unsupported timeframe: {timeframe}")
            anchor = _optional_string(config, "anchor") or "entry"
            if anchor not in SUPPORTED_ANCHORS:
                raise ValueError(f"Unsupported anchor: {anchor}")
            direction_scope = _optional_string(config, "direction_scope") or "all"
            if direction_scope not in SUPPORTED_DIRECTION_SCOPES:
                raise ValueError(f"Unsupported direction scope: {direction_scope}")
            patterns = _optional_string_list(config, "patterns")
            if not patterns:
                raise ValueError("At least one candlestick pattern is required.")
            normalized_patterns = [pattern.lower() for pattern in patterns]
            invalid_patterns = [
                pattern
                for pattern in normalized_patterns
                if pattern not in SUPPORTED_CANDLESTICK_PATTERNS
            ]
            if invalid_patterns:
                raise ValueError(
                    "Unsupported candlestick pattern(s): "
                    f"{', '.join(sorted(set(invalid_patterns)))}"
                )
            match_mode = _optional_string(config, "match_mode") or "any"
            if match_mode not in SUPPORTED_PATTERN_MATCH_MODES:
                raise ValueError(f"Unsupported pattern match mode: {match_mode}")
            config["timeframe"] = timeframe
            config["anchor"] = anchor
            config["direction_scope"] = direction_scope
            config["patterns"] = normalized_patterns
            config["match_mode"] = match_mode
        elif self.rule_type == "stop_loss":
            direction_scope = _optional_string(config, "direction_scope") or "all"
            if direction_scope not in SUPPORTED_DIRECTION_SCOPES:
                raise ValueError(f"Unsupported direction scope: {direction_scope}")
            max_distance_percent = _optional_decimal(config, "max_distance_percent")
            if max_distance_percent is not None:
                config["max_distance_percent"] = str(max_distance_percent)
            config["direction_scope"] = direction_scope
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
    timeframe: str | None = None
    anchor: str | None = None
    expected: str | None = None
    observed: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)


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


def _optional_string(config: dict[str, Any], key: str) -> str | None:
    raw_value = config.get(key)
    if raw_value is None or raw_value == "":
        return None
    return str(raw_value).strip()


def _required_string(config: dict[str, Any], key: str) -> str:
    value = _optional_string(config, key)
    if value is None:
        raise ValueError(f"{key} is required.")
    return value


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


def _decimal_value(raw_value: Any, key: str) -> Decimal:
    try:
        value = Decimal(str(raw_value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{key} must be numeric.") from exc
    if not value.is_finite():
        raise ValueError(f"{key} must be finite.")
    return value
