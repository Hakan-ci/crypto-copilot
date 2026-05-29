from contextlib import AbstractContextManager
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.db.models import Candle, FuturesPosition, IndicatorSnapshot
from app.services.indicator_engine import SUPERTREND_MULTIPLIER, IndicatorEngine


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
        self.positions: dict[UUID, FuturesPosition] = {}
        self.candles: list[Candle] = []
        self.snapshots: list[IndicatorSnapshot] = []
        self.transaction_started = False
        self.transaction_exited = False

    def begin(self) -> FakeTransaction:
        return FakeTransaction(self)

    def add(self, row: Any) -> None:
        if isinstance(row, IndicatorSnapshot):
            self.snapshots.append(row)


class IndicatorEngineForTest(IndicatorEngine):
    def _get_position(self, position_id: UUID) -> FuturesPosition | None:
        return self.db.positions.get(position_id)

    def _load_candles_for_snapshot(
        self,
        position: FuturesPosition,
        timeframe: str,
        anchor_at: datetime,
    ) -> list[Candle]:
        anchor_at_s = self._datetime_to_seconds(anchor_at)
        return sorted(
            [
                candle
                for candle in self.db.candles
                if candle.exchange == "MEXC"
                and candle.symbol == position.symbol
                and candle.timeframe == timeframe
                and candle.timestamp_s <= anchor_at_s
            ],
            key=lambda candle: candle.timestamp_s,
        )

    def _get_existing_snapshot(
        self,
        position_id: UUID,
        timeframe: str,
        anchor: str,
    ) -> IndicatorSnapshot | None:
        for snapshot in self.db.snapshots:
            if (
                snapshot.position_id == position_id
                and snapshot.timeframe == timeframe
                and (snapshot.anchor or "entry") == anchor
            ):
                return snapshot
        return None


def make_position(position_id: UUID, opened_at_s: int, symbol: str = "BTC_USDT") -> FuturesPosition:
    return FuturesPosition(
        id=position_id,
        user_id=uuid4(),
        exchange="MEXC",
        symbol=symbol,
        direction="long",
        opened_at=datetime.fromtimestamp(opened_at_s, tz=UTC),
        avg_entry_price=Decimal("100"),
        total_volume=Decimal("1"),
        realized_pnl=Decimal("0"),
        total_fees=Decimal("0"),
        funding_fees=Decimal("0"),
        status="open",
    )


def make_candles(
    count: int,
    start_s: int = 0,
    step_s: int = 3600,
    symbol: str = "BTC_USDT",
    timeframe: str = "Min60",
) -> list[Candle]:
    candles: list[Candle] = []
    for index in range(count):
        timestamp_s = start_s + index * step_s
        close = Decimal("100") + Decimal(index) + Decimal(index % 5) / Decimal("10")
        candles.append(
            Candle(
                exchange="MEXC",
                symbol=symbol,
                timeframe=timeframe,
                timestamp=datetime.fromtimestamp(timestamp_s, tz=UTC),
                timestamp_s=timestamp_s,
                open=close - Decimal("0.5"),
                high=close + Decimal("2"),
                low=close - Decimal("2"),
                close=close,
                volume=Decimal("100") + Decimal(index),
                raw_json=None,
            )
        )
    return candles


def run_engine(candles: list[Candle], timeframes: list[str] | None = None) -> IndicatorSnapshot:
    position_id = uuid4()
    opened_at_s = candles[-1].timestamp_s
    db = FakeDbSession()
    db.positions[position_id] = make_position(position_id=position_id, opened_at_s=opened_at_s)
    db.candles = candles
    engine = IndicatorEngineForTest(db=db)

    response = engine.calculate_snapshots(
        position_id=position_id,
        timeframes=timeframes or ["Min60"],
    )

    assert response.snapshots_created_or_updated == 1
    return db.snapshots[0]


def test_rsi_returns_expected_range_0_to_100():
    snapshot = run_engine(make_candles(80))

    assert snapshot.rsi_14 is not None
    assert Decimal("0") <= snapshot.rsi_14 <= Decimal("100")


def test_stochastic_rsi_k_and_d_return_expected_range_0_to_100():
    snapshot = run_engine(make_candles(80))

    assert snapshot.stoch_rsi_k is not None
    assert snapshot.stoch_rsi_d is not None
    assert Decimal("0") <= snapshot.stoch_rsi_k <= Decimal("100")
    assert Decimal("0") <= snapshot.stoch_rsi_d <= Decimal("100")


def test_macd_produces_macd_signal_and_histogram():
    snapshot = run_engine(make_candles(80))

    assert snapshot.macd is not None
    assert snapshot.macd_signal is not None
    assert snapshot.macd_histogram is not None
    assert snapshot.macd_histogram == snapshot.macd - snapshot.macd_signal


def test_supertrend_returns_value_and_direction():
    snapshot = run_engine(make_candles(80))

    assert SUPERTREND_MULTIPLIER == Decimal("1")
    assert snapshot.supertrend_value is not None
    assert snapshot.supertrend_direction in {"bullish", "bearish"}


