from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import utc_now
from app.db.base import Base

MONEY_NUMERIC = Numeric(38, 18)
PRICE_NUMERIC = Numeric(38, 18)
VOLUME_NUMERIC = Numeric(38, 18)
INDICATOR_NUMERIC = Numeric(38, 18)


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )

    mexc_api_credentials: Mapped[list["MexcApiCredential"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    raw_mexc_order_deals: Mapped[list["RawMexcOrderDeal"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    futures_positions: Mapped[list["FuturesPosition"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    ai_trade_reviews: Mapped[list["AiTradeReview"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    ai_trade_questions: Mapped[list["AiTradeQuestion"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    crypto_baskets: Mapped[list["CryptoBasket"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    trading_plans: Mapped[list["TradingPlan"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class MexcApiCredential(Base):
    __tablename__ = "mexc_api_credentials"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    access_key_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    secret_key_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )

    user: Mapped["User"] = relationship(back_populates="mexc_api_credentials")


class RawMexcOrderDeal(Base):
    __tablename__ = "raw_mexc_order_deals"
    __table_args__ = (
        UniqueConstraint("user_id", "mexc_deal_id", name="uq_raw_mexc_order_deals_user_deal"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    mexc_deal_id: Mapped[str] = mapped_column(String(128), nullable=False)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    side: Mapped[int] = mapped_column(Integer, nullable=False)
    vol: Mapped[Decimal] = mapped_column(VOLUME_NUMERIC, nullable=False)
    price: Mapped[Decimal] = mapped_column(PRICE_NUMERIC, nullable=False)
    fee: Mapped[Decimal] = mapped_column(MONEY_NUMERIC, nullable=False)
    fee_currency: Mapped[str | None] = mapped_column(String(32))
    profit: Mapped[Decimal] = mapped_column(MONEY_NUMERIC, nullable=False)
    category: Mapped[int | None] = mapped_column(Integer)
    order_id: Mapped[str] = mapped_column(String(128), nullable=False)
    timestamp_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    position_mode: Mapped[int | None] = mapped_column(Integer)
    taker: Mapped[bool | None] = mapped_column(Boolean)
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )

    user: Mapped["User"] = relationship(back_populates="raw_mexc_order_deals")
    futures_position_deals: Mapped[list["FuturesPositionDeal"]] = relationship(
        back_populates="raw_deal",
        cascade="all, delete-orphan",
    )


class FuturesPosition(Base):
    __tablename__ = "futures_positions"
    __table_args__ = (
        CheckConstraint("direction in ('long', 'short')", name="direction_allowed"),
        CheckConstraint("status in ('open', 'closed')", name="status_allowed"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    exchange: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="MEXC",
        server_default="MEXC",
    )
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    avg_entry_price: Mapped[Decimal] = mapped_column(PRICE_NUMERIC, nullable=False)
    avg_exit_price: Mapped[Decimal | None] = mapped_column(PRICE_NUMERIC)
    total_volume: Mapped[Decimal] = mapped_column(VOLUME_NUMERIC, nullable=False)
    realized_pnl: Mapped[Decimal] = mapped_column(
        MONEY_NUMERIC,
        nullable=False,
        default=Decimal("0"),
        server_default=text("0"),
    )
    total_fees: Mapped[Decimal] = mapped_column(
        MONEY_NUMERIC,
        nullable=False,
        default=Decimal("0"),
        server_default=text("0"),
    )
    funding_fees: Mapped[Decimal] = mapped_column(
        MONEY_NUMERIC,
        nullable=False,
        default=Decimal("0"),
        server_default=text("0"),
    )
    leverage: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    raw_source: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )

    user: Mapped["User"] = relationship(back_populates="futures_positions")
    indicator_snapshots: Mapped[list["IndicatorSnapshot"]] = relationship(
        back_populates="position",
        cascade="all, delete-orphan",
    )
    ai_trade_reviews: Mapped[list["AiTradeReview"]] = relationship(
        back_populates="position",
        cascade="all, delete-orphan",
    )
    futures_position_deals: Mapped[list["FuturesPositionDeal"]] = relationship(
        back_populates="position",
        cascade="all, delete-orphan",
        order_by="FuturesPositionDeal.sort_order",
    )
    ai_trade_questions: Mapped[list["AiTradeQuestion"]] = relationship(
        back_populates="position",
        cascade="all, delete-orphan",
    )
    trade_metadata: Mapped["PositionTradeMetadata | None"] = relationship(
        back_populates="position",
        cascade="all, delete-orphan",
        uselist=False,
    )


class Candle(Base):
    __tablename__ = "candles"
    __table_args__ = (
        UniqueConstraint(
            "exchange",
            "symbol",
            "timeframe",
            "timestamp_s",
            name="uq_candles_exchange_symbol_timeframe_timestamp",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    exchange: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="MEXC",
        server_default="MEXC",
    )
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(16), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    timestamp_s: Mapped[int] = mapped_column(BigInteger, nullable=False)
    open: Mapped[Decimal] = mapped_column(PRICE_NUMERIC, nullable=False)
    high: Mapped[Decimal] = mapped_column(PRICE_NUMERIC, nullable=False)
    low: Mapped[Decimal] = mapped_column(PRICE_NUMERIC, nullable=False)
    close: Mapped[Decimal] = mapped_column(PRICE_NUMERIC, nullable=False)
    volume: Mapped[Decimal] = mapped_column(VOLUME_NUMERIC, nullable=False)
    raw_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class IndicatorSnapshot(Base):
    __tablename__ = "indicator_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "position_id",
            "timeframe",
            "anchor",
            name="uq_indicator_snapshots_position_timeframe_anchor",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    position_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("futures_positions.id", ondelete="CASCADE"),
        nullable=False,
    )
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(16), nullable=False)
    anchor: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="entry",
        server_default="entry",
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    price: Mapped[Decimal] = mapped_column(PRICE_NUMERIC, nullable=False)
    rsi_14: Mapped[Decimal | None] = mapped_column(INDICATOR_NUMERIC)
    stoch_rsi_k: Mapped[Decimal | None] = mapped_column(INDICATOR_NUMERIC)
    stoch_rsi_d: Mapped[Decimal | None] = mapped_column(INDICATOR_NUMERIC)
    macd: Mapped[Decimal | None] = mapped_column(INDICATOR_NUMERIC)
    macd_signal: Mapped[Decimal | None] = mapped_column(INDICATOR_NUMERIC)
    macd_histogram: Mapped[Decimal | None] = mapped_column(INDICATOR_NUMERIC)
    supertrend_value: Mapped[Decimal | None] = mapped_column(INDICATOR_NUMERIC)
    supertrend_direction: Mapped[str | None] = mapped_column(String(16))
    atr_14: Mapped[Decimal | None] = mapped_column(INDICATOR_NUMERIC)
    volume_relative: Mapped[Decimal | None] = mapped_column(INDICATOR_NUMERIC)
    trend_label: Mapped[str | None] = mapped_column(String(64))
    candlestick_patterns: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )

    position: Mapped["FuturesPosition"] = relationship(back_populates="indicator_snapshots")


class AiTradeReview(Base):
    __tablename__ = "ai_trade_reviews"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    position_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("futures_positions.id", ondelete="CASCADE"),
        nullable=False,
    )
    timeframe: Mapped[str] = mapped_column(String(16), nullable=False)
    rule_match_score: Mapped[int | None] = mapped_column(Integer)
    risk_score: Mapped[int | None] = mapped_column(Integer)
    execution_score: Mapped[int | None] = mapped_column(Integer)
    mistake_tags: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    review_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )

    user: Mapped["User"] = relationship(back_populates="ai_trade_reviews")
    position: Mapped["FuturesPosition"] = relationship(back_populates="ai_trade_reviews")


class FuturesPositionDeal(Base):
    __tablename__ = "futures_position_deals"
    __table_args__ = (
        UniqueConstraint(
            "position_id",
            "raw_mexc_order_deal_id",
            name="uq_futures_position_deals_position_raw_deal",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    position_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("futures_positions.id", ondelete="CASCADE"),
        nullable=False,
    )
    raw_mexc_order_deal_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("raw_mexc_order_deals.id", ondelete="CASCADE"),
        nullable=False,
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )

    position: Mapped["FuturesPosition"] = relationship(back_populates="futures_position_deals")
    raw_deal: Mapped["RawMexcOrderDeal"] = relationship(back_populates="futures_position_deals")


class AiTradeQuestion(Base):
    __tablename__ = "ai_trade_questions"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    position_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("futures_positions.id", ondelete="CASCADE"),
        nullable=False,
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    context_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )

    user: Mapped["User"] = relationship(back_populates="ai_trade_questions")
    position: Mapped["FuturesPosition"] = relationship(back_populates="ai_trade_questions")


class PositionTradeMetadata(Base):
    __tablename__ = "position_trade_metadata"
    __table_args__ = (
        UniqueConstraint("position_id", name="uq_position_trade_metadata_position_id"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    position_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("futures_positions.id", ondelete="CASCADE"),
        nullable=False,
    )
    planned_stop_loss_price: Mapped[Decimal | None] = mapped_column(PRICE_NUMERIC)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
        server_default=func.now(),
    )

    position: Mapped["FuturesPosition"] = relationship(back_populates="trade_metadata")


class CryptoBasket(Base):
    __tablename__ = "crypto_baskets"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_crypto_baskets_user_id"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
        server_default=func.now(),
    )

    user: Mapped["User"] = relationship(back_populates="crypto_baskets")
    items: Mapped[list["CryptoBasketItem"]] = relationship(
        back_populates="basket",
        cascade="all, delete-orphan",
        order_by="CryptoBasketItem.sort_order",
    )
    sync_runs: Mapped[list["CryptoBasketSyncRun"]] = relationship(
        back_populates="basket",
        cascade="all, delete-orphan",
        order_by="CryptoBasketSyncRun.started_at.desc()",
    )


class CryptoBasketItem(Base):
    __tablename__ = "crypto_basket_items"
    __table_args__ = (
        CheckConstraint(
            "sync_status in ('idle', 'running', 'success', 'error')",
            name="crypto_basket_item_sync_status_allowed",
        ),
        UniqueConstraint("basket_id", "symbol", name="uq_crypto_basket_items_basket_symbol"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    basket_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("crypto_baskets.id", ondelete="CASCADE"),
        nullable=False,
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    sync_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="idle",
        server_default="idle",
    )
    last_sync_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_sync_finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_successful_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_sync_start_time_ms: Mapped[int | None] = mapped_column(BigInteger)
    last_sync_end_time_ms: Mapped[int | None] = mapped_column(BigInteger)
    last_imported: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    last_skipped_duplicates: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    last_positions_created: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    last_open_positions: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    last_closed_positions: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    last_warnings: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
        server_default=func.now(),
    )

    basket: Mapped["CryptoBasket"] = relationship(back_populates="items")
    sync_runs: Mapped[list["CryptoBasketSyncRun"]] = relationship(
        back_populates="item",
        cascade="all, delete-orphan",
        order_by="CryptoBasketSyncRun.started_at.desc()",
    )


class CryptoBasketSyncRun(Base):
    __tablename__ = "crypto_basket_sync_runs"
    __table_args__ = (
        CheckConstraint(
            "run_type in ('manual', 'automatic')",
            name="crypto_basket_sync_run_type_allowed",
        ),
        CheckConstraint(
            "status in ('running', 'success', 'error', 'skipped')",
            name="crypto_basket_sync_run_status_allowed",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    basket_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("crypto_baskets.id", ondelete="CASCADE"),
        nullable=False,
    )
    basket_item_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("crypto_basket_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    run_type: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    start_time_ms: Mapped[int | None] = mapped_column(BigInteger)
    end_time_ms: Mapped[int | None] = mapped_column(BigInteger)
    imported: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    skipped_duplicates: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    positions_created: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    open_positions: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    closed_positions: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    warnings: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    error: Mapped[str | None] = mapped_column(Text)

    basket: Mapped["CryptoBasket"] = relationship(back_populates="sync_runs")
    item: Mapped["CryptoBasketItem"] = relationship(back_populates="sync_runs")


class TradingPlan(Base):
    __tablename__ = "trading_plans"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_trading_plans_user_id"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
        server_default=func.now(),
    )

    user: Mapped["User"] = relationship(back_populates="trading_plans")
    items: Mapped[list["TradingPlanItem"]] = relationship(
        back_populates="plan",
        cascade="all, delete-orphan",
        order_by="TradingPlanItem.sort_order",
    )


class TradingPlanItem(Base):
    __tablename__ = "trading_plan_items"
    __table_args__ = (
        UniqueConstraint(
            "trading_plan_id",
            "sort_order",
            name="uq_trading_plan_items_plan_sort_order",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    trading_plan_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("trading_plans.id", ondelete="CASCADE"),
        nullable=False,
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(80))
    rule_type: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
        server_default=func.now(),
    )

    plan: Mapped["TradingPlan"] = relationship(back_populates="items")
