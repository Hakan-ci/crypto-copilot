from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.routes.mexc import build_mexc_client
from app.core.config import Settings, get_settings
from app.db.models import FuturesPosition
from app.db.session import get_db
from app.schemas.indicators import (
    CandleRead,
    IndicatorSnapshotCalculationRequest,
    IndicatorSnapshotCalculationResponse,
)
from app.schemas.trades import (
    AiTradeQuestionRead,
    AiTradeQuestionRequest,
    DashboardAnalytics,
    PositionDetail,
    PositionListItem,
    PositionTradeMetadataRead,
    PositionTradeMetadataUpsert,
    ReconstructionReport,
    TradeReviewRequest,
    TradeReviewResponse,
)
from app.services.ai_review_engine import (
    AiReviewEngine,
    OpenAiNotConfiguredError,
    ReviewContextMissingError,
    TradeReviewError,
)
from app.services.ai_review_engine import (
    PositionNotFoundError as ReviewPositionNotFoundError,
)
from app.services.candle_service import (
    INDICATOR_WARMUP_CANDLES,
    CandleService,
    timeframe_to_seconds,
)
from app.services.indicator_engine import IndicatorEngine, PositionNotFoundError
from app.services.mexc_client import MexcApiError
from app.services.position_reconstructor import PositionReconstructor
from app.services.risk_engine import RiskEngine
from app.services.trade_metadata_service import (
    TradeMetadataPositionNotFoundError,
    TradeMetadataService,
)

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


@router.get(
    "/positions/{position_id}/trade-metadata",
    response_model=PositionTradeMetadataRead | None,
)
async def get_position_trade_metadata(
    position_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> PositionTradeMetadataRead | None:
    service = TradeMetadataService(db=db)
    try:
        return await service.sync_stop_loss_from_mexc(
            position_id=position_id,
            client=build_mexc_client(settings),
        )
    except TradeMetadataPositionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MexcApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.put(
    "/positions/{position_id}/trade-metadata",
    response_model=PositionTradeMetadataRead,
)
def put_position_trade_metadata(
    position_id: UUID,
    payload: PositionTradeMetadataUpsert,
    db: Annotated[Session, Depends(get_db)],
) -> PositionTradeMetadataRead:
    service = TradeMetadataService(db=db)
    try:
        return service.upsert_metadata(position_id=position_id, payload=payload)
    except TradeMetadataPositionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/positions/{position_id}/indicator-snapshots",
    response_model=IndicatorSnapshotCalculationResponse,
)
async def calculate_indicator_snapshots(
    position_id: UUID,
    request: IndicatorSnapshotCalculationRequest,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> IndicatorSnapshotCalculationResponse:
    position = db.get(FuturesPosition, position_id)
    if position is None:
        raise HTTPException(status_code=404, detail=f"Position not found: {position_id}")
    _commit_active_transaction(db)

    candle_service = CandleService(db=db, client=build_mexc_client(settings))
    try:
        for timeframe in request.timeframes:
            await candle_service.ensure_candles_for_position(
                position=position,
                timeframe=timeframe,
            )
            _commit_active_transaction(db)
    except MexcApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    engine = IndicatorEngine(db=db)
    try:
        return engine.calculate_snapshots(position_id=position_id, timeframes=request.timeframes)
    except PositionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/positions/{position_id}/candles", response_model=list[CandleRead])
def list_position_candles(
    position_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    timeframe: Annotated[str, Query()] = "Min60",
) -> list[CandleRead]:
    position = db.get(FuturesPosition, position_id)
    if position is None:
        raise HTTPException(status_code=404, detail=f"Position not found: {position_id}")

    try:
        timeframe_seconds = timeframe_to_seconds(timeframe)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    opened_at_s = _datetime_to_seconds(position.opened_at)
    end_s = (
        _datetime_to_seconds(position.closed_at)
        if position.closed_at is not None
        else int(datetime.now(tz=UTC).timestamp())
    )
    start_s = opened_at_s - (INDICATOR_WARMUP_CANDLES * timeframe_seconds)
    service = CandleService(db=db, client=_NoopKlineClient())
    return [
        CandleRead.model_validate(candle)
        for candle in service.get_candles(
            symbol=position.symbol,
            timeframe=timeframe,
            start_s=start_s,
            end_s=end_s,
        )
    ]


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
        await TradeMetadataService(db=db).sync_stop_loss_from_mexc(
            position_id=position_id,
            client=build_mexc_client(settings),
        )
        return await engine.generate_review(
            position_id=position_id,
            review_timeframe=request.review_timeframe,
            similar_past_trade_stats=request.similar_past_trade_stats,
        )
    except ReviewPositionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TradeMetadataPositionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ReviewContextMissingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OpenAiNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except TradeReviewError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except MexcApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/positions/{position_id}/ai-questions", response_model=list[AiTradeQuestionRead])
def list_ai_questions(
    position_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[AiTradeQuestionRead]:
    engine = AiReviewEngine(
        db=db,
        openai_api_key=settings.openai_api_key,
        model=settings.openai_review_model,
    )
    try:
        return engine.list_questions(position_id=position_id)
    except ReviewPositionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/positions/{position_id}/ai-questions", response_model=AiTradeQuestionRead)
async def ask_ai_question(
    position_id: UUID,
    request: AiTradeQuestionRequest,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AiTradeQuestionRead:
    engine = AiReviewEngine(
        db=db,
        openai_api_key=settings.openai_api_key,
        model=settings.openai_review_model,
    )
    try:
        await TradeMetadataService(db=db).sync_stop_loss_from_mexc(
            position_id=position_id,
            client=build_mexc_client(settings),
        )
        return await engine.answer_question(position_id=position_id, question=request.question)
    except ReviewPositionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TradeMetadataPositionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except OpenAiNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except MexcApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


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


def _datetime_to_seconds(value: datetime) -> int:
    if value.tzinfo is None:
        return int(value.replace(tzinfo=UTC).timestamp())
    return int(value.timestamp())


def _commit_active_transaction(db: Session) -> None:
    in_transaction = getattr(db, "in_transaction", None)
    if callable(in_transaction) and in_transaction():
        db.commit()


class _NoopKlineClient:
    async def get_klines(
        self,
        symbol: str,
        interval: str,
        start_s: int | None = None,
        end_s: int | None = None,
    ) -> list[object]:
        _ = (symbol, interval, start_s, end_s)
        return []
