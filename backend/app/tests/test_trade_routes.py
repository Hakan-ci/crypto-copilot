import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.api.routes import trades as trade_routes
from app.core.config import Settings
from app.db.models import Candle
from app.schemas.indicators import (
    IndicatorSnapshotCalculationRequest,
    IndicatorSnapshotCalculationResponse,
)
from app.schemas.trades import (
    AiTradeQuestionRead,
    AiTradeQuestionRequest,
    IndicatorObservations,
    PositionTradeMetadataRead,
    PositionTradeMetadataUpsert,
    TimeframeAlignment,
    TradeReviewOutput,
    TradeReviewRequest,
    TradeReviewResponse,
)
from app.services.ai_review_engine import OpenAiNotConfiguredError
from app.services.trade_metadata_service import TradeMetadataPositionNotFoundError


def make_settings() -> Settings:
    return Settings(
        DATABASE_URL="postgresql+psycopg://user:pass@localhost:5432/app",
        MEXC_BASE_URL="https://contract.mexc.com",
        SECRET_KEY="test-secret-key",
        API_KEY_ENCRYPTION_KEY="test-encryption-key",
    )


class FakeDb:
    def __init__(self, position):
        self.position = position
        self.commits = 0
        self.transaction_open = True

    def get(self, model, id_):
        _ = (model, id_)
        return self.position

    def in_transaction(self):
        return self.transaction_open

    def commit(self):
        self.commits += 1
        self.transaction_open = False


def test_calculate_indicator_snapshots_fetches_candles_before_calculation(monkeypatch):
    position_id = uuid4()
    calls: list[tuple[str, object]] = []

    class FakeCandleService:
        def __init__(self, db, client):
            _ = (db, client)

        async def ensure_candles_for_position(self, position, timeframe):
            calls.append((timeframe, position))

    class FakeIndicatorEngine:
        def __init__(self, db):
            _ = db

        def calculate_snapshots(self, position_id, timeframes):
            assert timeframes == ["Min60", "Hour4"]
            return IndicatorSnapshotCalculationResponse(
                position_id=position_id,
                snapshots_created_or_updated=2,
                warnings=[],
            )

    monkeypatch.setattr(trade_routes, "CandleService", FakeCandleService)
    monkeypatch.setattr(trade_routes, "IndicatorEngine", FakeIndicatorEngine)
    monkeypatch.setattr(trade_routes, "build_mexc_client", lambda settings: object())
    db = FakeDb(position=SimpleNamespace(id=position_id))

    response = asyncio.run(
        trade_routes.calculate_indicator_snapshots(
            position_id=position_id,
            request=IndicatorSnapshotCalculationRequest(timeframes=["Min60", "Hour4"]),
            db=db,
            settings=make_settings(),
        )
    )

    assert [call[0] for call in calls] == ["Min60", "Hour4"]
    assert response.snapshots_created_or_updated == 2
    assert db.commits == 1


def test_list_position_candles_reads_expected_position_timeframe_range(monkeypatch):
    position_id = uuid4()
    opened_at = datetime.fromtimestamp(1_710_000_000, tz=UTC)
    closed_at = datetime.fromtimestamp(1_710_003_600, tz=UTC)
    candle_id = uuid4()
    calls: list[dict[str, object]] = []

    class FakeCandleService:
        def __init__(self, db, client):
            _ = (db, client)

        def get_candles(self, symbol, timeframe, start_s, end_s):
            calls.append(
                {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "start_s": start_s,
                    "end_s": end_s,
                }
            )
            return [
                Candle(
                    id=candle_id,
                    exchange="MEXC",
                    symbol=symbol,
                    timeframe=timeframe,
                    timestamp=opened_at,
                    timestamp_s=1_710_000_000,
                    open=Decimal("100"),
                    high=Decimal("110"),
                    low=Decimal("90"),
                    close=Decimal("105"),
                    volume=Decimal("42"),
                    raw_json=None,
                )
            ]

    monkeypatch.setattr(trade_routes, "CandleService", FakeCandleService)
    db = FakeDb(
        position=SimpleNamespace(
            id=position_id,
            symbol="BTC_USDT",
            opened_at=opened_at,
            closed_at=closed_at,
        )
    )

    response = trade_routes.list_position_candles(
        position_id=position_id,
        db=db,
        timeframe="Min60",
    )

    assert calls == [
        {
            "symbol": "BTC_USDT",
            "timeframe": "Min60",
            "start_s": 1_709_100_000,
            "end_s": 1_710_003_600,
        }
    ]
    assert response[0].id == candle_id
    assert response[0].close == Decimal("105")


