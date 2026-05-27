import asyncio
import logging
from collections.abc import Callable

from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.services.crypto_basket_service import CryptoBasketService
from app.services.mexc_client import MexcFuturesClient

logger = logging.getLogger(__name__)


class CryptoBasketScheduler:
    """Small in-process scheduler for read-only basket history sync."""

    def __init__(
        self,
        settings: Settings,
        session_factory: sessionmaker[Session],
        client_factory: Callable[[], MexcFuturesClient] | None = None,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.client_factory = client_factory or self._default_client_factory
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass

    async def run_once(self) -> None:
        with self.session_factory() as db:
            await CryptoBasketService(
                db=db,
                running_stale_seconds=self.settings.crypto_basket_running_stale_seconds,
            ).sync_all_baskets(
                client=self.client_factory(),
                run_type="automatic",
            )

    async def _run_loop(self) -> None:
        while True:
            try:
                await self.run_once()
            except Exception:
                logger.exception("Automatic crypto basket sync tick failed.")
            await asyncio.sleep(self.settings.crypto_basket_sync_interval_seconds)

    def _default_client_factory(self) -> MexcFuturesClient:
        return MexcFuturesClient(
            access_key=(
                self.settings.mexc_access_key.get_secret_value()
                if self.settings.mexc_access_key
                else None
            ),
            secret_key=(
                self.settings.mexc_secret_key.get_secret_value()
                if self.settings.mexc_secret_key
                else None
            ),
            base_url=self.settings.mexc_base_url,
        )
