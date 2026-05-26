from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class IndicatorSnapshotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    position_id: UUID
    symbol: str
    timeframe: str
    timestamp: datetime
    price: Decimal
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


class IndicatorSnapshotCalculationRequest(BaseModel):
    timeframes: list[str]


class IndicatorSnapshotCalculationResponse(BaseModel):
    position_id: UUID
    snapshots_created_or_updated: int
    warnings: list[str]


class CandleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    exchange: str
    symbol: str
    timeframe: str
    timestamp: datetime
    timestamp_s: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
