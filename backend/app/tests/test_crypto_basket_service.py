import asyncio
from contextlib import AbstractContextManager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.db.models import CryptoBasket, CryptoBasketItem, CryptoBasketSyncRun
from app.schemas.crypto_basket import CryptoBasketUpsert
from app.schemas.trades import ReconstructionReport
from app.services import crypto_basket_service as service_module
from app.services.crypto_basket_service import CryptoBasketService


class FakeDb(AbstractContextManager["FakeDb"]):
    def __init__(self, basket: CryptoBasket) -> None:
        self.basket = basket
        self.runs: list[CryptoBasketSyncRun] = []
        self.commits = 0
        self.rollbacks = 0

    def __enter__(self) -> "FakeDb":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def add(self, row) -> None:
        if getattr(row, "id", None) is None:
            row.id = uuid4()
        if isinstance(row, CryptoBasketSyncRun):
            self.runs.append(row)

    def delete(self, row) -> None:
        if isinstance(row, CryptoBasketItem):
            self.basket.items.remove(row)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def get(self, model, row_id: UUID):
        if model is CryptoBasketItem:
            return next(item for item in self.basket.items if item.id == row_id)
        if model is CryptoBasketSyncRun:
            return next(run for run in self.runs if run.id == row_id)
        return None


class ServiceForTest(CryptoBasketService):
    def _ensure_user_exists(self, user_id: UUID) -> None:
        self.seen_user_id = user_id

    def _load_basket(self, user_id: UUID) -> CryptoBasket | None:
        self.seen_user_id = user_id
        return self.db.basket

    def _load_baskets_with_enabled_items(self) -> list[CryptoBasket]:
        return [self.db.basket]


class FakeImporter:
    calls: list[dict[str, object]] = []
    failures: set[str] = set()

    def __init__(self, db, client) -> None:
        self.db = db
        self.client = client

    async def import_order_deals(self, user_id, symbol, start_time_ms, end_time_ms):
        self.calls.append(
            {
                "user_id": user_id,
                "symbol": symbol,
                "start_time_ms": start_time_ms,
                "end_time_ms": end_time_ms,
            }
        )
        if symbol in self.failures:
            raise RuntimeError(f"{symbol} import failed")
        return SimpleNamespace(imported=3, skipped_duplicates=1, symbol=symbol)


class FakeReconstructor:
    calls: list[dict[str, object]] = []

    def __init__(self, db) -> None:
        self.db = db

    def reconstruct(self, user_id, symbol):
        self.calls.append({"user_id": user_id, "symbol": symbol})
        return ReconstructionReport(
            positions_created=2,
            open_positions=1,
            closed_positions=1,
            warnings=[f"{symbol} warning"],
        )


class FakeClient:
    trading_endpoint_called = False

    async def place_order(self) -> None:
        self.trading_endpoint_called = True
        raise AssertionError("Basket sync must not place orders.")


@pytest.fixture(autouse=True)
def fake_sync_dependencies(monkeypatch):
    FakeImporter.calls = []
    FakeImporter.failures = set()
    FakeReconstructor.calls = []
    monkeypatch.setattr(service_module, "MexcImporter", FakeImporter)
    monkeypatch.setattr(service_module, "PositionReconstructor", FakeReconstructor)


def make_basket(*items: CryptoBasketItem) -> CryptoBasket:
    created_at = datetime(2026, 1, 1, tzinfo=UTC)
    basket = CryptoBasket(
        id=uuid4(),
        user_id=uuid4(),
        created_at=created_at,
        updated_at=created_at,
    )
    basket.items = list(items)
    for item in basket.items:
        item.basket_id = basket.id
    return basket


def make_item(
    symbol: str = "BTC_USDT",
    sort_order: int = 0,
    enabled: bool = True,
    last_sync_end_time_ms: int | None = None,
    sync_status: str = "idle",
    last_sync_started_at: datetime | None = None,
) -> CryptoBasketItem:
    created_at = datetime(2026, 1, 1, tzinfo=UTC)
    return CryptoBasketItem(
        id=uuid4(),
        basket_id=uuid4(),
        sort_order=sort_order,
        symbol=symbol,
        enabled=enabled,
        sync_status=sync_status,
        last_sync_started_at=last_sync_started_at,
        last_sync_end_time_ms=last_sync_end_time_ms,
        last_imported=0,
        last_skipped_duplicates=0,
        last_positions_created=0,
        last_open_positions=0,
        last_closed_positions=0,
        last_warnings=[],
        created_at=created_at,
        updated_at=created_at,
    )


