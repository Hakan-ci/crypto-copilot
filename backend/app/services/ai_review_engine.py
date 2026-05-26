import json
from decimal import Decimal
from typing import Any
from uuid import UUID

import httpx
from pydantic import SecretStr, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AiTradeReview, FuturesPosition, IndicatorSnapshot
from app.schemas.trades import (
    IndicatorObservations,
    TimeframeAlignment,
    TradeReviewIndicatorSnapshotInput,
    TradeReviewInput,
    TradeReviewOutput,
    TradeReviewPositionInput,
    TradeReviewResponse,
    UserTradingRules,
)

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


class TradeReviewError(RuntimeError):
    pass


class PositionNotFoundError(ValueError):
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
        user_rules: UserTradingRules | None = None,
        similar_past_trade_stats: dict[str, Any] | None = None,
    ) -> TradeReviewResponse:
        position = self._get_position(position_id)
        if position is None:
            raise PositionNotFoundError(f"Position not found: {position_id}")

        snapshots = self._load_required_snapshots(position_id)
        review_input = self._build_review_input(
            position=position,
            snapshots=snapshots,
            user_rules=user_rules,
            similar_past_trade_stats=similar_past_trade_stats,
        )

        missing_timeframes = [
            timeframe for timeframe in REQUIRED_REVIEW_TIMEFRAMES if timeframe not in snapshots
        ]
        if missing_timeframes or not self.openai_api_key:
            review = self._fallback_review(
                review_input=review_input,
                missing_timeframes=missing_timeframes,
            )
        else:
            review = await self._generate_llm_review_or_fallback(review_input)

        if self.contains_forbidden_phrase(review):
            review = self._fallback_review(
                review_input=review_input,
                missing_timeframes=missing_timeframes,
            )

        review_row = self._save_review(position=position, review=review)
        return TradeReviewResponse(
            position_id=position_id,
            review_id=getattr(review_row, "id", None),
            review=review,
        )

    def _get_position(self, position_id: UUID) -> FuturesPosition | None:
        return self.db.get(FuturesPosition, position_id)

    def _load_required_snapshots(self, position_id: UUID) -> dict[str, IndicatorSnapshot]:
        statement = (
            select(IndicatorSnapshot)
            .where(IndicatorSnapshot.position_id == position_id)
            .where(IndicatorSnapshot.timeframe.in_(REQUIRED_REVIEW_TIMEFRAMES))
        )
        return {snapshot.timeframe: snapshot for snapshot in self.db.scalars(statement).all()}

    def _save_review(self, position: FuturesPosition, review: TradeReviewOutput) -> AiTradeReview:
        review_row = AiTradeReview(
            user_id=position.user_id,
            position_id=position.id,
            timeframe="multi",
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

    def _build_review_input(
        self,
        position: FuturesPosition,
        snapshots: dict[str, IndicatorSnapshot],
        user_rules: UserTradingRules | None,
        similar_past_trade_stats: dict[str, Any] | None,
    ) -> TradeReviewInput:
        return TradeReviewInput(
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
                for timeframe, snapshot in sorted(snapshots.items())
                if timeframe in REQUIRED_REVIEW_TIMEFRAMES
            ],
            user_rules=user_rules,
            similar_past_trade_stats=self._sanitize_payload(similar_past_trade_stats),
        )

    def _snapshot_to_input(
        self,
        snapshot: IndicatorSnapshot,
    ) -> TradeReviewIndicatorSnapshotInput:
        return TradeReviewIndicatorSnapshotInput(
            timeframe=snapshot.timeframe,
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
        )

    async def _generate_llm_review_or_fallback(
        self,
        review_input: TradeReviewInput,
    ) -> TradeReviewOutput:
        for attempt in range(2):
            try:
                raw_review = await self._request_llm_review(
                    review_input=review_input,
                    strict_retry=attempt > 0,
                )
                review = TradeReviewOutput.model_validate(raw_review)
                if not self.contains_forbidden_phrase(review):
                    return review
            except (httpx.HTTPError, KeyError, TypeError, ValueError, ValidationError):
                continue

        return self._fallback_review(review_input=review_input, missing_timeframes=[])

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

    def _build_openai_payload(
        self,
        review_input: TradeReviewInput,
        strict_retry: bool = False,
    ) -> dict[str, Any]:
        sanitized_input = self._sanitize_payload(review_input.model_dump(mode="json"))
        system_prompt = (
            "You are an educational trade-review assistant for completed MEXC Futures "
            "positions. You are not a signal bot. Review only the past trade and user "
            "rules. Do not instruct the user to buy, sell, short, long, or enter. "
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
                    "schema": TradeReviewOutput.model_json_schema(),
                    "strict": True,
                }
            },
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

    def _fallback_review(
        self,
        review_input: TradeReviewInput,
        missing_timeframes: list[str],
    ) -> TradeReviewOutput:
        snapshot_by_timeframe = {
            snapshot.timeframe: snapshot for snapshot in review_input.indicator_snapshots
        }
        timeframe_alignment = self._fallback_timeframe_alignment(snapshot_by_timeframe)
        observations = self._fallback_indicator_observations(snapshot_by_timeframe)
        risk_flags = [
            f"Missing {TIMEFRAME_LABELS[timeframe]} indicator snapshot."
            for timeframe in missing_timeframes
        ]
        risk_flags.extend(self._indicator_risk_flags(snapshot_by_timeframe, review_input.position))
        direction = review_input.position.direction
        strengths = self._fallback_strengths(snapshot_by_timeframe, direction)
        weaknesses = self._fallback_weaknesses(snapshot_by_timeframe, direction)
        mistake_tags = self._fallback_mistake_tags(risk_flags=risk_flags, weaknesses=weaknesses)

        summary = (
            f"Educational review for the completed {review_input.position.direction} "
            f"{review_input.position.symbol} position. The multi-timeframe context was "
            f"{timeframe_alignment.overall}, with realized PnL of "
            f"{review_input.position.realized_pnl} before review interpretation."
        )

        return TradeReviewOutput(
            summary=summary,
            timeframe_alignment=timeframe_alignment,
            indicator_observations=observations,
            strengths=strengths,
            weaknesses=weaknesses,
            risk_flags=risk_flags,
            mistake_tags=mistake_tags,
            rule_match_score=self._rule_match_score(review_input),
            risk_score=max(0, 100 - (len(risk_flags) * 15)),
            execution_score=70 if review_input.position.status == "closed" else 50,
            final_note=(
                "Final decision belongs to the user. "
                "This review is educational and retrospective."
            ),
        )

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

    def _rule_match_score(self, review_input: TradeReviewInput) -> int | None:
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
