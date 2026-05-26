import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import RawMexcOrderDeal
from app.schemas.mexc import MEXC_ORDER_DEAL_SIDES, MexcOrderDealDTO
from app.services.mexc_client import MexcApiError

logger = logging.getLogger(__name__)

RETRYABLE_MEXC_STATUS_CODES = {429, 500, 502, 503, 504}


class OrderDealsClient(Protocol):
    def iter_order_deals(
        self,
        symbol: str,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
    ) -> AsyncIterator[MexcOrderDealDTO | dict[str, Any]]:
        ...


@dataclass(frozen=True)
class MexcImportResult:
    imported: int
    skipped_duplicates: int
    symbol: str


class MexcImporter:
    """Imports read-only MEXC Futures historical order deals."""

    def __init__(
        self,
        db: Session,
        client: OrderDealsClient,
        max_retries: int = 3,
        backoff_base_s: float = 0.25,
    ) -> None:
        self.db = db
        self.client = client
        self.max_retries = max_retries
        self.backoff_base_s = backoff_base_s

    async def import_order_deals(
        self,
        user_id: UUID,
        symbol: str,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
    ) -> MexcImportResult:
        deals = await self._collect_order_deals_with_retry(
            symbol=symbol,
            start_time_ms=start_time_ms,
            end_time_ms=end_time_ms,
        )

        imported = 0
        skipped_duplicates = 0
        seen_deal_ids: set[str] = set()

        with self.db.begin():
            for deal in deals:
                normalized = self._normalize_deal(deal)
                mexc_deal_id = normalized["mexc_deal_id"]

                if mexc_deal_id in seen_deal_ids or self._deal_exists(user_id, mexc_deal_id):
                    skipped_duplicates += 1
                    continue

                seen_deal_ids.add(mexc_deal_id)
                self.db.add(RawMexcOrderDeal(user_id=user_id, **normalized))
                imported += 1

        return MexcImportResult(
            imported=imported,
            skipped_duplicates=skipped_duplicates,
            symbol=symbol,
        )

    async def _collect_order_deals_with_retry(
        self,
        symbol: str,
        start_time_ms: int | None,
        end_time_ms: int | None,
    ) -> list[MexcOrderDealDTO | dict[str, Any]]:
        for attempt in range(1, self.max_retries + 1):
            try:
                return [
                    deal
                    async for deal in self.client.iter_order_deals(
                        symbol=symbol,
                        start_time_ms=start_time_ms,
                        end_time_ms=end_time_ms,
                    )
                ]
            except MexcApiError as exc:
                if not self._should_retry(exc, attempt):
                    raise
                logger.warning(
                    "Temporary MEXC order deal import error; retrying.",
                    extra={"status_code": exc.status_code, "attempt": attempt},
                )
                await asyncio.sleep(self.backoff_base_s * (2 ** (attempt - 1)))

        return []

    def _should_retry(self, exc: MexcApiError, attempt: int) -> bool:
        return exc.status_code in RETRYABLE_MEXC_STATUS_CODES and attempt < self.max_retries

    def _deal_exists(self, user_id: UUID, mexc_deal_id: str) -> bool:
        statement = (
            select(RawMexcOrderDeal.id)
            .where(RawMexcOrderDeal.user_id == user_id)
            .where(RawMexcOrderDeal.mexc_deal_id == mexc_deal_id)
            .limit(1)
        )
        return self.db.scalar(statement) is not None

    def _normalize_deal(self, deal: MexcOrderDealDTO | dict[str, Any]) -> dict[str, Any]:
        if isinstance(deal, MexcOrderDealDTO):
            normalized = deal.model_dump()
        elif isinstance(deal, dict):
            normalized = self._normalize_raw_deal_dict(deal)
        else:
            raise TypeError(f"Unsupported MEXC order deal item: {type(deal)!r}")

        side = int(normalized["side"])
        if side not in MEXC_ORDER_DEAL_SIDES:
            logger.warning(
                "Unknown MEXC order deal side encountered during import.",
                extra={"mexc_deal_id": normalized["mexc_deal_id"], "side": side},
            )
        normalized["side"] = side
        return normalized

    def _normalize_raw_deal_dict(self, raw: dict[str, Any]) -> dict[str, Any]:
        return {
            "mexc_deal_id": str(self._required(raw, "mexc_deal_id", "dealId", "deal_id", "id")),
            "symbol": str(self._required(raw, "symbol")),
            "side": int(self._required(raw, "side")),
            "vol": self._decimal(self._required(raw, "vol", "volume")),
            "price": self._decimal(self._required(raw, "price")),
            "fee": self._decimal(self._required(raw, "fee")),
            "fee_currency": self._optional_str(raw, "fee_currency", "feeCurrency"),
            "profit": self._decimal(self._required(raw, "profit")),
            "category": self._optional_int(raw, "category"),
            "order_id": str(self._required(raw, "order_id", "orderId")),
            "timestamp_ms": int(self._required(raw, "timestamp_ms", "timestamp", "createTime")),
            "position_mode": self._optional_int(raw, "position_mode", "positionMode"),
            "taker": self._optional_bool(raw, "taker", "isTaker"),
            "raw_json": dict(raw),
        }

    def _required(self, raw: dict[str, Any], *keys: str) -> Any:
        for key in keys:
            value = raw.get(key)
            if value is not None:
                return value
        raise ValueError(f"MEXC order deal is missing required field: {', '.join(keys)}")

    def _optional_str(self, raw: dict[str, Any], *keys: str) -> str | None:
        for key in keys:
            value = raw.get(key)
            if value is not None:
                return str(value)
        return None

    def _optional_int(self, raw: dict[str, Any], *keys: str) -> int | None:
        value = self._optional_str(raw, *keys)
        return int(value) if value is not None else None

    def _optional_bool(self, raw: dict[str, Any], *keys: str) -> bool | None:
        for key in keys:
            value = raw.get(key)
            if value is None:
                continue
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                return value.lower() in {"true", "1", "yes"}
            return bool(value)
        return None

    def _decimal(self, value: Any) -> Decimal:
        return Decimal(str(value))
