from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.schemas.mexc import MexcOrderDealsImportRequest, MexcOrderDealsImportResponse
from app.services.mexc_client import MexcApiError, MexcFuturesClient
from app.services.mexc_importer import MexcImporter

router = APIRouter(prefix="/mexc", tags=["mexc"])


@router.post("/import/order-deals", response_model=MexcOrderDealsImportResponse)
async def import_order_deals(
    request: MexcOrderDealsImportRequest,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> MexcOrderDealsImportResponse:
    client = MexcFuturesClient(
        access_key=(
            settings.mexc_access_key.get_secret_value() if settings.mexc_access_key else None
        ),
        secret_key=(
            settings.mexc_secret_key.get_secret_value() if settings.mexc_secret_key else None
        ),
        base_url=settings.mexc_base_url,
    )
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
