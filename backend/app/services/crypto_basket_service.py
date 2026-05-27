import logging
from datetime import timedelta
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.time import utc_now
from app.db.models import (
    CryptoBasket,
    CryptoBasketItem,
    CryptoBasketSyncRun,
    User,
)
from app.schemas.crypto_basket import (
    CRYPTO_BASKET_MAX_ITEMS,
    CryptoBasketRead,
    CryptoBasketSyncResponse,
    CryptoBasketSyncRunRead,
    CryptoBasketUpsert,
)
from app.services.mexc_importer import MexcImporter, OrderDealsClient
from app.services.position_reconstructor import PositionReconstructor

logger = logging.getLogger(__name__)

INITIAL_SYNC_LOOKBACK_DAYS = 90
INCREMENTAL_SYNC_OVERLAP_MS = 60_000
DEFAULT_RUNNING_STALE_SECONDS = 60 * 60


class ReadOnlyMexcClient(OrderDealsClient, Protocol):
    pass


class CryptoBasketService:
    """Persists per-user sync baskets and imports their MEXC transaction history."""

    def __init__(
        self,
        db: Session,
        initial_lookback_days: int = INITIAL_SYNC_LOOKBACK_DAYS,
        overlap_ms: int = INCREMENTAL_SYNC_OVERLAP_MS,
        running_stale_seconds: int = DEFAULT_RUNNING_STALE_SECONDS,
    ) -> None:
        self.db = db
        self.initial_lookback_days = initial_lookback_days
        self.overlap_ms = overlap_ms
        self.running_stale_seconds = running_stale_seconds

    def read_basket(self, user_id: UUID) -> CryptoBasketRead:
        self._ensure_user_exists(user_id=user_id)
        basket = self._load_basket(user_id=user_id)
        if basket is None:
            basket = CryptoBasket(user_id=user_id)
            self.db.add(basket)
            self.db.commit()
            if hasattr(self.db, "refresh"):
                self.db.refresh(basket)
        return self._to_read(basket)

    def upsert_basket(self, user_id: UUID, payload: CryptoBasketUpsert) -> CryptoBasketRead:
        self._ensure_user_exists(user_id=user_id)
        if len(payload.items) > CRYPTO_BASKET_MAX_ITEMS:
            raise CryptoBasketValidationError(
                f"Crypto basket can contain at most {CRYPTO_BASKET_MAX_ITEMS} items."
            )

        basket = self._load_basket(user_id=user_id)
        if basket is None:
            basket = CryptoBasket(user_id=user_id)
            self.db.add(basket)
            if hasattr(self.db, "flush"):
                self.db.flush()

        existing_by_symbol = {item.symbol: item for item in basket.items}
        requested_symbols = {item.symbol for item in payload.items}
        for existing_item in list(basket.items):
            if existing_item.symbol not in requested_symbols:
                self.db.delete(existing_item)
                basket.items.remove(existing_item)

        ordered_items = sorted(payload.items, key=lambda item: item.sort_order)
        for sort_order, incoming in enumerate(ordered_items):
            existing = existing_by_symbol.get(incoming.symbol)
            if existing is None:
                basket.items.append(
                    CryptoBasketItem(
                        sort_order=sort_order,
                        symbol=incoming.symbol,
                        enabled=incoming.enabled,
                    )
                )
            else:
                existing.sort_order = sort_order
                existing.enabled = incoming.enabled

        basket.updated_at = utc_now()
        self.db.commit()
        if hasattr(self.db, "refresh"):
            self.db.refresh(basket)
        return self._to_read(basket)

    async def sync_basket(
        self,
        user_id: UUID,
        client: ReadOnlyMexcClient,
        run_type: str = "manual",
    ) -> CryptoBasketSyncResponse:
        self._ensure_user_exists(user_id=user_id)
        basket = self._load_basket(user_id=user_id)
        if basket is None:
            basket = CryptoBasket(user_id=user_id)
            self.db.add(basket)
            self.db.commit()
            if hasattr(self.db, "refresh"):
                self.db.refresh(basket)

        runs: list[CryptoBasketSyncRunRead] = []
        for item in sorted(basket.items, key=lambda basket_item: basket_item.sort_order):
            if not item.enabled:
                continue
            runs.append(
                await self._sync_item(
                    basket=basket,
                    item=item,
                    client=client,
                    run_type=run_type,
                )
            )

        basket = self._load_basket(user_id=user_id) or basket
        return CryptoBasketSyncResponse(basket=self._to_read(basket), runs=runs)

    async def sync_all_baskets(
        self,
        client: ReadOnlyMexcClient,
        run_type: str = "automatic",
    ) -> list[CryptoBasketSyncResponse]:
        responses: list[CryptoBasketSyncResponse] = []
        for basket in self._load_baskets_with_enabled_items():
            responses.append(
                await self.sync_basket(
                    user_id=basket.user_id,
                    client=client,
                    run_type=run_type,
                )
            )
        return responses

    async def _sync_item(
        self,
        basket: CryptoBasket,
        item: CryptoBasketItem,
        client: ReadOnlyMexcClient,
        run_type: str,
    ) -> CryptoBasketSyncRunRead:
        now = utc_now()
        start_time_ms, end_time_ms = self._sync_window(item=item, now=now)

        if self._is_running_and_fresh(item=item, now=now):
            run = CryptoBasketSyncRun(
                basket_id=basket.id,
                basket_item_id=item.id,
                symbol=item.symbol,
                run_type=run_type,
                status="skipped",
                started_at=now,
                finished_at=now,
                start_time_ms=start_time_ms,
                end_time_ms=end_time_ms,
                imported=0,
                skipped_duplicates=0,
                positions_created=0,
                open_positions=0,
                closed_positions=0,
                warnings=[],
                error="Sync already running.",
            )
            self.db.add(run)
            self.db.commit()
            return CryptoBasketSyncRunRead.model_validate(run)

        run = CryptoBasketSyncRun(
            basket_id=basket.id,
            basket_item_id=item.id,
            symbol=item.symbol,
            run_type=run_type,
            status="running",
            started_at=now,
            start_time_ms=start_time_ms,
            end_time_ms=end_time_ms,
            imported=0,
            skipped_duplicates=0,
            positions_created=0,
            open_positions=0,
            closed_positions=0,
            warnings=[],
        )
        item.sync_status = "running"
        item.last_sync_started_at = now
        item.last_error = None
        self.db.add(run)
        self.db.commit()
        run_id = run.id
        item_id = item.id

        try:
            import_result = await MexcImporter(db=self.db, client=client).import_order_deals(
                user_id=basket.user_id,
                symbol=item.symbol,
                start_time_ms=start_time_ms,
                end_time_ms=end_time_ms,
            )
            reconstruction = PositionReconstructor(db=self.db).reconstruct(
                user_id=basket.user_id,
                symbol=item.symbol,
            )
        except Exception as exc:
            logger.warning(
                "Crypto basket symbol sync failed.",
                extra={"symbol": item.symbol, "run_type": run_type},
                exc_info=exc,
            )
            self.db.rollback()
            finished_at = utc_now()
            item = self._get_item(item_id)
            run = self._get_run(run_id)
            item.sync_status = "error"
            item.last_sync_finished_at = finished_at
            item.last_sync_start_time_ms = start_time_ms
            item.last_sync_end_time_ms = end_time_ms
            item.last_error = str(exc)
            run.status = "error"
            run.finished_at = finished_at
            run.error = str(exc)
            self.db.commit()
            return CryptoBasketSyncRunRead.model_validate(run)

        finished_at = utc_now()
        item = self._get_item(item_id)
        run = self._get_run(run_id)
        item.sync_status = "success"
        item.last_sync_finished_at = finished_at
        item.last_successful_sync_at = finished_at
        item.last_sync_start_time_ms = start_time_ms
        item.last_sync_end_time_ms = end_time_ms
        item.last_imported = import_result.imported
        item.last_skipped_duplicates = import_result.skipped_duplicates
        item.last_positions_created = reconstruction.positions_created
        item.last_open_positions = reconstruction.open_positions
        item.last_closed_positions = reconstruction.closed_positions
        item.last_warnings = list(reconstruction.warnings)
        item.last_error = None

        run.status = "success"
        run.finished_at = finished_at
        run.imported = import_result.imported
        run.skipped_duplicates = import_result.skipped_duplicates
        run.positions_created = reconstruction.positions_created
        run.open_positions = reconstruction.open_positions
        run.closed_positions = reconstruction.closed_positions
        run.warnings = list(reconstruction.warnings)
        run.error = None
        self.db.commit()
        return CryptoBasketSyncRunRead.model_validate(run)

    def _sync_window(self, item: CryptoBasketItem, now) -> tuple[int, int]:
        end_time_ms = int(now.timestamp() * 1000)
        if item.last_sync_end_time_ms is None:
            start = now - timedelta(days=self.initial_lookback_days)
            return int(start.timestamp() * 1000), end_time_ms
        return max(0, item.last_sync_end_time_ms - self.overlap_ms), end_time_ms

    def _is_running_and_fresh(self, item: CryptoBasketItem, now) -> bool:
        if item.sync_status != "running" or item.last_sync_started_at is None:
            return False
        age_seconds = (now - item.last_sync_started_at).total_seconds()
        return age_seconds < self.running_stale_seconds

    def _load_basket(self, user_id: UUID) -> CryptoBasket | None:
        statement = (
            select(CryptoBasket)
            .options(selectinload(CryptoBasket.items))
            .where(CryptoBasket.user_id == user_id)
        )
        return self.db.scalars(statement).first()

    def _load_baskets_with_enabled_items(self) -> list[CryptoBasket]:
        statement = select(CryptoBasket).options(selectinload(CryptoBasket.items))
        return [
            basket
            for basket in self.db.scalars(statement).all()
            if any(item.enabled for item in basket.items)
        ]

    def _get_item(self, item_id: UUID) -> CryptoBasketItem:
        item = self.db.get(CryptoBasketItem, item_id)
        if item is None:
            raise CryptoBasketValidationError(f"Crypto basket item not found: {item_id}")
        return item

    def _get_run(self, run_id: UUID) -> CryptoBasketSyncRun:
        run = self.db.get(CryptoBasketSyncRun, run_id)
        if run is None:
            raise CryptoBasketValidationError(f"Crypto basket sync run not found: {run_id}")
        return run

    def _ensure_user_exists(self, user_id: UUID) -> None:
        if self.db.get(User, user_id) is None:
            raise CryptoBasketUserNotFoundError(f"User not found: {user_id}")

    @staticmethod
    def _to_read(basket: CryptoBasket) -> CryptoBasketRead:
        basket_read = CryptoBasketRead.model_validate(basket)
        basket_read.items = sorted(basket_read.items, key=lambda item: item.sort_order)
        return basket_read


class CryptoBasketUserNotFoundError(ValueError):
    pass


class CryptoBasketValidationError(ValueError):
    pass
