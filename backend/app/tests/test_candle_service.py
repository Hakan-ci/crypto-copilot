import asyncio
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from app.db.models import Candle, FuturesPosition
from app.schemas.mexc import CandleDTO
from app.services.candle_service import (
    INDICATOR_WARMUP_CANDLES,
    MAX_CANDLES_PER_REQUEST,
    CandleService,
    normalize_timeframe,
    timeframe_to_seconds,
)


class FakeTransaction(AbstractContextManager["FakeTransaction"]):
    def __init__(self, db: "FakeDbSession") -> None:
        self.db = db

    def __enter__(self) -> "FakeTransaction":
        self.db.transaction_started = True
        return self

    def __exit__(self, *args: object) -> None:
        self.db.transaction_exited = True
        return None


class FakeDbSession:
    def __init__(self) -> None:
        self.candles: list[Candle] = []
        self.transaction_started = False
        self.transaction_exited = False

    def begin(self) -> FakeTransaction:
        return FakeTransaction(self)

    def add(self, row: Any) -> None:
        self.candles.append(row)


class CandleServiceForTest(CandleService):
    def _get_existing_candle(
        self,
        symbol: str,
        timeframe: str,
        timestamp_s: int,
    ) -> Candle | None:
        for candle in self.db.candles:
            if (
                candle.exchange == "MEXC"
                and candle.symbol == symbol
                and candle.timeframe == timeframe
                and candle.timestamp_s == timestamp_s
            ):
                return candle
        return None

    def get_candles(
        self,
        symbol: str,
        timeframe: str,
        start_s: int,
        end_s: int,
    ) -> list[Candle]:
        normalized_timeframe = normalize_timeframe(timeframe)
        self._validate_seconds_range(start_s=start_s, end_s=end_s)
        return sorted(
            [
                candle
                for candle in self.db.candles
                if candle.exchange == "MEXC"
                and candle.symbol == symbol
                and candle.timeframe == normalized_timeframe
                and start_s <= candle.timestamp_s <= end_s
            ],
            key=lambda candle: candle.timestamp_s,
        )


class FakeMexcClient:
    def __init__(self, candles: list[CandleDTO] | None = None) -> None:
        self.candles = candles or []
        self.calls: list[dict[str, Any]] = []

    async def get_klines(
        self,
        symbol: str,
        interval: str,
        start_s: int | None = None,
        end_s: int | None = None,
    ) -> list[CandleDTO]:
        self.calls.append(
            {
                "symbol": symbol,
                "interval": interval,
                "start_s": start_s,
                "end_s": end_s,
            }
        )
        return [
            candle
            for candle in self.candles
            if candle.symbol == symbol
            and candle.interval == interval
            and start_s is not None
            and end_s is not None
            and start_s <= candle.timestamp_s <= end_s
        ]


def make_candle(timestamp_s: int, symbol: str = "BTC_USDT", interval: str = "Min60") -> CandleDTO:
    return CandleDTO(
        symbol=symbol,
        interval=interval,
        timestamp_s=timestamp_s,
        open=Decimal("100.123456789123456789"),
        high=Decimal("110.123456789123456789"),
        low=Decimal("90.123456789123456789"),
        close=Decimal("105.123456789123456789"),
        volume=Decimal("42.123456789123456789"),
    )


def make_stored_candle(
    timestamp_s: int,
    symbol: str = "BTC_USDT",
    timeframe: str = "Min60",
) -> Candle:
    return Candle(
        exchange="MEXC",
        symbol=symbol,
        timeframe=timeframe,
        timestamp=datetime.fromtimestamp(timestamp_s, tz=UTC),
        timestamp_s=timestamp_s,
        open=Decimal("1"),
        high=Decimal("1"),
        low=Decimal("1"),
        close=Decimal("1"),
        volume=Decimal("1"),
        raw_json=None,
    )


def test_timeframe_to_seconds_works():
    assert timeframe_to_seconds("Min60") == 3600
    assert timeframe_to_seconds("Hour4") == 14_400
    assert timeframe_to_seconds("Day1") == 86_400


def test_normalize_timeframe_accepts_supported_aliases():
    assert normalize_timeframe("1h") == "Min60"
    assert normalize_timeframe("1H") == "Min60"
    assert normalize_timeframe("Min60") == "Min60"
    assert normalize_timeframe("4h") == "Hour4"
    assert normalize_timeframe("4H") == "Hour4"
    assert normalize_timeframe("Hour4") == "Hour4"
    assert normalize_timeframe("1d") == "Day1"
    assert normalize_timeframe("1D") == "Day1"
    assert normalize_timeframe("Day1") == "Day1"


