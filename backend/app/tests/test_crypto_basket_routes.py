import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.routes import crypto_basket as crypto_basket_routes
from app.core.config import Settings
from app.schemas.crypto_basket import (
    CryptoBasketItemRead,
    CryptoBasketRead,
    CryptoBasketSyncResponse,
    CryptoBasketSyncRunRead,
    CryptoBasketUpsert,
)
from app.services.crypto_basket_service import CryptoBasketUserNotFoundError


def make_settings() -> Settings:
    return Settings(
        DATABASE_URL="postgresql+psycopg://user:pass@localhost:5432/app",
        MEXC_BASE_URL="https://contract.mexc.com",
        SECRET_KEY="test-secret-key",
        API_KEY_ENCRYPTION_KEY="test-encryption-key",
        MEXC_ACCESS_KEY="access-key",
        MEXC_SECRET_KEY="secret-key",
    )


def make_basket_read(user_id=None) -> CryptoBasketRead:
    now = datetime(2026, 5, 27, tzinfo=UTC)
    basket_id = uuid4()
    return CryptoBasketRead(
        id=basket_id,
        user_id=user_id or uuid4(),
        created_at=now,
        updated_at=now,
        items=[
            CryptoBasketItemRead(
                id=uuid4(),
                basket_id=basket_id,
                sort_order=0,
                symbol="BTC_USDT",
                enabled=True,
                sync_status="idle",
                last_imported=0,
                last_skipped_duplicates=0,
                last_positions_created=0,
                last_open_positions=0,
                last_closed_positions=0,
                last_warnings=[],
                created_at=now,
                updated_at=now,
            )
        ],
    )


def test_crypto_basket_routes_delegate(monkeypatch):
    user_id = uuid4()
    calls: list[str] = []

    class FakeService:
        def __init__(self, db):
            self.db = db

        def read_basket(self, user_id):
            calls.append(f"read:{user_id}")
            return make_basket_read(user_id=user_id)

        def upsert_basket(self, user_id, payload):
            calls.append(f"upsert:{user_id}:{len(payload.items)}")
            return make_basket_read(user_id=user_id)

    monkeypatch.setattr(crypto_basket_routes, "CryptoBasketService", FakeService)

    read_response = crypto_basket_routes.get_crypto_basket(user_id=user_id, db=object())
    put_response = crypto_basket_routes.put_crypto_basket(
        user_id=user_id,
        payload=CryptoBasketUpsert(items=[{"sort_order": 0, "symbol": "BTC_USDT"}]),
        db=object(),
    )

    assert read_response.user_id == user_id
    assert put_response.items[0].symbol == "BTC_USDT"
    assert calls == [f"read:{user_id}", f"upsert:{user_id}:1"]


def test_crypto_basket_route_maps_missing_user(monkeypatch):
    class FakeService:
        def __init__(self, db):
            self.db = db

        def read_basket(self, user_id):
            raise CryptoBasketUserNotFoundError(f"User not found: {user_id}")

    monkeypatch.setattr(crypto_basket_routes, "CryptoBasketService", FakeService)

    with pytest.raises(HTTPException) as exc_info:
        crypto_basket_routes.get_crypto_basket(user_id=uuid4(), db=object())

    assert exc_info.value.status_code == 404


def test_crypto_basket_sync_route_delegates(monkeypatch):
    user_id = uuid4()
    now = datetime(2026, 5, 27, tzinfo=UTC)
    client = object()

    class FakeService:
        def __init__(self, db):
            self.db = db

        async def sync_basket(self, user_id, client, run_type):
            return CryptoBasketSyncResponse(
                basket=make_basket_read(user_id=user_id),
                runs=[
                    CryptoBasketSyncRunRead(
                        id=uuid4(),
                        basket_id=uuid4(),
                        basket_item_id=uuid4(),
                        symbol="BTC_USDT",
                        run_type=run_type,
                        status="success",
                        started_at=now,
                        finished_at=now,
                        imported=1,
                        skipped_duplicates=0,
                        positions_created=1,
                        open_positions=0,
                        closed_positions=1,
                        warnings=[],
                    )
                ],
            )

    monkeypatch.setattr(crypto_basket_routes, "CryptoBasketService", FakeService)
    monkeypatch.setattr(crypto_basket_routes, "build_mexc_client", lambda settings: client)

    response = asyncio.run(
        crypto_basket_routes.sync_crypto_basket(
            user_id=user_id,
            db=object(),
            settings=make_settings(),
        )
    )

    assert response.runs[0].run_type == "manual"
    assert response.runs[0].status == "success"
