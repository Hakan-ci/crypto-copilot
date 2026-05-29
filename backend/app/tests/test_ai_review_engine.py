import asyncio
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from pydantic import ValidationError

from app.db.models import (
    AiTradeQuestion,
    AiTradeReview,
    FuturesPosition,
    IndicatorSnapshot,
    PositionTradeMetadata,
    RawMexcOrderDeal,
)
from app.schemas.trades import (
    IndicatorObservations,
    TimeframeAlignment,
    TradeReviewOutput,
)
from app.schemas.trading_plan import (
    TradingPlanEvaluation,
    TradingPlanEvaluationItem,
    TradingPlanReviewContext,
    TradingPlanReviewItem,
)
from app.services.ai_review_engine import (
    AiReviewEngine,
    OpenAiNotConfiguredError,
    ReviewContextMissingError,
    TradeReviewError,
    trade_review_output_openai_schema,
)


class FakeDbSession:
    def __init__(self) -> None:
        self.positions: dict[UUID, FuturesPosition] = {}
        self.snapshots: list[IndicatorSnapshot] = []
        self.reviews: list[AiTradeReview] = []
        self.raw_deals: list[RawMexcOrderDeal] = []
        self.trade_metadata: list[PositionTradeMetadata] = []
        self.questions: list[AiTradeQuestion] = []
        self.committed = False

    def get(self, model: type, object_id: UUID) -> FuturesPosition | None:
        _ = model
        return self.positions.get(object_id)

    def add(self, row: Any) -> None:
        if isinstance(row, AiTradeReview):
            self.reviews.append(row)
        elif isinstance(row, AiTradeQuestion):
            self.questions.append(row)

    def commit(self) -> None:
        self.committed = True

    def refresh(self, row: Any) -> None:
        if getattr(row, "id", None) is None:
            row.id = uuid4()


class AiReviewEngineForTest(AiReviewEngine):
    def __init__(
        self,
        db: FakeDbSession,
        openai_api_key: str | None = None,
        llm_responses: list[dict[str, Any] | Exception] | None = None,
        question_responses: list[str] | None = None,
    ) -> None:
        super().__init__(db=db, openai_api_key=openai_api_key, model="gpt-4o-mini")
        self.llm_responses = llm_responses or []
        self.question_responses = question_responses or []
        self.prompt_payloads: list[dict[str, Any]] = []
        self.question_payloads: list[dict[str, Any]] = []

    def _load_required_snapshots(self, position_id: UUID) -> list[IndicatorSnapshot]:
        return [
            snapshot
            for snapshot in self.db.snapshots
            if snapshot.position_id == position_id
        ]

    async def _request_llm_review(
        self,
        review_input,
        strict_retry: bool = False,
    ) -> dict[str, Any]:
        self.prompt_payloads.append(
            self._build_openai_payload(review_input=review_input, strict_retry=strict_retry)
        )
        if not self.llm_responses:
            raise AssertionError("No fake LLM response configured.")
        response = self.llm_responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    async def _request_question_answer(self, question: str, context: dict[str, Any]) -> str:
        self.question_payloads.append({"question": question, "context": context})
        if not self.question_responses:
            raise AssertionError("No fake question response configured.")
        return self.question_responses.pop(0)


def make_position(position_id: UUID) -> FuturesPosition:
    return FuturesPosition(
        id=position_id,
        user_id=uuid4(),
        exchange="MEXC",
        symbol="BTC_USDT",
        direction="long",
        opened_at=datetime.fromtimestamp(1_710_000_000, tz=UTC),
        closed_at=datetime.fromtimestamp(1_710_003_600, tz=UTC),
        avg_entry_price=Decimal("100"),
        avg_exit_price=Decimal("110"),
        total_volume=Decimal("1"),
        realized_pnl=Decimal("10"),
        total_fees=Decimal("0.20"),
        funding_fees=Decimal("0"),
        status="closed",
    )


