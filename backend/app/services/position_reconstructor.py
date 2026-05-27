from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.constants import (
    MEXC_SIDE_CLOSE_LONG,
    MEXC_SIDE_CLOSE_SHORT,
    MEXC_SIDE_OPEN_LONG,
    MEXC_SIDE_OPEN_SHORT,
)
from app.core.time import datetime_from_ms
from app.db.models import FuturesPosition, FuturesPositionDeal, RawMexcOrderDeal
from app.schemas.trades import ReconstructionReport

RAW_SOURCE_MEXC_ORDER_DEALS_V3 = "mexc_order_deals_v3"
MEXC_EXCHANGE = "MEXC"
ZERO = Decimal("0")


@dataclass
class PositionLedger:
    user_id: UUID
    symbol: str
    direction: str
    opened_at: datetime
    avg_entry_price: Decimal
    total_volume: Decimal
    open_volume: Decimal
    total_fees: Decimal = ZERO
    realized_pnl: Decimal = ZERO
    funding_fees: Decimal = ZERO
    closed_volume: Decimal = ZERO
    avg_exit_price: Decimal | None = None
    raw_deal_ids: list[UUID] = field(default_factory=list)

    def add_entry(
        self,
        volume: Decimal,
        price: Decimal,
        fee: Decimal,
        raw_deal_id: UUID | None,
    ) -> None:
        new_total_volume = self.total_volume + volume
        self.avg_entry_price = (
            (self.avg_entry_price * self.total_volume) + (price * volume)
        ) / new_total_volume
        self.total_volume = new_total_volume
        self.open_volume += volume
        self.total_fees += abs(fee)
        if raw_deal_id is not None:
            self.raw_deal_ids.append(raw_deal_id)

    def add_exit(
        self,
        volume: Decimal,
        price: Decimal,
        fee: Decimal,
        profit: Decimal,
        raw_deal_id: UUID | None,
    ) -> None:
        new_closed_volume = self.closed_volume + volume
        if self.avg_exit_price is None:
            self.avg_exit_price = price
        else:
            self.avg_exit_price = (
                (self.avg_exit_price * self.closed_volume) + (price * volume)
            ) / new_closed_volume

        self.closed_volume = new_closed_volume
        self.open_volume -= volume
        if self.open_volume < ZERO:
            self.open_volume = ZERO
        self.total_fees += abs(fee)
        self.realized_pnl += profit
        if raw_deal_id is not None:
            self.raw_deal_ids.append(raw_deal_id)

    def to_model(self, status: str, closed_at: datetime | None = None) -> FuturesPosition:
        position = FuturesPosition(
            user_id=self.user_id,
            exchange=MEXC_EXCHANGE,
            symbol=self.symbol,
            direction=self.direction,
            opened_at=self.opened_at,
            closed_at=closed_at,
            avg_entry_price=self.avg_entry_price,
            avg_exit_price=self.avg_exit_price,
            total_volume=self.total_volume,
            realized_pnl=self.realized_pnl,
            total_fees=self.total_fees,
            funding_fees=self.funding_fees,
            leverage=None,
            status=status,
            raw_source=RAW_SOURCE_MEXC_ORDER_DEALS_V3,
        )
        position._raw_deal_ids = list(self.raw_deal_ids)
        return position


