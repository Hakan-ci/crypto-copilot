import asyncio
from collections.abc import AsyncIterator
from contextlib import AbstractContextManager
from decimal import Decimal
from typing import Any
from uuid import uuid4

from app.schemas.mexc import MexcOrderDealDTO
from app.services.mexc_importer import MexcImporter


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
    def __init__(self, existing_deal_ids: set[str] | None = None) -> None:
        self.existing_deal_ids = existing_deal_ids or set()
        self.added: list[Any] = []
        self.transaction_started = False
        self.transaction_exited = False

    def begin(self) -> FakeTransaction:
        return FakeTransaction(self)

    def add(self, row: Any) -> None:
        self.added.append(row)


class ImporterForTest(MexcImporter):
    def _deal_exists(self, user_id, mexc_deal_id: str) -> bool:
        _ = user_id
        return mexc_deal_id in self.db.existing_deal_ids


class FakeMexcClient:
    def __init__(self, deals: list[MexcOrderDealDTO | dict[str, Any]]) -> None:
        self.deals = deals
        self.iter_calls: list[dict[str, Any]] = []
        self.trading_endpoint_called = False

    async def iter_order_deals(
        self,
        symbol: str,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
    ) -> AsyncIterator[MexcOrderDealDTO | dict[str, Any]]:
        self.iter_calls.append(
            {
                "symbol": symbol,
                "start_time_ms": start_time_ms,
                "end_time_ms": end_time_ms,
            }
        )
        for deal in self.deals:
            yield deal

    async def place_order(self) -> None:
        self.trading_endpoint_called = True
        raise AssertionError("Importer must not call trading endpoints.")

    async def cancel_order(self) -> None:
        self.trading_endpoint_called = True
        raise AssertionError("Importer must not call trading endpoints.")


def make_deal(
    mexc_deal_id: str = "deal-1",
    side: int = 1,
    timestamp_ms: int = 1710000000123,
) -> MexcOrderDealDTO:
    return MexcOrderDealDTO(
        mexc_deal_id=mexc_deal_id,
        symbol="BTC_USDT",
        side=side,
        vol=Decimal("0.123456789123456789"),
        price=Decimal("61234.123456789123456789"),
        fee=Decimal("0.000012345678912345"),
        fee_currency="USDT",
        profit=Decimal("-1.234567891234567891"),
        category=1,
        order_id=f"order-{mexc_deal_id}",
        timestamp_ms=timestamp_ms,
        position_mode=1,
        taker=True,
        raw_json={
            "id": mexc_deal_id,
            "symbol": "BTC_USDT",
            "side": side,
            "vol": "0.123456789123456789",
            "price": "61234.123456789123456789",
            "fee": "0.000012345678912345",
            "profit": "-1.234567891234567891",
            "orderId": f"order-{mexc_deal_id}",
            "timestamp": timestamp_ms,
        },
    )


def test_imports_new_rows():
    user_id = uuid4()
    db = FakeDbSession()
    client = FakeMexcClient([make_deal("deal-1"), make_deal("deal-2", side=4)])
    importer = ImporterForTest(db=db, client=client, backoff_base_s=0)

    result = asyncio.run(
        importer.import_order_deals(
            user_id=user_id,
            symbol="BTC_USDT",
            start_time_ms=1710000000000,
            end_time_ms=1710003600000,
        )
    )

    assert result.imported == 2
    assert result.skipped_duplicates == 0
    assert result.symbol == "BTC_USDT"
    assert db.transaction_started is True
    assert db.transaction_exited is True
    assert [row.mexc_deal_id for row in db.added] == ["deal-1", "deal-2"]
    assert all(row.user_id == user_id for row in db.added)
    assert client.iter_calls == [
        {
            "symbol": "BTC_USDT",
            "start_time_ms": 1710000000000,
            "end_time_ms": 1710003600000,
        }
    ]


def test_skips_duplicates():
    user_id = uuid4()
    db = FakeDbSession(existing_deal_ids={"deal-1"})
    client = FakeMexcClient([make_deal("deal-1"), make_deal("deal-2"), make_deal("deal-2")])
    importer = ImporterForTest(db=db, client=client, backoff_base_s=0)

    result = asyncio.run(importer.import_order_deals(user_id=user_id, symbol="BTC_USDT"))

    assert result.imported == 1
    assert result.skipped_duplicates == 2
    assert [row.mexc_deal_id for row in db.added] == ["deal-2"]


def test_handles_optional_missing_fields():
    raw_deal = {
        "id": "deal-optional",
        "symbol": "BTC_USDT",
        "side": 2,
        "vol": "1.5",
        "price": "100.25",
        "fee": "0.01",
        "profit": "2.5",
        "orderId": "order-optional",
        "timestamp": 1710000000456,
    }
    db = FakeDbSession()
    client = FakeMexcClient([raw_deal])
    importer = ImporterForTest(db=db, client=client, backoff_base_s=0)

    asyncio.run(importer.import_order_deals(user_id=uuid4(), symbol="BTC_USDT"))

    row = db.added[0]
    assert row.fee_currency is None
    assert row.category is None
    assert row.position_mode is None
    assert row.taker is None
    assert row.raw_json == raw_deal


def test_preserves_timestamp_ms_correctly():
    timestamp_ms = 1711234567890
    db = FakeDbSession()
    client = FakeMexcClient([make_deal("deal-timestamp", timestamp_ms=timestamp_ms)])
    importer = ImporterForTest(db=db, client=client, backoff_base_s=0)

    asyncio.run(importer.import_order_deals(user_id=uuid4(), symbol="BTC_USDT"))

    assert db.added[0].timestamp_ms == timestamp_ms


def test_preserves_decimal_precision():
    db = FakeDbSession()
    client = FakeMexcClient([make_deal("deal-decimal")])
    importer = ImporterForTest(db=db, client=client, backoff_base_s=0)

    asyncio.run(importer.import_order_deals(user_id=uuid4(), symbol="BTC_USDT"))

    row = db.added[0]
    assert row.vol == Decimal("0.123456789123456789")
    assert row.price == Decimal("61234.123456789123456789")
    assert row.fee == Decimal("0.000012345678912345")
    assert row.profit == Decimal("-1.234567891234567891")


def test_unknown_side_does_not_crash(caplog):
    db = FakeDbSession()
    client = FakeMexcClient([make_deal("deal-unknown-side", side=99)])
    importer = ImporterForTest(db=db, client=client, backoff_base_s=0)

    result = asyncio.run(importer.import_order_deals(user_id=uuid4(), symbol="BTC_USDT"))

    assert result.imported == 1
    assert db.added[0].side == 99
    assert "Unknown MEXC order deal side" in caplog.text


def test_importer_does_not_call_any_trading_endpoint():
    db = FakeDbSession()
    client = FakeMexcClient([make_deal("deal-read-only")])
    importer = ImporterForTest(db=db, client=client, backoff_base_s=0)

    asyncio.run(importer.import_order_deals(user_id=uuid4(), symbol="BTC_USDT"))

    assert client.trading_endpoint_called is False
    assert len(client.iter_calls) == 1