def test_review_position_ignores_request_user_rules(monkeypatch):
    position_id = uuid4()
    calls: list[dict[str, object]] = []

    class FakeAiReviewEngine:
        def __init__(self, db, openai_api_key, model):
            _ = (db, openai_api_key, model)

        async def generate_review(
            self,
            position_id,
            review_timeframe="Hour4",
            similar_past_trade_stats=None,
        ):
            calls.append(
                {
                    "position_id": position_id,
                    "review_timeframe": review_timeframe,
                    "similar_past_trade_stats": similar_past_trade_stats,
                }
            )
            return TradeReviewResponse(
                position_id=position_id,
                review_id=None,
                review=TradeReviewOutput(
                    summary="Educational review.",
                    timeframe_alignment=TimeframeAlignment(
                        one_hour="unknown",
                        four_hour="unknown",
                        one_day="unknown",
                        overall="unknown",
                    ),
                    indicator_observations=IndicatorObservations(
                        rsi=[],
                        stoch_rsi=[],
                        macd=[],
                        supertrend=[],
                    ),
                    strengths=[],
                    weaknesses=[],
                    risk_flags=[],
                    mistake_tags=[],
                    rule_match_score=None,
                    risk_score=None,
                    execution_score=None,
                    final_note="Final decision belongs to the user.",
                ),
            )

    class FakeTradeMetadataService:
        def __init__(self, db):
            _ = db

        async def sync_stop_loss_from_mexc(self, position_id, client):
            calls.append({"sync_position_id": position_id, "client": client})
            return None

    monkeypatch.setattr(trade_routes, "AiReviewEngine", FakeAiReviewEngine)
    monkeypatch.setattr(trade_routes, "TradeMetadataService", FakeTradeMetadataService)
    monkeypatch.setattr(trade_routes, "build_mexc_client", lambda settings: "mexc-client")

    asyncio.run(
        trade_routes.review_position(
            position_id=position_id,
            request=TradeReviewRequest(
                review_timeframe="Hour4",
                user_rules={"notes": "browser-only override"},
                similar_past_trade_stats={"wins": 1},
            ),
            db=object(),
            settings=make_settings(),
        )
    )

    assert calls == [
        {"sync_position_id": position_id, "client": "mexc-client"},
        {
            "position_id": position_id,
            "review_timeframe": "Hour4",
            "similar_past_trade_stats": {"wins": 1},
        }
    ]


