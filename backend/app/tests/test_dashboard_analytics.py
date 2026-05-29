from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.db.models import AiTradeReview, FuturesPosition, IndicatorSnapshot
from app.schemas.trading_plan import TradingPlanEvaluation
from app.services.risk_engine import RiskEngine


class FakeDbSession:
    def __init__(self) -> None:
        self.positions: list[FuturesPosition] = []
        self.snapshots: list[IndicatorSnapshot] = []
        self.reviews: list[AiTradeReview] = []


class RiskEngineForTest(RiskEngine):
    def _load_user_positions(self, user_id: UUID) -> list[FuturesPosition]:
        return sorted(
            [
                position
                for position in self.db.positions
                if position.user_id == user_id and position.exchange == "MEXC"
            ],
            key=lambda position: (position.opened_at, position.created_at),
            reverse=True,
        )

    def _load_snapshots_for_positions(self, position_ids: list[UUID]) -> list[IndicatorSnapshot]:
        return [
            snapshot
            for snapshot in self.db.snapshots
            if snapshot.position_id in position_ids
        ]

    def _load_position(self, position_id: UUID) -> FuturesPosition | None:
        for position in self.db.positions:
            if position.id == position_id and position.exchange == "MEXC":
                return position
        return None

    def _load_position_snapshots(self, position_id: UUID) -> list[IndicatorSnapshot]:
        return [
            snapshot
            for snapshot in self.db.snapshots
            if snapshot.position_id == position_id
        ]

    def _load_latest_review(self, position_id: UUID) -> AiTradeReview | None:
        reviews = [
            review for review in self.db.reviews if review.position_id == position_id
        ]
        if not reviews:
            return None
        return sorted(reviews, key=lambda review: review.created_at, reverse=True)[0]


def make_position(
    user_id: UUID,
    symbol: str = "BTC_USDT",
    direction: str = "long",
    status: str = "closed",
    realized_pnl: str = "0",
    total_fees: str = "0",
    funding_fees: str = "0",
    opened_at: datetime | None = None,
) -> FuturesPosition:
    opened_at = opened_at or datetime(2026, 1, 1, tzinfo=UTC)
    return FuturesPosition(
        id=uuid4(),
        user_id=user_id,
        exchange="MEXC",
        symbol=symbol,
        direction=direction,
        opened_at=opened_at,
        closed_at=opened_at + timedelta(hours=1) if status == "closed" else None,
        avg_entry_price=Decimal("100"),
        avg_exit_price=Decimal("110") if status == "closed" else None,
        total_volume=Decimal("1"),
        realized_pnl=Decimal(realized_pnl),
        total_fees=Decimal(total_fees),
        funding_fees=Decimal(funding_fees),
        leverage=None,
        status=status,
        raw_source="mexc_order_deals_v3",
        created_at=opened_at,
    )


def make_snapshot(
    position: FuturesPosition,
    timeframe: str = "Min60",
    rsi_14: str | None = "50",
    supertrend_direction: str | None = "bullish",
    macd: str | None = "1",
    macd_signal: str | None = "0",
) -> IndicatorSnapshot:
    return IndicatorSnapshot(
        id=uuid4(),
        position_id=position.id,
        symbol=position.symbol,
        timeframe=timeframe,
        timestamp=position.opened_at,
        price=Decimal("100"),
        rsi_14=Decimal(rsi_14) if rsi_14 is not None else None,
        stoch_rsi_k=Decimal("60"),
        stoch_rsi_d=Decimal("55"),
        macd=Decimal(macd) if macd is not None else None,
        macd_signal=Decimal(macd_signal) if macd_signal is not None else None,
        macd_histogram=Decimal("1"),
        supertrend_value=Decimal("95") if supertrend_direction else None,
        supertrend_direction=supertrend_direction,
        atr_14=Decimal("3"),
        volume_relative=Decimal("1.2"),
        trend_label="bullish",
    )


def make_review(
    position: FuturesPosition,
    created_at: datetime,
    summary: str,
) -> AiTradeReview:
    return AiTradeReview(
        id=uuid4(),
        user_id=position.user_id,
        position_id=position.id,
        timeframe="multi",
        rule_match_score=80,
        risk_score=60,
        execution_score=70,
        mistake_tags=["late_exit"],
        summary=summary,
        review_json={"summary": summary},
        created_at=created_at,
    )


