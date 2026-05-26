import asyncio
import hashlib
import hmac

import pytest

from app.services.mexc_client import MEXC_SIDE_LABELS, MexcFuturesClient


def test_query_string_sorts_keys_and_excludes_none_values():
    client = MexcFuturesClient(access_key="access", secret_key="secret")

    query_string = client._build_query_string(
        {
            "symbol": "BTC_USDT",
            "end_time": None,
            "page_size": 1000,
            "page_num": 1,
            "start_time": 1710000000000,
        }
    )

    assert query_string == "page_num=1&page_size=1000&start_time=1710000000000&symbol=BTC_USDT"
    assert "end_time" not in query_string


def test_signature_is_reproducible_with_fixed_timestamp():
    client = MexcFuturesClient(access_key="access-key", secret_key="secret-key")
    timestamp = "1710000000123"
    params = {
        "symbol": "BTC_USDT",
        "page_size": 1000,
        "page_num": 1,
        "start_time": None,
    }

    signature = client._sign(timestamp, params)

    target = "access-key" + timestamp + "page_num=1&page_size=1000&symbol=BTC_USDT"
    expected = hmac.new(b"secret-key", target.encode("utf-8"), hashlib.sha256).hexdigest()
    assert signature == expected


def test_page_size_cannot_exceed_1000():
    client = MexcFuturesClient(access_key="access", secret_key="secret")

    with pytest.raises(ValueError, match="page_size"):
        asyncio.run(client.get_order_deals(symbol="BTC_USDT", page_size=1001))


def test_unsupported_interval_is_rejected():
    client = MexcFuturesClient(access_key=None, secret_key=None)

    with pytest.raises(ValueError, match="Unsupported MEXC interval"):
        asyncio.run(client.get_klines(symbol="BTC_USDT", interval="Min15"))


def test_side_mapping_is_correct():
    assert MEXC_SIDE_LABELS == {
        1: "open_long",
        2: "close_short",
        3: "open_short",
        4: "close_long",
    }

