from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.core.constants import (
    MEXC_SIDE_CLOSE_LONG,
    MEXC_SIDE_CLOSE_SHORT,
    MEXC_SIDE_OPEN_LONG,
    MEXC_SIDE_OPEN_SHORT,
    SUPPORTED_TIMEFRAMES,
    TIMEFRAME_LABELS,
)
from app.core.security import FORBIDDEN_EXCHANGE_ACTIONS

MEXC_ORDER_DEAL_SIDES = {
    MEXC_SIDE_OPEN_LONG,
    MEXC_SIDE_CLOSE_SHORT,
    MEXC_SIDE_OPEN_SHORT,
    MEXC_SIDE_CLOSE_LONG,
}


class MexcReadOnlyCapabilities(BaseModel):
    exchange: str = "MEXC"
    base_url: str
    supported_timeframes: list[str] = list(SUPPORTED_TIMEFRAMES)
    timeframe_labels: dict[str, str] = dict(TIMEFRAME_LABELS)
    forbidden_exchange_actions: list[str] = sorted(FORBIDDEN_EXCHANGE_ACTIONS)


class CandleDTO(BaseModel):
    symbol: str
    interval: str
    timestamp_s: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal

    @field_validator("interval")
    @classmethod
    def validate_interval(cls, value: str) -> str:
        if value not in SUPPORTED_TIMEFRAMES:
            raise ValueError(f"Unsupported MEXC interval: {value}")
        return value


class MexcOrderDealDTO(BaseModel):
    mexc_deal_id: str
    symbol: str
    side: int
    vol: Decimal
    price: Decimal
    fee: Decimal
    fee_currency: str | None
    profit: Decimal
    category: int | None
    order_id: str
    timestamp_ms: int
    position_mode: int | None
    taker: bool | None
    raw_json: dict[str, Any]


class MexcStopOrderDTO(BaseModel):
    stop_order_id: str
    symbol: str
    order_id: str | None = None
    position_id: str | None = None
    stop_loss_price: Decimal | None = None
    take_profit_price: Decimal | None = None
    state: int | None = None
    trigger_side: int | None = None
    position_type: int | None = None
    vol: Decimal | None = None
    reality_vol: Decimal | None = None
    place_order_id: str | None = None
    is_finished: int | None = None
    create_time_ms: int | None = None
    update_time_ms: int | None = None
    raw_json: dict[str, Any]


class MexcOrderDealsImportRequest(BaseModel):
    user_id: UUID
    symbol: str = Field(min_length=1)
    start_time_ms: int | None = None
    end_time_ms: int | None = None


class MexcOrderDealsImportResponse(BaseModel):
    imported: int
    skipped_duplicates: int
    symbol: str


class MexcImportAndReconstructResponse(MexcOrderDealsImportResponse):
    positions_created: int
    open_positions: int
    closed_positions: int
    warnings: list[str]


class MexcReadinessResponse(BaseModel):
    base_url: str
    credentials_configured: bool
    public_api_reachable: bool
    private_read_authenticated: bool
    message: str
