from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import SUPPORTED_TIMEFRAMES
from app.db.models import AiTradeReview, FuturesPosition, IndicatorSnapshot
from app.schemas.indicators import IndicatorSnapshotRead
from app.schemas.trades import (
    AiTradeReviewRead,
    DashboardAnalytics,
    FuturesPositionRead,
    IndicatorSummary,
    PositionDetail,
    PositionListItem,
    SymbolPerformance,
)
from app.services.position_context import PositionContextService
from app.services.trading_plan_service import TradingPlanService

MEXC_EXCHANGE = "MEXC"
ZERO = Decimal("0")
HUNDRED = Decimal("100")


class RiskEngine:
    """Read-only performance analytics for reconstructed MEXC Futures positions."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_dashboard(self, user_id: UUID) -> DashboardAnalytics:
        positions = self._load_user_positions(user_id=user_id)
        closed_positions = [position for position in positions if position.status == "closed"]
        net_values = {position.id: self._net_pnl(position) for position in positions}
        closed_net_values = [net_values[position.id] for position in closed_positions]

        gross_profit = sum((value for value in closed_net_values if value > ZERO), ZERO)
        gross_loss = sum((value for value in closed_net_values if value < ZERO), ZERO)
        wins = [value for value in closed_net_values if value > ZERO]
        losses = [value for value in closed_net_values if value < ZERO]

        indicator_summary = self._indicator_summary(
            positions=positions,
            snapshots=self._load_snapshots_for_positions(
                [position.id for position in positions if position.id is not None]
            ),
        )

        return DashboardAnalytics(
            total_realized_pnl=sum(
                (self._decimal(position.realized_pnl) for position in positions),
                ZERO,
            ),
            total_fees=sum((self._decimal(position.total_fees) for position in positions), ZERO),
            net_pnl=sum(net_values.values(), ZERO),
            trade_count=len(closed_positions),
            win_rate=self._divide(
                Decimal(len(wins)) * HUNDRED,
                Decimal(len(closed_positions)),
            ),
            average_win=self._divide(sum(wins, ZERO), Decimal(len(wins))),
            average_loss=self._divide(sum(losses, ZERO), Decimal(len(losses))),
            profit_factor=None if gross_loss == ZERO else gross_profit / abs(gross_loss),
            long_pnl=sum(
                (net_values[position.id] for position in positions if position.direction == "long"),
                ZERO,
            ),
            short_pnl=sum(
                (
                    net_values[position.id]
                    for position in positions
                    if position.direction == "short"
                ),
                ZERO,
            ),
            best_symbols=self._symbol_performance(closed_positions, net_values, reverse=True),
            worst_symbols=self._symbol_performance(closed_positions, net_values, reverse=False),
            open_positions=len([position for position in positions if position.status == "open"]),
            closed_positions=len(closed_positions),
            indicator_summary=indicator_summary,
        )

    def list_positions(
        self,
        user_id: UUID,
        symbol: str | None = None,
        status: str | None = None,
        direction: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        timeframe: str | None = None,
    ) -> list[PositionListItem]:
        normalized_timeframe = self._validate_timeframe(timeframe) if timeframe else None
        normalized_status = self._validate_optional_value(
            value=status,
            allowed={"open", "closed"},
            label="status",
        )
        normalized_direction = self._validate_optional_value(
            value=direction,
            allowed={"long", "short"},
            label="direction",
        )
        start = self._normalize_datetime(start)
        end = self._normalize_datetime(end)

        positions = self._load_user_positions(user_id=user_id)
        all_user_positions = positions
        all_snapshots = self._load_snapshots_for_positions(
            [position.id for position in positions if position.id is not None]
        )
        snapshots_by_position: dict[UUID, list[IndicatorSnapshot]] = {}
        for snapshot in all_snapshots:
            snapshots_by_position.setdefault(snapshot.position_id, []).append(snapshot)

        if normalized_timeframe:
            position_ids_with_timeframe = {
                snapshot.position_id
                for snapshot in all_snapshots
                if snapshot.timeframe == normalized_timeframe
            }
            positions = [
                position for position in positions if position.id in position_ids_with_timeframe
            ]

        filtered_positions = [
            position
            for position in positions
            if (symbol is None or position.symbol == symbol)
            and (normalized_status is None or position.status == normalized_status)
            and (normalized_direction is None or position.direction == normalized_direction)
            and (start is None or self._normalize_datetime(position.opened_at) >= start)
            and (end is None or self._normalize_datetime(position.opened_at) <= end)
        ]

        plan_service = TradingPlanService(db=self.db)
        plan = plan_service.load_active_plan(user_id=user_id)
        return [
            self._position_list_item(
                position=position,
                plan_evaluation=plan_service.evaluate_position(
                    plan=plan,
                    position=position,
                    snapshots=snapshots_by_position.get(position.id, []),
                    positions_for_daily_count=all_user_positions,
                ),
            )
            for position in filtered_positions
        ]

    def get_position_detail(self, position_id: UUID) -> PositionDetail | None:
        position = self._load_position(position_id=position_id)
        if position is None:
            return None

        snapshots = [
            snapshot
            for snapshot in self._load_position_snapshots(position_id=position_id)
            if snapshot.timeframe in SUPPORTED_TIMEFRAMES
        ]
        snapshots.sort(
            key=lambda snapshot: (
                SUPPORTED_TIMEFRAMES.index(snapshot.timeframe),
                {"entry": 0, "exit": 1}.get(getattr(snapshot, "anchor", None) or "entry", 99),
            )
        )
        review = self._load_latest_review(position_id=position_id)
        transaction_timeline, transaction_timeline_source = PositionContextService(
            db=self.db
        ).transaction_timeline(position)
        plan_service = TradingPlanService(db=self.db)
        plan = plan_service.load_active_plan(user_id=position.user_id)
        plan_evaluation = plan_service.evaluate_position(
            plan=plan,
            position=position,
            snapshots=snapshots,
            positions_for_daily_count=self._load_user_positions(user_id=position.user_id),
        )

        return PositionDetail(
            position=FuturesPositionRead.model_validate(position),
            indicator_snapshots=[
                IndicatorSnapshotRead.model_validate(snapshot) for snapshot in snapshots
            ],
            ai_review=AiTradeReviewRead.model_validate(review) if review else None,
            plan_evaluation=plan_evaluation,
            transaction_timeline=transaction_timeline,
            transaction_timeline_source=transaction_timeline_source,
        )

    def _load_user_positions(self, user_id: UUID) -> list[FuturesPosition]:
        statement = (
            select(FuturesPosition)
            .where(FuturesPosition.user_id == user_id)
            .where(FuturesPosition.exchange == MEXC_EXCHANGE)
            .order_by(FuturesPosition.opened_at.desc(), FuturesPosition.created_at.desc())
        )
        return list(self.db.scalars(statement).all())

    def _load_snapshots_for_positions(self, position_ids: list[UUID]) -> list[IndicatorSnapshot]:
        if not position_ids:
            return []
        statement = (
            select(IndicatorSnapshot)
            .where(IndicatorSnapshot.position_id.in_(position_ids))
            .where(IndicatorSnapshot.timeframe.in_(SUPPORTED_TIMEFRAMES))
        )
        return list(self.db.scalars(statement).all())

    def _load_position(self, position_id: UUID) -> FuturesPosition | None:
        position = self.db.get(FuturesPosition, position_id)
        if position is not None and position.exchange != MEXC_EXCHANGE:
            return None
        return position

    def _load_position_snapshots(self, position_id: UUID) -> list[IndicatorSnapshot]:
        statement = (
            select(IndicatorSnapshot)
            .where(IndicatorSnapshot.position_id == position_id)
            .where(IndicatorSnapshot.timeframe.in_(SUPPORTED_TIMEFRAMES))
        )
        return list(self.db.scalars(statement).all())

    def _load_latest_review(self, position_id: UUID) -> AiTradeReview | None:
        statement = (
            select(AiTradeReview)
            .where(AiTradeReview.position_id == position_id)
            .order_by(AiTradeReview.created_at.desc())
            .limit(1)
        )
        return self.db.scalar(statement)

    def _indicator_summary(
        self,
        positions: list[FuturesPosition],
        snapshots: list[IndicatorSnapshot],
    ) -> IndicatorSummary:
        position_by_id = {position.id: position for position in positions}
        rsi_overbought_entries = 0
        rsi_oversold_entries = 0
        supertrend_aligned_trades = 0
        supertrend_against_trades = 0
        macd_aligned_trades = 0
        macd_against_trades = 0

        for snapshot in snapshots:
            if (getattr(snapshot, "anchor", None) or "entry") != "entry":
                continue
            position = position_by_id.get(snapshot.position_id)
            if position is None:
                continue

            rsi_14 = self._optional_decimal(snapshot.rsi_14)
            if rsi_14 is not None:
                if rsi_14 > Decimal("70"):
                    rsi_overbought_entries += 1
                elif rsi_14 < Decimal("30"):
                    rsi_oversold_entries += 1

            if snapshot.supertrend_direction in {"bullish", "bearish"}:
                supertrend_aligned = (
                    position.direction == "long"
                    and snapshot.supertrend_direction == "bullish"
                ) or (
                    position.direction == "short"
                    and snapshot.supertrend_direction == "bearish"
                )
                if supertrend_aligned:
                    supertrend_aligned_trades += 1
                else:
                    supertrend_against_trades += 1

            macd = self._optional_decimal(snapshot.macd)
            macd_signal = self._optional_decimal(snapshot.macd_signal)
            if macd is not None and macd_signal is not None and macd != macd_signal:
                macd_aligned = (
                    position.direction == "long"
                    and macd > macd_signal
                    or position.direction == "short"
                    and macd < macd_signal
                )
                if macd_aligned:
                    macd_aligned_trades += 1
                else:
                    macd_against_trades += 1

        return IndicatorSummary(
            rsi_overbought_entries=rsi_overbought_entries,
            rsi_oversold_entries=rsi_oversold_entries,
            supertrend_aligned_trades=supertrend_aligned_trades,
            supertrend_against_trades=supertrend_against_trades,
            macd_aligned_trades=macd_aligned_trades,
            macd_against_trades=macd_against_trades,
        )

    def _symbol_performance(
        self,
        positions: list[FuturesPosition],
        net_values: dict[UUID, Decimal],
        reverse: bool,
    ) -> list[SymbolPerformance]:
        totals: dict[str, Decimal] = {}
        counts: dict[str, int] = {}
        for position in positions:
            totals[position.symbol] = totals.get(position.symbol, ZERO) + net_values[position.id]
            counts[position.symbol] = counts.get(position.symbol, 0) + 1

        sorted_symbols = sorted(
            totals,
            key=lambda symbol: (totals[symbol], symbol),
            reverse=reverse,
        )
        return [
            SymbolPerformance(
                symbol=symbol,
                net_pnl=totals[symbol],
                trade_count=counts[symbol],
            )
            for symbol in sorted_symbols[:5]
        ]

    def _position_list_item(self, position: FuturesPosition, plan_evaluation) -> PositionListItem:
        return PositionListItem(
            **FuturesPositionRead.model_validate(position).model_dump(),
            net_pnl=self._net_pnl(position),
            plan_score=plan_evaluation.score,
            plan_failed_items_count=plan_evaluation.failed_items_count,
            plan_unknown_items_count=plan_evaluation.unknown_items_count,
        )

    def _net_pnl(self, position: FuturesPosition) -> Decimal:
        return (
            self._decimal(position.realized_pnl)
            - self._decimal(position.total_fees)
            + self._decimal(position.funding_fees)
        )

    def _divide(self, numerator: Decimal, denominator: Decimal) -> Decimal:
        if denominator == ZERO:
            return ZERO
        return numerator / denominator

    def _validate_timeframe(self, timeframe: str) -> str:
        if timeframe not in SUPPORTED_TIMEFRAMES:
            supported = ", ".join(SUPPORTED_TIMEFRAMES)
            raise ValueError(f"Unsupported timeframe {timeframe!r}. Supported: {supported}.")
        return timeframe

    def _validate_optional_value(
        self,
        value: str | None,
        allowed: set[str],
        label: str,
    ) -> str | None:
        if value is None:
            return None
        normalized = value.lower()
        if normalized not in allowed:
            raise ValueError(f"Unsupported {label} {value!r}.")
        return normalized

    def _normalize_datetime(self, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def _optional_decimal(self, value: object) -> Decimal | None:
        if value is None:
            return None
        return self._decimal(value)

    def _decimal(self, value: object) -> Decimal:
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))
