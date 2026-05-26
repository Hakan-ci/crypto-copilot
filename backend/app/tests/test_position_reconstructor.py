from contextlib import AbstractContextManager
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from app.core.time import datetime_from_ms
from app.db.models import FuturesPosition, RawMexcOrderDeal
from app.services.position_reconstructor import (
    RAW_SOURCE_MEXC_ORDER_DEALS_V3,
    PositionReconstructor,
)


class FakeTransaction(AbstractContextManager["FakeTransaction"]):
    def __init__(self, db: "FakeDbSession") -> None:
        self.db = db

    def __enter__(self) -> "FakeTransaction":
        self.db.transaction_started = True
        return self

    def __exit__(self, *args: object) -> None:
        self.db.transaction_exited = True
        return None


class FakeDbSession:
    def __init__(self) -> None:
        self.raw_deals: list[RawMexcOrderDeal] = []
        self.positions: list[FuturesPosition] = []
        self.transaction_started = False
        self.transaction_exited = False

    def begin(self) -> FakeTransaction:
        return FakeTransaction(self)

    def add(self, row: Any) -> None:
        self.positions.append(row)


class ReconstructorForTest(PositionReconstructor):
    def _load_raw_deals(self, user_id: UUID, symbol: str) -> list[RawMexcOrderDeal]:
        return [
            deal
            for deal in self.db.raw_deals
            if deal.user_id == user_id and deal.symbol == symbol
        ]

    def _delete_existing_positions(self, user_id: UUID, symbol: str) -> None:
        self.db.positions = [
            position
            for position in self.db.positions
            if not (
                position.user_id == user_id
                and position.symbol == symbol
                and position.raw_source == RAW_SOURCE_MEXC_ORDER_DEALS_V3
            )
        ]


def make_raw_deal(
    user_id: UUID,
    deal_id: str,
    side: int,
    vol: str,
    price: str,
    timestamp_ms: int,
    fee: str = "0",
    profit: str = "0",
    symbol: str = "BTC_USDT",
) -> RawMexcOrderDeal:
    return RawMexcOrderDeal(
        user_id=user_id,
        mexc_deal_id=deal_id,
        symbol=symbol,
        side=side,
        vol=Decimal(vol),
        price=Decimal(price),
        fee=Decimal(fee),
        fee_currency="USDT",
        profit=Decimal(profit),
        category=None,
        order_id=f"order-{deal_id}",
        timestamp_ms=timestamp_ms,
        position_mode=None,
        taker=None,
        raw_json={
            "id": deal_id,
            "side": side,
            "vol": vol,
            "price": price,
            "timestamp": timestamp_ms,
        },
    )


def run_reconstruction(
    raw_deals: list[RawMexcOrderDeal],
    user_id: UUID,
    symbol: str = "BTC_USDT",
) -> tuple[FakeDbSession, ReconstructorForTest, Any]:
    db = FakeDbSession()
    db.raw_deals = raw_deals
    reconstructor = ReconstructorForTest(db)
    report = reconstructor.reconstruct(user_id=user_id, symbol=symbol)
    return db, reconstructor, report


def test_single_long_open_close_creates_closed_position():
    user_id = uuid4()
    db, _, report = run_reconstruction(
        [
            make_raw_deal(user_id, "001", side=1, vol="1", price="100", timestamp_ms=1000),
            make_raw_deal(
                user_id,
                "002",
                side=4,
                vol="1",
                price="110",
                timestamp_ms=2000,
                profit="10",
            ),
        ],
        user_id,
    )

    assert report.positions_created == 1
    assert report.closed_positions == 1
    position = db.positions[0]
    assert position.direction == "long"
    assert position.status == "closed"
    assert position.avg_entry_price == Decimal("100")
    assert position.avg_exit_price == Decimal("110")
    assert position.realized_pnl == Decimal("10")
    assert position.opened_at == datetime_from_ms(1000)
    assert position.closed_at == datetime_from_ms(2000)


def test_partial_long_entries_update_weighted_average_entry():
    user_id = uuid4()
    db, _, report = run_reconstruction(
        [
            make_raw_deal(user_id, "001", side=1, vol="1", price="100", timestamp_ms=1000),
            make_raw_deal(user_id, "002", side=1, vol="1", price="120", timestamp_ms=2000),
        ],
        user_id,
    )

    assert report.open_positions == 1
    assert db.positions[0].status == "open"
    assert db.positions[0].avg_entry_price == Decimal("110")
    assert db.positions[0].total_volume == Decimal("2")


def test_partial_long_exits_update_weighted_average_exit():
    user_id = uuid4()
    db, _, report = run_reconstruction(
        [
            make_raw_deal(user_id, "001", side=1, vol="2", price="100", timestamp_ms=1000),
            make_raw_deal(user_id, "002", side=4, vol="1", price="110", timestamp_ms=2000),
            make_raw_deal(user_id, "003", side=4, vol="1", price="120", timestamp_ms=3000),
        ],
        user_id,
    )

    assert report.closed_positions == 1
    assert db.positions[0].avg_exit_price == Decimal("115")
    assert db.positions[0].total_volume == Decimal("2")


