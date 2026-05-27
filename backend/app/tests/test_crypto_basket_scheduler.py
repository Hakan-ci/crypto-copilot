import asyncio
from types import SimpleNamespace

from app.services import crypto_basket_scheduler as scheduler_module
from app.services.crypto_basket_scheduler import CryptoBasketScheduler


class FakeSession:
    def __enter__(self):
        return self

    def __exit__(self, *args: object) -> None:
        return None


class FakeSessionFactory:
    def __call__(self) -> FakeSession:
        return FakeSession()


def test_scheduler_run_once_syncs_all_baskets(monkeypatch):
    calls: list[dict[str, object]] = []
    fake_client = object()
    settings = SimpleNamespace(
        crypto_basket_running_stale_seconds=3600,
        crypto_basket_sync_interval_seconds=900,
    )

    class FakeService:
        def __init__(self, db, running_stale_seconds):
            self.db = db
            self.running_stale_seconds = running_stale_seconds

        async def sync_all_baskets(self, client, run_type):
            calls.append(
                {
                    "client": client,
                    "run_type": run_type,
                    "running_stale_seconds": self.running_stale_seconds,
                }
            )
            return []

    monkeypatch.setattr(scheduler_module, "CryptoBasketService", FakeService)
    scheduler = CryptoBasketScheduler(
        settings=settings,
        session_factory=FakeSessionFactory(),
        client_factory=lambda: fake_client,
    )

    asyncio.run(scheduler.run_once())

    assert calls == [
        {
            "client": fake_client,
            "run_type": "automatic",
            "running_stale_seconds": 3600,
        }
    ]
