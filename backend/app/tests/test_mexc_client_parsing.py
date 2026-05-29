import asyncio
from decimal import Decimal
from typing import Any

import pytest

from app.services import mexc_client
from app.services.mexc_client import MexcApiError, MexcFuturesClient


class FakeResponse:
    def __init__(self, payload: Any) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        return self._payload


class FakeAsyncClient:
    payload: Any = {"success": True, "data": []}
    calls: list[dict[str, Any]] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs

    async def __aenter__(self) -> "FakeAsyncClient":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> FakeResponse:
        self.calls.append(
            {
                "path": path,
                "params": params,
                "headers": headers,
                "kwargs": self.kwargs,
            }
        )
        return FakeResponse(self.payload)


@pytest.fixture(autouse=True)
def fake_httpx_client(monkeypatch):
    FakeAsyncClient.payload = {"success": True, "data": []}
    FakeAsyncClient.calls = []
    monkeypatch.setattr(mexc_client.httpx, "AsyncClient", FakeAsyncClient)


def test_start_and_end_for_klines_are_unix_seconds():
    client = MexcFuturesClient(access_key=None, secret_key=None)
    FakeAsyncClient.payload = {"success": True, "data": []}

    candles = asyncio.run(
        client.get_klines(
            symbol="BTC_USDT",
            interval="Min60",
            start_s=1710000000,
            end_s=1710003600,
        )
    )

    assert candles == []
    assert FakeAsyncClient.calls[0]["path"] == "/api/v1/contract/kline/BTC_USDT"
    assert FakeAsyncClient.calls[0]["params"] == {
        "interval": "Min60",
        "start": 1710000000,
        "end": 1710003600,
    }


def test_start_time_and_end_time_for_order_deals_are_unix_milliseconds(monkeypatch):
    client = MexcFuturesClient(access_key="access", secret_key="secret")
    monkeypatch.setattr(client, "_timestamp_ms", lambda: "1710000000123")
    FakeAsyncClient.payload = {"success": True, "data": {"resultList": []}}

    deals = asyncio.run(
        client.get_order_deals(
            symbol="BTC_USDT",
            start_time_ms=1710000000000,
            end_time_ms=1710003600000,
            page_num=2,
            page_size=500,
        )
    )

    assert deals == []
    assert FakeAsyncClient.calls[0]["path"] == "/api/v1/private/order/list/order_deals/v3"
    assert FakeAsyncClient.calls[0]["params"] == {
        "symbol": "BTC_USDT",
        "start_time": 1710000000000,
        "end_time": 1710003600000,
        "page_num": 2,
        "page_size": 500,
    }
    assert FakeAsyncClient.calls[0]["headers"]["ApiKey"] == "access"
    assert FakeAsyncClient.calls[0]["headers"]["Request-Time"] == "1710000000123"


def test_kline_parser_handles_mexc_array_style_response():
    client = MexcFuturesClient(access_key=None, secret_key=None)
    FakeAsyncClient.payload = {
        "success": True,
        "data": {
            "time": [1710000000, 1710003600],
            "open": ["100.000000000000000001", "101.2"],
            "high": ["110.5", "102.5"],
            "low": ["99.75", "100.5"],
            "close": ["105.25", "101.9"],
            "vol": ["123.456789123456789123", "7"],
        },
    }

    candles = asyncio.run(client.get_klines(symbol="BTC_USDT", interval="Hour4"))

    assert len(candles) == 2
    assert candles[0].symbol == "BTC_USDT"
    assert candles[0].interval == "Hour4"
    assert candles[0].timestamp_s == 1710000000
    assert candles[0].open == Decimal("100.000000000000000001")
    assert candles[0].volume == Decimal("123.456789123456789123")


def test_kline_parser_handles_list_rows():
    client = MexcFuturesClient(access_key=None, secret_key=None)
    FakeAsyncClient.payload = {
        "success": True,
        "data": [
            [1710000000, "100.1", "110.2", "99.3", "105.4", "5.123456789123456789"],
        ],
    }

    candles = asyncio.run(client.get_klines(symbol="ETH_USDT", interval="Day1"))

    assert candles[0].timestamp_s == 1710000000
    assert candles[0].open == Decimal("100.1")
    assert candles[0].high == Decimal("110.2")
    assert candles[0].low == Decimal("99.3")
    assert candles[0].close == Decimal("105.4")
    assert candles[0].volume == Decimal("5.123456789123456789")


def test_order_deal_parser_preserves_decimal_precision(monkeypatch):
    client = MexcFuturesClient(access_key="access", secret_key="secret")
    monkeypatch.setattr(client, "_timestamp_ms", lambda: "1710000000123")
    FakeAsyncClient.payload = {
        "success": True,
        "data": {
            "resultList": [
                {
                    "id": "deal-1",
                    "symbol": "BTC_USDT",
                    "side": 1,
                    "vol": "0.123456789123456789",
                    "price": "61234.123456789123456789",
                    "fee": "0.000012345678912345",
                    "feeCurrency": "USDT",
                    "profit": "-1.234567891234567891",
                    "category": 1,
                    "orderId": "order-1",
                    "timestamp": 1710000000123,
                    "positionMode": 1,
                    "isTaker": True,
                }
            ]
        },
    }

    deals = asyncio.run(client.get_order_deals(symbol="BTC_USDT"))

    assert len(deals) == 1
    assert deals[0].mexc_deal_id == "deal-1"
    assert deals[0].side == 1
    assert deals[0].vol == Decimal("0.123456789123456789")
    assert deals[0].price == Decimal("61234.123456789123456789")
    assert deals[0].fee == Decimal("0.000012345678912345")
    assert deals[0].profit == Decimal("-1.234567891234567891")
    assert deals[0].raw_json["id"] == "deal-1"


def test_stop_order_parser_reads_stop_loss_fields(monkeypatch):
    client = MexcFuturesClient(access_key="access", secret_key="secret")
    monkeypatch.setattr(client, "_timestamp_ms", lambda: "1710000000123")
    FakeAsyncClient.payload = {
        "success": True,
        "data": [
            {
                "id": 1001,
                "orderId": "0",
                "symbol": "BTC_USDT",
                "positionId": 2002,
                "stopLossPrice": "98.123456789123456789",
                "takeProfitPrice": "0",
                "state": 3,
                "triggerSide": 2,
                "positionType": 1,
                "vol": "1.5",
                "realityVol": "1.5",
                "placeOrderId": "entry-order",
                "isFinished": 1,
                "createTime": 1710000000123,
                "updateTime": 1710000000456,
            }
        ],
    }

    orders = asyncio.run(
        client.get_stop_orders(
            symbol="BTC_USDT",
            start_time_ms=1710000000000,
            end_time_ms=1710003600000,
            page_num=2,
            page_size=50,
        )
    )

    assert FakeAsyncClient.calls[0]["path"] == "/api/v1/private/stoporder/list/orders"
    assert FakeAsyncClient.calls[0]["params"] == {
        "symbol": "BTC_USDT",
        "start_time": 1710000000000,
        "end_time": 1710003600000,
        "page_num": 2,
        "page_size": 50,
    }
    assert orders[0].stop_order_id == "1001"
    assert orders[0].stop_loss_price == Decimal("98.123456789123456789")
    assert orders[0].trigger_side == 2
    assert orders[0].position_type == 1


def test_missing_data_raises_mexc_api_error():
    client = MexcFuturesClient(access_key=None, secret_key=None)
    FakeAsyncClient.payload = {"success": True}

    with pytest.raises(MexcApiError, match="missing data"):
        asyncio.run(client.get_klines(symbol="BTC_USDT", interval="Min60"))
