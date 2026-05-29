from datetime import UTC
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.time import utc_now
from app.db.models import (
    FuturesPosition,
    IndicatorSnapshot,
    PositionTradeMetadata,
    TradingPlan,
    TradingPlanItem,
    User,
)
from app.schemas.trading_plan import (
    NUMERIC_INDICATOR_FIELDS,
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
        trade_metadata: PositionTradeMetadata | None = None,
    ) -> TradingPlanEvaluation:
        if plan is None:
            return self.empty_evaluation()

        available_timeframes = {snapshot.timeframe for snapshot in snapshots}
        snapshot_lookup = {
            (
                snapshot.timeframe,
                getattr(snapshot, "anchor", None) or "entry",
            ): snapshot
            for snapshot in snapshots
        }
        if trade_metadata is None:
            trade_metadata = self._load_trade_metadata(position.id)
        same_day_trade_count = self._same_day_trade_count(
            position=position,
            positions=positions_for_daily_count,
        )
        evaluation_items = [
            self._evaluate_item(
                item=item,
                position=position,
                available_timeframes=available_timeframes,
                snapshot_lookup=snapshot_lookup,
                same_day_trade_count=same_day_trade_count,
                trade_metadata=trade_metadata,
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

    def _load_trade_metadata(self, position_id: UUID) -> PositionTradeMetadata | None:
        if not hasattr(self.db, "scalar"):
            metadata_rows = getattr(self.db, "trade_metadata", [])
            return next(
                (
                    metadata
                    for metadata in metadata_rows
                    if metadata.position_id == position_id
                ),
                None,
            )
        statement = (
            select(PositionTradeMetadata)
            .where(PositionTradeMetadata.position_id == position_id)
            .limit(1)
        )
        return self.db.scalar(statement)

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
        snapshot_lookup: dict[tuple[str, str], IndicatorSnapshot],
        same_day_trade_count: int,
        trade_metadata: PositionTradeMetadata | None,
    ) -> TradingPlanEvaluationItem:
        config = dict(item.config or {})
        status = "unknown"
        message = "This rule could not be evaluated from stored trade data."
        timeframe = None
        anchor = None
        expected = None
        observed = None
        evidence: dict[str, Any] = {}

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
        elif item.rule_type == "indicator_condition":
            result = self._evaluate_indicator_condition(
                config=config,
                position=position,
                snapshot_lookup=snapshot_lookup,
            )
            status, message, timeframe, anchor, expected, observed, evidence = result
        elif item.rule_type == "candlestick_pattern":
            result = self._evaluate_candlestick_pattern(
                config=config,
                position=position,
                snapshot_lookup=snapshot_lookup,
            )
            status, message, timeframe, anchor, expected, observed, evidence = result
        elif item.rule_type == "stop_loss":
            result = self._evaluate_stop_loss(
                config=config,
                position=position,
                trade_metadata=trade_metadata,
            )
            status, message, timeframe, anchor, expected, observed, evidence = result

        return TradingPlanEvaluationItem(
            item_id=item.id,
            sort_order=item.sort_order,
            title=item.title,
            description=item.description,
            category=item.category,
            rule_type=item.rule_type,
            status=status,
            message=message,
            timeframe=timeframe,
            anchor=anchor,
            expected=expected,
            observed=observed,
            evidence=evidence,
        )

    def _evaluate_indicator_condition(
        self,
        config: dict[str, Any],
        position: FuturesPosition,
        snapshot_lookup: dict[tuple[str, str], IndicatorSnapshot],
    ) -> tuple[str, str, str | None, str | None, str | None, str | None, dict[str, Any]]:
        timeframe = str(config.get("timeframe", ""))
        anchor = str(config.get("anchor") or "entry")
        indicator = str(config.get("indicator", ""))
        operator = str(config.get("operator", ""))
        expected_value = config.get("value")
        expected = f"{indicator} {operator} {expected_value}"
        evidence = self._base_rule_evidence(
            config=config,
            position=position,
            timeframe=timeframe,
            anchor=anchor,
            expected=expected,
        )

        if not self._direction_applies(config=config, position=position):
            return (
                "manual",
                f"Rule does not apply to {position.direction} positions.",
                timeframe,
                anchor,
                expected,
                None,
                evidence | {"applies": False},
            )

        snapshot = snapshot_lookup.get((timeframe, anchor))
        if snapshot is None:
            return (
                "unknown",
                f"Missing {timeframe} {anchor} snapshot for indicator rule.",
                timeframe,
                anchor,
                expected,
                None,
                evidence,
            )

        observed_value = getattr(snapshot, indicator, None)
        observed = None if observed_value is None else str(observed_value)
        evidence |= {
            "snapshot_timestamp": snapshot.timestamp.isoformat(),
            "observed": observed,
            "indicator": indicator,
            "operator": operator,
        }
        if observed_value is None:
            return (
                "unknown",
                f"{indicator} was unavailable on the {timeframe} {anchor} snapshot.",
                timeframe,
                anchor,
                expected,
                observed,
                evidence,
            )

        passed = self._compare_rule_value(
            observed_value=observed_value,
            expected_value=expected_value,
            operator=operator,
            numeric=indicator in NUMERIC_INDICATOR_FIELDS,
        )
        status = "passed" if passed else "failed"
        message = (
            f"{timeframe} {anchor} {indicator} observed {observed}; expected {operator} "
            f"{expected_value}."
        )
        return status, message, timeframe, anchor, expected, observed, evidence

    def _evaluate_candlestick_pattern(
        self,
        config: dict[str, Any],
        position: FuturesPosition,
        snapshot_lookup: dict[tuple[str, str], IndicatorSnapshot],
    ) -> tuple[str, str, str | None, str | None, str | None, str | None, dict[str, Any]]:
        timeframe = str(config.get("timeframe", ""))
        anchor = str(config.get("anchor") or "entry")
        patterns = _string_list(config, "patterns")
        match_mode = str(config.get("match_mode") or "any")
        expected = f"{match_mode} of {', '.join(patterns)}"
        evidence = self._base_rule_evidence(
            config=config,
            position=position,
            timeframe=timeframe,
            anchor=anchor,
            expected=expected,
        )

        if not self._direction_applies(config=config, position=position):
            return (
                "manual",
                f"Rule does not apply to {position.direction} positions.",
                timeframe,
                anchor,
                expected,
                None,
                evidence | {"applies": False},
            )

        snapshot = snapshot_lookup.get((timeframe, anchor))
        if snapshot is None:
            return (
                "unknown",
                f"Missing {timeframe} {anchor} snapshot for candlestick rule.",
                timeframe,
                anchor,
                expected,
                None,
                evidence,
            )

        detected_patterns = [
            str(pattern)
            for pattern in (getattr(snapshot, "candlestick_patterns", None) or [])
        ]
        detected_set = set(detected_patterns)
        expected_set = set(patterns)
        passed = (
            bool(expected_set.intersection(detected_set))
            if match_mode == "any"
            else expected_set.issubset(detected_set)
        )
        observed = ", ".join(detected_patterns) if detected_patterns else "none"
        evidence |= {
            "snapshot_timestamp": snapshot.timestamp.isoformat(),
            "detected_patterns": detected_patterns,
            "patterns": patterns,
            "match_mode": match_mode,
            "observed": observed,
        }
        status = "passed" if passed else "failed"
        message = (
            f"{timeframe} {anchor} candlestick patterns observed {observed}; "
            f"expected {expected}."
        )
        return status, message, timeframe, anchor, expected, observed, evidence

    def _evaluate_stop_loss(
        self,
        config: dict[str, Any],
        position: FuturesPosition,
        trade_metadata: PositionTradeMetadata | None,
    ) -> tuple[str, str, str | None, str | None, str | None, str | None, dict[str, Any]]:
        expected = "planned stop-loss recorded with valid direction"
        max_distance = _optional_decimal(config.get("max_distance_percent"))
        if max_distance is not None:
            expected += f" and distance <= {max_distance}%"
        evidence = self._base_rule_evidence(
            config=config,
            position=position,
            timeframe=None,
            anchor="entry",
            expected=expected,
        )

        if not self._direction_applies(config=config, position=position):
            return (
                "manual",
                f"Rule does not apply to {position.direction} positions.",
                None,
                "entry",
                expected,
                None,
                evidence | {"applies": False},
            )

        stop_loss = (
            None
            if trade_metadata is None
            else _optional_decimal(trade_metadata.planned_stop_loss_price)
        )
        if stop_loss is None:
            return (
                "failed",
                "No planned stop-loss price was recorded for this position.",
                None,
                "entry",
                expected,
                None,
                evidence,
            )

        entry = _optional_decimal(position.avg_entry_price)
        observed = str(stop_loss)
        evidence |= {
            "planned_stop_loss_price": observed,
            "avg_entry_price": str(entry) if entry is not None else None,
            "observed": observed,
        }
        if entry is None or entry <= Decimal("0"):
            return (
                "unknown",
                "Average entry price was unavailable for stop-loss validation.",
                None,
                "entry",
                expected,
                observed,
                evidence,
            )

        direction_valid = (
            stop_loss < entry if position.direction == "long" else stop_loss > entry
        )
        if not direction_valid:
            return (
                "failed",
                (
                    f"Planned stop-loss {stop_loss} is invalid for a "
                    f"{position.direction} entry at {entry}."
                ),
                None,
                "entry",
                expected,
                observed,
                evidence,
            )

        distance_percent = (abs(entry - stop_loss) / entry) * Decimal("100")
        evidence["distance_percent"] = str(distance_percent)
        if max_distance is not None and distance_percent > max_distance:
            return (
                "failed",
                f"Stop-loss distance {distance_percent}% exceeds the limit of {max_distance}%.",
                None,
                "entry",
                expected,
                observed,
                evidence,
            )

        return (
            "passed",
            f"Planned stop-loss {stop_loss} is valid for this {position.direction} position.",
            None,
            "entry",
            expected,
            observed,
            evidence,
        )

    def _base_rule_evidence(
        self,
        config: dict[str, Any],
        position: FuturesPosition,
        timeframe: str | None,
        anchor: str | None,
        expected: str | None,
    ) -> dict[str, Any]:
        return {
            "timeframe": timeframe,
            "anchor": anchor,
            "direction_scope": config.get("direction_scope", "all"),
            "position_direction": position.direction,
            "expected": expected,
            "applies": True,
        }

    @staticmethod
    def _direction_applies(config: dict[str, Any], position: FuturesPosition) -> bool:
        direction_scope = str(config.get("direction_scope") or "all")
        return direction_scope == "all" or direction_scope == position.direction

    def _compare_rule_value(
        self,
        observed_value: Any,
        expected_value: Any,
        operator: str,
        numeric: bool,
    ) -> bool:
        if numeric:
            observed = _optional_decimal(observed_value)
            expected = _optional_decimal(expected_value)
            if observed is None or expected is None:
                return False
            return self._compare_decimal(observed=observed, expected=expected, operator=operator)

        observed_text = str(observed_value)
        if operator in {"in", "not_in"}:
            expected_values = _list_value(expected_value)
            result = observed_text in expected_values
        else:
            expected_text = str(expected_value)
            result = observed_text == expected_text

        if operator == "eq":
            return result
        if operator == "neq":
            return not result
        if operator == "in":
            return result
        if operator == "not_in":
            return not result
        return False

    @staticmethod
    def _compare_decimal(observed: Decimal, expected: Decimal, operator: str) -> bool:
        if operator == "lt":
            return observed < expected
        if operator == "lte":
            return observed <= expected
        if operator == "gt":
            return observed > expected
        if operator == "gte":
            return observed >= expected
        if operator == "eq":
            return observed == expected
        if operator == "neq":
            return observed != expected
        return False

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


def _list_value(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


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