def test_snapshot_uses_candle_at_or_before_opened_at():
    position_id = uuid4()
    opened_at_s = 50 * 3600
    db = FakeDbSession()
    db.positions[position_id] = make_position(position_id=position_id, opened_at_s=opened_at_s)
    db.candles = make_candles(55)
    engine = IndicatorEngineForTest(db=db)

    engine.calculate_snapshots(position_id=position_id, timeframes=["Min60"])

    assert db.snapshots[0].timestamp == datetime.fromtimestamp(opened_at_s, tz=UTC)
    assert db.snapshots[0].price == db.candles[50].close


def test_snapshot_does_not_use_future_candle():
    position_id = uuid4()
    opened_at_s = 50 * 3600
    future_timestamp_s = 51 * 3600
    db = FakeDbSession()
    db.positions[position_id] = make_position(position_id=position_id, opened_at_s=opened_at_s)
    db.candles = make_candles(51)
    future_candle = make_candles(1, start_s=future_timestamp_s)[0]
    future_candle.close = Decimal("999999")
    db.candles.append(future_candle)
    engine = IndicatorEngineForTest(db=db)

    engine.calculate_snapshots(position_id=position_id, timeframes=["Min60"])

    assert db.snapshots[0].timestamp == datetime.fromtimestamp(opened_at_s, tz=UTC)
    assert db.snapshots[0].price != Decimal("999999")


def test_insufficient_candles_returns_warning_and_none_fields():
    position_id = uuid4()
    candles = make_candles(5)
    db = FakeDbSession()
    db.positions[position_id] = make_position(
        position_id=position_id,
        opened_at_s=candles[-1].timestamp_s,
    )
    db.candles = candles
    engine = IndicatorEngineForTest(db=db)

    response = engine.calculate_snapshots(position_id=position_id, timeframes=["Min60"])

    snapshot = db.snapshots[0]
    assert response.warnings
    assert snapshot.rsi_14 is None
    assert snapshot.stoch_rsi_k is None
    assert snapshot.stoch_rsi_d is None
    assert snapshot.macd_signal is None
    assert snapshot.supertrend_value is None
    assert snapshot.atr_14 is None
    assert snapshot.volume_relative is None


def test_unsupported_timeframe_rejected():
    position_id = uuid4()
    db = FakeDbSession()
    db.positions[position_id] = make_position(position_id=position_id, opened_at_s=0)
    engine = IndicatorEngineForTest(db=db)

    with pytest.raises(ValueError, match="Unsupported timeframe"):
        engine.calculate_snapshots(position_id=position_id, timeframes=["Min15"])


def test_idempotency_running_twice_updates_same_snapshot():
    position_id = uuid4()
    candles = make_candles(80)
    db = FakeDbSession()
    db.positions[position_id] = make_position(
        position_id=position_id,
        opened_at_s=candles[-1].timestamp_s,
    )
    db.candles = candles
    engine = IndicatorEngineForTest(db=db)

    first_response = engine.calculate_snapshots(position_id=position_id, timeframes=["Min60"])
    first_snapshot = db.snapshots[0]
    db.candles[-1].close = Decimal("222")
    second_response = engine.calculate_snapshots(position_id=position_id, timeframes=["Min60"])

    assert first_response.snapshots_created_or_updated == 1
    assert second_response.snapshots_created_or_updated == 1
    assert len(db.snapshots) == 1
    assert db.snapshots[0] is first_snapshot
    assert db.snapshots[0].price == Decimal("222")


def test_closed_position_gets_entry_and_exit_snapshots():
    position_id = uuid4()
    candles = make_candles(90)
    db = FakeDbSession()
    position = make_position(
        position_id=position_id,
        opened_at_s=candles[60].timestamp_s,
    )
    position.status = "closed"
    position.closed_at = datetime.fromtimestamp(candles[80].timestamp_s, tz=UTC)
    db.positions[position_id] = position
    db.candles = candles
    engine = IndicatorEngineForTest(db=db)

    response = engine.calculate_snapshots(position_id=position_id, timeframes=["Min60"])

    assert response.snapshots_created_or_updated == 2
    assert [snapshot.anchor for snapshot in db.snapshots] == ["entry", "exit"]
    assert db.snapshots[0].timestamp == candles[60].timestamp
    assert db.snapshots[1].timestamp == candles[80].timestamp


def test_snapshot_detects_candlestick_patterns():
    candles = make_candles(30)
    candles[-2].open = Decimal("110")
    candles[-2].high = Decimal("111")
    candles[-2].low = Decimal("99")
    candles[-2].close = Decimal("100")
    candles[-1].open = Decimal("99")
    candles[-1].high = Decimal("113")
    candles[-1].low = Decimal("98")
    candles[-1].close = Decimal("112")

    snapshot = run_engine(candles)

    assert "bullish_engulfing" in snapshot.candlestick_patterns


def test_decimal_conversion_does_not_break_database_insert():
    snapshot = run_engine(make_candles(80))

    decimal_fields = [
        snapshot.price,
        snapshot.rsi_14,
        snapshot.stoch_rsi_k,
        snapshot.stoch_rsi_d,
        snapshot.macd,
        snapshot.macd_signal,
        snapshot.macd_histogram,
        snapshot.supertrend_value,
        snapshot.atr_14,
        snapshot.volume_relative,
    ]
    assert all(value is None or isinstance(value, Decimal) for value in decimal_fields)