def test_single_short_open_close_creates_closed_position():
    user_id = uuid4()
    db, _, report = run_reconstruction(
        [
            make_raw_deal(user_id, "001", side=3, vol="1", price="100", timestamp_ms=1000),
            make_raw_deal(
                user_id,
                "002",
                side=2,
                vol="1",
                price="90",
                timestamp_ms=2000,
                profit="10",
            ),
        ],
        user_id,
    )

    assert report.positions_created == 1
    assert report.closed_positions == 1
    position = db.positions[0]
    assert position.direction == "short"
    assert position.status == "closed"
    assert position.avg_entry_price == Decimal("100")
    assert position.avg_exit_price == Decimal("90")
    assert position.realized_pnl == Decimal("10")


def test_partial_short_entries_and_exits():
    user_id = uuid4()
    db, _, report = run_reconstruction(
        [
            make_raw_deal(user_id, "001", side=3, vol="1", price="100", timestamp_ms=1000),
            make_raw_deal(user_id, "002", side=3, vol="1", price="120", timestamp_ms=2000),
            make_raw_deal(user_id, "003", side=2, vol="1", price="90", timestamp_ms=3000),
            make_raw_deal(user_id, "004", side=2, vol="1", price="80", timestamp_ms=4000),
        ],
        user_id,
    )

    assert report.closed_positions == 1
    position = db.positions[0]
    assert position.direction == "short"
    assert position.avg_entry_price == Decimal("110")
    assert position.avg_exit_price == Decimal("85")
    assert position.status == "closed"


def test_orphan_close_does_not_crash_and_adds_warning():
    user_id = uuid4()
    db, _, report = run_reconstruction(
        [make_raw_deal(user_id, "001", side=4, vol="1", price="110", timestamp_ms=1000)],
        user_id,
    )

    assert db.positions == []
    assert report.positions_created == 0
    assert "without open position" in report.warnings[0]


def test_excess_close_closes_to_zero_without_negative_volume():
    user_id = uuid4()
    db, _, report = run_reconstruction(
        [
            make_raw_deal(user_id, "001", side=1, vol="1", price="100", timestamp_ms=1000),
            make_raw_deal(user_id, "002", side=4, vol="2", price="110", timestamp_ms=2000),
        ],
        user_id,
    )

    assert report.closed_positions == 1
    assert report.open_positions == 0
    assert "exceeds open long volume" in report.warnings[0]
    assert db.positions[0].total_volume == Decimal("1")
    assert db.positions[0].avg_exit_price == Decimal("110")


def test_total_fees_sums_absolute_entry_and_exit_fees():
    user_id = uuid4()
    db, _, _ = run_reconstruction(
        [
            make_raw_deal(
                user_id,
                "001",
                side=1,
                vol="1",
                price="100",
                timestamp_ms=1000,
                fee="-0.10",
            ),
            make_raw_deal(
                user_id,
                "002",
                side=4,
                vol="1",
                price="110",
                timestamp_ms=2000,
                fee="0.20",
            ),
        ],
        user_id,
    )

    assert db.positions[0].total_fees == Decimal("0.30")


def test_idempotency_rebuilds_without_duplicates():
    user_id = uuid4()
    db = FakeDbSession()
    db.raw_deals = [
        make_raw_deal(user_id, "001", side=1, vol="1", price="100", timestamp_ms=1000),
        make_raw_deal(user_id, "002", side=4, vol="1", price="110", timestamp_ms=2000),
    ]
    reconstructor = ReconstructorForTest(db)

    first_report = reconstructor.reconstruct(user_id=user_id, symbol="BTC_USDT")
    second_report = reconstructor.reconstruct(user_id=user_id, symbol="BTC_USDT")

    assert first_report.positions_created == 1
    assert second_report.positions_created == 1
    assert len(db.positions) == 1


def test_same_timestamp_sorts_by_timestamp_then_mexc_deal_id():
    user_id = uuid4()
    db, _, report = run_reconstruction(
        [
            make_raw_deal(user_id, "b-close", side=4, vol="1", price="110", timestamp_ms=1000),
            make_raw_deal(user_id, "a-open", side=1, vol="1", price="100", timestamp_ms=1000),
        ],
        user_id,
    )

    assert report.closed_positions == 1
    assert report.warnings == []
    assert db.positions[0].status == "closed"


def test_hedge_behavior_allows_long_and_short_for_same_symbol():
    user_id = uuid4()
    db, _, report = run_reconstruction(
        [
            make_raw_deal(user_id, "001", side=1, vol="1", price="100", timestamp_ms=1000),
            make_raw_deal(user_id, "002", side=3, vol="1", price="200", timestamp_ms=2000),
        ],
        user_id,
    )

    assert report.positions_created == 2
    assert report.open_positions == 2
    assert {position.direction for position in db.positions} == {"long", "short"}
