from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import (
    MEXC_SIDE_CLOSE_LONG,
    MEXC_SIDE_CLOSE_SHORT,
    MEXC_SIDE_OPEN_LONG,
    MEXC_SIDE_OPEN_SHORT,
)
from app.core.time import datetime_from_ms
from app.db.models import FuturesPosition, FuturesPositionDeal, RawMexcOrderDeal
from app.schemas.trades import PositionTransactionRead

SIDE_LABELS = {
    MEXC_SIDE_OPEN_LONG: "open_long",
    MEXC_SIDE_CLOSE_SHORT: "close_short",
    MEXC_SIDE_OPEN_SHORT: "open_short",
    MEXC_SIDE_CLOSE_LONG: "close_long",
}


class PositionContextService:
    """Builds transaction-time context for reconstructed positions."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def transaction_timeline(
        self,
        position: FuturesPosition,
    ) -> tuple[list[PositionTransactionRead], str]:
        linked_deals = self._load_linked_deals(position_id=position.id)
        if linked_deals:
            return [self._deal_to_read(deal, "linked") for deal in linked_deals], "linked"

        inferred_deals = self._infer_deals(position=position)
        if inferred_deals:
            return [self._deal_to_read(deal, "inferred") for deal in inferred_deals], "inferred"

        return [], "unavailable"

    def _load_linked_deals(self, position_id: UUID) -> list[RawMexcOrderDeal]:
        if not hasattr(self.db, "execute"):
            position_deals = getattr(self.db, "position_deals", [])
            raw_deals = getattr(self.db, "raw_deals", [])
            linked_raw_ids = [
                link.raw_mexc_order_deal_id
                for link in sorted(
                    position_deals,
                    key=lambda link: getattr(link, "sort_order", 0),
                )
                if link.position_id == position_id
            ]
            return [
                deal
                for raw_id in linked_raw_ids
                for deal in raw_deals
                if getattr(deal, "id", None) == raw_id
            ]

        statement = (
            select(RawMexcOrderDeal)
            .join(
                FuturesPositionDeal,
                FuturesPositionDeal.raw_mexc_order_deal_id == RawMexcOrderDeal.id,
            )
            .where(FuturesPositionDeal.position_id == position_id)
            .order_by(FuturesPositionDeal.sort_order.asc())
        )
        return list(self.db.scalars(statement).all())

    def _infer_deals(self, position: FuturesPosition) -> list[RawMexcOrderDeal]:
        start_ms = _datetime_to_ms(position.opened_at)
        end_ms = _datetime_to_ms(position.closed_at) if position.closed_at is not None else None

        if not hasattr(self.db, "scalars"):
            return sorted(
                [
                    deal
                    for deal in getattr(self.db, "raw_deals", [])
                    if deal.user_id == position.user_id
                    and deal.symbol == position.symbol
                    and deal.timestamp_ms >= start_ms
                    and (end_ms is None or deal.timestamp_ms <= end_ms)
                ],
                key=lambda deal: (deal.timestamp_ms, str(deal.mexc_deal_id)),
            )

        statement = (
            select(RawMexcOrderDeal)
            .where(RawMexcOrderDeal.user_id == position.user_id)
            .where(RawMexcOrderDeal.symbol == position.symbol)
            .where(RawMexcOrderDeal.timestamp_ms >= start_ms)
            .order_by(RawMexcOrderDeal.timestamp_ms.asc(), RawMexcOrderDeal.mexc_deal_id.asc())
        )
        if end_ms is not None:
            statement = statement.where(RawMexcOrderDeal.timestamp_ms <= end_ms)
        return list(self.db.scalars(statement).all())

    @staticmethod
    def _deal_to_read(deal: RawMexcOrderDeal, source: str) -> PositionTransactionRead:
        raw_id = getattr(deal, "id", None) or uuid4()
        return PositionTransactionRead(
            id=raw_id,
            raw_mexc_order_deal_id=raw_id,
            mexc_deal_id=deal.mexc_deal_id,
            order_id=deal.order_id,
            side=deal.side,
            side_label=SIDE_LABELS.get(deal.side, f"unknown_{deal.side}"),
            vol=deal.vol,
            price=deal.price,
            fee=deal.fee,
            fee_currency=deal.fee_currency,
            profit=deal.profit,
            timestamp=datetime_from_ms(deal.timestamp_ms),
            timestamp_ms=deal.timestamp_ms,
            source=source,
        )


def _datetime_to_ms(value: datetime) -> int:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return int(value.timestamp() * 1000)
