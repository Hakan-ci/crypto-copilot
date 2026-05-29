import asyncio
from types import SimpleNamespace
from uuid import uuid4

from app.api.routes import mexc as mexc_routes
from app.core.config import Settings
from app.schemas.mexc import MexcOrderDealsImportRequest
from app.schemas.trades import ReconstructionReport


def make_settings(
    access_key: str = "access-key",
    secret_key: str = "secret-key",
) -> Settings:
    return Settings(
        DATABASE_URL="postgresql+psycopg://user:pass@localhost:5432/app",
        MEXC_BASE_URL="https://contract.mexc.com",
        SECRET_KEY="test-secret-key",
        API_KEY_ENCRYPTION_KEY="test-encryption-key",
        MEXC_ACCESS_KEY=access_key,
        MEXC_SECRET_KEY=secret_key,
    )


def test_mexc_readiness_checks_public_and_private_access_without_returning_secrets(monkeypatch):
    class FakeMexcClient:
        def __init__(self, access_key, secret_key, base_url):
            self.access_key = access_key
            self.secret_key = secret_key
            self.base_url = base_url

        async def ping(self):
            return 1710000000000

        async def get_order_deals(self, symbol, page_num, page_size):
            assert symbol == "BTC_USDT"
            assert page_num == 1
            assert page_size == 1
            return []

    monkeypatch.setattr(mexc_routes, "MexcFuturesClient", FakeMexcClient)

    response = asyncio.run(mexc_routes.get_mexc_readiness(settings=make_settings()))

    assert response.base_url == "https://contract.mexc.com"
    assert response.credentials_configured is True
    assert response.public_api_reachable is True
    assert response.private_read_authenticated is True
    serialized = response.model_dump_json()
    assert "access-key" not in serialized
    assert "secret-key" not in serialized


def test_mexc_readiness_reports_missing_credentials_without_private_call(monkeypatch):
    class FakeMexcClient:
        private_called = False

        def __init__(self, access_key, secret_key, base_url):
            self.access_key = access_key
            self.secret_key = secret_key
            self.base_url = base_url

        async def ping(self):
            return 1710000000000

        async def get_order_deals(self, symbol, page_num, page_size):
            self.private_called = True
            return []

    monkeypatch.setattr(mexc_routes, "MexcFuturesClient", FakeMexcClient)

    response = asyncio.run(
        mexc_routes.get_mexc_readiness(settings=make_settings(access_key="", secret_key=""))
    )

    assert response.credentials_configured is False
    assert response.public_api_reachable is True
    assert response.private_read_authenticated is False
    assert "not configured" in response.message


def test_import_order_deals_and_reconstruct_combines_results(monkeypatch):
    user_id = uuid4()

    class FakeMexcClient:
        def __init__(self, access_key, secret_key, base_url):
            self.access_key = access_key
            self.secret_key = secret_key
            self.base_url = base_url

    class FakeImporter:
        def __init__(self, db, client):
            self.db = db
            self.client = client

        async def import_order_deals(self, user_id, symbol, start_time_ms, end_time_ms):
            assert symbol == "BTC_USDT"
            assert start_time_ms == 1710000000000
            assert end_time_ms == 1710003600000
            return SimpleNamespace(imported=2, skipped_duplicates=1, symbol=symbol)

    class FakeReconstructor:
        def __init__(self, db):
            self.db = db

        def reconstruct(self, user_id, symbol):
            return ReconstructionReport(
                positions_created=1,
                open_positions=0,
                closed_positions=1,
                warnings=["partial close adjusted"],
            )

    class FakeTradeMetadataService:
        def __init__(self, db):
            self.db = db

        async def sync_stop_losses_for_user_symbol(self, user_id, symbol, client):
            assert symbol == "BTC_USDT"
            assert client.access_key == "access-key"
            return 1

    monkeypatch.setattr(mexc_routes, "MexcFuturesClient", FakeMexcClient)
    monkeypatch.setattr(mexc_routes, "MexcImporter", FakeImporter)
    monkeypatch.setattr(mexc_routes, "PositionReconstructor", FakeReconstructor)
    monkeypatch.setattr(mexc_routes, "TradeMetadataService", FakeTradeMetadataService)

    response = asyncio.run(
        mexc_routes.import_order_deals_and_reconstruct(
            request=MexcOrderDealsImportRequest(
                user_id=user_id,
                symbol="BTC_USDT",
                start_time_ms=1710000000000,
                end_time_ms=1710003600000,
            ),
            db=object(),
            settings=make_settings(),
        )
    )

    assert response.imported == 2
    assert response.skipped_duplicates == 1
    assert response.positions_created == 1
    assert response.open_positions == 0
    assert response.closed_positions == 1
    assert response.warnings == [
        "partial close adjusted",
        "Synced stop-loss metadata for 1 position(s).",
    ]
