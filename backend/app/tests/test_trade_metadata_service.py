import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from app.core.constants import MEXC_SIDE_OPEN_LONG
from app.db.models import FuturesPosition, PositionTradeMetadata, RawMexcOrderDeal
from app.schemas.mexc import MexcStopOrderDTO
from app.services.trade_metadata_service import TradeMetadataService


class FakeDbSession:
    def __init__(
        self,
        position: FuturesPosition,
        metadata: PositionTradeMetadata | None = None,
    ) -> None:
        self.position = position
        self.metadata = metadata
        self.added: list[Any] = []
        self.raw_deals: list[RawMexcOrderDeal] = []
        self.committed = False

    def get(self, model: type, object_id: UUID) -> FuturesPosition | None:
        _ = model
        return self.position if object_id == self.position.id else None

    def scalar(self, statement) -> PositionTradeMetadata | None:
        _ = statement
        return self.metadata

    def add(self, row: Any) -> None:
        self.added.append(row)
        if isinstance(row, PositionTradeMetadata):
            self.metadata = row

    def commit(self) -> None:
        self.committed = True

    def refresh(self, row: Any) -> None:
        if getattr(row, "id", None) is None:
            row.id = uuid4()


class FakeStopOrdersClient:
    def __init__(self, orders: list[MexcStopOrderDTO]) -> None:
        self.orders = orders
        self.calls: list[dict[str, Any]] = []

    async def iter_stop_orders(
        self,
        symbol: str,
        is_finished: int | None = None,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
    ) -> AsyncIterator[MexcStopOrderDTO]:
        self.calls.append(
            {
                "symbol": symbol,
                "is_finished": is_finished,
                "start_time_ms": start_time_ms,
                "end_time_ms": end_time_ms,
            }
        )
        for order in self.orders:
            yield order


def make_position(position_id: UUID | None = None) -> FuturesPosition:
    opened_at = datetime.fromtimestamp(1_710_000_000, tz=UTC)
    return FuturesPosition(
        id=position_id or uuid4(),
        user_id=uuid4(),
        exchange="MEXC",
        symbol="BTC_USDT",
        direction="long",
        opened_at=opened_at,
        closed_at=datetime.fromtimestamp(1_710_003_600, tz=UTC),
        avg_entry_price=Decimal("100"),
        avg_exit_price=Decimal("110"),
        total_volume=Decimal("1"),
        realized_pnl=Decimal("10"),
        total_fees=Decimal("0.20"),
        funding_fees=Decimal("0"),
        status="closed",
    )


def make_raw_entry(position: FuturesPosition) -> RawMexcOrderDeal:
    return RawMexcOrderDeal(
        id=uuid4(),
        user_id=position.user_id,
        mexc_deal_id="deal-entry",
        symbol=position.symbol,
        side=MEXC_SIDE_OPEN_LONG,
        vol=Decimal("1"),
        price=Decimal("100"),
        fee=Decimal("0.10"),
        fee_currency="USDT",
        profit=Decimal("0"),
        category=None,
        order_id="entry-order",
        timestamp_ms=1_710_000_000_000,
        position_mode=None,
        taker=None,
        raw_json={"id": "deal-entry"},
    )


def make_stop_order(
    stop_order_id: str,
    stop_loss_price: str,
    position_type: int = 1,
    place_order_id: str | None = None,
    create_time_ms: int = 1_710_000_030_000,
) -> MexcStopOrderDTO:
    return MexcStopOrderDTO(
        stop_order_id=stop_order_id,
        symbol="BTC_USDT",
        order_id="0",
        position_id=None,
        stop_loss_price=Decimal(stop_loss_price),
        take_profit_price=Decimal("0"),
        state=3,
        trigger_side=2,
        position_type=position_type,
        vol=Decimal("1"),
        reality_vol=Decimal("1"),
        place_order_id=place_order_id,
        is_finished=1,
        create_time_ms=create_time_ms,
        update_time_ms=create_time_ms,
        raw_json={"id": stop_order_id},
    )


def test_sync_stop_loss_persists_matching_mexc_stop_order():
    position = make_position()
    db = FakeDbSession(position=position)
    db.raw_deals = [make_raw_entry(position)]
    client = FakeStopOrdersClient(
        [
            make_stop_order("wrong-side", "91", position_type=2),
            make_stop_order("matched", "98", place_order_id="entry-order"),
        ]
    )
    service = TradeMetadataService(db=db)

    metadata = asyncio.run(
        service.sync_stop_loss_from_mexc(position_id=position.id, client=client)
    )

    assert metadata is not None
    assert metadata.planned_stop_loss_price == Decimal("98")
    assert db.metadata is not None
    assert db.metadata.planned_stop_loss_price == Decimal("98")
    assert db.committed is True
    assert client.calls[0]["symbol"] == "BTC_USDT"
    assert client.calls[0]["start_time_ms"] == 1_709_999_700_000


def test_sync_stop_loss_leaves_existing_metadata_when_no_match():
    position = make_position()
    metadata = PositionTradeMetadata(
        id=uuid4(),
        position_id=position.id,
        planned_stop_loss_price=Decimal("97"),
        notes=None,
        created_at=position.opened_at,
        updated_at=position.opened_at,
    )
    db = FakeDbSession(position=position, metadata=metadata)
    client = FakeStopOrdersClient([])
    service = TradeMetadataService(db=db)

    synced = asyncio.run(
        service.sync_stop_loss_from_mexc(position_id=position.id, client=client)
    )

    assert synced is not None
    assert synced.planned_stop_loss_price == Decimal("97")
    assert db.committed is False
