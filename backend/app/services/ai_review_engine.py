import json
import re
from decimal import Decimal
from typing import Any
from uuid import UUID

import httpx
from pydantic import SecretStr, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.db.models import (
    AiTradeQuestion,
    AiTradeReview,
    FuturesPosition,
    IndicatorSnapshot,
    PositionTradeMetadata,
)
from app.schemas.trades import (
    DEFAULT_REVIEW_TIMEFRAME,
    AiTradeQuestionRead,
    IndicatorObservations,
    PositionTradeMetadataRead,
    PositionTransactionRead,
    TimeframeAlignment,
    TradeReviewIndicatorSnapshotInput,
    TradeReviewInput,
    TradeReviewOutput,
    TradeReviewPositionInput,
    TradeReviewResponse,
    TradingPlanRuleResult,
)
from app.services.position_context import PositionContextService
from app.services.trading_plan_service import TradingPlanService

REQUIRED_REVIEW_TIMEFRAMES = ("Min60", "Hour4", "Day1")
TIMEFRAME_OUTPUT_KEYS = {
    "Min60": "one_hour",
    "Hour4": "four_hour",
    "Day1": "one_day",
}
TIMEFRAME_LABELS = {
    "Min60": "1H",
    "Hour4": "4H",
    "Day1": "1D",
}
FORBIDDEN_AI_PHRASES = (
    "buy now",
    "sell now",
    "short now",
    "long now",
    "enter now",
    "guaranteed",
    "guaranteed profit",
    "high probability profit",
    "you should buy",
    "you should sell",
    "you should short",
    "financial advice",
)
SENSITIVE_KEY_FRAGMENTS = (
    "api_key",
    "apikey",
    "secret",
    "credential",
    "password",
    "token",
    "access_key",
    "secret_key",
)