def make_snapshot(
    position_id: UUID,
    timeframe: str,
    trend_label: str,
    rsi: str = "55",
) -> IndicatorSnapshot:
    return IndicatorSnapshot(
        position_id=position_id,
        symbol="BTC_USDT",
        timeframe=timeframe,
        timestamp=datetime.fromtimestamp(1_710_000_000, tz=UTC),
        price=Decimal("100"),
        rsi_14=Decimal(rsi),
        stoch_rsi_k=Decimal("60"),
        stoch_rsi_d=Decimal("58"),
        macd=Decimal("1.5") if trend_label == "bullish" else Decimal("-1.5"),
        macd_signal=Decimal("1.0") if trend_label == "bullish" else Decimal("-1.0"),
        macd_histogram=Decimal("0.5"),
        supertrend_value=Decimal("95"),
        supertrend_direction=trend_label if trend_label in {"bullish", "bearish"} else "bullish",
        atr_14=Decimal("3.5"),
        volume_relative=Decimal("1.2"),
        trend_label=trend_label,
    )


def make_raw_deal(
    position: FuturesPosition,
    deal_id: str,
    side: int,
    timestamp_ms: int,
) -> RawMexcOrderDeal:
    return RawMexcOrderDeal(
        id=uuid4(),
        user_id=position.user_id,
        mexc_deal_id=deal_id,
        symbol=position.symbol,
        side=side,
        vol=Decimal("1"),
        price=Decimal("100") if side in {1, 3} else Decimal("110"),
        fee=Decimal("0.10"),
        fee_currency="USDT",
        profit=Decimal("0") if side in {1, 3} else Decimal("10"),
        category=None,
        order_id=f"order-{deal_id}",
        timestamp_ms=timestamp_ms,
        position_mode=None,
        taker=None,
        raw_json={"id": deal_id, "timestamp": timestamp_ms},
    )


def make_trade_metadata(position_id: UUID, stop_loss: str = "98") -> PositionTradeMetadata:
    created_at = datetime.fromtimestamp(1_710_000_000, tz=UTC)
    return PositionTradeMetadata(
        id=uuid4(),
        position_id=position_id,
        planned_stop_loss_price=Decimal(stop_loss),
        notes=None,
        created_at=created_at,
        updated_at=created_at,
    )


def make_db(with_all_snapshots: bool = True) -> tuple[FakeDbSession, UUID]:
    position_id = uuid4()
    db = FakeDbSession()
    db.positions[position_id] = make_position(position_id)
    db.snapshots = [
        make_snapshot(position_id, "Min60", "bullish", "72"),
        make_snapshot(position_id, "Hour4", "mixed"),
    ]
    if with_all_snapshots:
        db.snapshots.append(make_snapshot(position_id, "Day1", "bearish"))
    return db, position_id


def valid_review_dict() -> dict[str, Any]:
    return {
        "summary": "Structured educational review for the completed BTC_USDT position.",
        "timeframe_alignment": {
            "one_hour": "bullish",
            "four_hour": "mixed",
            "one_day": "bearish",
            "overall": "mixed",
        },
        "indicator_observations": {
            "rsi": ["RSI was overbought on 1H at entry."],
            "stoch_rsi": ["Stoch RSI showed momentum exhaustion."],
            "macd": ["MACD supported 1H but not all higher timeframes."],
            "supertrend": ["Supertrend was bearish on 1D."],
        },
        "strengths": ["The review had clear 1H context."],
        "weaknesses": ["The 1D context opposed the position direction."],
        "risk_flags": ["RSI was overbought at entry."],
        "mistake_tags": ["against_higher_timeframe_trend"],
        "rule_match_score": 80,
        "risk_score": 65,
        "execution_score": 70,
        "final_note": "Final decision belongs to the user.",
    }


def _assert_strict_openai_schema(schema: dict[str, Any]) -> None:
    def walk(node: Any) -> None:
        if isinstance(node, dict):
            assert "default" not in node
            if node.get("type") == "object":
                properties = node["properties"]
                assert node.get("additionalProperties") is False
                assert sorted(node["required"]) == sorted(properties)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(schema)


def test_openai_review_schema_is_strict_api_compatible():
    schema = trade_review_output_openai_schema()

    _assert_strict_openai_schema(schema)
    rule_result_schema = schema["properties"]["trading_plan_rule_results"]["items"]
    assert rule_result_schema["required"] == ["title", "status", "reason"]
    assert rule_result_schema["properties"]["status"]["enum"] == [
        "followed",
        "not_followed",
    ]


