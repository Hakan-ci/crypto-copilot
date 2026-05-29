import hashlib
import hmac
import time as time_module
from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any

import httpx

from app.core.constants import (
    MEXC_SIDE_CLOSE_LONG,
    MEXC_SIDE_CLOSE_SHORT,
    MEXC_SIDE_OPEN_LONG,
    MEXC_SIDE_OPEN_SHORT,
    SUPPORTED_TIMEFRAMES,
)
from app.schemas.mexc import CandleDTO, MexcOrderDealDTO, MexcStopOrderDTO

MEXC_SIDE_LABELS = {
    MEXC_SIDE_OPEN_LONG: "open_long",
    MEXC_SIDE_CLOSE_SHORT: "close_short",
    MEXC_SIDE_OPEN_SHORT: "open_short",
    MEXC_SIDE_CLOSE_LONG: "close_long",
}

KLINE_PATH_TEMPLATE = "/api/v1/contract/kline/{symbol}"
ORDER_DEALS_PATH = "/api/v1/private/order/list/order_deals/v3"
STOP_ORDERS_PATH = "/api/v1/private/stoporder/list/orders"
PING_PATH = "/api/v1/contract/ping"
MAX_ORDER_DEALS_PAGE_SIZE = 1000
MAX_STOP_ORDERS_PAGE_SIZE = 100


