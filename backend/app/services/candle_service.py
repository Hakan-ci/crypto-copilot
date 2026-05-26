from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.db.models import Candle, FuturesPosition
from app.schemas.mexc import CandleDTO

MEXC_EXCHANGE = "MEXC"
MAX_CANDLES_PER_REQUEST = 2000
INDICATOR_WARMUP_CANDLES = 250
LIKELY_MILLISECONDS_TIMESTAMP = 1_000_000_000_000

_TIMEFRAME_SECONDS = {
    "Min60": 3600,
    "Hour4": 14_400,
    "Day1": 86_400,
}

_TIMEFRAME_ALIASES = {
    "1h": "Min60",
    "min60": "Min60",
    "4h": "Hour4",
    "hour4": "Hour4",
    "1d": "Day1",
    "day1": "Day1",
}


class KlineClient(Protocol):
    async def get_klines(
        self,
        symbol: str,
        interval: str,
        start_s: int | None = None,
        end_s: int | None = None,
    ) -> list[CandleDTO]:
        ...


def normalize_timeframe(input: str) -> str:
    normalized = _TIMEFRAME_ALIASES.get(input.strip().lower())
    if normalized is None:
        raise ValueError(f"Unsupported timeframe: {input}")
    return normalized


def timeframe_to_seconds(interval: str) -> int:
    normalized = normalize_timeframe(interval)
    return _TIMEFRAME_SECONDS[normalized]


class CandleService:
    """Fetches and stores read-only MEXC Futures candles for analysis timeframes."""

    def __init__(self, db: Session, client: KlineClient) -> None:
        self.db = db
        self.client = client

    async def fetch_and_store_candles(
        self,
        symbol: str,
        timeframe: str,
        start_s: int,
        end_s: int,
    ) -> list[Candle]:
        normalized_timeframe = normalize_timeframe(timeframe)
        self._validate_seconds_range(start_s=start_s, end_s=end_s)

        fetched_candles: list[CandleDTO] = []
        timeframe_seconds = timeframe_to_seconds(normalized_timeframe)
        segment_start = start_s
        while segment_start <= end_s:
            segment_end = min(
                end_s,
                segment_start + timeframe_seconds * (MAX_CANDLES_PER_REQUEST - 1),
            )
            fetched_candles.extend(
                await self.client.get_klines(
                    symbol=symbol,
                    interval=normalized_timeframe,
                    start_s=segment_start,
                    end_s=segment_end,
                )
            )
            segment_start = segment_end + timeframe_seconds

        stored_candles: list[Candle] = []
        seen_keys: set[tuple[str, str, str, int]] = set()
        with self.db.begin():
            for candle_dto in fetched_candles:
                key = (
                    MEXC_EXCHANGE,
                    candle_dto.symbol,
                    normalized_timeframe,
                    candle_dto.timestamp_s,
                )
                if key in seen_keys:
                    continue
                seen_keys.add(key)

                existing_candle = self._get_existing_candle(
                    symbol=candle_dto.symbol,
                    timeframe=normalized_timeframe,
                    timestamp_s=candle_dto.timestamp_s,
                )
                if existing_candle is not None:
                    continue

                candle = Candle(
                    exchange=MEXC_EXCHANGE,
                    symbol=candle_dto.symbol,
                    timeframe=normalized_timeframe,
                    timestamp=datetime.fromtimestamp(candle_dto.timestamp_s, tz=UTC),
                    timestamp_s=candle_dto.timestamp_s,
                    open=candle_dto.open,
                    high=candle_dto.high,
                    low=candle_dto.low,
                    close=candle_dto.close,
                    volume=candle_dto.volume,
                    raw_json=None,
                )
                self._save_candle(candle)
                stored_candles.append(candle)

        return stored_candles

    def get_candles(
        self,
        symbol: str,
        timeframe: str,
        start_s: int,
        end_s: int,
    ) -> list[Candle]:
        normalized_timeframe = normalize_timeframe(timeframe)
        self._validate_seconds_range(start_s=start_s, end_s=end_s)
        statement = (
            select(Candle)
            .where(Candle.exchange == MEXC_EXCHANGE)
            .where(Candle.symbol == symbol)
            .where(Candle.timeframe == normalized_timeframe)
            .where(Candle.timestamp_s >= start_s)
            .where(Candle.timestamp_s <= end_s)
            .order_by(Candle.timestamp_s.asc())
        )
        return list(self.db.scalars(statement).all())

    async def ensure_candles_for_position(
        self,
        position: FuturesPosition,
        timeframe: str,
    ) -> list[Candle]:
        normalized_timeframe = normalize_timeframe(timeframe)
        timeframe_seconds = timeframe_to_seconds(normalized_timeframe)
        opened_at_s = self._datetime_to_seconds(position.opened_at)
        start_s = opened_at_s - (INDICATOR_WARMUP_CANDLES * timeframe_seconds)
        end_s = (
            self._datetime_to_seconds(position.closed_at)
            if position.closed_at is not None
            else int(utc_now().timestamp())
        )

        await self.fetch_and_store_candles(
            symbol=position.symbol,
            timeframe=normalized_timeframe,
            start_s=start_s,
            end_s=end_s,
        )
        return self.get_candles(
            symbol=position.symbol,
            timeframe=normalized_timeframe,
            start_s=start_s,
            end_s=end_s,
        )

    def _get_existing_candle(
        self,
        symbol: str,
        timeframe: str,
        timestamp_s: int,
    ) -> Candle | None:
        statement = (
            select(Candle)
            .where(Candle.exchange == MEXC_EXCHANGE)
            .where(Candle.symbol == symbol)
            .where(Candle.timeframe == timeframe)
            .where(Candle.timestamp_s == timestamp_s)
        )
        return self.db.scalar(statement)

    def _save_candle(self, candle: Candle) -> None:
        self.db.add(candle)

    def _validate_seconds_range(self, start_s: int, end_s: int) -> None:
        if start_s >= LIKELY_MILLISECONDS_TIMESTAMP or end_s >= LIKELY_MILLISECONDS_TIMESTAMP:
            raise ValueError("MEXC kline start/end must be Unix seconds, not milliseconds.")
        if end_s < start_s:
            raise ValueError("end_s must be greater than or equal to start_s.")

    def _datetime_to_seconds(self, value: datetime) -> int:
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return int(value.timestamp())