def test_ai_question_routes_delegate_and_map_missing_key(monkeypatch):
    position_id = uuid4()
    question_id = uuid4()
    user_id = uuid4()
    created_at = datetime.fromtimestamp(1_710_000_000, tz=UTC)

    class FakeAiReviewEngine:
        def __init__(self, db, openai_api_key, model):
            _ = (db, openai_api_key, model)

        def list_questions(self, position_id):
            return [
                AiTradeQuestionRead(
                    id=question_id,
                    user_id=user_id,
                    position_id=position_id,
                    question="What happened?",
                    answer="A retrospective answer.",
                    context_json={},
                    model="gpt-4o-mini",
                    created_at=created_at,
                )
            ]

        async def answer_question(self, position_id, question):
            _ = (position_id, question)
            raise OpenAiNotConfiguredError("OpenAI API key is missing.")

    class FakeTradeMetadataService:
        def __init__(self, db):
            _ = db

        async def sync_stop_loss_from_mexc(self, position_id, client):
            _ = (position_id, client)
            return None

    monkeypatch.setattr(trade_routes, "AiReviewEngine", FakeAiReviewEngine)
    monkeypatch.setattr(trade_routes, "TradeMetadataService", FakeTradeMetadataService)
    monkeypatch.setattr(trade_routes, "build_mexc_client", lambda settings: object())

    questions = trade_routes.list_ai_questions(
        position_id=position_id,
        db=object(),
        settings=make_settings(),
    )

    assert questions[0].id == question_id
    with pytest.raises(trade_routes.HTTPException) as exc_info:
        asyncio.run(
            trade_routes.ask_ai_question(
                position_id=position_id,
                request=AiTradeQuestionRequest(question="What happened?"),
                db=object(),
                settings=make_settings(),
            )
        )
    assert exc_info.value.status_code == 503


def test_trade_metadata_routes_delegate_and_map_missing_position(monkeypatch):
    position_id = uuid4()
    metadata_id = uuid4()
    created_at = datetime.fromtimestamp(1_710_000_000, tz=UTC)
    metadata = PositionTradeMetadataRead(
        id=metadata_id,
        position_id=position_id,
        planned_stop_loss_price=Decimal("98"),
        notes="Planned before entry.",
        created_at=created_at,
        updated_at=created_at,
    )
    calls: list[tuple[str, object]] = []

    class FakeTradeMetadataService:
        def __init__(self, db):
            calls.append(("init", db))

        def read_metadata(self, position_id):
            calls.append(("read", position_id))
            return metadata

        async def sync_stop_loss_from_mexc(self, position_id, client):
            calls.append(("sync", position_id))
            return metadata

        def upsert_metadata(self, position_id, payload):
            calls.append(("upsert", payload))
            return metadata

    monkeypatch.setattr(trade_routes, "TradeMetadataService", FakeTradeMetadataService)
    monkeypatch.setattr(trade_routes, "build_mexc_client", lambda settings: object())

    assert (
        asyncio.run(
            trade_routes.get_position_trade_metadata(
                position_id=position_id,
                db=object(),
                settings=make_settings(),
            )
        )
        == metadata
    )
    assert (
        trade_routes.put_position_trade_metadata(
            position_id=position_id,
            payload=PositionTradeMetadataUpsert(planned_stop_loss_price=Decimal("98")),
            db=object(),
        )
        == metadata
    )
    assert calls[1] == ("sync", position_id)
    assert calls[3][0] == "upsert"

    class MissingTradeMetadataService:
        def __init__(self, db):
            _ = db

        def read_metadata(self, position_id):
            raise TradeMetadataPositionNotFoundError(f"Position not found: {position_id}")

        async def sync_stop_loss_from_mexc(self, position_id, client):
            raise TradeMetadataPositionNotFoundError(f"Position not found: {position_id}")

        def upsert_metadata(self, position_id, payload):
            raise TradeMetadataPositionNotFoundError(f"Position not found: {position_id}")

    monkeypatch.setattr(trade_routes, "TradeMetadataService", MissingTradeMetadataService)
    with pytest.raises(trade_routes.HTTPException) as get_exc:
        asyncio.run(
            trade_routes.get_position_trade_metadata(
                position_id=position_id,
                db=object(),
                settings=make_settings(),
            )
        )
    with pytest.raises(trade_routes.HTTPException) as put_exc:
        trade_routes.put_position_trade_metadata(
            position_id=position_id,
            payload=PositionTradeMetadataUpsert(planned_stop_loss_price=Decimal("98")),
            db=object(),
        )
    assert get_exc.value.status_code == 404
    assert put_exc.value.status_code == 404