def _strict_object_schema(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def _string_array_schema() -> dict[str, Any]:
    return {"type": "array", "items": {"type": "string"}}


def _nullable_integer_schema() -> dict[str, Any]:
    return {"anyOf": [{"type": "integer"}, {"type": "null"}]}


def trade_review_output_openai_schema() -> dict[str, Any]:
    """Return a strict Responses API schema for TradeReviewOutput."""

    return _strict_object_schema(
        {
            "summary": {"type": "string"},
            "timeframe_alignment": _strict_object_schema(
                {
                    "one_hour": {"type": "string"},
                    "four_hour": {"type": "string"},
                    "one_day": {"type": "string"},
                    "overall": {"type": "string"},
                }
            ),
            "indicator_observations": _strict_object_schema(
                {
                    "rsi": _string_array_schema(),
                    "stoch_rsi": _string_array_schema(),
                    "macd": _string_array_schema(),
                    "supertrend": _string_array_schema(),
                }
            ),
            "strengths": _string_array_schema(),
            "weaknesses": _string_array_schema(),
            "risk_flags": _string_array_schema(),
            "mistake_tags": _string_array_schema(),
            "rule_match_score": _nullable_integer_schema(),
            "risk_score": _nullable_integer_schema(),
            "execution_score": _nullable_integer_schema(),
            "final_note": {"type": "string"},
            "transaction_timeline": _string_array_schema(),
            "entry_analysis": _string_array_schema(),
            "exit_analysis": _string_array_schema(),
            "plan_compliance": _string_array_schema(),
            "execution_notes": _string_array_schema(),
            "missed_context": _string_array_schema(),
            "follow_up_questions": _string_array_schema(),
            "abandoned_rules": _string_array_schema(),
            "rule_violations": _string_array_schema(),
            "trading_plan_rule_results": {
                "type": "array",
                "items": _strict_object_schema(
                    {
                        "title": {"type": "string"},
                        "status": {
                            "type": "string",
                            "enum": ["followed", "not_followed"],
                        },
                        "reason": {"type": "string"},
                    }
                ),
            },
        }
    )


class TradeReviewError(RuntimeError):
    pass


class PositionNotFoundError(ValueError):
    pass


class OpenAiNotConfiguredError(TradeReviewError):
    pass


class ReviewContextMissingError(TradeReviewError):
    pass


class AiReviewEngine:
    """Generates structured educational trade reviews without trading instructions."""

    def __init__(
        self,
        db: Session,
        openai_api_key: SecretStr | str | None = None,
        model: str = "gpt-4o-mini",
        openai_base_url: str = "https://api.openai.com/v1",
    ) -> None:
        self.db = db
        self.openai_api_key = self._secret_to_string(openai_api_key)
        self.model = model
        self.openai_base_url = openai_base_url.rstrip("/")

    async def generate_review(
        self,
        position_id: UUID,
        review_timeframe: str = DEFAULT_REVIEW_TIMEFRAME,
        similar_past_trade_stats: dict[str, Any] | None = None,
    ) -> TradeReviewResponse:
        position = self._get_position(position_id)
        if position is None:
            raise PositionNotFoundError(f"Position not found: {position_id}")

        normalized_timeframe = self._normalize_review_timeframe(review_timeframe)
        review_input = self._build_review_context(
            position=position,
            review_timeframe=normalized_timeframe,
            similar_past_trade_stats=similar_past_trade_stats,
        )
        self._ensure_review_timeframe_snapshot(review_input)
        if not self.openai_api_key:
            raise OpenAiNotConfiguredError("OpenAI API key is missing.")

        review = await self._generate_llm_review_or_fallback(review_input)
        review = self._enforce_rule_only_review(review=review, review_input=review_input)
        if self.contains_forbidden_phrase(review):
            raise TradeReviewError("AI review failed safety checks.")

        review = self._sanitize_review_text(review)
        review_row = self._save_review(
            position=position,
            review=review,
            review_timeframe=normalized_timeframe,
        )
        return TradeReviewResponse(
            position_id=position_id,
            review_id=getattr(review_row, "id", None),
            review=review,
        )

    def list_questions(self, position_id: UUID) -> list[AiTradeQuestionRead]:
        position = self._get_position(position_id)
        if position is None:
            raise PositionNotFoundError(f"Position not found: {position_id}")

        if not hasattr(self.db, "scalars"):
            questions = [
                question
                for question in getattr(self.db, "questions", [])
                if question.position_id == position_id
            ]
            return [
                AiTradeQuestionRead.model_validate(row)
                for row in sorted(
                    questions,
                    key=lambda question: question.created_at,
                    reverse=True,
                )
            ]

        statement = (
            select(AiTradeQuestion)
            .where(AiTradeQuestion.position_id == position_id)
            .order_by(AiTradeQuestion.created_at.desc())
        )
        return [AiTradeQuestionRead.model_validate(row) for row in self.db.scalars(statement).all()]

    async def answer_question(self, position_id: UUID, question: str) -> AiTradeQuestionRead:
        position = self._get_position(position_id)
        if position is None:
            raise PositionNotFoundError(f"Position not found: {position_id}")
        if not self.openai_api_key:
            raise OpenAiNotConfiguredError("OpenAI API key is missing.")

        context = self._build_question_context(position=position)
        answer = await self._request_question_answer(question=question, context=context)
        if self.contains_forbidden_phrase(answer):
            answer = (
                "I cannot provide trading instructions. Based on the stored retrospective "
                "context, review the transaction timing, plan compliance, and documented "
                "risk flags before making your own decision."
            )
        answer = self._plain_text(answer, fallback="I could not create a clear answer.")

        row = AiTradeQuestion(
            user_id=position.user_id,
            position_id=position.id,
            question=question.strip(),
            answer=answer.strip(),
            context_json=context,
            model=self.model,
            created_at=utc_now(),
        )
        self.db.add(row)
        self.db.commit()
        if hasattr(self.db, "refresh"):
            self.db.refresh(row)
        return AiTradeQuestionRead.model_validate(row)

    def _get_position(self, position_id: UUID) -> FuturesPosition | None:
        return self.db.get(FuturesPosition, position_id)

    def _load_required_snapshots(self, position_id: UUID) -> list[IndicatorSnapshot]:
        statement = (
            select(IndicatorSnapshot)
            .where(IndicatorSnapshot.position_id == position_id)
            .where(IndicatorSnapshot.timeframe.in_(REQUIRED_REVIEW_TIMEFRAMES))
        )
        return list(self.db.scalars(statement).all())

    def _load_user_positions(self, user_id: UUID) -> list[FuturesPosition]:
        if not hasattr(self.db, "scalars"):
            positions = getattr(self.db, "positions", [])
            if isinstance(positions, dict):
                return [
                    position
                    for position in positions.values()
                    if getattr(position, "user_id", None) == user_id
                ]
            return [
                position
                for position in positions
                if getattr(position, "user_id", None) == user_id
            ]
        statement = select(FuturesPosition).where(FuturesPosition.user_id == user_id)
        return list(self.db.scalars(statement).all())

    def _save_review(
        self,
        position: FuturesPosition,
        review: TradeReviewOutput,
        review_timeframe: str,
    ) -> AiTradeReview:
        review_row = AiTradeReview(
            user_id=position.user_id,
            position_id=position.id,
            timeframe=review_timeframe,
            rule_match_score=review.rule_match_score,
            risk_score=review.risk_score,
            execution_score=review.execution_score,
            mistake_tags=list(review.mistake_tags),
            summary=review.summary,
            review_json=review.model_dump(mode="json"),
        )
        self.db.add(review_row)
        self.db.commit()
        if hasattr(self.db, "refresh"):
            self.db.refresh(review_row)
        return review_row

    def _build_review_context(
        self,
        position: FuturesPosition,
        review_timeframe: str,
        similar_past_trade_stats: dict[str, Any] | None,
    ) -> TradeReviewInput:
        raw_snapshots = self._load_required_snapshots(position.id)
        snapshots = (
            list(raw_snapshots.values())
            if isinstance(raw_snapshots, dict)
            else list(raw_snapshots)
        )
        review_snapshots = [
            snapshot for snapshot in snapshots if snapshot.timeframe == review_timeframe
        ]
        transaction_timeline, transaction_timeline_source = PositionContextService(
            db=self.db
        ).transaction_timeline(position)
        plan_service = TradingPlanService(db=self.db)
        trading_plan = plan_service.load_active_plan(user_id=position.user_id)
        trade_metadata = self._load_trade_metadata(position_id=position.id)
        plan_evaluation = plan_service.evaluate_position(
            plan=trading_plan,
            position=position,
            snapshots=review_snapshots,
            positions_for_daily_count=self._load_user_positions(position.user_id),
            trade_metadata=trade_metadata,
        )
        return self._build_review_input(
            position=position,
            review_timeframe=review_timeframe,
            snapshots=review_snapshots,
            transaction_timeline=transaction_timeline,
            transaction_timeline_source=transaction_timeline_source,
            trade_metadata=trade_metadata,
            trading_plan=plan_service.to_review_context(trading_plan),
            plan_evaluation=plan_evaluation,
            similar_past_trade_stats=similar_past_trade_stats,
        )

    def _build_review_input(
        self,
        position: FuturesPosition,
        review_timeframe: str,
        snapshots: list[IndicatorSnapshot],
        transaction_timeline: list[PositionTransactionRead],
        transaction_timeline_source: str,
        trade_metadata: PositionTradeMetadata | None,
        trading_plan,
        plan_evaluation,
        similar_past_trade_stats: dict[str, Any] | None,
    ) -> TradeReviewInput:
        return TradeReviewInput(
            review_timeframe=review_timeframe,
            position=TradeReviewPositionInput(
                symbol=position.symbol,
                direction=position.direction,
                opened_at=position.opened_at,
                closed_at=position.closed_at,
                avg_entry_price=position.avg_entry_price,
                avg_exit_price=position.avg_exit_price,
                realized_pnl=position.realized_pnl,
                total_fees=position.total_fees,
                status=position.status,
            ),
            indicator_snapshots=[
                self._snapshot_to_input(snapshot)
                for snapshot in sorted(
                    snapshots,
                    key=lambda snapshot: (
                        getattr(snapshot, "anchor", "entry"),
                        REQUIRED_REVIEW_TIMEFRAMES.index(snapshot.timeframe)
                        if snapshot.timeframe in REQUIRED_REVIEW_TIMEFRAMES
                        else 99,
                    ),
                )
                if snapshot.timeframe == review_timeframe
            ],
            transaction_timeline=transaction_timeline,
            transaction_timeline_source=transaction_timeline_source,
            trade_metadata=(
                PositionTradeMetadataRead.model_validate(trade_metadata)
                if trade_metadata is not None
                else None
            ),
            trading_plan=trading_plan,
            plan_evaluation=plan_evaluation,
            rule_evidence=self._rule_evidence(plan_evaluation),
            user_rules=None,
            similar_past_trade_stats=self._sanitize_payload(similar_past_trade_stats),
        )

    def _snapshot_to_input(
        self,
        snapshot: IndicatorSnapshot,
    ) -> TradeReviewIndicatorSnapshotInput:
        return TradeReviewIndicatorSnapshotInput(
            timeframe=snapshot.timeframe,
            anchor=getattr(snapshot, "anchor", None) or "entry",
            rsi_14=snapshot.rsi_14,
            stoch_rsi_k=snapshot.stoch_rsi_k,
            stoch_rsi_d=snapshot.stoch_rsi_d,
            macd=snapshot.macd,
            macd_signal=snapshot.macd_signal,
            macd_histogram=snapshot.macd_histogram,
            supertrend_value=snapshot.supertrend_value,
            supertrend_direction=snapshot.supertrend_direction,
            atr_14=snapshot.atr_14,
            volume_relative=snapshot.volume_relative,
            trend_label=snapshot.trend_label,
            candlestick_patterns=list(getattr(snapshot, "candlestick_patterns", []) or []),
        )

    def _rule_evidence(self, plan_evaluation) -> list[dict[str, Any]]:
        if plan_evaluation is None:
            return []
        return [
            {
                "title": item.title,
                "rule_type": item.rule_type,
                "status": item.status,
                "message": item.message,
                "timeframe": item.timeframe,
                "anchor": item.anchor,
                "expected": item.expected,
                "observed": item.observed,
                "evidence": item.evidence,
            }
            for item in plan_evaluation.items
            if item.status in {"failed", "unknown"}
        ]

    def _build_question_context(self, position: FuturesPosition) -> dict[str, Any]:
        latest_review = self._load_latest_review(position_id=position.id)
        review_timeframe = self._latest_review_timeframe(latest_review)
        review_input = self._build_review_context(
            position=position,
            review_timeframe=review_timeframe,
            similar_past_trade_stats=None,
        )
        context = review_input.model_dump(mode="json")
        context["latest_review"] = (
            latest_review.review_json if latest_review is not None else None
        )
        context["latest_review_timeframe"] = review_timeframe
        return self._sanitize_payload(context)

    def _load_trade_metadata(self, position_id: UUID) -> PositionTradeMetadata | None:
        if not hasattr(self.db, "scalar"):
            metadata_rows = getattr(self.db, "trade_metadata", [])
            return next(
                (
                    metadata
                    for metadata in metadata_rows
                    if getattr(metadata, "position_id", None) == position_id
                ),
                None,
            )
        statement = (
            select(PositionTradeMetadata)
            .where(PositionTradeMetadata.position_id == position_id)
            .limit(1)
        )
        return self.db.scalar(statement)

    def _load_latest_review(self, position_id: UUID) -> AiTradeReview | None:
        if not hasattr(self.db, "scalar"):
            reviews = [
                review
                for review in getattr(self.db, "reviews", [])
                if review.position_id == position_id
            ]
            return (
                sorted(reviews, key=lambda review: review.created_at, reverse=True)[0]
                if reviews
                else None
            )
        statement = (
            select(AiTradeReview)
            .where(AiTradeReview.position_id == position_id)
            .order_by(AiTradeReview.created_at.desc())
            .limit(1)
        )
        return self.db.scalar(statement)

    async def _generate_llm_review_or_fallback(
        self,
        review_input: TradeReviewInput,
    ) -> TradeReviewOutput:
        last_error: Exception | None = None
        last_failure_message: str | None = None
        for attempt in range(2):
            try:
                raw_review = await self._request_llm_review(
                    review_input=review_input,
                    strict_retry=attempt > 0,
                )
                review = TradeReviewOutput.model_validate(raw_review)
                if self.contains_forbidden_phrase(review):
                    last_failure_message = "AI review failed safety checks."
                    continue
                return review
            except httpx.HTTPStatusError as exc:
                last_error = exc
                last_failure_message = self._llm_generation_failure_message(exc)
                if 400 <= exc.response.status_code < 500:
                    break
            except (httpx.HTTPError, KeyError, TypeError, ValueError, ValidationError) as exc:
                last_error = exc
                last_failure_message = self._llm_generation_failure_message(exc)
                continue

        error = TradeReviewError(
            last_failure_message or "AI review could not be generated."
        )
        if last_error is not None:
            raise error from last_error
        raise error

    @staticmethod
    def _llm_generation_failure_message(exc: Exception) -> str:
        if isinstance(exc, httpx.HTTPStatusError):
            return "OpenAI rejected the review request."
        if isinstance(exc, httpx.HTTPError):
            return "OpenAI review request failed."
        if isinstance(exc, (KeyError, TypeError, ValueError, ValidationError)):
            return "AI returned unreadable review data."
        return "AI review could not be generated."

    async def _request_llm_review(
        self,
        review_input: TradeReviewInput,
        strict_retry: bool = False,
    ) -> dict[str, Any]:
        if not self.openai_api_key:
            raise TradeReviewError("OpenAI API key is missing.")

        payload = self._build_openai_payload(review_input=review_input, strict_retry=strict_retry)
        async with httpx.AsyncClient(base_url=self.openai_base_url, timeout=30.0) as client:
            response = await client.post(
                "/responses",
                headers={
                    "Authorization": f"Bearer {self.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
        return self._extract_structured_output(response.json())

    async def _request_question_answer(self, question: str, context: dict[str, Any]) -> str:
        payload = self._build_question_payload(question=question, context=context)
        async with httpx.AsyncClient(base_url=self.openai_base_url, timeout=30.0) as client:
            response = await client.post(
                "/responses",
                headers={
                    "Authorization": f"Bearer {self.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
        return self._extract_text_output(response.json())

    def _build_openai_payload(
        self,
        review_input: TradeReviewInput,
        strict_retry: bool = False,
    ) -> dict[str, Any]:
        sanitized_input = self._sanitize_payload(review_input.model_dump(mode="json"))
        system_prompt = (
            "You are an educational trade-review assistant for completed MEXC Futures "
            "positions. You are not a signal bot. Ground the review in the stored "
            "transaction timestamps, indicator snapshots, and saved trading plan rules. "
            "The trade timeframe is review_timeframe. The supplied indicator snapshots "
            "are limited to that timeframe. Judge indicator criteria against that "
            "timeframe unless a saved rule explicitly names another timeframe. "
            "Judge only the rules under trading_plan.items. Return one "
            "trading_plan_rule_results item for each saved rule, in the same order. "
            "Use status followed only when the provided context clearly shows the rule "
            "was followed. Use status not_followed when evidence is missing, unclear, "
            "or the rule was broken. Do not create, rename, or skip rules. "
            "Do not add generic strengths, weaknesses, indicator commentary, or candle "
            "analysis unless it directly explains a saved rule result. "
            "Use short plain ASCII sentences. Do not use markdown, bullets, emojis, "
            "underscores, semicolons, or technical field names in user-facing text. "
            "Do not instruct the user to buy, sell, short, long, or enter. "
            "Never claim guarantees. The final decision belongs to the user."
        )
        if strict_retry:
            system_prompt += (
                " The previous draft failed safety checks. Avoid all direct trading "
                "instructions and all forbidden phrases exactly."
            )

        return {
            "model": self.model,
            "input": [
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": system_prompt}],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": json.dumps(sanitized_input, sort_keys=True),
                        }
                    ],
                },
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "trade_review_output",
                    "schema": trade_review_output_openai_schema(),
                    "strict": True,
                }
            },
            "temperature": 0.2,
        }

    def _build_question_payload(self, question: str, context: dict[str, Any]) -> dict[str, Any]:
        return {
            "model": self.model,
            "input": [
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "You answer retrospective questions about completed or "
                                "reconstructed MEXC Futures positions. Use only the provided "
                                "transaction timeline, position data, indicator snapshots, AI "
                                "review, and trading plan. Do not give direct trading "
                                "instructions or financial advice. Keep answers short and easy "
                                "to understand. Use plain ASCII sentences. Do not use markdown, "
                                "bullets, emojis, underscores, semicolons, or technical field "
                                "names."
                            ),
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": json.dumps(
                                {
                                    "question": question,
                                    "context": context,
                                },
                                sort_keys=True,
                            ),
                        }
                    ],
                },
            ],
            "temperature": 0.2,
        }

    def _extract_structured_output(self, payload: dict[str, Any]) -> dict[str, Any]:
        if isinstance(payload.get("output_text"), str):
            return json.loads(payload["output_text"])

        for output_item in payload.get("output", []):
            for content_item in output_item.get("content", []):
                text = content_item.get("text")
                if isinstance(text, str):
                    return json.loads(text)
        raise ValueError("OpenAI response did not include structured text output.")

    def _extract_text_output(self, payload: dict[str, Any]) -> str:
        if isinstance(payload.get("output_text"), str):
            return payload["output_text"]

        fragments: list[str] = []
        for output_item in payload.get("output", []):
            for content_item in output_item.get("content", []):
                text = content_item.get("text")
                if isinstance(text, str):
                    fragments.append(text)
        answer = "\n".join(fragments).strip()
        if answer:
            return answer
        raise ValueError("OpenAI response did not include text output.")

    def _normalize_review_timeframe(self, timeframe: str | None) -> str:
        normalized = timeframe or DEFAULT_REVIEW_TIMEFRAME
        if normalized not in REQUIRED_REVIEW_TIMEFRAMES:
            raise ReviewContextMissingError(f"Unsupported review timeframe: {normalized}")
        return normalized

    def _latest_review_timeframe(self, latest_review: AiTradeReview | None) -> str:
        if latest_review is not None and latest_review.timeframe in REQUIRED_REVIEW_TIMEFRAMES:
            return latest_review.timeframe
        return DEFAULT_REVIEW_TIMEFRAME

    def _ensure_review_timeframe_snapshot(self, review_input: TradeReviewInput) -> None:
        entry_snapshots = self._entry_snapshots_by_timeframe(review_input.indicator_snapshots)
        if review_input.review_timeframe in entry_snapshots:
            return
        label = TIMEFRAME_LABELS.get(review_input.review_timeframe, review_input.review_timeframe)
        raise ReviewContextMissingError(
            f"Prepare the {label} entry snapshot before generating an AI review."
        )

    def _fallback_review(
        self,
        review_input: TradeReviewInput,
        missing_timeframes: list[str],
    ) -> TradeReviewOutput:
        _ = missing_timeframes
        rule_results = self._fallback_rule_results(review_input)
        not_followed_rules = self._not_followed_rule_lines(rule_results)
        score = self._rule_results_score(rule_results)

        return TradeReviewOutput(
            summary=self._rule_summary(score=score, total_rules=len(rule_results)),
            timeframe_alignment=self._empty_timeframe_alignment(),
            indicator_observations=self._empty_indicator_observations(),
            strengths=[],
            weaknesses=not_followed_rules,
            risk_flags=[],
            mistake_tags=[],
            rule_match_score=score,
            risk_score=None,
            execution_score=None,
            final_note="This review is educational and retrospective.",
            transaction_timeline=[],
            entry_analysis=[],
            exit_analysis=[],
            plan_compliance=not_followed_rules,
            execution_notes=[],
            missed_context=[],
            follow_up_questions=[],
            abandoned_rules=not_followed_rules,
            rule_violations=not_followed_rules,
            trading_plan_rule_results=rule_results,
        )

    def _enforce_rule_only_review(
        self,
        review: TradeReviewOutput,
        review_input: TradeReviewInput,
    ) -> TradeReviewOutput:
        rule_results = self._normalize_rule_results(
            raw_results=review.trading_plan_rule_results,
            review_input=review_input,
        )
        not_followed_rules = self._not_followed_rule_lines(rule_results)
        score = self._rule_results_score(rule_results)
        review.timeframe_alignment = self._empty_timeframe_alignment()
        review.indicator_observations = self._empty_indicator_observations()
        review.strengths = []
        review.weaknesses = not_followed_rules
        review.risk_flags = []
        review.mistake_tags = []
        review.rule_match_score = score
        review.risk_score = None
        review.execution_score = None
        review.transaction_timeline = []
        review.entry_analysis = []
        review.exit_analysis = []
        review.plan_compliance = not_followed_rules
        review.execution_notes = []
        review.missed_context = []
        review.follow_up_questions = []
        review.abandoned_rules = not_followed_rules
        review.rule_violations = not_followed_rules
        review.trading_plan_rule_results = rule_results
        review.summary = self._rule_summary(score=score, total_rules=len(rule_results))
        review.final_note = "This review is educational and retrospective."
        return review

    @staticmethod
    def _empty_timeframe_alignment() -> TimeframeAlignment:
        return TimeframeAlignment(
            one_hour="not reviewed",
            four_hour="not reviewed",
            one_day="not reviewed",
            overall="rule-only",
        )

    @staticmethod
    def _empty_indicator_observations() -> IndicatorObservations:
        return IndicatorObservations(rsi=[], stoch_rsi=[], macd=[], supertrend=[])

    @staticmethod
    def _rule_only_mistake_tags(
        failed_rules: list[str],
        unknown_rules: list[str],
    ) -> list[str]:
        tags: list[str] = []
        if failed_rules:
            tags.append("trading_plan_rule_abandoned")
        if unknown_rules:
            tags.append("trading_plan_rule_unknown")
        return tags

    @staticmethod
    def _rule_only_follow_up_questions(abandoned_rules: list[str]) -> list[str]:
        if not abandoned_rules:
            return []
        return ["Which failed or unknown rule needs clearer evidence before the next review?"]

    def _active_plan_rules(self, review_input: TradeReviewInput) -> list[dict[str, Any]]:
        if review_input.trading_plan is not None:
            return [
                {
                    "title": item.title,
                    "description": item.description,
                    "sort_order": item.sort_order,
                    "fallback_reason": None,
                }
                for item in sorted(
                    review_input.trading_plan.items,
                    key=lambda item: item.sort_order,
                )
                if item.enabled
            ]

        evaluation = review_input.plan_evaluation
        if evaluation is None:
            return []
        return [
            {
                "title": item.title,
                "description": item.description,
                "sort_order": item.sort_order,
                "fallback_reason": item.message
                if item.status in {"failed", "unknown"}
                else None,
            }
            for item in sorted(evaluation.items, key=lambda item: item.sort_order)
        ]

    def _fallback_rule_results(
        self,
        review_input: TradeReviewInput,
    ) -> list[TradingPlanRuleResult]:
        return [
            TradingPlanRuleResult(
                title=str(rule["title"]),
                status="not_followed",
                reason=self._plain_text(
                    str(
                        rule.get("fallback_reason")
                        or "Stored evidence did not prove this rule was followed."
                    ),
                    fallback="Stored evidence did not prove this rule was followed.",
                ),
            )
            for rule in self._active_plan_rules(review_input)
        ]

    def _normalize_rule_results(
        self,
        raw_results: list[TradingPlanRuleResult],
        review_input: TradeReviewInput,
    ) -> list[TradingPlanRuleResult]:
        rules = self._active_plan_rules(review_input)
        normalized: list[TradingPlanRuleResult] = []
        for index, rule in enumerate(rules):
            raw_result = raw_results[index] if index < len(raw_results) else None
            status = (
                raw_result.status
                if raw_result is not None and raw_result.status == "followed"
                else "not_followed"
            )
            reason = (
                raw_result.reason
                if raw_result is not None and raw_result.reason.strip()
                else "Stored evidence did not prove this rule was followed."
            )
            normalized.append(
                TradingPlanRuleResult(
                    title=str(rule["title"]),
                    status=status,
                    reason=self._plain_text(
                        reason,
                        fallback="Stored evidence did not prove this rule was followed.",
                    ),
                )
            )
        return normalized

    @staticmethod
    def _rule_results_score(rule_results: list[TradingPlanRuleResult]) -> int | None:
        if not rule_results:
            return None
        followed_count = len(
            [result for result in rule_results if result.status == "followed"]
        )
        return int((followed_count / len(rule_results)) * 100)

    def _not_followed_rule_lines(
        self,
        rule_results: list[TradingPlanRuleResult],
    ) -> list[str]:
        return [
            self._plain_text(
                f"{result.title}. {result.reason}",
                fallback=result.title,
            )
            for result in rule_results
            if result.status == "not_followed"
        ]

    @staticmethod
    def _rule_summary(score: int | None, total_rules: int) -> str:
        if total_rules == 0 or score is None:
            return "No saved trading plan rules were available."
        return f"{score} percent of saved trading plan rules were followed."

    def _fallback_timeframe_alignment(
        self,
        snapshot_by_timeframe: dict[str, TradeReviewIndicatorSnapshotInput],
    ) -> TimeframeAlignment:
        labels = {
            timeframe: snapshot_by_timeframe.get(timeframe).trend_label
            if snapshot_by_timeframe.get(timeframe) is not None
            else "unknown"
            for timeframe in REQUIRED_REVIEW_TIMEFRAMES
        }
        known_labels = [label for label in labels.values() if label in {"bullish", "bearish"}]
        if known_labels and all(label == "bullish" for label in known_labels):
            overall = "bullish"
        elif known_labels and all(label == "bearish" for label in known_labels):
            overall = "bearish"
        elif known_labels:
            overall = "mixed"
        else:
            overall = "unknown"

        return TimeframeAlignment(
            one_hour=labels["Min60"] or "unknown",
            four_hour=labels["Hour4"] or "unknown",
            one_day=labels["Day1"] or "unknown",
            overall=overall,
        )

    def _fallback_indicator_observations(
        self,
        snapshot_by_timeframe: dict[str, TradeReviewIndicatorSnapshotInput],
    ) -> IndicatorObservations:
        rsi: list[str] = []
        stoch_rsi: list[str] = []
        macd: list[str] = []
        supertrend: list[str] = []

        for timeframe in REQUIRED_REVIEW_TIMEFRAMES:
            snapshot = snapshot_by_timeframe.get(timeframe)
            label = TIMEFRAME_LABELS[timeframe]
            if snapshot is None:
                continue

            if snapshot.rsi_14 is not None:
                rsi.append(f"{label} RSI was {self._rsi_label(snapshot.rsi_14)} at entry.")
            if snapshot.stoch_rsi_k is not None and snapshot.stoch_rsi_d is not None:
                stoch_rsi.append(
                    f"{label} Stoch RSI showed K {snapshot.stoch_rsi_k} and "
                    f"D {snapshot.stoch_rsi_d}."
                )
            if snapshot.macd is not None and snapshot.macd_signal is not None:
                macd.append(
                    f"{label} MACD was {self._macd_label(snapshot.macd, snapshot.macd_signal)}."
                )
            if snapshot.supertrend_direction is not None:
                supertrend.append(f"{label} Supertrend was {snapshot.supertrend_direction}.")

        return IndicatorObservations(
            rsi=rsi or ["RSI data was unavailable for the reviewed snapshots."],
            stoch_rsi=stoch_rsi
            or ["Stoch RSI data was unavailable for the reviewed snapshots."],
            macd=macd or ["MACD data was unavailable for the reviewed snapshots."],
            supertrend=supertrend
            or ["Supertrend data was unavailable for the reviewed snapshots."],
        )

    def _indicator_risk_flags(
        self,
        snapshot_by_timeframe: dict[str, TradeReviewIndicatorSnapshotInput],
        position: TradeReviewPositionInput,
    ) -> list[str]:
        flags: list[str] = []
        for timeframe, snapshot in snapshot_by_timeframe.items():
            label = TIMEFRAME_LABELS.get(timeframe, timeframe)
            is_overbought_long = (
                position.direction == "long"
                and snapshot.rsi_14 is not None
                and snapshot.rsi_14 > 70
            )
            is_oversold_short = (
                position.direction == "short"
                and snapshot.rsi_14 is not None
                and snapshot.rsi_14 < 30
            )
            if is_overbought_long:
                flags.append(f"{label} RSI was overbought at entry.")
            if is_oversold_short:
                flags.append(f"{label} RSI was oversold at entry.")
            if snapshot.volume_relative is not None and snapshot.volume_relative > Decimal("2"):
                flags.append(f"{label} volume was elevated relative to its rolling baseline.")
        return flags

    def _fallback_strengths(
        self,
        snapshot_by_timeframe: dict[str, TradeReviewIndicatorSnapshotInput],
        direction: str,
    ) -> list[str]:
        aligned = "bullish" if direction == "long" else "bearish"
        strengths = [
            f"{TIMEFRAME_LABELS[timeframe]} context aligned with the trade direction."
            for timeframe, snapshot in snapshot_by_timeframe.items()
            if snapshot.trend_label == aligned
        ]
        return strengths or ["The review found limited clear multi-timeframe confirmation."]

    def _fallback_weaknesses(
        self,
        snapshot_by_timeframe: dict[str, TradeReviewIndicatorSnapshotInput],
        direction: str,
    ) -> list[str]:
        opposing = "bearish" if direction == "long" else "bullish"
        weaknesses = [
            f"{TIMEFRAME_LABELS[timeframe]} context opposed the trade direction."
            for timeframe, snapshot in snapshot_by_timeframe.items()
            if snapshot.trend_label == opposing
        ]
        return weaknesses or ["No deterministic weakness was identified from stored snapshots."]

    def _fallback_mistake_tags(self, risk_flags: list[str], weaknesses: list[str]) -> list[str]:
        tags: list[str] = []
        if any("Missing" in flag for flag in risk_flags):
            tags.append("missing_timeframe_context")
        if any("opposed" in weakness for weakness in weaknesses):
            tags.append("against_timeframe_context")
        if any("overbought" in flag.lower() or "oversold" in flag.lower() for flag in risk_flags):
            tags.append("momentum_extreme_at_entry")
        return tags

    def _fallback_transaction_timeline(self, review_input: TradeReviewInput) -> list[str]:
        if not review_input.transaction_timeline:
            return ["No stored transaction timeline was available for this position."]
        return [
            (
                f"{transaction.timestamp.isoformat()}: {transaction.side_label} "
                f"{transaction.vol} {review_input.position.symbol} at {transaction.price} "
                f"(fee {transaction.fee}, realized PnL {transaction.profit})."
            )
            for transaction in review_input.transaction_timeline
        ]

    def _fallback_anchor_analysis(
        self,
        snapshots: list[TradeReviewIndicatorSnapshotInput],
        anchor: str,
    ) -> list[str]:
        if not snapshots:
            return [f"No {anchor} indicator snapshots were available."]
        return [
            (
                f"{TIMEFRAME_LABELS.get(snapshot.timeframe, snapshot.timeframe)} {anchor}: "
                f"trend {snapshot.trend_label or 'unknown'}, "
                f"RSI {snapshot.rsi_14 if snapshot.rsi_14 is not None else 'unavailable'}, "
                f"Supertrend {snapshot.supertrend_direction or 'unavailable'}."
            )
            for snapshot in snapshots
        ]

    def _fallback_plan_compliance(self, review_input: TradeReviewInput) -> list[str]:
        evaluation = review_input.plan_evaluation
        if evaluation is None or not evaluation.items:
            return ["No enabled trading plan items were available for this review."]
        return [
            f"{item.title}: {item.status} - {item.message}"
            for item in evaluation.items
            if item.status in {"failed", "unknown"}
        ]

    def _abandoned_rule_lines(self, review_input: TradeReviewInput) -> list[str]:
        evaluation = review_input.plan_evaluation
        if evaluation is None:
            return []
        return [
            f"{item.title}: {item.status} - {item.message}"
            for item in evaluation.items
            if item.status in {"failed", "unknown"}
        ]

    def _fallback_execution_notes(self, review_input: TradeReviewInput) -> list[str]:
        notes = [
            (
                f"Position opened at {review_input.position.opened_at.isoformat()} "
                f"and status is {review_input.position.status}."
            )
        ]
        if review_input.position.closed_at is not None:
            notes.append(f"Position closed at {review_input.position.closed_at.isoformat()}.")
        if review_input.transaction_timeline_source == "inferred":
            notes.append(
                "Transaction timeline was inferred from raw fills and may include overlap."
            )
        elif review_input.transaction_timeline_source == "linked":
            notes.append("Transaction timeline is linked to the reconstructed position.")
        return notes

    def _entry_snapshots_by_timeframe(
        self,
        snapshots: list[TradeReviewIndicatorSnapshotInput],
    ) -> dict[str, TradeReviewIndicatorSnapshotInput]:
        return {
            snapshot.timeframe: snapshot
            for snapshot in snapshots
            if snapshot.anchor == "entry"
        }

    def _rule_match_score(self, review_input: TradeReviewInput) -> int | None:
        if review_input.plan_evaluation is not None:
            return review_input.plan_evaluation.score

        rules = review_input.user_rules
        if rules is None:
            return None
        checks = 0
        matches = 0
        if rules.allowed_symbols:
            checks += 1
            matches += int(review_input.position.symbol in rules.allowed_symbols)
        if rules.allowed_timeframes:
            checks += 1
            snapshot_timeframes = {
                snapshot.timeframe for snapshot in review_input.indicator_snapshots
            }
            matches += int(bool(snapshot_timeframes.intersection(rules.allowed_timeframes)))
        if rules.max_risk_per_trade is not None:
            checks += 1
            matches += 1
        if rules.min_risk_reward is not None:
            checks += 1
            matches += 1
        if rules.max_trades_per_day is not None:
            checks += 1
            matches += 1
        return None if checks == 0 else int((matches / checks) * 100)

    def _rsi_label(self, rsi: Decimal) -> str:
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

    def _sanitize_payload(self, value: Any) -> Any:
        if isinstance(value, dict):
            clean: dict[str, Any] = {}
            for key, item in value.items():
                key_text = str(key).lower()
                if any(fragment in key_text for fragment in SENSITIVE_KEY_FRAGMENTS):
                    continue
                clean[key] = self._sanitize_payload(item)
            return clean
        if isinstance(value, list):
            return [self._sanitize_payload(item) for item in value]
        return value

    def _sanitize_review_text(self, review: TradeReviewOutput) -> TradeReviewOutput:
        review.summary = self._plain_text(review.summary, fallback="Review complete.")
        review.final_note = self._plain_text(
            review.final_note,
            fallback="This review is educational and retrospective.",
        )
        review.strengths = [self._plain_text(item, fallback="") for item in review.strengths]
        review.weaknesses = [self._plain_text(item, fallback="") for item in review.weaknesses]
        review.risk_flags = [self._plain_text(item, fallback="") for item in review.risk_flags]
        review.transaction_timeline = [
            self._plain_text(item, fallback="") for item in review.transaction_timeline
        ]
        review.entry_analysis = [
            self._plain_text(item, fallback="") for item in review.entry_analysis
        ]
        review.exit_analysis = [
            self._plain_text(item, fallback="") for item in review.exit_analysis
        ]
        review.plan_compliance = [
            self._plain_text(item, fallback="") for item in review.plan_compliance
        ]
        review.execution_notes = [
            self._plain_text(item, fallback="") for item in review.execution_notes
        ]
        review.missed_context = [
            self._plain_text(item, fallback="") for item in review.missed_context
        ]
        review.follow_up_questions = [
            self._plain_text(item, fallback="") for item in review.follow_up_questions
        ]
        review.abandoned_rules = [
            self._plain_text(item, fallback="") for item in review.abandoned_rules
        ]
        review.rule_violations = [
            self._plain_text(item, fallback="") for item in review.rule_violations
        ]
        review.trading_plan_rule_results = [
            TradingPlanRuleResult(
                title=result.title,
                status=result.status,
                reason=self._plain_text(
                    result.reason,
                    fallback="Stored evidence did not prove this rule was followed.",
                ),
            )
            for result in review.trading_plan_rule_results
        ]
        return review

    @staticmethod
    def _plain_text(value: str, fallback: str, max_length: int = 220) -> str:
        text = value.encode("ascii", errors="ignore").decode("ascii")
        text = text.replace("_", " ").replace(";", ".")
        replacements = {
            "Min60": "1 hour",
            "Hour4": "4 hour",
            "Day1": "1 day",
            "rsi 14": "RSI",
            " lt ": " less than ",
            " lte ": " less than or equal to ",
            " gt ": " greater than ",
            " gte ": " greater than or equal to ",
            " eq ": " equal to ",
        }
        for source, replacement in replacements.items():
            text = re.sub(re.escape(source), replacement, text, flags=re.IGNORECASE)
        text = re.sub(r"(?m)^\s*[-*#]+\s*", "", text)
        text = re.sub(r"[`*_#>{}\[\]|~^]+", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) > max_length:
            text = text[:max_length].rsplit(" ", 1)[0].rstrip(" .")
            text = f"{text}."
        return text or fallback

    @classmethod
    def contains_forbidden_phrase(cls, value: TradeReviewOutput | dict[str, Any] | str) -> bool:
        if isinstance(value, TradeReviewOutput):
            text = value.model_dump_json()
        elif isinstance(value, str):
            text = value
        else:
            text = json.dumps(value, default=str)
        normalized = text.lower()
        return any(phrase in normalized for phrase in FORBIDDEN_AI_PHRASES)

    def _secret_to_string(self, value: SecretStr | str | None) -> str | None:
        if value is None:
            return None
        if isinstance(value, SecretStr):
            secret = value.get_secret_value()
            return secret or None
        return value or None
