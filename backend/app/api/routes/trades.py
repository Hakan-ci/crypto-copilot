from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.schemas.indicators import (
    IndicatorSnapshotCalculationRequest,
    IndicatorSnapshotCalculationResponse,
)
from app.schemas.trades import (
    DashboardAnalytics,
    PositionDetail,
    PositionListItem,
    ReconstructionReport,
    TradeReviewRequest,
    TradeReviewResponse,
)
from app.services.ai_review_engine import (
    AiReviewEngine,
)
from app.services.ai_review_engine import (
    PositionNotFoundError as ReviewPositionNotFoundError,
)
from app.services.indicator_engine import IndicatorEngine, PositionNotFoundError
from app.services.position_reconstructor import PositionReconstructor
from app.services.risk_engine import RiskEngine

router = APIRouter(tags=["trades"])


@router.post(
    "/users/{user_id}/symbols/{symbol}/reconstruct-positions",
    response_model=ReconstructionReport,
)
def reconstruct_positions(
    user_id: UUID,
    symbol: str,
    db: Annotated[Session, Depends(get_db)],
) -> ReconstructionReport:
    reconstructor = PositionReconstructor(db=db)
    return reconstructor.reconstruct(user_id=user_id, symbol=symbol)


@router.get("/users/{user_id}/dashboard", response_model=DashboardAnalytics)
def get_dashboard(
    user_id: UUID,
    db: Annotated[Session, Depends(get_db)],
) -> DashboardAnalytics:
    engine = RiskEngine(db=db)
    return engine.get_dashboard(user_id=user_id)


@router.get("/users/{user_id}/positions", response_model=list[PositionListItem])
def list_user_positions(
    user_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    symbol: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
    direction: Annotated[str | None, Query()] = None,
    start: Annotated[str | None, Query()] = None,
    end: Annotated[str | None, Query()] = None,
    timeframe: Annotated[str | None, Query()] = None,
) -> list[PositionListItem]:
    engine = RiskEngine(db=db)
    try:
        return engine.list_positions(
            user_id=user_id,
            symbol=symbol,
            status=status,
            direction=direction,
            start=_parse_datetime_query(start, "start"),
            end=_parse_datetime_query(end, "end"),
            timeframe=timeframe,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/positions/{position_id}", response_model=PositionDetail)
def get_position_detail(
    position_id: UUID,
    db: Annotated[Session, Depends(get_db)],
) -> PositionDetail:
    engine = RiskEngine(db=db)
    detail = engine.get_position_detail(position_id=position_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Position not found: {position_id}")
    return detail


@router.post(
    "/positions/{position_id}/indicator-snapshots",
    response_model=IndicatorSnapshotCalculationResponse,
)
def calculate_indicator_snapshots(
    position_id: UUID,
    request: IndicatorSnapshotCalculationRequest,
    db: Annotated[Session, Depends(get_db)],
) -> IndicatorSnapshotCalculationResponse:
    engine = IndicatorEngine(db=db)
    try:
        return engine.calculate_snapshots(position_id=position_id, timeframes=request.timeframes)
    except PositionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/positions/{position_id}/review", response_model=TradeReviewResponse)
async def review_position(
    position_id: UUID,
    request: TradeReviewRequest,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TradeReviewResponse:
    engine = AiReviewEngine(
        db=db,
        openai_api_key=settings.openai_api_key,
        model=settings.openai_review_model,
    )
    try:
        return await engine.generate_review(
            position_id=position_id,
            user_rules=request.user_rules,
            similar_past_trade_stats=request.similar_past_trade_stats,
        )
    except ReviewPositionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _parse_datetime_query(value: str | None, label: str) -> datetime | None:
    if value is None:
        return None

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {label} datetime. Use ISO 8601 format.",
        ) from exc