def test_basket_payload_rejects_duplicate_symbols():
    with pytest.raises(ValidationError, match="Duplicate basket symbols"):
        CryptoBasketUpsert(
            items=[
                {"sort_order": 0, "symbol": "btc_usdt", "enabled": True},
                {"sort_order": 1, "symbol": "BTC_USDT", "enabled": True},
            ]
        )


def test_basket_payload_rejects_invalid_symbol():
    with pytest.raises(ValidationError, match="MEXC Futures format"):
        CryptoBasketUpsert(items=[{"sort_order": 0, "symbol": "BTCUSDT", "enabled": True}])


def test_initial_sync_uses_90_day_backfill(monkeypatch):
    now = datetime(2026, 5, 27, 12, 0, tzinfo=UTC)
    monkeypatch.setattr(service_module, "utc_now", lambda: now)
    item = make_item()
    basket = make_basket(item)
    service = ServiceForTest(db=FakeDb(basket))

    response = asyncio.run(
        service.sync_basket(user_id=basket.user_id, client=FakeClient(), run_type="manual")
    )

    expected_start_ms = int((now - timedelta(days=90)).timestamp() * 1000)
    expected_end_ms = int(now.timestamp() * 1000)
    assert FakeImporter.calls[0]["start_time_ms"] == expected_start_ms
    assert FakeImporter.calls[0]["end_time_ms"] == expected_end_ms
    assert FakeReconstructor.calls == [{"user_id": basket.user_id, "symbol": "BTC_USDT"}]
    assert response.runs[0].status == "success"
    assert item.last_successful_sync_at == now
    assert item.last_positions_created == 2


def test_incremental_sync_uses_last_end_with_overlap(monkeypatch):
    now = datetime(2026, 5, 27, 12, 0, tzinfo=UTC)
    monkeypatch.setattr(service_module, "utc_now", lambda: now)
    item = make_item(last_sync_end_time_ms=1_710_000_000_000)
    basket = make_basket(item)
    service = ServiceForTest(db=FakeDb(basket))

    asyncio.run(service.sync_basket(user_id=basket.user_id, client=FakeClient()))

    assert FakeImporter.calls[0]["start_time_ms"] == 1_709_999_940_000
    assert FakeImporter.calls[0]["end_time_ms"] == int(now.timestamp() * 1000)


def test_symbol_failures_are_isolated(monkeypatch):
    now = datetime(2026, 5, 27, 12, 0, tzinfo=UTC)
    monkeypatch.setattr(service_module, "utc_now", lambda: now)
    first = make_item("BTC_USDT", 0)
    second = make_item("ETH_USDT", 1)
    basket = make_basket(first, second)
    FakeImporter.failures = {"BTC_USDT"}
    service = ServiceForTest(db=FakeDb(basket))

    response = asyncio.run(service.sync_basket(user_id=basket.user_id, client=FakeClient()))

    assert [run.status for run in response.runs] == ["error", "success"]
    assert first.sync_status == "error"
    assert second.sync_status == "success"
    assert first.last_error == "BTC_USDT import failed"
    assert [call["symbol"] for call in FakeImporter.calls] == ["BTC_USDT", "ETH_USDT"]


def test_fresh_running_item_is_skipped(monkeypatch):
    now = datetime(2026, 5, 27, 12, 0, tzinfo=UTC)
    monkeypatch.setattr(service_module, "utc_now", lambda: now)
    item = make_item(
        sync_status="running",
        last_sync_started_at=now - timedelta(seconds=30),
    )
    basket = make_basket(item)
    service = ServiceForTest(db=FakeDb(basket), running_stale_seconds=3600)

    response = asyncio.run(service.sync_basket(user_id=basket.user_id, client=FakeClient()))

    assert response.runs[0].status == "skipped"
    assert response.runs[0].error == "Sync already running."
    assert FakeImporter.calls == []