class MexcApiError(RuntimeError):
    """Raised when MEXC returns an unusable response or private auth is missing."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class MexcFuturesClient:
    """Read-only async client for MEXC Futures history and candle endpoints."""

    def __init__(
        self,
        access_key: str | None,
        secret_key: str | None,
        base_url: str = "https://contract.mexc.com",
        recv_window_ms: int = 10000,
    ) -> None:
        self.access_key = access_key
        self.secret_key = secret_key
        self.base_url = base_url.rstrip("/")
        self.recv_window_ms = recv_window_ms

    def _timestamp_ms(self) -> str:
        return str(int(time_module.time() * 1000))

    def _build_query_string(self, params: dict[str, Any]) -> str:
        filtered_params = self._without_none(params)
        return "&".join(f"{key}={filtered_params[key]}" for key in sorted(filtered_params))

    def _sign(self, timestamp: str, params: dict[str, Any] | None) -> str:
        if not self.access_key or not self.secret_key:
            raise MexcApiError("Private MEXC requests require encrypted API credentials.")

        parameter_string = self._build_query_string(params or {})
        target = f"{self.access_key}{timestamp}{parameter_string}"
        return hmac.new(
            self.secret_key.encode("utf-8"),
            target.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def _private_headers(self, signature: str, timestamp: str) -> dict[str, str]:
        if not self.access_key:
            raise MexcApiError("Private MEXC requests require an access key.")

        return {
            "ApiKey": self.access_key,
            "Request-Time": timestamp,
            "Signature": signature,
            "Recv-Window": str(self.recv_window_ms),
            "Language": "English",
        }

    async def _get_public(self, path: str, params: dict[str, Any] | None) -> Any:
        return await self._get(path=path, params=params, headers=None)

    async def _get_private(self, path: str, params: dict[str, Any] | None) -> Any:
        clean_params = self._without_none(params or {})
        timestamp = self._timestamp_ms()
        signature = self._sign(timestamp, clean_params)
        headers = self._private_headers(signature, timestamp)
        return await self._get(path=path, params=clean_params, headers=headers)

    async def ping(self) -> int | None:
        payload = await self._get_public(PING_PATH, params=None)
        data = self._extract_data(payload)
        return int(data) if data is not None else None

    async def get_klines(
        self,
        symbol: str,
        interval: str,
        start_s: int | None = None,
        end_s: int | None = None,
    ) -> list[CandleDTO]:
        self._validate_interval(interval)
        params = {
            "interval": interval,
            "start": start_s,
            "end": end_s,
        }
        payload = await self._get_public(KLINE_PATH_TEMPLATE.format(symbol=symbol), params)
        data = self._extract_data(payload)
        return self._parse_klines(symbol=symbol, interval=interval, data=data)

    async def get_order_deals(
        self,
        symbol: str,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
        page_num: int = 1,
        page_size: int = MAX_ORDER_DEALS_PAGE_SIZE,
    ) -> list[MexcOrderDealDTO]:
        self._validate_order_deals_pagination(page_num=page_num, page_size=page_size)
        params = {
            "symbol": symbol,
            "start_time": start_time_ms,
            "end_time": end_time_ms,
            "page_num": page_num,
            "page_size": page_size,
        }
        payload = await self._get_private(ORDER_DEALS_PATH, params)
        items = self._extract_order_deals(payload)
        return [self._parse_order_deal(item) for item in items]

    async def iter_order_deals(
        self,
        symbol: str,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
    ) -> AsyncIterator[MexcOrderDealDTO]:
        page_num = 1
        while True:
            deals = await self.get_order_deals(
                symbol=symbol,
                start_time_ms=start_time_ms,
                end_time_ms=end_time_ms,
                page_num=page_num,
                page_size=MAX_ORDER_DEALS_PAGE_SIZE,
            )
            if not deals:
                return

            for deal in deals:
                yield deal

            if len(deals) < MAX_ORDER_DEALS_PAGE_SIZE:
                return
            page_num += 1

    async def get_stop_orders(
        self,
        symbol: str,
        is_finished: int | None = None,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
        page_num: int = 1,
        page_size: int = MAX_STOP_ORDERS_PAGE_SIZE,
    ) -> list[MexcStopOrderDTO]:
        self._validate_stop_orders_pagination(page_num=page_num, page_size=page_size)
        params = {
            "symbol": symbol,
            "is_finished": is_finished,
            "start_time": start_time_ms,
            "end_time": end_time_ms,
            "page_num": page_num,
            "page_size": page_size,
        }
        payload = await self._get_private(STOP_ORDERS_PATH, params)
        items = self._extract_stop_orders(payload)
        return [self._parse_stop_order(item) for item in items]

    async def iter_stop_orders(
        self,
        symbol: str,
        is_finished: int | None = None,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
    ) -> AsyncIterator[MexcStopOrderDTO]:
        page_num = 1
        while True:
            orders = await self.get_stop_orders(
                symbol=symbol,
                is_finished=is_finished,
                start_time_ms=start_time_ms,
                end_time_ms=end_time_ms,
                page_num=page_num,
                page_size=MAX_STOP_ORDERS_PAGE_SIZE,
            )
            if not orders:
                return

            for order in orders:
                yield order

            if len(orders) < MAX_STOP_ORDERS_PAGE_SIZE:
                return
            page_num += 1

    async def _get(
        self,
        path: str,
        params: dict[str, Any] | None,
        headers: dict[str, str] | None,
    ) -> Any:
        clean_params = self._without_none(params or {})
        async with httpx.AsyncClient(base_url=self.base_url, timeout=20.0) as client:
            try:
                response = await client.get(path, params=clean_params, headers=headers)
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise MexcApiError(
                    "MEXC Futures API GET request failed.",
                    status_code=exc.response.status_code,
                ) from exc
            except httpx.HTTPError as exc:
                raise MexcApiError("MEXC Futures API GET request failed.") from exc

        payload = response.json()
        self._raise_for_mexc_error(payload)
        return payload

    def _parse_klines(self, symbol: str, interval: str, data: Any) -> list[CandleDTO]:
        if isinstance(data, list):
            return [
                self._parse_kline_row(symbol=symbol, interval=interval, row=row) for row in data
            ]

        if isinstance(data, dict):
            if "resultList" in data and isinstance(data["resultList"], list):
                return [
                    self._parse_kline_row(symbol=symbol, interval=interval, row=row)
                    for row in data["resultList"]
                ]
            return self._parse_kline_columnar_data(symbol=symbol, interval=interval, data=data)

        raise MexcApiError("MEXC kline response data has an unsupported shape.")

    def _parse_kline_row(self, symbol: str, interval: str, row: Any) -> CandleDTO:
        if isinstance(row, dict):
            timestamp_s = self._timestamp_to_seconds(
                self._required(row, "timestamp_s", "timestamp", "time")
            )
            return CandleDTO(
                symbol=symbol,
                interval=interval,
                timestamp_s=timestamp_s,
                open=self._decimal(self._required(row, "open", "o")),
                high=self._decimal(self._required(row, "high", "h")),
                low=self._decimal(self._required(row, "low", "l")),
                close=self._decimal(self._required(row, "close", "c")),
                volume=self._decimal(self._required(row, "volume", "vol", "v")),
            )

        if isinstance(row, (list, tuple)) and len(row) >= 6:
            timestamp_s, open_, high, low, close, volume = row[:6]
            return CandleDTO(
                symbol=symbol,
                interval=interval,
                timestamp_s=self._timestamp_to_seconds(timestamp_s),
                open=self._decimal(open_),
                high=self._decimal(high),
                low=self._decimal(low),
                close=self._decimal(close),
                volume=self._decimal(volume),
            )

        raise MexcApiError("MEXC kline row has an unsupported shape.")

    def _parse_kline_columnar_data(
        self,
        symbol: str,
        interval: str,
        data: dict[str, Any],
    ) -> list[CandleDTO]:
        timestamps = self._required(data, "time", "timestamp", "timestamp_s")
        opens = self._required(data, "open")
        highs = self._required(data, "high")
        lows = self._required(data, "low")
        closes = self._required(data, "close")
        volumes = self._required(data, "volume", "vol")

        columnar_values = [timestamps, opens, highs, lows, closes, volumes]
        if not all(isinstance(values, list) for values in columnar_values):
            raise MexcApiError("MEXC kline columnar response fields must be lists.")

        lengths = {len(values) for values in columnar_values}
        if len(lengths) != 1:
            raise MexcApiError("MEXC kline columnar response fields have mismatched lengths.")

        candles: list[CandleDTO] = []
        for index, timestamp_s in enumerate(timestamps):
            candles.append(
                CandleDTO(
                    symbol=symbol,
                    interval=interval,
                    timestamp_s=self._timestamp_to_seconds(timestamp_s),
                    open=self._decimal(opens[index]),
                    high=self._decimal(highs[index]),
                    low=self._decimal(lows[index]),
                    close=self._decimal(closes[index]),
                    volume=self._decimal(volumes[index]),
                )
            )
        return candles

    def _parse_order_deal(self, item: Any) -> MexcOrderDealDTO:
        if not isinstance(item, dict):
            raise MexcApiError("MEXC order deal item must be an object.")

        side = int(self._required(item, "side"))
        return MexcOrderDealDTO(
            mexc_deal_id=str(self._required(item, "mexc_deal_id", "dealId", "deal_id", "id")),
            symbol=str(self._required(item, "symbol")),
            side=side,
            vol=self._decimal(self._required(item, "vol", "volume")),
            price=self._decimal(self._required(item, "price")),
            fee=self._decimal(self._required(item, "fee")),
            fee_currency=self._optional(item, "fee_currency", "feeCurrency"),
            profit=self._decimal(self._required(item, "profit")),
            category=self._optional_int(item, "category"),
            order_id=str(self._required(item, "order_id", "orderId")),
            timestamp_ms=int(self._required(item, "timestamp_ms", "timestamp", "createTime")),
            position_mode=self._optional_int(item, "position_mode", "positionMode"),
            taker=self._optional_bool(item, "taker", "isTaker"),
            raw_json=dict(item),
        )

    def _parse_stop_order(self, item: Any) -> MexcStopOrderDTO:
        if not isinstance(item, dict):
            raise MexcApiError("MEXC stop order item must be an object.")

        return MexcStopOrderDTO(
            stop_order_id=str(self._required(item, "stop_order_id", "stopPlanOrderId", "id")),
            symbol=str(self._required(item, "symbol")),
            order_id=self._optional(item, "order_id", "orderId"),
            position_id=self._optional(item, "position_id", "positionId"),
            stop_loss_price=self._optional_decimal(item, "stop_loss_price", "stopLossPrice"),
            take_profit_price=self._optional_decimal(
                item,
                "take_profit_price",
                "takeProfitPrice",
            ),
            state=self._optional_int(item, "state"),
            trigger_side=self._optional_int(item, "trigger_side", "triggerSide"),
            position_type=self._optional_int(item, "position_type", "positionType"),
            vol=self._optional_decimal(item, "vol"),
            reality_vol=self._optional_decimal(item, "reality_vol", "realityVol"),
            place_order_id=self._optional(item, "place_order_id", "placeOrderId"),
            is_finished=self._optional_int(item, "is_finished", "isFinished"),
            create_time_ms=self._optional_timestamp_ms(item, "create_time_ms", "createTime"),
            update_time_ms=self._optional_timestamp_ms(item, "update_time_ms", "updateTime"),
            raw_json=dict(item),
        )

    def _extract_data(self, payload: Any) -> Any:
        if isinstance(payload, dict) and "data" in payload:
            return payload["data"]
        raise MexcApiError("MEXC response is missing data.")

    def _extract_order_deals(self, payload: Any) -> list[dict[str, Any]]:
        data = self._extract_data(payload)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            result_list = data.get("resultList")
            if isinstance(result_list, list):
                return result_list
        raise MexcApiError("MEXC order deals response is missing data.resultList.")

    def _extract_stop_orders(self, payload: Any) -> list[dict[str, Any]]:
        data = self._extract_data(payload)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            result_list = data.get("resultList")
            if isinstance(result_list, list):
                return result_list
        raise MexcApiError("MEXC stop orders response is missing data.")

    def _raise_for_mexc_error(self, payload: Any) -> None:
        if not isinstance(payload, dict):
            return

        success = payload.get("success")
        code = payload.get("code")
        if success is False or code not in (None, 0, "0", 200, "200"):
            message = payload.get("message") or payload.get("msg") or "MEXC API returned an error."
            raise MexcApiError(str(message))

    def _validate_interval(self, interval: str) -> None:
        if interval not in SUPPORTED_TIMEFRAMES:
            raise ValueError(f"Unsupported MEXC interval: {interval}")

    def _validate_order_deals_pagination(self, page_num: int, page_size: int) -> None:
        if page_num < 1:
            raise ValueError("page_num must be greater than or equal to 1.")
        if page_size < 1 or page_size > MAX_ORDER_DEALS_PAGE_SIZE:
            raise ValueError("page_size must be between 1 and 1000.")

    def _validate_stop_orders_pagination(self, page_num: int, page_size: int) -> None:
        if page_num < 1:
            raise ValueError("page_num must be greater than or equal to 1.")
        if page_size < 1 or page_size > MAX_STOP_ORDERS_PAGE_SIZE:
            raise ValueError("page_size must be between 1 and 100.")

    def _timestamp_to_seconds(self, value: Any) -> int:
        timestamp = int(value)
        if timestamp >= 1_000_000_000_000:
            return timestamp // 1000
        return timestamp

    def _required(self, item: dict[str, Any], *keys: str) -> Any:
        for key in keys:
            value = item.get(key)
            if value is not None:
                return value
        joined_keys = ", ".join(keys)
        raise MexcApiError(f"MEXC response is missing required field: {joined_keys}")

    def _optional(self, item: dict[str, Any], *keys: str) -> str | None:
        for key in keys:
            value = item.get(key)
            if value is not None:
                return str(value)
        return None

    def _optional_int(self, item: dict[str, Any], *keys: str) -> int | None:
        value = self._optional(item, *keys)
        return int(value) if value is not None else None

    def _optional_bool(self, item: dict[str, Any], *keys: str) -> bool | None:
        for key in keys:
            value = item.get(key)
            if value is None:
                continue
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                return value.lower() in {"true", "1", "yes"}
            return bool(value)
        return None

    def _optional_decimal(self, item: dict[str, Any], *keys: str) -> Decimal | None:
        value = self._optional(item, *keys)
        return Decimal(value) if value is not None else None

    def _optional_timestamp_ms(self, item: dict[str, Any], *keys: str) -> int | None:
        value = self._optional(item, *keys)
        if value is None or value == "":
            return None
        timestamp = int(value)
        if timestamp and timestamp < 1_000_000_000_000:
            return timestamp * 1000
        return timestamp

    def _decimal(self, value: Any) -> Decimal:
        if value is None:
            raise MexcApiError("MEXC numeric field cannot be null.")
        return Decimal(str(value))

    def _without_none(self, params: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in params.items() if value is not None}
