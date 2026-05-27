import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from app.api.routes import trades as trade_routes
from app.core.config import Settings
from app.db.models import Candle
from app.schemas.indicators import (
    IndicatorSnapshotCalculationRequest,
    IndicatorSnapshotCalculationResponse,
)


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
