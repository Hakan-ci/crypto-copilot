from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.trading_plan import TradingPlanRead, TradingPlanUpsert
from app.services.trading_plan_service import TradingPlanService, TradingPlanUserNotFoundError

router = APIRouter(tags=["trading-plan"])


@router.get("/users/{user_id}/trading-plan", response_model=TradingPlanRead)
def get_trading_plan(
    user_id: UUID,
    db: Annotated[Session, Depends(get_db)],
) -> TradingPlanRead:
    try:
        return TradingPlanService(db=db).read_plan(user_id=user_id)
    except TradingPlanUserNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/users/{user_id}/trading-plan", response_model=TradingPlanRead)
def put_trading_plan(
    user_id: UUID,
    payload: TradingPlanUpsert,
    db: Annotated[Session, Depends(get_db)],
) -> TradingPlanRead:
    try:
        return TradingPlanService(db=db).upsert_plan(user_id=user_id, payload=payload)
    except TradingPlanUserNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
