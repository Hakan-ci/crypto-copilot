from datetime import UTC
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.time import utc_now
from app.db.models import FuturesPosition, IndicatorSnapshot, TradingPlan, TradingPlanItem, User
from app.schemas.trading_plan import (
    TradingPlanEvaluation,
    TradingPlanEvaluationItem,
    TradingPlanRead,
    TradingPlanReviewContext,
    TradingPlanReviewItem,
    TradingPlanUpsert,
)


class TradingPlanService:
    """Persists itemized trading plans and evaluates positions against active items."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def read_plan(self, user_id: UUID) -> TradingPlanRead:
        self._ensure_user_exists(user_id=user_id)
        plan = self._load_plan(user_id=user_id)
        if plan is None:
            plan = TradingPlan(user_id=user_id)
            self.db.add(plan)
            self.db.commit()
            if hasattr(self.db, "refresh"):
                self.db.refresh(plan)
        return self._to_read(plan)

    def upsert_plan(self, user_id: UUID, payload: TradingPlanUpsert) -> TradingPlanRead:
        self._ensure_user_exists(user_id=user_id)
        plan = self._load_plan(user_id=user_id)
        if plan is None:
            plan = TradingPlan(user_id=user_id)
            self.db.add(plan)
            if hasattr(self.db, "flush"):
                self.db.flush()

        for existing_item in list(plan.items):
            self.db.delete(existing_item)
        plan.items.clear()
        if hasattr(self.db, "flush"):
            self.db.flush()

        ordered_items = sorted(payload.items, key=lambda item: item.sort_order)
        plan.items = [
            TradingPlanItem(
                sort_order=index,
                title=item.title,
                description=item.description,
                category=item.category,
                rule_type=item.rule_type,
                enabled=item.enabled,
                config=item.config,
            )
            for index, item in enumerate(ordered_items)
        ]
        plan.updated_at = utc_now()
        self.db.commit()
        if hasattr(self.db, "refresh"):
            self.db.refresh(plan)
        return self._to_read(plan)

    def load_active_plan(self, user_id: UUID) -> TradingPlan | None:
        return self._load_plan(user_id=user_id)

    def to_review_context(self, plan: TradingPlan | None) -> TradingPlanReviewContext | None:
        if plan is None:
            return None
        enabled_items = [item for item in plan.items if item.enabled]
        if not enabled_items:
            return None
        return TradingPlanReviewContext(
            items=[
                TradingPlanReviewItem(
                    title=item.title,
                    description=item.description,
                    category=item.category,
                    rule_type=item.rule_type,
                    enabled=item.enabled,
                    config=dict(item.config or {}),
                    sort_order=item.sort_order,
                )
                for item in sorted(enabled_items, key=lambda item: item.sort_order)
            ]
        )

    def evaluate_position(
        self,
        plan: TradingPlan | None,
        position: FuturesPosition,
        snapshots: list[IndicatorSnapshot],
        positions_for_daily_count: list[FuturesPosition],
    ) -> TradingPlanEvaluation:
        if plan is None:
            return self.empty_evaluation()

        available_timeframes = {snapshot.timeframe for snapshot in snapshots}
        same_day_trade_count = self._same_day_trade_count(
            position=position,
            positions=positions_for_daily_count,
        )
        evaluation_items = [
            self._evaluate_item(
                item=item,
                position=position,
                available_timeframes=available_timeframes,
                same_day_trade_count=same_day_trade_count,
            )
            for item in sorted(plan.items, key=lambda item: item.sort_order)
            if item.enabled
        ]
        return self._summarize(evaluation_items)

    @staticmethod
    def empty_evaluation() -> TradingPlanEvaluation:
        return TradingPlanEvaluation(
            score=None,
            passed_items_count=0,
            failed_items_count=0,
            unknown_items_count=0,
            manual_items_count=0,
            total_scored_items=0,
            items=[],
        )

    def _load_plan(self, user_id: UUID) -> TradingPlan | None:
        if not hasattr(self.db, "scalars"):
            return None
        statement = (
            select(TradingPlan)
            .options(selectinload(TradingPlan.items))
            .where(TradingPlan.user_id == user_id)
        )
        return self.db.scalars(statement).first()

    def _ensure_user_exists(self, user_id: UUID) -> None:
        if hasattr(self.db, "get") and self.db.get(User, user_id) is None:
            raise TradingPlanUserNotFoundError(f"User not found: {user_id}")

    @staticmethod
    def _to_read(plan: TradingPlan) -> TradingPlanRead:
        plan_read = TradingPlanRead.model_validate(plan)
        plan_read.items = sorted(plan_read.items, key=lambda item: item.sort_order)
        return plan_read

    def _evaluate_item(
        self,
        item: TradingPlanItem,
        position: FuturesPosition,
        available_timeframes: set[str],
        same_day_trade_count: int,
    ) -> TradingPlanEvaluationItem:
        config = dict(item.config or {})
        status = "unknown"
        message = "This rule could not be evaluated from stored trade data."

        if item.rule_type == "manual_check":
            status = "manual"
            message = "Manual checklist item."
        elif item.rule_type == "allowed_symbols":
            symbols = _string_list(config, "symbols", uppercase=True)
            if not symbols:
                message = "No symbols configured."
            elif position.symbol in symbols:
                status = "passed"
                message = f"{position.symbol} is allowed by this plan item."
            else:
                status = "failed"
                message = f"{position.symbol} is not in the allowed symbol list."
        elif item.rule_type == "required_timeframes":
            required_timeframes = _string_list(config, "timeframes")
            if not required_timeframes:
                message = "No required timeframes configured."
            else:
                missing_timeframes = [
                    timeframe
                    for timeframe in required_timeframes
                    if timeframe not in available_timeframes
                ]
                if missing_timeframes:
                    status = "failed"
                    message = f"Missing required snapshot(s): {', '.join(missing_timeframes)}."
                else:
                    status = "passed"
                    message = "All required timeframe snapshots are present."
        elif item.rule_type == "max_trades_per_day":
            limit = _integer_limit(config)
            if limit is None:
                message = "No daily trade limit configured."
            elif same_day_trade_count <= limit:
                status = "passed"
                message = f"{same_day_trade_count} trade(s) opened on this UTC day."
            else:
                status = "failed"
                message = (
                    f"{same_day_trade_count} trade(s) opened on this UTC day, "
                    f"above the limit of {limit}."
                )
        elif item.rule_type == "max_leverage":
            limit = _decimal_limit(config)
            leverage = _optional_decimal(getattr(position, "leverage", None))
            if limit is None:
                message = "No leverage limit configured."
            elif leverage is None:
                message = "Leverage was not available for this position."
            elif leverage <= limit:
                status = "passed"
                message = f"Leverage {leverage} is within the limit of {limit}."
            else:
                status = "failed"
                message = f"Leverage {leverage} is above the limit of {limit}."
        elif item.rule_type == "max_risk_per_trade":
            message = "Stored positions do not include planned risk per trade yet."
        elif item.rule_type == "min_risk_reward":
            message = "Stored positions do not include planned risk/reward yet."

        return TradingPlanEvaluationItem(
            item_id=item.id,
            sort_order=item.sort_order,
            title=item.title,
            description=item.description,
            category=item.category,
            rule_type=item.rule_type,
            status=status,
            message=message,
        )

    @staticmethod
    def _summarize(items: list[TradingPlanEvaluationItem]) -> TradingPlanEvaluation:
        passed_count = len([item for item in items if item.status == "passed"])
        failed_count = len([item for item in items if item.status == "failed"])
        unknown_count = len([item for item in items if item.status == "unknown"])
        manual_count = len([item for item in items if item.status == "manual"])
        total_scored = passed_count + failed_count
        score = None if total_scored == 0 else int((passed_count / total_scored) * 100)
        return TradingPlanEvaluation(
            score=score,
            passed_items_count=passed_count,
            failed_items_count=failed_count,
            unknown_items_count=unknown_count,
            manual_items_count=manual_count,
            total_scored_items=total_scored,
            items=items,
        )

    @staticmethod
    def _same_day_trade_count(
        position: FuturesPosition,
        positions: list[FuturesPosition],
    ) -> int:
        position_date = _utc_date(position.opened_at)
        return len(
            [
                candidate
                for candidate in positions
                if candidate.user_id == position.user_id
                and _utc_date(candidate.opened_at) == position_date
            ]
        )


def _utc_date(value):
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).date()


def _string_list(config: dict[str, Any], key: str, uppercase: bool = False) -> list[str]:
    raw_value = config.get(key)
    if not isinstance(raw_value, list):
        return []
    values = [str(item).strip() for item in raw_value if str(item).strip()]
    if uppercase:
        return [value.upper() for value in values]
    return values


def _integer_limit(config: dict[str, Any]) -> int | None:
    value = _decimal_limit(config)
    if value is None or value != value.to_integral_value():
        return None
    return int(value)


def _decimal_limit(config: dict[str, Any]) -> Decimal | None:
    return _optional_decimal(config.get("limit"))


def _optional_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not decimal_value.is_finite():
        return None
    return decimal_value


class TradingPlanUserNotFoundError(ValueError):
    pass
