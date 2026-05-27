from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.routes.mexc import build_mexc_client
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.schemas.crypto_basket import (
    CryptoBasketRead,
    CryptoBasketSyncResponse,
    CryptoBasketUpsert,
)
from app.services.crypto_basket_service import (
    CryptoBasketService,
    CryptoBasketUserNotFoundError,
    CryptoBasketValidationError,
)

router = APIRouter(tags=["crypto-basket"])


@router.get("/users/{user_id}/crypto-basket", response_model=CryptoBasketRead)
def get_crypto_basket(
    user_id: UUID,
    db: Annotated[Session, Depends(get_db)],
) -> CryptoBasketRead:
    try:
        return CryptoBasketService(db=db).read_basket(user_id=user_id)
    except CryptoBasketUserNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/users/{user_id}/crypto-basket", response_model=CryptoBasketRead)
def put_crypto_basket(
    user_id: UUID,
    payload: CryptoBasketUpsert,
    db: Annotated[Session, Depends(get_db)],
) -> CryptoBasketRead:
    try:
        return CryptoBasketService(db=db).upsert_basket(user_id=user_id, payload=payload)
    except CryptoBasketUserNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CryptoBasketValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/users/{user_id}/crypto-basket/sync", response_model=CryptoBasketSyncResponse)
async def sync_crypto_basket(
    user_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CryptoBasketSyncResponse:
    try:
        return await CryptoBasketService(db=db).sync_basket(
            user_id=user_id,
            client=build_mexc_client(settings),
            run_type="manual",
        )
    except CryptoBasketUserNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CryptoBasketValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