def make_engine(
    positions: list[FuturesPosition] | None = None,
    snapshots: list[IndicatorSnapshot] | None = None,
    reviews: list[AiTradeReview] | None = None,
) -> RiskEngineForTest:
    db = FakeDbSession()
    db.positions = positions or []
    db.snapshots = snapshots or []
    db.reviews = reviews or []
    return RiskEngineForTest(db=db)


def test_dashboard_no_trades_returns_zero_values():
    dashboard = make_engine().get_dashboard(user_id=uuid4())

    assert dashboard.total_realized_pnl == Decimal("0")
    assert dashboard.total_fees == Decimal("0")
    assert dashboard.net_pnl == Decimal("0")
    assert dashboard.trade_count == 0
    assert dashboard.win_rate == Decimal("0")
    assert dashboard.average_win == Decimal("0")
    assert dashboard.average_loss == Decimal("0")
    assert dashboard.profit_factor is None
    assert dashboard.best_symbols == []
    assert dashboard.worst_symbols == []


def test_dashboard_only_winners():
    user_id = uuid4()
    positions = [
        make_position(user_id, symbol="BTC_USDT", realized_pnl="10", total_fees="1"),
        make_position(user_id, symbol="ETH_USDT", realized_pnl="20", total_fees="1.5"),
    ]

    dashboard = make_engine(positions=positions).get_dashboard(user_id=user_id)

    assert dashboard.trade_count == 2
    assert dashboard.win_rate == Decimal("100")
    assert dashboard.average_win == Decimal("13.75")
    assert dashboard.average_loss == Decimal("0")
    assert dashboard.profit_factor is None
    assert dashboard.best_symbols[0].symbol == "ETH_USDT"


def test_dashboard_only_losers():
    user_id = uuid4()
    positions = [
        make_position(user_id, symbol="BTC_USDT", realized_pnl="-4", total_fees="1"),
        make_position(user_id, symbol="ETH_USDT", realized_pnl="-1", total_fees="1"),
    ]

    dashboard = make_engine(positions=positions).get_dashboard(user_id=user_id)

    assert dashboard.trade_count == 2
    assert dashboard.win_rate == Decimal("0")
    assert dashboard.average_win == Decimal("0")
    assert dashboard.average_loss == Decimal("-3.5")
    assert dashboard.profit_factor == Decimal("0")
    assert dashboard.worst_symbols[0].symbol == "BTC_USDT"


def test_dashboard_mixed_long_short_and_open_positions():
    user_id = uuid4()
    positions = [
        make_position(
            user_id,
            symbol="BTC_USDT",
            direction="long",
            realized_pnl="12",
            total_fees="2",
            funding_fees="-1",
        ),
        make_position(
            user_id,
            symbol="ETH_USDT",
            direction="short",
            realized_pnl="-6",
            total_fees="1",
        ),
        make_position(
            user_id,
            symbol="SOL_USDT",
            direction="long",
            status="open",
            realized_pnl="1",
            total_fees="0.5",
        ),
    ]

    dashboard = make_engine(positions=positions).get_dashboard(user_id=user_id)

    assert dashboard.total_realized_pnl == Decimal("7")
    assert dashboard.total_fees == Decimal("3.5")
    assert dashboard.net_pnl == Decimal("2.5")
    assert dashboard.long_pnl == Decimal("9.5")
    assert dashboard.short_pnl == Decimal("-7")
    assert dashboard.open_positions == 1
    assert dashboard.closed_positions == 2


def test_dashboard_zero_fees_and_decimal_precision():
    user_id = uuid4()
    positions = [
        make_position(
            user_id,
            realized_pnl="0.123456789123456789",
            total_fees="0",
            funding_fees="0.000000000000000001",
        )
    ]

    dashboard = make_engine(positions=positions).get_dashboard(user_id=user_id)

    assert dashboard.total_fees == Decimal("0")
    assert dashboard.net_pnl == Decimal("0.123456789123456790")


