import asyncio
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.db.models import AiTradeReview, FuturesPosition, IndicatorSnapshot
from app.schemas.trades import (
    IndicatorObservations,
    TimeframeAlignment,
    TradeReviewOutput,
    UserTradingRules,
)
from app.services.ai_review_engine import FORBIDDEN_AI_PHRASES, AiReviewEngine


class FakeDbSession:
    def __init__(self) -> None:
        self.positions: dict[UUID, FuturesPosition] = {}
        self.snapshots: list[IndicatorSnapshot] = []
        self.reviews: list[AiTradeReview] = []
        self.committed = False

    def get(self, model: type, object_id: UUID) -> FuturesPosition | None:
        _ = model
        return self.positions.get(object_id)

    def add(self, row: Any) -> None:
        if isinstance(row, AiTradeReview):
            self.reviews.append(row)

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
        llm_responses: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(db=db, openai_api_key=openai_api_key, model="gpt-4o-mini")
        self.llm_responses = llm_responses or []
        self.prompt_payloads: list[dict[str, Any]] = []

    def _load_required_snapshots(self, position_id: UUID) -> dict[str, IndicatorSnapshot]:
        return {
            snapshot.timeframe: snapshot
            for snapshot in self.db.snapshots
            if snapshot.position_id == position_id
        }

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
        return self.llm_responses.pop(0)


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


def test_valid_structured_review_saved_with_full_json():
    db, position_id = make_db()
    engine = AiReviewEngineForTest(
        db=db,
        openai_api_key="test-openai-key",
        llm_responses=[valid_review_dict()],
    )

    response = asyncio.run(engine.generate_review(position_id=position_id))

    assert response.review.summary == valid_review_dict()["summary"]
    assert len(db.reviews) == 1
    assert db.reviews[0].summary == response.review.summary
    assert db.reviews[0].review_json["timeframe_alignment"]["one_day"] == "bearish"
    assert db.reviews[0].timeframe == "multi"
    assert db.committed is True


def test_forbidden_phrases_are_detected_case_insensitively():
    assert AiReviewEngine.contains_forbidden_phrase("You SHOULD BUY this.")
    assert AiReviewEngine.contains_forbidden_phrase({"summary": "guaranteed profit"})


def test_missing_llm_key_returns_fallback_review():
    db, position_id = make_db()
    engine = AiReviewEngineForTest(db=db, openai_api_key=None)

    response = asyncio.run(engine.generate_review(position_id=position_id))

    assert response.review.summary
    assert len(db.reviews) == 1
    assert response.review.timeframe_alignment.one_hour == "bullish"
    assert response.review.timeframe_alignment.four_hour == "mixed"
    assert response.review.timeframe_alignment.one_day == "bearish"


def test_scores_outside_0_to_100_are_rejected():
    payload = valid_review_dict()
    payload["risk_score"] = 101

    with pytest.raises(ValidationError):
        TradeReviewOutput.model_validate(payload)


def test_review_includes_all_three_timeframes():
    db, position_id = make_db()
    engine = AiReviewEngineForTest(db=db, openai_api_key=None)

    response = asyncio.run(engine.generate_review(position_id=position_id))

    alignment = response.review.timeframe_alignment
    assert alignment.one_hour
    assert alignment.four_hour
    assert alignment.one_day


def test_review_mentions_all_supported_indicators_when_data_exists():
    db, position_id = make_db()
    engine = AiReviewEngineForTest(db=db, openai_api_key=None)

    response = asyncio.run(engine.generate_review(position_id=position_id))
    observations = response.review.indicator_observations

    assert any("RSI" in item for item in observations.rsi)
    assert any("Stoch RSI" in item for item in observations.stoch_rsi)
    assert any("MACD" in item for item in observations.macd)
    assert any("Supertrend" in item for item in observations.supertrend)


def test_no_direct_trading_instruction_allowed_in_fallback_review():
    db, position_id = make_db()
    engine = AiReviewEngineForTest(db=db, openai_api_key=None)

    response = asyncio.run(engine.generate_review(position_id=position_id))
    review_text = response.review.model_dump_json().lower()

    assert not any(phrase in review_text for phrase in FORBIDDEN_AI_PHRASES)


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
            user_rules=UserTradingRules(notes="follow checklist"),
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


def test_forbidden_llm_output_falls_back_to_safe_review():
    db, position_id = make_db()
    bad_review = valid_review_dict()
    bad_review["summary"] = "You should buy now."
    engine = AiReviewEngineForTest(
        db=db,
        openai_api_key="test-openai-key",
        llm_responses=[bad_review, bad_review],
    )

    response = asyncio.run(engine.generate_review(position_id=position_id))

    assert not AiReviewEngine.contains_forbidden_phrase(response.review)
    assert len(engine.prompt_payloads) == 2


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