def failed_rule_evaluation() -> TradingPlanEvaluation:
    return TradingPlanEvaluation(
        score=0,
        passed_items_count=0,
        failed_items_count=1,
        unknown_items_count=1,
        manual_items_count=0,
        total_scored_items=1,
        items=[
            TradingPlanEvaluationItem(
                item_id=uuid4(),
                sort_order=0,
                title="RSI entry rule",
                description=None,
                category="Indicator",
                rule_type="indicator_condition",
                status="failed",
                message="Min60 entry rsi_14 observed 46; expected lt 35.",
                timeframe="Min60",
                anchor="entry",
                expected="rsi_14 lt 35",
                observed="46",
                evidence={"indicator": "rsi_14", "operator": "lt"},
            ),
            TradingPlanEvaluationItem(
                item_id=uuid4(),
                sort_order=1,
                title="Stop-loss recorded",
                description=None,
                category="Risk",
                rule_type="stop_loss",
                status="unknown",
                message="Average entry price was unavailable for stop-loss validation.",
                anchor="entry",
                expected="planned stop-loss recorded with valid direction",
                observed="98",
                evidence={"planned_stop_loss_price": "98"},
            ),
        ],
    )


def test_valid_structured_review_saved_with_full_json():
    db, position_id = make_db()
    engine = AiReviewEngineForTest(
        db=db,
        openai_api_key="test-openai-key",
        llm_responses=[valid_review_dict()],
    )

    response = asyncio.run(engine.generate_review(position_id=position_id))

    assert response.review.summary == "No saved trading plan rules were available."
    assert len(db.reviews) == 1
    assert db.reviews[0].summary == response.review.summary
    assert db.reviews[0].review_json["timeframe_alignment"]["overall"] == "rule-only"
    assert db.reviews[0].review_json["trading_plan_rule_results"] == []
    assert db.reviews[0].timeframe == "Hour4"
    assert db.committed is True


def test_forbidden_phrases_are_detected_case_insensitively():
    assert AiReviewEngine.contains_forbidden_phrase("You SHOULD BUY this.")
    assert AiReviewEngine.contains_forbidden_phrase({"summary": "guaranteed profit"})


def test_missing_llm_key_does_not_save_fallback_review():
    db, position_id = make_db()
    engine = AiReviewEngineForTest(db=db, openai_api_key=None)

    with pytest.raises(OpenAiNotConfiguredError):
        asyncio.run(engine.generate_review(position_id=position_id))

    assert db.reviews == []


def test_scores_outside_0_to_100_are_rejected():
    payload = valid_review_dict()
    payload["risk_score"] = 101

    with pytest.raises(ValidationError):
        TradeReviewOutput.model_validate(payload)


def test_review_uses_selected_timeframe_only():
    db, position_id = make_db()
    engine = AiReviewEngineForTest(
        db=db,
        openai_api_key="test-openai-key",
        llm_responses=[valid_review_dict()],
    )

    asyncio.run(engine.generate_review(position_id=position_id, review_timeframe="Hour4"))

    prompt_input = json.loads(engine.prompt_payloads[0]["input"][1]["content"][0]["text"])
    assert prompt_input["review_timeframe"] == "Hour4"
    assert {snapshot["timeframe"] for snapshot in prompt_input["indicator_snapshots"]} == {
        "Hour4"
    }
    assert db.reviews[0].timeframe == "Hour4"


def test_missing_selected_timeframe_snapshot_does_not_save_review():
    db, position_id = make_db()
    db.snapshots = [snapshot for snapshot in db.snapshots if snapshot.timeframe != "Hour4"]
    engine = AiReviewEngineForTest(
        db=db,
        openai_api_key="test-openai-key",
        llm_responses=[valid_review_dict()],
    )

    with pytest.raises(ReviewContextMissingError, match="4H entry snapshot"):
        asyncio.run(engine.generate_review(position_id=position_id, review_timeframe="Hour4"))

    assert db.reviews == []