class PositionReconstructor:
    """Reconstructs MEXC Futures positions from imported read-only order deals."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def reconstruct(self, user_id: UUID, symbol: str) -> ReconstructionReport:
        warnings: list[str] = []
        with self.db.begin():
            self._delete_existing_positions(user_id=user_id, symbol=symbol)
            raw_deals = self._load_raw_deals(user_id=user_id, symbol=symbol)
            positions = self._reconstruct_positions(
                user_id=user_id,
                symbol=symbol,
                raw_deals=raw_deals,
                warnings=warnings,
            )
            for position in positions:
                self._save_position(position)

        open_positions = sum(1 for position in positions if position.status == "open")
        closed_positions = sum(1 for position in positions if position.status == "closed")
        return ReconstructionReport(
            positions_created=len(positions),
            open_positions=open_positions,
            closed_positions=closed_positions,
            warnings=warnings,
        )

    def _load_raw_deals(self, user_id: UUID, symbol: str) -> list[RawMexcOrderDeal]:
        statement = (
            select(RawMexcOrderDeal)
            .where(RawMexcOrderDeal.user_id == user_id)
            .where(RawMexcOrderDeal.symbol == symbol)
            .order_by(RawMexcOrderDeal.timestamp_ms.asc(), RawMexcOrderDeal.mexc_deal_id.asc())
        )
        return list(self.db.scalars(statement).all())

    def _delete_existing_positions(self, user_id: UUID, symbol: str) -> None:
        statement = (
            delete(FuturesPosition)
            .where(FuturesPosition.user_id == user_id)
            .where(FuturesPosition.symbol == symbol)
            .where(FuturesPosition.raw_source == RAW_SOURCE_MEXC_ORDER_DEALS_V3)
        )
        self.db.execute(statement)

    def _save_position(self, position: FuturesPosition) -> None:
        self.db.add(position)
        raw_deal_ids = getattr(position, "_raw_deal_ids", [])
        if not raw_deal_ids:
            return
        if hasattr(self.db, "flush"):
            self.db.flush()
        if position.id is None:
            return
        for sort_order, raw_deal_id in enumerate(raw_deal_ids):
            self.db.add(
                FuturesPositionDeal(
                    position_id=position.id,
                    raw_mexc_order_deal_id=raw_deal_id,
                    sort_order=sort_order,
                )
            )

    def _reconstruct_positions(
        self,
        user_id: UUID,
        symbol: str,
        raw_deals: list[RawMexcOrderDeal],
        warnings: list[str],
    ) -> list[FuturesPosition]:
        positions: list[FuturesPosition] = []
        ledgers: dict[str, PositionLedger | None] = {"long": None, "short": None}

        for deal in self._sort_deals(raw_deals):
            side = deal.side
            if side == MEXC_SIDE_OPEN_LONG:
                ledgers["long"] = self._handle_entry(
                    user_id=user_id,
                    symbol=symbol,
                    direction="long",
                    ledger=ledgers["long"],
                    deal=deal,
                    warnings=warnings,
                )
            elif side == MEXC_SIDE_CLOSE_LONG:
                ledgers["long"] = self._handle_exit(
                    direction="long",
                    ledger=ledgers["long"],
                    deal=deal,
                    warnings=warnings,
                    positions=positions,
                )
            elif side == MEXC_SIDE_OPEN_SHORT:
                ledgers["short"] = self._handle_entry(
                    user_id=user_id,
                    symbol=symbol,
                    direction="short",
                    ledger=ledgers["short"],
                    deal=deal,
                    warnings=warnings,
                )
            elif side == MEXC_SIDE_CLOSE_SHORT:
                ledgers["short"] = self._handle_exit(
                    direction="short",
                    ledger=ledgers["short"],
                    deal=deal,
                    warnings=warnings,
                    positions=positions,
                )
            else:
                warnings.append(
                    f"Skipping deal {deal.mexc_deal_id}: unknown MEXC side {deal.side}."
                )

        for ledger in ledgers.values():
            if ledger is not None and ledger.open_volume > ZERO:
                positions.append(ledger.to_model(status="open"))

        return positions

    def _handle_entry(
        self,
        user_id: UUID,
        symbol: str,
        direction: str,
        ledger: PositionLedger | None,
        deal: RawMexcOrderDeal,
        warnings: list[str],
    ) -> PositionLedger | None:
        volume = self._decimal(deal.vol)
        if volume <= ZERO:
            warnings.append(f"Skipping deal {deal.mexc_deal_id}: non-positive entry volume.")
            return ledger

        price = self._decimal(deal.price)
        fee = self._decimal(deal.fee)
        if ledger is None:
            return PositionLedger(
                user_id=user_id,
                symbol=symbol,
                direction=direction,
                opened_at=datetime_from_ms(deal.timestamp_ms),
                avg_entry_price=price,
                total_volume=volume,
                open_volume=volume,
                total_fees=abs(fee),
                raw_deal_ids=[deal.id] if getattr(deal, "id", None) is not None else [],
            )

        ledger.add_entry(
            volume=volume,
            price=price,
            fee=fee,
            raw_deal_id=getattr(deal, "id", None),
        )
        return ledger

    def _handle_exit(
        self,
        direction: str,
        ledger: PositionLedger | None,
        deal: RawMexcOrderDeal,
        warnings: list[str],
        positions: list[FuturesPosition],
    ) -> PositionLedger | None:
        if ledger is None or ledger.open_volume <= ZERO:
            warnings.append(
                f"Skipping deal {deal.mexc_deal_id}: close {direction} without open position."
            )
            return ledger

        close_volume = self._decimal(deal.vol)
        if close_volume <= ZERO:
            warnings.append(f"Skipping deal {deal.mexc_deal_id}: non-positive close volume.")
            return ledger

        applied_close_volume = close_volume
        if close_volume > ledger.open_volume:
            applied_close_volume = ledger.open_volume
            warnings.append(
                f"Deal {deal.mexc_deal_id}: close volume {close_volume} exceeds open "
                f"{direction} volume {ledger.open_volume}; closed available volume only."
            )

        ledger.add_exit(
            volume=applied_close_volume,
            price=self._decimal(deal.price),
            fee=self._decimal(deal.fee),
            profit=self._decimal_or_zero(getattr(deal, "profit", None)),
            raw_deal_id=getattr(deal, "id", None),
        )

        if ledger.open_volume == ZERO:
            positions.append(
                ledger.to_model(status="closed", closed_at=datetime_from_ms(deal.timestamp_ms))
            )
            return None

        return ledger

    def _sort_deals(self, raw_deals: list[RawMexcOrderDeal]) -> list[RawMexcOrderDeal]:
        return sorted(raw_deals, key=lambda deal: (deal.timestamp_ms, str(deal.mexc_deal_id)))

    def _decimal(self, value: Decimal | int | str) -> Decimal:
        return value if isinstance(value, Decimal) else Decimal(str(value))

    def _decimal_or_zero(self, value: Decimal | int | str | None) -> Decimal:
        return ZERO if value is None else self._decimal(value)
