from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Candle, FuturesPosition, IndicatorSnapshot
from app.schemas.indicators import IndicatorSnapshotCalculationResponse
from app.services.candle_service import MEXC_EXCHANGE, normalize_timeframe

ZERO = Decimal("0")
ONE = Decimal("1")
TWO = Decimal("2")
HUNDRED = Decimal("100")

RSI_LENGTH = 14
STOCH_RSI_LENGTH = 14
STOCH_RSI_K_SMOOTHING = 3
STOCH_RSI_D_SMOOTHING = 3
MACD_FAST_EMA = 12
MACD_SLOW_EMA = 26
MACD_SIGNAL_EMA = 9
SUPERTREND_ATR_LENGTH = 10
SUPERTREND_MULTIPLIER = Decimal("1")
ATR_14_LENGTH = 14
VOLUME_RELATIVE_LENGTH = 20
ENTRY_ANCHOR = "entry"
EXIT_ANCHOR = "exit"


class PositionNotFoundError(ValueError):
    pass


class IndicatorEngine:
    """Calculates deterministic indicator snapshots from stored candles."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def calculate_snapshots(
        self,
        position_id: UUID,
        timeframes: list[str],
    ) -> IndicatorSnapshotCalculationResponse:
        warnings: list[str] = []
        normalized_timeframes = [normalize_timeframe(timeframe) for timeframe in timeframes]
        snapshots_created_or_updated = 0

        with self.db.begin():
            position = self._get_position(position_id)
            if position is None:
                raise PositionNotFoundError(f"Position not found: {position_id}")

            for timeframe in normalized_timeframes:
                for anchor, anchor_at in self._snapshot_anchors(position).items():
                    candles = self._load_candles_for_snapshot(
                        position=position,
                        timeframe=timeframe,
                        anchor_at=anchor_at,
                    )
                    if not candles:
                        warnings.append(
                            f"No candles found for position {position_id} "
                            f"timeframe {timeframe} {anchor}."
                        )
                        continue

                    snapshot_values = self._calculate_snapshot_values(
                        position=position,
                        timeframe=timeframe,
                        anchor=anchor,
                        candles=candles,
                        warnings=warnings,
                    )
                    snapshot = self._get_existing_snapshot(
                        position_id=position_id,
                        timeframe=timeframe,
                        anchor=anchor,
                    )
                    if snapshot is None:
                        snapshot = IndicatorSnapshot(position_id=position_id, **snapshot_values)
                        self._save_snapshot(snapshot)
                    else:
                        self._update_snapshot(snapshot=snapshot, values=snapshot_values)

                    snapshots_created_or_updated += 1

        return IndicatorSnapshotCalculationResponse(
            position_id=position_id,
            snapshots_created_or_updated=snapshots_created_or_updated,
            warnings=warnings,
        )

    def _get_position(self, position_id: UUID) -> FuturesPosition | None:
        return self.db.get(FuturesPosition, position_id)

    def _load_candles_for_snapshot(
        self,
        position: FuturesPosition,
        timeframe: str,
        anchor_at: datetime,
    ) -> list[Candle]:
        anchor_at_s = self._datetime_to_seconds(anchor_at)
        statement = (
            select(Candle)
            .where(Candle.exchange == MEXC_EXCHANGE)
            .where(Candle.symbol == position.symbol)
            .where(Candle.timeframe == timeframe)
            .where(Candle.timestamp_s <= anchor_at_s)
            .order_by(Candle.timestamp_s.asc())
        )
        return list(self.db.scalars(statement).all())

    def _get_existing_snapshot(
        self,
        position_id: UUID,
        timeframe: str,
        anchor: str,
    ) -> IndicatorSnapshot | None:
        statement = (
            select(IndicatorSnapshot)
            .where(IndicatorSnapshot.position_id == position_id)
            .where(IndicatorSnapshot.timeframe == timeframe)
            .where(IndicatorSnapshot.anchor == anchor)
        )
        return self.db.scalar(statement)

    def _save_snapshot(self, snapshot: IndicatorSnapshot) -> None:
        self.db.add(snapshot)

    def _update_snapshot(self, snapshot: IndicatorSnapshot, values: dict[str, object]) -> None:
        for key, value in values.items():
            setattr(snapshot, key, value)

    def _calculate_snapshot_values(
        self,
        position: FuturesPosition,
        timeframe: str,
        anchor: str,
        candles: list[Candle],
        warnings: list[str],
    ) -> dict[str, object]:
        candles = sorted(candles, key=lambda candle: candle.timestamp_s)
        snapshot_candle = candles[-1]
        closes = [self._decimal(candle.close) for candle in candles]
        highs = [self._decimal(candle.high) for candle in candles]
        lows = [self._decimal(candle.low) for candle in candles]
        volumes = [self._decimal(candle.volume) for candle in candles]
        candlestick_patterns = self._candlestick_patterns(candles)

        rsi_14 = self._rsi(closes=closes, length=RSI_LENGTH)
        stoch_rsi_k, stoch_rsi_d = self._stoch_rsi(
            closes=closes,
            rsi_length=RSI_LENGTH,
            stochastic_length=STOCH_RSI_LENGTH,
            k_smoothing=STOCH_RSI_K_SMOOTHING,
            d_smoothing=STOCH_RSI_D_SMOOTHING,
        )
        macd, macd_signal, macd_histogram = self._macd(
            closes=closes,
            fast_period=MACD_FAST_EMA,
            slow_period=MACD_SLOW_EMA,
            signal_period=MACD_SIGNAL_EMA,
        )
        supertrend_value, supertrend_direction = self._supertrend(
            highs=highs,
            lows=lows,
            closes=closes,
            atr_length=SUPERTREND_ATR_LENGTH,
            multiplier=SUPERTREND_MULTIPLIER,
        )
        atr_14 = self._atr(highs=highs, lows=lows, closes=closes, length=ATR_14_LENGTH)
        volume_relative = self._volume_relative(volumes=volumes, length=VOLUME_RELATIVE_LENGTH)
        trend_label = self._trend_label(
            macd=macd,
            macd_signal=macd_signal,
            supertrend_direction=supertrend_direction,
        )

        missing_fields = [
            name
            for name, value in {
                "rsi_14": rsi_14,
                "stoch_rsi_k": stoch_rsi_k,
                "stoch_rsi_d": stoch_rsi_d,
                "macd": macd,
                "macd_signal": macd_signal,
                "macd_histogram": macd_histogram,
                "supertrend_value": supertrend_value,
                "supertrend_direction": supertrend_direction,
                "atr_14": atr_14,
                "volume_relative": volume_relative,
            }.items()
            if value is None
        ]
        if missing_fields:
            warnings.append(
                f"Insufficient candles for {position.id} {timeframe}: "
                f"{', '.join(missing_fields)} unavailable."
            )

        return {
            "symbol": position.symbol,
            "timeframe": timeframe,
            "anchor": anchor,
            "timestamp": snapshot_candle.timestamp,
            "price": self._decimal(snapshot_candle.close),
            "rsi_14": rsi_14,
            "stoch_rsi_k": stoch_rsi_k,
            "stoch_rsi_d": stoch_rsi_d,
            "macd": macd,
            "macd_signal": macd_signal,
            "macd_histogram": macd_histogram,
            "supertrend_value": supertrend_value,
            "supertrend_direction": supertrend_direction,
            "atr_14": atr_14,
            "volume_relative": volume_relative,
            "trend_label": trend_label,
            "candlestick_patterns": candlestick_patterns,
        }

    def _snapshot_anchors(self, position: FuturesPosition) -> dict[str, datetime]:
        anchors = {ENTRY_ANCHOR: position.opened_at}
        if position.closed_at is not None:
            anchors[EXIT_ANCHOR] = position.closed_at
        return anchors

    def _rsi(self, closes: list[Decimal], length: int) -> Decimal | None:
        if len(closes) < length + 1:
            return None
        gains: list[Decimal] = []
        losses: list[Decimal] = []
        for index in range(len(closes) - length, len(closes)):
            delta = closes[index] - closes[index - 1]
            gains.append(max(delta, ZERO))
            losses.append(abs(min(delta, ZERO)))

        average_gain = sum(gains, ZERO) / Decimal(length)
        average_loss = sum(losses, ZERO) / Decimal(length)
        return self._rsi_from_average(average_gain=average_gain, average_loss=average_loss)

    def _rsi_series(self, closes: list[Decimal], length: int) -> list[Decimal | None]:
        values: list[Decimal | None] = [None] * len(closes)
        for index in range(length, len(closes)):
            window = closes[index - length : index + 1]
            values[index] = self._rsi(closes=window, length=length)
        return values

    def _rsi_from_average(self, average_gain: Decimal, average_loss: Decimal) -> Decimal:
        if average_loss == ZERO:
            return HUNDRED if average_gain > ZERO else ZERO
        relative_strength = average_gain / average_loss
        return HUNDRED - (HUNDRED / (ONE + relative_strength))

    def _stoch_rsi(
        self,
        closes: list[Decimal],
        rsi_length: int,
        stochastic_length: int,
        k_smoothing: int,
        d_smoothing: int,
    ) -> tuple[Decimal | None, Decimal | None]:
        rsi_values = self._rsi_series(closes=closes, length=rsi_length)
        raw_stoch_values: list[Decimal | None] = [None] * len(rsi_values)
        for index in range(len(rsi_values)):
            rsi_window = [
                value
                for value in rsi_values[max(0, index - stochastic_length + 1) : index + 1]
                if value is not None
            ]
            current_rsi = rsi_values[index]
            if current_rsi is None or len(rsi_window) < stochastic_length:
                continue
            lowest = min(rsi_window)
            highest = max(rsi_window)
            raw_stoch_values[index] = ZERO
            if highest != lowest:
                raw_stoch_values[index] = (
                    (current_rsi - lowest) / (highest - lowest)
                ) * HUNDRED

        k_values = self._simple_moving_average_series(raw_stoch_values, k_smoothing)
        d_values = self._simple_moving_average_series(k_values, d_smoothing)
        return k_values[-1], d_values[-1]

    def _macd(
        self,
        closes: list[Decimal],
        fast_period: int,
        slow_period: int,
        signal_period: int,
    ) -> tuple[Decimal | None, Decimal | None, Decimal | None]:
        fast_ema = self._ema_series(closes, fast_period)
        slow_ema = self._ema_series(closes, slow_period)
        macd_series: list[Decimal | None] = []
        for fast, slow in zip(fast_ema, slow_ema, strict=False):
            macd_series.append(None if fast is None or slow is None else fast - slow)

        compact_macd = [value for value in macd_series if value is not None]
        signal_compact = self._ema_series(compact_macd, signal_period)
        signal_values = [value for value in signal_compact if value is not None]
        macd = macd_series[-1]
        macd_signal = signal_values[-1] if signal_values else None
        if macd is None or macd_signal is None:
            return macd, macd_signal, None
        return macd, macd_signal, macd - macd_signal

    def _supertrend(
        self,
        highs: list[Decimal],
        lows: list[Decimal],
        closes: list[Decimal],
        atr_length: int,
        multiplier: Decimal,
    ) -> tuple[Decimal | None, str | None]:
        atr_values = self._atr_series(highs=highs, lows=lows, closes=closes, length=atr_length)
        final_upper: Decimal | None = None
        final_lower: Decimal | None = None
        direction: str | None = None
        supertrend_value: Decimal | None = None

        for index, atr in enumerate(atr_values):
            if atr is None:
                continue

            hl2 = (highs[index] + lows[index]) / TWO
            basic_upper = hl2 + (multiplier * atr)
            basic_lower = hl2 - (multiplier * atr)

            if final_upper is None or final_lower is None or direction is None:
                final_upper = basic_upper
                final_lower = basic_lower
                direction = "bullish" if closes[index] >= hl2 else "bearish"
            else:
                previous_close = closes[index - 1]
                previous_upper = final_upper
                previous_lower = final_lower
                final_upper = (
                    basic_upper
                    if basic_upper < previous_upper or previous_close > previous_upper
                    else previous_upper
                )
                final_lower = (
                    basic_lower
                    if basic_lower > previous_lower or previous_close < previous_lower
                    else previous_lower
                )

                if direction == "bearish":
                    direction = "bullish" if closes[index] > final_upper else "bearish"
                else:
                    direction = "bearish" if closes[index] < final_lower else "bullish"

            supertrend_value = final_lower if direction == "bullish" else final_upper

        return supertrend_value, direction

    def _atr(
        self,
        highs: list[Decimal],
        lows: list[Decimal],
        closes: list[Decimal],
        length: int,
    ) -> Decimal | None:
        values = self._atr_series(highs=highs, lows=lows, closes=closes, length=length)
        return values[-1] if values else None

    def _atr_series(
        self,
        highs: list[Decimal],
        lows: list[Decimal],
        closes: list[Decimal],
        length: int,
    ) -> list[Decimal | None]:
        if len(closes) < length + 1:
            return [None] * len(closes)

        true_ranges: list[Decimal] = []
        values: list[Decimal | None] = [None] * len(closes)
        for index in range(1, len(closes)):
            true_range = max(
                highs[index] - lows[index],
                abs(highs[index] - closes[index - 1]),
                abs(lows[index] - closes[index - 1]),
            )
            true_ranges.append(true_range)
            if len(true_ranges) >= length:
                values[index] = sum(true_ranges[-length:], ZERO) / Decimal(length)
        return values

    def _volume_relative(self, volumes: list[Decimal], length: int) -> Decimal | None:
        if len(volumes) < length:
            return None
        average_volume = sum(volumes[-length:], ZERO) / Decimal(length)
        if average_volume == ZERO:
            return None
        return volumes[-1] / average_volume

    def _ema_series(self, values: list[Decimal], period: int) -> list[Decimal | None]:
        if len(values) < period:
            return [None] * len(values)

        ema_values: list[Decimal | None] = [None] * len(values)
        multiplier = Decimal("2") / Decimal(period + 1)
        current_ema = sum(values[:period], ZERO) / Decimal(period)
        ema_values[period - 1] = current_ema
        for index in range(period, len(values)):
            current_ema = (values[index] - current_ema) * multiplier + current_ema
            ema_values[index] = current_ema
        return ema_values

    def _simple_moving_average_series(
        self,
        values: list[Decimal | None],
        period: int,
    ) -> list[Decimal | None]:
        averages: list[Decimal | None] = [None] * len(values)
        for index in range(period - 1, len(values)):
            window = values[index - period + 1 : index + 1]
            if all(value is not None for value in window):
                total = sum((value for value in window if value is not None), ZERO)
                averages[index] = total / Decimal(period)
        return averages

    def _trend_label(
        self,
        macd: Decimal | None,
        macd_signal: Decimal | None,
        supertrend_direction: str | None,
    ) -> str | None:
        if macd is None or macd_signal is None or supertrend_direction is None:
            return None
        macd_direction = self._macd_label(macd=macd, macd_signal=macd_signal)
        if macd_direction == "bullish" and supertrend_direction == "bullish":
            return "bullish"
        if macd_direction == "bearish" and supertrend_direction == "bearish":
            return "bearish"
        return "mixed"

    def _candlestick_patterns(self, candles: list[Candle]) -> list[str]:
        if not candles:
            return []
        sorted_candles = sorted(candles, key=lambda candle: candle.timestamp_s)
        patterns: list[str] = []
        current = sorted_candles[-1]
        body = self._candle_body(current)
        candle_range = self._candle_range(current)
        upper_shadow = self._upper_shadow(current)
        lower_shadow = self._lower_shadow(current)

        if candle_range > ZERO and body <= candle_range * Decimal("0.1"):
            patterns.append("doji")
        small_upper_shadow = upper_shadow <= max(body, candle_range * Decimal("0.1"))
        small_lower_shadow = lower_shadow <= max(body, candle_range * Decimal("0.1"))
        if candle_range > ZERO and lower_shadow >= body * TWO and small_upper_shadow:
            patterns.append("hammer")
        if candle_range > ZERO and upper_shadow >= body * TWO and small_lower_shadow:
            patterns.append("shooting_star")

        if len(sorted_candles) >= 2:
            previous = sorted_candles[-2]
            if self._is_bearish(previous) and self._is_bullish(current):
                opens_below_previous_close = (
                    self._decimal(current.open) <= self._decimal(previous.close)
                )
                closes_above_previous_open = (
                    self._decimal(current.close) >= self._decimal(previous.open)
                )
                if opens_below_previous_close and closes_above_previous_open:
                    patterns.append("bullish_engulfing")
            if self._is_bullish(previous) and self._is_bearish(current):
                opens_above_previous_close = (
                    self._decimal(current.open) >= self._decimal(previous.close)
                )
                closes_below_previous_open = (
                    self._decimal(current.close) <= self._decimal(previous.open)
                )
                if opens_above_previous_close and closes_below_previous_open:
                    patterns.append("bearish_engulfing")

        if len(sorted_candles) >= 3:
            first, middle, last = sorted_candles[-3:]
            if (
                self._is_bearish(first)
                and self._candle_body(middle) <= self._candle_range(middle) * Decimal("0.35")
                and self._is_bullish(last)
                and self._decimal(last.close) > self._midpoint(first)
            ):
                patterns.append("morning_star")
            if (
                self._is_bullish(first)
                and self._candle_body(middle) <= self._candle_range(middle) * Decimal("0.35")
                and self._is_bearish(last)
                and self._decimal(last.close) < self._midpoint(first)
            ):
                patterns.append("evening_star")

        return sorted(set(patterns))

    def _candle_body(self, candle: Candle) -> Decimal:
        return abs(self._decimal(candle.close) - self._decimal(candle.open))

    def _candle_range(self, candle: Candle) -> Decimal:
        return max(self._decimal(candle.high) - self._decimal(candle.low), ZERO)

    def _upper_shadow(self, candle: Candle) -> Decimal:
        return self._decimal(candle.high) - max(
            self._decimal(candle.open),
            self._decimal(candle.close),
        )

    def _lower_shadow(self, candle: Candle) -> Decimal:
        return min(
            self._decimal(candle.open),
            self._decimal(candle.close),
        ) - self._decimal(candle.low)

    def _is_bullish(self, candle: Candle) -> bool:
        return self._decimal(candle.close) > self._decimal(candle.open)

    def _is_bearish(self, candle: Candle) -> bool:
        return self._decimal(candle.close) < self._decimal(candle.open)

    def _midpoint(self, candle: Candle) -> Decimal:
        return (self._decimal(candle.open) + self._decimal(candle.close)) / TWO

    def _rsi_label(self, rsi: Decimal | None) -> str | None:
        if rsi is None:
            return None
        if rsi > Decimal("70"):
            return "overbought"
        if rsi < Decimal("30"):
            return "oversold"
        return "neutral"

    def _macd_label(self, macd: Decimal, macd_signal: Decimal) -> str:
        if macd > macd_signal:
            return "bullish"
        if macd < macd_signal:
            return "bearish"
        return "mixed"

    def _datetime_to_seconds(self, value: datetime) -> int:
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return int(value.timestamp())

    def _decimal(self, value: Decimal | int | str) -> Decimal:
        return value if isinstance(value, Decimal) else Decimal(str(value))
