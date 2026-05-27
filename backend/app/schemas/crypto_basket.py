import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

CRYPTO_BASKET_MAX_ITEMS = 50
SYMBOL_PATTERN = re.compile(r"^[A-Z0-9]+_[A-Z0-9]+$")


class CryptoBasketItemInput(BaseModel):
    id: UUID | None = None
    sort_order: int = Field(ge=0)
    symbol: str = Field(min_length=1, max_length=64)
    enabled: bool = True

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        symbol = value.strip().upper()
        if not symbol:
            raise ValueError("Symbol must not be empty.")
        if not SYMBOL_PATTERN.match(symbol):
            raise ValueError("Symbol must use MEXC Futures format like BTC_USDT.")
        return symbol


class CryptoBasketUpsert(BaseModel):
    items: list[CryptoBasketItemInput] = Field(
        default_factory=list,
        max_length=CRYPTO_BASKET_MAX_ITEMS,
    )

    @field_validator("items")
    @classmethod
    def reject_duplicate_symbols(
        cls,
        value: list[CryptoBasketItemInput],
    ) -> list[CryptoBasketItemInput]:
        symbols = [item.symbol for item in value]
        duplicates = sorted({symbol for symbol in symbols if symbols.count(symbol) > 1})
        if duplicates:
            raise ValueError(f"Duplicate basket symbols are not allowed: {', '.join(duplicates)}.")
        return value


class CryptoBasketItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    basket_id: UUID
    sort_order: int
    symbol: str
    enabled: bool
    sync_status: Literal["idle", "running", "success", "error"]
    last_sync_started_at: datetime | None = None
    last_sync_finished_at: datetime | None = None
    last_successful_sync_at: datetime | None = None
    last_sync_start_time_ms: int | None = None
    last_sync_end_time_ms: int | None = None
    last_imported: int
    last_skipped_duplicates: int
    last_positions_created: int
    last_open_positions: int
    last_closed_positions: int
    last_warnings: list[str]
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime


class CryptoBasketRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    items: list[CryptoBasketItemRead]
    created_at: datetime
    updated_at: datetime


class CryptoBasketSyncRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    basket_id: UUID
    basket_item_id: UUID
    symbol: str
    run_type: Literal["manual", "automatic"]
    status: Literal["running", "success", "error", "skipped"]
    started_at: datetime
    finished_at: datetime | None = None
    start_time_ms: int | None = None
    end_time_ms: int | None = None
    imported: int
    skipped_duplicates: int
    positions_created: int
    open_positions: int
    closed_positions: int
    warnings: list[str]
    error: str | None = None


class CryptoBasketSyncResponse(BaseModel):
    basket: CryptoBasketRead
    runs: list[CryptoBasketSyncRunRead]
