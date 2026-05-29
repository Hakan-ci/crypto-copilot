from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import MEXC_SIDE_OPEN_LONG, MEXC_SIDE_OPEN_SHORT
from app.core.time import utc_now
from app.db.models import FuturesPosition, PositionTradeMetadata
from app.schemas.mexc import MexcStopOrderDTO
from app.schemas.trades import PositionTradeMetadataRead, PositionTradeMetadataUpsert
from app.services.position_context import PositionContextService

OPENING_STOP_LOOKBACK = timedelta(minutes=5)
OPENING_STOP_LOOKAHEAD = timedelta(hours=24)
MEXC_POSITION_TYPE_BY_DIRECTION = {"long": 1, "short": 2}
OPENING_SIDE_BY_DIRECTION = {"long": MEXC_SIDE_OPEN_LONG, "short": MEXC_SIDE_OPEN_SHORT}
ZERO = Decimal("0")


class StopOrdersClient(Protocol):
    def iter_stop_orders(
        self,
        symbol: str,
        is_finished: int | None = None,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
    ) -> AsyncIterator[MexcStopOrderDTO]:
        ...


class TradeMetadataService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def read_metadata(self, position_id: UUID) -> PositionTradeMetadataRead | None:
        self._ensure_position_exists(position_id)
        row = self.load_metadata(position_id)
        return PositionTradeMetadataRead.model_validate(row) if row is not None else None

    def upsert_metadata(
        self,
        position_id: UUID,
        payload: PositionTradeMetadataUpsert,
    ) -> PositionTradeMetadataRead:
        self._ensure_position_exists(position_id)
        row = self.load_metadata(position_id)
        if row is None:
            row = PositionTradeMetadata(position_id=position_id)
            self.db.add(row)
        row.planned_stop_loss_price = payload.planned_stop_loss_price
        row.notes = payload.notes
        row.updated_at = utc_now()
        self.db.commit()
        if hasattr(self.db, "refresh"):
            self.db.refresh(row)
        return PositionTradeMetadataRead.model_validate(row)

    async def sync_stop_loss_from_mexc(
        self,
        position_id: UUID,
        client: StopOrdersClient,
    ) -> PositionTradeMetadataRead | None:
        position = self._ensure_position_exists(position_id)
        stop_order = await self._find_opening_stop_loss_order(position=position, client=client)
        if stop_order is None or stop_order.stop_loss_price is None:
            row = self.load_metadata(position_id)
            return PositionTradeMetadataRead.model_validate(row) if row is not None else None

        row = self.load_metadata(position_id)
        now = utc_now()
        if row is None:
            row = PositionTradeMetadata(
                position_id=position_id,
                created_at=now,
                updated_at=now,
            )
            self.db.add(row)
        row.planned_stop_loss_price = stop_order.stop_loss_price
        if row.created_at is None:
            row.created_at = now
        row.updated_at = now
        self.db.commit()
        if hasattr(self.db, "refresh"):
            self.db.refresh(row)
        return PositionTradeMetadataRead.model_validate(row)

    async def sync_stop_losses_for_user_symbol(
        self,
        user_id: UUID,
        symbol: str,
        client: StopOrdersClient,
    ) -> int:
        synced = 0
        for position in self._load_positions_for_user_symbol(user_id=user_id, symbol=symbol):
            before = self.load_metadata(position.id) if position.id is not None else None
            before_stop = before.planned_stop_loss_price if before is not None else None
            metadata = await self.sync_stop_loss_from_mexc(
                position_id=position.id,
                client=client,
            )
            after_stop = (
                metadata.planned_stop_loss_price if metadata is not None else before_stop
            )
            if after_stop is not None and after_stop != before_stop:
                synced += 1
        return synced

    def load_metadata(self, position_id: UUID) -> PositionTradeMetadata | None:
        statement = (
            select(PositionTradeMetadata)
            .where(PositionTradeMetadata.position_id == position_id)
            .limit(1)
        )
        return self.db.scalar(statement)

    def _ensure_position_exists(self, position_id: UUID) -> FuturesPosition:
        position = self.db.get(FuturesPosition, position_id)
        if position is None:
            raise TradeMetadataPositionNotFoundError(f"Position not found: {position_id}")
        return position

    def _load_positions_for_user_symbol(self, user_id: UUID, symbol: str) -> list[FuturesPosition]:
        statement = (
            select(FuturesPosition)
            .where(FuturesPosition.user_id == user_id)
            .where(FuturesPosition.symbol == symbol)
            .order_by(FuturesPosition.opened_at.asc(), FuturesPosition.created_at.asc())
        )
        return list(self.db.scalars(statement).all())

    async def _find_opening_stop_loss_order(
        self,
        position: FuturesPosition,
        client: StopOrdersClient,
    ) -> MexcStopOrderDTO | None:
        start_time_ms, end_time_ms = self._opening_stop_order_window_ms(position)
        opening_order_id = self._opening_order_id(position)
        candidates: list[MexcStopOrderDTO] = []
        async for order in client.iter_stop_orders(
            symbol=position.symbol,
            start_time_ms=start_time_ms,
            end_time_ms=end_time_ms,
        ):
            if self._is_matching_stop_loss_order(
                order=order,
                position=position,
            ):
                candidates.append(order)

        if not candidates:
            return None
        return sorted(
            candidates,
            key=lambda order: self._stop_order_rank(order, opening_order_id),
        )[0]

    def _opening_order_id(self, position: FuturesPosition) -> str | None:
        expected_side = OPENING_SIDE_BY_DIRECTION.get(position.direction)
        if expected_side is None:
            return None
        transactions, _source = PositionContextService(db=self.db).transaction_timeline(position)
        for transaction in transactions:
            if transaction.side == expected_side and transaction.order_id:
                return transaction.order_id
        return None

    def _is_matching_stop_loss_order(
        self,
        order: MexcStopOrderDTO,
        position: FuturesPosition,
    ) -> bool:
        if order.symbol != position.symbol:
            return False
        if order.stop_loss_price is None or order.stop_loss_price <= ZERO:
            return False

        expected_position_type = MEXC_POSITION_TYPE_BY_DIRECTION.get(position.direction)
        if (
            expected_position_type is not None
            and order.position_type is not None
            and order.position_type != expected_position_type
        ):
            return False

        return order.trigger_side in {None, 0, 2}

    def _stop_order_rank(
        self,
        order: MexcStopOrderDTO,
        opening_order_id: str | None,
    ) -> tuple[int, int, str]:
        order_ids = {value for value in (order.order_id, order.place_order_id) if value}
        order_id_rank = 0 if opening_order_id is not None and opening_order_id in order_ids else 1
        create_time_ms = order.create_time_ms or 9_999_999_999_999
        return (order_id_rank, create_time_ms, order.stop_order_id)

    def _opening_stop_order_window_ms(self, position: FuturesPosition) -> tuple[int, int]:
        opened_at = self._normalize_datetime(position.opened_at)
        latest_opening_time = opened_at + OPENING_STOP_LOOKAHEAD
        if position.closed_at is not None:
            latest_opening_time = min(
                latest_opening_time,
                self._normalize_datetime(position.closed_at),
            )
        else:
            latest_opening_time = min(latest_opening_time, datetime.now(tz=UTC))
        if latest_opening_time <= opened_at:
            latest_opening_time = opened_at + timedelta(minutes=1)
        return (
            self._datetime_to_ms(opened_at - OPENING_STOP_LOOKBACK),
            self._datetime_to_ms(latest_opening_time),
        )

    @staticmethod
    def _normalize_datetime(value: datetime) -> datetime:
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

    @staticmethod
    def _datetime_to_ms(value: datetime) -> int:
        return int(value.timestamp() * 1000)


class TradeMetadataPositionNotFoundError(ValueError):
    pass
