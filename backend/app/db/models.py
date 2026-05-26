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
            name="uq_indicator_snapshots_position_timeframe",
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