def test_dashboard_indicator_alignment_counts():
    user_id = uuid4()
    long_position = make_position(user_id, direction="long")
    short_position = make_position(user_id, direction="short")
    snapshots = [
        make_snapshot(
            long_position,
            timeframe="Min60",
            rsi_14="72",
            supertrend_direction="bullish",
            macd="2",
            macd_signal="1",
        ),
        make_snapshot(
            long_position,
            timeframe="Hour4",
            rsi_14="25",
            supertrend_direction="bearish",
            macd="-1",
            macd_signal="0",
        ),
        make_snapshot(
            short_position,
            timeframe="Day1",
            supertrend_direction="bearish",
            macd="-2",
            macd_signal="-1",
        ),
        make_snapshot(
            short_position,
            timeframe="Hour4",
            rsi_14=None,
            supertrend_direction="bullish",
            macd="1",
            macd_signal="0",
        ),
    ]

    dashboard = make_engine(
        positions=[long_position, short_position],
        snapshots=snapshots,
    ).get_dashboard(user_id=user_id)

    assert dashboard.indicator_summary.rsi_overbought_entries == 1
    assert dashboard.indicator_summary.rsi_oversold_entries == 1
    assert dashboard.indicator_summary.supertrend_aligned_trades == 2
    assert dashboard.indicator_summary.supertrend_against_trades == 2
    assert dashboard.indicator_summary.macd_aligned_trades == 2
    assert dashboard.indicator_summary.macd_against_trades == 2


def test_positions_filter_by_timeframe_and_reject_unsupported_timeframe():
    user_id = uuid4()
    first_position = make_position(user_id, symbol="BTC_USDT")
    second_position = make_position(user_id, symbol="ETH_USDT")
    engine = make_engine(
        positions=[first_position, second_position],
        snapshots=[make_snapshot(first_position, timeframe="Hour4")],
    )

    filtered = engine.list_positions(user_id=user_id, timeframe="Hour4")

    assert [position.symbol for position in filtered] == ["BTC_USDT"]
    with pytest.raises(ValueError, match="Unsupported timeframe"):
        engine.list_positions(user_id=user_id, timeframe="Min15")


def test_position_detail_returns_snapshots_and_latest_review():
    user_id = uuid4()
    position = make_position(user_id)
    older_review = make_review(
        position,
        created_at=position.opened_at + timedelta(minutes=5),
        summary="Older review",
    )
    latest_review = make_review(
        position,
        created_at=position.opened_at + timedelta(minutes=10),
        summary="Latest review",
    )
    engine = make_engine(
        positions=[position],
        snapshots=[
            make_snapshot(position, timeframe="Day1"),
            make_snapshot(position, timeframe="Min60"),
            make_snapshot(position, timeframe="Hour4"),
        ],
        reviews=[older_review, latest_review],
    )

    detail = engine.get_position_detail(position_id=position.id)

    assert detail is not None
    assert [snapshot.timeframe for snapshot in detail.indicator_snapshots] == [
        "Min60",
        "Hour4",
        "Day1",
    ]
    assert detail.ai_review is not None
    assert detail.ai_review.summary == "Latest review"


def test_positions_include_trading_plan_summary(monkeypatch):
    user_id = uuid4()
    position = make_position(user_id)
    evaluation = TradingPlanEvaluation(
        score=50,
        passed_items_count=1,
        failed_items_count=1,
        unknown_items_count=2,
        manual_items_count=0,
        total_scored_items=2,
        items=[],
    )

    monkeypatch.setattr(
        "app.services.trading_plan_service.TradingPlanService.load_active_plan",
        lambda self, user_id: object(),
    )
    monkeypatch.setattr(
        "app.services.trading_plan_service.TradingPlanService.evaluate_position",
        (
            lambda self, plan, position, snapshots, positions_for_daily_count, **kwargs: evaluation
        ),
    )

    listed = make_engine(positions=[position]).list_positions(user_id=user_id)
    detail = make_engine(positions=[position]).get_position_detail(position_id=position.id)

    assert listed[0].plan_score == 50
    assert listed[0].plan_failed_items_count == 1
    assert listed[0].plan_unknown_items_count == 2
    assert detail is not None
    assert detail.plan_evaluation == evaluation