def test_unsupported_timeframe_rejected():
    with pytest.raises(ValueError, match="Unsupported timeframe"):
        normalize_timeframe("Min15")


def test_milliseconds_are_rejected_before_calling_mexc():
    db = FakeDbSession()
    client = FakeMexcClient()
    service = CandleServiceForTest(db=db, client=client)

    with pytest.raises(ValueError, match="seconds"):
        asyncio.run(
            service.fetch_and_store_candles(
                symbol="BTC_USDT",
                timeframe="Min60",
                start_s=1_710_000_000_000,
                end_s=1_710_003_600_000,
            )
        )

    assert client.calls == []
    assert db.candles == []


def test_fetch_passes_seconds_to_mexc_kline_endpoint():
    db = FakeDbSession()
    client = FakeMexcClient()
    service = CandleServiceForTest(db=db, client=client)

    asyncio.run(
        service.fetch_and_store_candles(
            symbol="BTC_USDT",
            timeframe="1H",
            start_s=1_710_000_000,
            end_s=1_710_003_600,
        )
    )

    assert client.calls == [
        {
            "symbol": "BTC_USDT",
            "interval": "Min60",
            "start_s": 1_710_000_000,
            "end_s": 1_710_003_600,
        }
    ]


def test_segmented_fetching_respects_max_2000_candles_per_request():
    db = FakeDbSession()
    client = FakeMexcClient()
    service = CandleServiceForTest(db=db, client=client)
    timeframe_seconds = timeframe_to_seconds("Min60")
    start_s = 0
    end_s = timeframe_seconds * MAX_CANDLES_PER_REQUEST

    asyncio.run(
        service.fetch_and_store_candles(
            symbol="BTC_USDT",
            timeframe="Min60",
            start_s=start_s,
            end_s=end_s,
        )
    )

    assert len(client.calls) == 2
    for call in client.calls:
        candle_count = ((call["end_s"] - call["start_s"]) // timeframe_seconds) + 1
        assert candle_count <= MAX_CANDLES_PER_REQUEST
    assert client.calls[0]["end_s"] == timeframe_seconds * (MAX_CANDLES_PER_REQUEST - 1)
    assert client.calls[1]["start_s"] == timeframe_seconds * MAX_CANDLES_PER_REQUEST


def test_duplicate_candle_insert_is_skipped():
    db = FakeDbSession()
    db.candles.append(make_stored_candle(timestamp_s=1000))
    client = FakeMexcClient(
        [
            make_candle(timestamp_s=1000),
            make_candle(timestamp_s=2000),
            make_candle(timestamp_s=2000),
        ]
    )
    service = CandleServiceForTest(db=db, client=client)

    stored = asyncio.run(
        service.fetch_and_store_candles(
            symbol="BTC_USDT",
            timeframe="Min60",
            start_s=1000,
            end_s=2000,
        )
    )

    assert len(stored) == 1
    assert len(db.candles) == 2
    assert [candle.timestamp_s for candle in db.candles] == [1000, 2000]


def test_stored_ohlcv_values_remain_decimal():
    db = FakeDbSession()
    client = FakeMexcClient([make_candle(timestamp_s=1000)])
    service = CandleServiceForTest(db=db, client=client)

    asyncio.run(
        service.fetch_and_store_candles(
            symbol="BTC_USDT",
            timeframe="Min60",
            start_s=1000,
            end_s=1000,
        )
    )

    candle = db.candles[0]
    assert candle.open == Decimal("100.123456789123456789")
    assert candle.high == Decimal("110.123456789123456789")
    assert candle.low == Decimal("90.123456789123456789")
    assert candle.close == Decimal("105.123456789123456789")
    assert candle.volume == Decimal("42.123456789123456789")


def test_ensure_candles_for_position_fetches_warmup_before_opened_at():
    db = FakeDbSession()
    client = FakeMexcClient()
    service = CandleServiceForTest(db=db, client=client)
    opened_at = datetime.fromtimestamp(1_710_000_000, tz=UTC)
    closed_at = datetime.fromtimestamp(1_710_003_600, tz=UTC)
    position = FuturesPosition(
        symbol="BTC_USDT",
        opened_at=opened_at,
        closed_at=closed_at,
    )

    asyncio.run(service.ensure_candles_for_position(position=position, timeframe="1H"))

    expected_start_s = 1_710_000_000 - (
        INDICATOR_WARMUP_CANDLES * timeframe_to_seconds("Min60")
    )
    assert client.calls[0]["start_s"] == expected_start_s
    assert client.calls[-1]["end_s"] == 1_710_003_600
