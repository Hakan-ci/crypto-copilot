from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.api.routes import trading_plan as trading_plan_routes
from app.db.models import FuturesPosition, IndicatorSnapshot, TradingPlan, TradingPlanItem
from app.schemas.trading_plan import (
    TradingPlanItemUpsert,
    TradingPlanRead,
    TradingPlanUpsert,
)
from app.services.trading_plan_service import TradingPlanService


def make_position(
    user_id,
    symbol: str = "BTC_USDT",
    opened_at: datetime | None = None,
    leverage: Decimal | None = None,
) -> FuturesPosition:
    opened_at = opened_at or datetime(2026, 1, 1, 8, tzinfo=UTC)
    return FuturesPosition(
        id=uuid4(),
        user_id=user_id,
        exchange="MEXC",
        symbol=symbol,
        direction="long",
        opened_at=opened_at,
        closed_at=opened_at + timedelta(hours=1),
        avg_entry_price=Decimal("100"),
        avg_exit_price=Decimal("110"),
        total_volume=Decimal("1"),
        realized_pnl=Decimal("10"),
        total_fees=Decimal("1"),
        funding_fees=Decimal("0"),
        leverage=leverage,
        status="closed",
    )


def make_snapshot(position: FuturesPosition, timeframe: str) -> IndicatorSnapshot:
    return IndicatorSnapshot(
        id=uuid4(),
        position_id=position.id,
        symbol=position.symbol,
        timeframe=timeframe,
        timestamp=position.opened_at,
        price=Decimal("100"),
    )


def make_plan(user_id) -> TradingPlan:
    plan_id = uuid4()
    now = datetime(2026, 1, 1, tzinfo=UTC)
    return TradingPlan(
        id=plan_id,
        user_id=user_id,
        created_at=now,
        updated_at=now,
        items=[
            TradingPlanItem(
                id=uuid4(),
                trading_plan_id=plan_id,
                sort_order=0,
                title="Major pairs only",
                category="Setup",
                rule_type="allowed_symbols",
                enabled=True,
                config={"symbols": ["BTC_USDT"]},
                created_at=now,
                updated_at=now,
            ),
            TradingPlanItem(
                id=uuid4(),
                trading_plan_id=plan_id,
                sort_order=1,
                title="All review snapshots",
                rule_type="required_timeframes",
                enabled=True,
                config={"timeframes": ["Min60", "Hour4", "Day1"]},
                created_at=now,
                updated_at=now,
            ),
            TradingPlanItem(
                id=uuid4(),
                trading_plan_id=plan_id,
                sort_order=2,
                title="Two trades max",
                rule_type="max_trades_per_day",
                enabled=True,
                config={"limit": 2},
                created_at=now,
                updated_at=now,
            ),
            TradingPlanItem(
                id=uuid4(),
                trading_plan_id=plan_id,
                sort_order=3,
                title="Know the leverage",
                rule_type="max_leverage",
                enabled=True,
                config={"limit": "5"},
                created_at=now,
                updated_at=now,
            ),
            TradingPlanItem(
                id=uuid4(),
                trading_plan_id=plan_id,
                sort_order=4,
                title="Journal reviewed",
                rule_type="manual_check",
                enabled=True,
                config={},
                created_at=now,
                updated_at=now,
            ),
        ],
    )


def test_trading_plan_item_validation_rejects_invalid_inputs():
    with pytest.raises(ValidationError):
        TradingPlanItemUpsert(title=" ", rule_type="manual_check")

    with pytest.raises(ValidationError):
        TradingPlanItemUpsert(title="Bad type", rule_type="not_a_rule")

    with pytest.raises(ValidationError):
        TradingPlanItemUpsert(
            title="Bad timeframe",
            rule_type="required_timeframes",
            config={"timeframes": ["Min15"]},
        )

    with pytest.raises(ValidationError):
        TradingPlanItemUpsert(
            title="Bad limit",
            rule_type="max_trades_per_day",
            config={"limit": -1},
        )


def test_evaluate_position_returns_item_level_statuses():
    user_id = uuid4()
    position = make_position(user_id=user_id)
    same_day_positions = [
        position,
        make_position(user_id=user_id, symbol="ETH_USDT"),
        make_position(user_id=user_id, symbol="SOL_USDT"),
    ]
    service = TradingPlanService(db=SimpleNamespace())

    evaluation = service.evaluate_position(
        plan=make_plan(user_id),
        position=position,
        snapshots=[make_snapshot(position, "Min60"), make_snapshot(position, "Hour4")],
        positions_for_daily_count=same_day_positions,
    )

    assert evaluation.score == 33
    assert evaluation.passed_items_count == 1
    assert evaluation.failed_items_count == 2
    assert evaluation.unknown_items_count == 1
    assert evaluation.manual_items_count == 1
    assert [item.status for item in evaluation.items] == [
        "passed",
        "failed",
        "failed",
        "unknown",
        "manual",
    ]


def test_trading_plan_routes_delegate_get_and_put(monkeypatch):
    user_id = uuid4()
    now = datetime(2026, 1, 1, tzinfo=UTC)
    plan = TradingPlanRead(
        id=uuid4(),
        user_id=user_id,
        items=[],
        created_at=now,
        updated_at=now,
    )
    calls: list[tuple[str, object]] = []

    class FakeTradingPlanService:
        def __init__(self, db):
            calls.append(("init", db))

        def read_plan(self, user_id):
            calls.append(("read", user_id))
            return plan

        def upsert_plan(self, user_id, payload):
            calls.append(("upsert", payload))
            return plan

    monkeypatch.setattr(trading_plan_routes, "TradingPlanService", FakeTradingPlanService)

    assert trading_plan_routes.get_trading_plan(user_id=user_id, db=object()) == plan
    assert (
        trading_plan_routes.put_trading_plan(
            user_id=user_id,
            payload=TradingPlanUpsert(items=[]),
            db=object(),
        )
        == plan
    )
    assert calls[1] == ("read", user_id)
    assert calls[3][0] == "upsert"