def test_rule_only_review_suppresses_generic_indicator_observations():
    db, position_id = make_db()
    engine = AiReviewEngineForTest(
        db=db,
        openai_api_key="test-openai-key",
        llm_responses=[valid_review_dict()],
    )

    response = asyncio.run(engine.generate_review(position_id=position_id))
    observations = response.review.indicator_observations

    assert observations.rsi == []
    assert observations.stoch_rsi == []
    assert observations.macd == []
    assert observations.supertrend == []


def test_llm_failure_does_not_save_fallback_review():
    db, position_id = make_db()
    engine = AiReviewEngineForTest(
        db=db,
        openai_api_key="test-openai-key",
        llm_responses=[{}, {}],
    )

    with pytest.raises(TradeReviewError, match="AI returned unreadable review data"):
        asyncio.run(engine.generate_review(position_id=position_id))

    assert db.reviews == []


def test_openai_http_error_returns_actionable_message():
    db, position_id = make_db()
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    response = httpx.Response(
        status_code=400,
        request=request,
        json={"error": {"message": "Invalid schema."}},
    )
    openai_error = httpx.HTTPStatusError(
        "Bad request",
        request=request,
        response=response,
    )
    engine = AiReviewEngineForTest(
        db=db,
        openai_api_key="test-openai-key",
        llm_responses=[openai_error],
    )

    with pytest.raises(TradeReviewError, match="OpenAI rejected the review request"):
        asyncio.run(engine.generate_review(position_id=position_id))

    assert len(engine.prompt_payloads) == 1
    assert db.reviews == []


def test_raw_api_secrets_are_never_included_in_prompt_input():
    db, position_id = make_db()
    engine = AiReviewEngineForTest(
        db=db,
        openai_api_key="test-openai-key",
        llm_responses=[valid_review_dict()],
    )

    asyncio.run(
        engine.generate_review(
            position_id=position_id,
            similar_past_trade_stats={
                "wins": 2,
                "api_key": "MEXC-SECRET-KEY",
                "secret_key": "OPENAI-SECRET",
                "nested": {"credential": "RAW-CREDENTIAL"},
            },
        )
    )

    prompt_text = json.dumps(engine.prompt_payloads)
    assert "MEXC-SECRET-KEY" not in prompt_text
    assert "OPENAI-SECRET" not in prompt_text
    assert "RAW-CREDENTIAL" not in prompt_text


def test_backend_trading_plan_context_is_included_in_prompt(monkeypatch):
    db, position_id = make_db()
    engine = AiReviewEngineForTest(
        db=db,
        openai_api_key="test-openai-key",
        llm_responses=[valid_review_dict()],
    )
    plan_context = TradingPlanReviewContext(
        items=[
            TradingPlanReviewItem(
                title="Only trade major pairs",
                description=None,
                category="Setup",
                rule_type="allowed_symbols",
                enabled=True,
                config={"symbols": ["BTC_USDT"]},
                sort_order=0,
            )
        ]
    )
    plan_evaluation = failed_rule_evaluation()

    def fake_evaluate_position(
        self,
        plan,
        position,
        snapshots,
        positions_for_daily_count,
        trade_metadata=None,
    ):
        _ = (self, plan, position, snapshots, positions_for_daily_count, trade_metadata)
        return plan_evaluation

    monkeypatch.setattr(
        "app.services.trading_plan_service.TradingPlanService.load_active_plan",
        lambda self, user_id: object(),
    )
    monkeypatch.setattr(
        "app.services.trading_plan_service.TradingPlanService.to_review_context",
        lambda self, plan: None,
    )
    monkeypatch.setattr(
        "app.services.trading_plan_service.TradingPlanService.to_review_context",
        lambda self, plan: plan_context,
    )
    monkeypatch.setattr(
        "app.services.trading_plan_service.TradingPlanService.evaluate_position",
        fake_evaluate_position,
    )

    asyncio.run(engine.generate_review(position_id=position_id))

    prompt_text = json.dumps(engine.prompt_payloads)
    assert "Only trade major pairs" in prompt_text
    assert "allowed_symbols" in prompt_text
    assert "rule_evidence" in prompt_text
    assert "RSI entry rule" in prompt_text


