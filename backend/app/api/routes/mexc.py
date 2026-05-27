from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.schemas.mexc import (
    MexcImportAndReconstructResponse,
    MexcOrderDealsImportRequest,
    MexcOrderDealsImportResponse,
    MexcReadinessResponse,
)
from app.services.mexc_client import MexcApiError, MexcFuturesClient
from app.services.mexc_importer import MexcImporter
from app.services.position_reconstructor import PositionReconstructor

router = APIRouter(prefix="/mexc", tags=["mexc"])


def build_mexc_client(settings: Settings) -> MexcFuturesClient:
    return MexcFuturesClient(
        access_key=(
            settings.mexc_access_key.get_secret_value() if settings.mexc_access_key else None
        ),
        secret_key=(
            settings.mexc_secret_key.get_secret_value() if settings.mexc_secret_key else None
        ),
        base_url=settings.mexc_base_url,
    )


@router.get("/readiness", response_model=MexcReadinessResponse)
async def get_mexc_readiness(
    settings: Annotated[Settings, Depends(get_settings)],
    symbol: str = "BTC_USDT",
) -> MexcReadinessResponse:
    client = build_mexc_client(settings)
    credentials_configured = bool(client.access_key and client.secret_key)
    public_api_reachable = False
    private_read_authenticated = False
    messages: list[str] = []

    try:
        await client.ping()
        public_api_reachable = True
    except MexcApiError:
        messages.append("Public MEXC contract API is not reachable.")

    if credentials_configured:
        try:
            await client.get_order_deals(symbol=symbol, page_num=1, page_size=1)
            private_read_authenticated = True
        except MexcApiError:
            messages.append("Private read-only MEXC history request failed.")
    else:
        messages.append("MEXC access and secret keys are not configured in backend .env.")

    if not messages:
        messages.append("MEXC public API and private read-only history access are ready.")

    return MexcReadinessResponse(
        base_url=settings.mexc_base_url,
        credentials_configured=credentials_configured,
        public_api_reachable=public_api_reachable,
        private_read_authenticated=private_read_authenticated,
        message=" ".join(messages),
    )


@router.post("/import/order-deals", response_model=MexcOrderDealsImportResponse)
async def import_order_deals(
    request: MexcOrderDealsImportRequest,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> MexcOrderDealsImportResponse:
    client = build_mexc_client(settings)
    importer = MexcImporter(db=db, client=client)

    try:
        result = await importer.import_order_deals(
            user_id=request.user_id,
            symbol=request.symbol,
            start_time_ms=request.start_time_ms,
            end_time_ms=request.end_time_ms,
        )
    except MexcApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return MexcOrderDealsImportResponse(
        imported=result.imported,
        skipped_duplicates=result.skipped_duplicates,
        symbol=result.symbol,
    )


@router.post(
    "/import/order-deals-and-reconstruct",
    response_model=MexcImportAndReconstructResponse,
)
async def import_order_deals_and_reconstruct(
    request: MexcOrderDealsImportRequest,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> MexcImportAndReconstructResponse:
    client = build_mexc_client(settings)
    importer = MexcImporter(db=db, client=client)
    reconstructor = PositionReconstructor(db=db)

    try:
        import_result = await importer.import_order_deals(
            user_id=request.user_id,
            symbol=request.symbol,
            start_time_ms=request.start_time_ms,
            end_time_ms=request.end_time_ms,
        )
    except MexcApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    reconstruction = reconstructor.reconstruct(user_id=request.user_id, symbol=request.symbol)

    return MexcImportAndReconstructResponse(
        imported=import_result.imported,
        skipped_duplicates=import_result.skipped_duplicates,
        symbol=import_result.symbol,
        positions_created=reconstruction.positions_created,
        open_positions=reconstruction.open_positions,
        closed_positions=reconstruction.closed_positions,
        warnings=reconstruction.warnings,
    )