def test_ai_review_scores_saved_trading_plan_rules(monkeypatch):
    db, position_id = make_db()
    engine = AiReviewEngineForTest(
        db=db,
        openai_api_key="test-openai-key",
        llm_responses=[
            valid_review_dict()
            | {
                "trading_plan_rule_results": [
                    {
                        "title": "Wait for clear setup",
                        "status": "followed",
                        "reason": "The setup was documented.",
                    },
                    {
                        "title": "Use planned stop",
                        "status": "not_followed",
                        "reason": "No_planned_stop was saved;",
                    },
                ]
            }
        ],
    )
    plan_context = TradingPlanReviewContext(
        items=[
            TradingPlanReviewItem(
                title="Wait for clear setup",
                description="The trade should have a clear setup note.",
                category=None,
                rule_type="manual_check",
                enabled=True,
                config={},
                sort_order=0,
            ),
            TradingPlanReviewItem(
                title="Use planned stop",
                description="Every trade should have a planned stop loss.",
                category=None,
                rule_type="manual_check",
                enabled=True,
                config={},
                sort_order=1,
            ),
        ]
    )
    empty_evaluation = TradingPlanEvaluation(
        score=None,
        passed_items_count=0,
        failed_items_count=0,
        unknown_items_count=0,
        manual_items_count=0,
        total_scored_items=0,
        items=[],
    )

    def fake_evaluate_position(
        self,
        plan,
        position,
        snapshots,
        positions_for_daily_count,
        trade_metadata=None,
    ):
        _ = (self, plan, position, snapshots, positions_for_daily_count, trade_metadata)
        return empty_evaluation

    monkeypatch.setattr(
        "app.services.trading_plan_service.TradingPlanService.load_active_plan",
        lambda self, user_id: object(),
    )
    monkeypatch.setattr(
        "app.services.trading_plan_service.TradingPlanService.to_review_context",
        lambda self, plan: plan_context,
    )
    monkeypatch.setattr(
        "app.services.trading_plan_service.TradingPlanService.evaluate_position",
        fake_evaluate_position,
    )

    response = asyncio.run(engine.generate_review(position_id=position_id))

    prompt_text = json.dumps(engine.prompt_payloads)
    assert "The trade should have a clear setup note." in prompt_text
    assert "Every trade should have a planned stop loss." in prompt_text
    assert response.review.rule_match_score == 50
    assert [result.status for result in response.review.trading_plan_rule_results] == [
        "followed",
        "not_followed",
    ]
    assert response.review.rule_violations == [
        "Use planned stop. No planned stop was saved."
    ]
    assert "_" not in response.review.trading_plan_rule_results[1].reason
    assert ";" not in response.review.trading_plan_rule_results[1].reason


def test_review_prompt_includes_transaction_timeline():
    db, position_id = make_db()
    position = db.positions[position_id]
    db.raw_deals = [
        make_raw_deal(position, "entry-1", side=1, timestamp_ms=1_710_000_000_000),
        make_raw_deal(position, "exit-1", side=4, timestamp_ms=1_710_003_600_000),
    ]
    engine = AiReviewEngineForTest(
        db=db,
        openai_api_key="test-openai-key",
        llm_responses=[valid_review_dict()],
    )

    asyncio.run(engine.generate_review(position_id=position_id))

    prompt_text = json.dumps(engine.prompt_payloads)
    assert "entry-1" in prompt_text
    assert "exit-1" in prompt_text
    assert "transaction_timeline" in prompt_text


def test_review_prompt_includes_stop_loss_metadata():
    db, position_id = make_db()
    db.trade_metadata = [make_trade_metadata(position_id, "98")]
    engine = AiReviewEngineForTest(
        db=db,
        openai_api_key="test-openai-key",
        llm_responses=[valid_review_dict()],
    )

    asyncio.run(engine.generate_review(position_id=position_id))

    prompt_text = json.dumps(engine.prompt_payloads)
    assert "trade_metadata" in prompt_text
    assert "planned_stop_loss_price" in prompt_text
    assert "98" in prompt_text


def test_missing_ai_rule_result_uses_plain_evidence_reason(monkeypatch):
    db, position_id = make_db()
    engine = AiReviewEngineForTest(
        db=db,
        openai_api_key="test-openai-key",
        llm_responses=[valid_review_dict()],
    )
    plan_context = TradingPlanReviewContext(
        items=[
            TradingPlanReviewItem(
                title="RSI Long Entry Plan",
                description="For long entries RSI should be below 35.",
                category=None,
                rule_type="manual_check",
                enabled=True,
                config={},
                sort_order=0,
            )
        ]
    )
    empty_evaluation = TradingPlanEvaluation(
        score=None,
        passed_items_count=0,
        failed_items_count=0,
        unknown_items_count=0,
        manual_items_count=0,
        total_scored_items=0,
        items=[],
    )

    def fake_evaluate_position(
        self,
        plan,
        position,
        snapshots,
        positions_for_daily_count,
        trade_metadata=None,
    ):
        _ = (self, plan, position, snapshots, positions_for_daily_count, trade_metadata)
        return empty_evaluation

    monkeypatch.setattr(
        "app.services.trading_plan_service.TradingPlanService.load_active_plan",
        lambda self, user_id: object(),
    )
    monkeypatch.setattr(
        "app.services.trading_plan_service.TradingPlanService.to_review_context",
        lambda self, plan: plan_context,
    )
    monkeypatch.setattr(
        "app.services.trading_plan_service.TradingPlanService.evaluate_position",
        fake_evaluate_position,
    )

    response = asyncio.run(engine.generate_review(position_id=position_id))

    assert response.review.rule_match_score == 0
    assert response.review.trading_plan_rule_results[0].reason == (
        "Stored evidence did not prove this rule was followed."
    )
    assert "not checked by AI" not in response.review.model_dump_json()


def test_ai_question_answer_is_saved_with_context():
    db, position_id = make_db()
    position = db.positions[position_id]
    db.raw_deals = [make_raw_deal(position, "entry-1", side=1, timestamp_ms=1_710_000_000_000)]
    db.trade_metadata = [make_trade_metadata(position_id, "98")]
    engine = AiReviewEngineForTest(
        db=db,
        openai_api_key="test-openai-key",
        question_responses=["The stored_entry fill; happened at the reviewed transaction time."],
    )

    question = asyncio.run(
        engine.answer_question(position_id=position_id, question="How was the timing?")
    )

    assert question.answer.startswith("The stored entry fill.")
    assert "_" not in question.answer
    assert ";" not in question.answer
    assert len(db.questions) == 1
    assert db.questions[0].context_json["transaction_timeline"]
    assert db.questions[0].context_json["trade_metadata"]["planned_stop_loss_price"] == "98"
    assert engine.list_questions(position_id=position_id)[0].id == question.id


def test_ai_question_requires_openai_key():
    db, position_id = make_db()
    engine = AiReviewEngineForTest(db=db, openai_api_key=None)

    with pytest.raises(Exception, match="OpenAI API key is missing"):
        asyncio.run(engine.answer_question(position_id=position_id, question="What happened?"))


def test_forbidden_llm_output_does_not_save_fallback_review():
    db, position_id = make_db()
    bad_review = valid_review_dict()
    bad_review["summary"] = "You should buy now."
    engine = AiReviewEngineForTest(
        db=db,
        openai_api_key="test-openai-key",
        llm_responses=[bad_review, bad_review],
    )

    with pytest.raises(TradeReviewError, match="AI review failed safety checks"):
        asyncio.run(engine.generate_review(position_id=position_id))

    assert len(engine.prompt_payloads) == 2
    assert db.reviews == []


def test_trade_review_output_schema_helpers_construct():
    output = TradeReviewOutput(
        summary="Educational review.",
        timeframe_alignment=TimeframeAlignment(
            one_hour="bullish",
            four_hour="mixed",
            one_day="bearish",
            overall="mixed",
        ),
        indicator_observations=IndicatorObservations(
            rsi=["RSI neutral."],
            stoch_rsi=["Stoch RSI neutral."],
            macd=["MACD mixed."],
            supertrend=["Supertrend bearish."],
        ),
        strengths=[],
        weaknesses=[],
        risk_flags=[],
        mistake_tags=[],
        rule_match_score=None,
        risk_score=None,
        execution_score=None,
        final_note="Final decision belongs to the user.",
    )

    assert output.timeframe_alignment.overall == "mixed"
