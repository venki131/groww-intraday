"""
Tests for the Groww integration layer.

All tests use unittest.mock — no network calls, no real API credentials needed.

Coverage
--------
  authentication.py     — TokenCache, get_api_token, obtain_access_token
  groww_client.py       — GrowwClient methods, retry logic, LiveTradingBlockedError
  historical_data.py    — _date_chunks, _response_to_dataframe, fetch_candles_chunked
  live_data.py          — get_ltp_rest, get_ohlc_rest, LiveDataFeed

Run with:
    pytest tests/test_groww_client.py -v
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch, PropertyMock
import tempfile
import os

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_candle_response(n: int = 5, base_price: float = 2500.0) -> dict:
    """
    Build a mock ``get_historical_candles`` response with ``n`` candles.
    Format: {"candles": [[epoch_ms, open, high, low, close, volume], ...]}
    """
    candles = []
    ts = int(datetime(2023, 1, 2, 9, 15).timestamp() * 1000)
    for i in range(n):
        o = base_price + i
        h = o + 5
        l = o - 5
        c = o + 2
        v = 1000 + i * 100
        candles.append([ts + i * 300_000, o, h, l, c, v])  # 5-min apart
    return {"candles": candles}


@pytest.fixture
def mock_groww_api():
    """A MagicMock standing in for a real GrowwAPI instance."""
    api = MagicMock()
    api.get_historical_candles.return_value = _make_candle_response()
    api.get_ltp.return_value = {
        "NSE_RELIANCE": {"ltp": 2500.0},
        "NSE_INFY": {"ltp": 1800.0},
    }
    api.get_ohlc.return_value = {
        "NSE_RELIANCE": {"open": 2490.0, "high": 2510.0, "low": 2480.0, "close": 2500.0},
    }
    api.get_quote.return_value = {"ltp": 2500.0, "volume": 50000}
    api.get_order_list.return_value = {"orders": [], "total": 0}
    api.get_order_detail.return_value = {"order_id": "GW123", "status": "COMPLETE"}
    api.get_order_status.return_value = {"status": "COMPLETE"}
    api.get_order_status_by_reference.return_value = {"status": "PENDING"}
    api.get_trade_list_for_order.return_value = {"trades": []}
    api.get_positions_for_user.return_value = {"positions": []}
    api.get_position_for_trading_symbol.return_value = {"qty": 10, "avg_price": 2490.0}
    api.get_holdings_for_user.return_value = {"holdings": []}
    api.get_available_margin_details.return_value = {"available_cash": 50000.0}
    api.get_user_profile.return_value = {"name": "Test User", "email": "test@example.com"}
    api.get_instrument_by_exchange_and_trading_symbol.return_value = {
        "exchange": "NSE",
        "trading_symbol": "RELIANCE",
        "groww_symbol": "NSE-RELIANCE",
        "instrument_type": "EQ",
    }
    api.get_instrument_by_groww_symbol.return_value = {
        "groww_symbol": "NSE-RELIANCE",
        "trading_symbol": "RELIANCE",
    }
    return api


@pytest.fixture
def groww_client(mock_groww_api):
    """GrowwClient with the internal _api replaced by mock_groww_api."""
    with patch("growwapi.GrowwAPI", return_value=mock_groww_api):
        from app.broker.groww_client import GrowwClient
        client = GrowwClient(access_token="fake-token-for-tests")
        client._api = mock_groww_api  # ensure our mock is used
    return client


# ===========================================================================
# authentication.py tests
# ===========================================================================

class TestTokenCache:

    def test_save_and_load_plaintext(self, tmp_path):
        """TokenCache round-trips a token without encryption."""
        from app.broker.authentication import TokenCache
        cache = TokenCache(path=tmp_path / "token.json")
        cache.save("my-secret-token")
        assert cache.load() == "my-secret-token"

    def test_save_sets_file_permissions(self, tmp_path):
        """Saved token file should be owner read/write only (0o600)."""
        from app.broker.authentication import TokenCache
        cache = TokenCache(path=tmp_path / "token.json")
        cache.save("test-token")
        stat = (tmp_path / "token.json").stat()
        assert oct(stat.st_mode)[-3:] == "600"

    def test_clear_removes_file(self, tmp_path):
        from app.broker.authentication import TokenCache
        p = tmp_path / "token.json"
        cache = TokenCache(path=p)
        cache.save("x")
        assert p.exists()
        cache.clear()
        assert not p.exists()

    def test_load_returns_none_when_missing(self, tmp_path):
        from app.broker.authentication import TokenCache
        cache = TokenCache(path=tmp_path / "nonexistent.json")
        assert cache.load() is None

    def test_load_warns_on_old_token(self, tmp_path, caplog):
        """A token stored > 20 hours ago should trigger a warning."""
        import logging
        from app.broker.authentication import TokenCache
        cache = TokenCache(path=tmp_path / "token.json")
        # Manually write a stale token (stored 25 hours ago)
        old_time = time.time() - 25 * 3600
        payload = {"token": "stale-token", "stored_at": old_time, "encrypted": False}
        (tmp_path / "token.json").write_text(json.dumps(payload))
        (tmp_path / "token.json").chmod(0o600)

        with caplog.at_level(logging.WARNING, logger="app.broker.authentication"):
            result = cache.load()
        assert result == "stale-token"
        assert "daily renewal" in caplog.text.lower() or "hours old" in caplog.text.lower()


class TestGetApiToken:

    def test_reads_from_env_var(self, monkeypatch):
        monkeypatch.setenv("GROWW_API_TOKEN", "env-token-123")
        from app.broker import authentication
        # Reload to pick up env changes
        import importlib
        importlib.reload(authentication)
        token = authentication.get_api_token()
        assert token == "env-token-123"

    def test_reads_from_cache_when_no_env(self, tmp_path, monkeypatch):
        monkeypatch.delenv("GROWW_API_TOKEN", raising=False)
        from app.broker.authentication import TokenCache, get_api_token
        cache = TokenCache(path=tmp_path / "token.json")
        cache.save("cached-token")
        token = get_api_token(cache=cache)
        assert token == "cached-token"

    def test_raises_when_no_token(self, monkeypatch, tmp_path):
        monkeypatch.delenv("GROWW_API_TOKEN", raising=False)
        from app.broker.authentication import TokenCache, get_api_token
        empty_cache = TokenCache(path=tmp_path / "empty.json")
        with pytest.raises(RuntimeError, match="Groww access token not found"):
            get_api_token(cache=empty_cache)


class TestObtainAccessToken:

    def test_raises_without_api_key(self, monkeypatch):
        monkeypatch.delenv("GROWW_API_KEY", raising=False)
        from app.broker.authentication import obtain_access_token
        with pytest.raises(RuntimeError, match="API key not provided"):
            obtain_access_token(totp="123456")

    def test_raises_without_totp_or_secret(self, monkeypatch):
        monkeypatch.setenv("GROWW_API_KEY", "myapikey")
        monkeypatch.delenv("GROWW_API_SECRET", raising=False)
        from app.broker.authentication import obtain_access_token
        with pytest.raises(RuntimeError, match="totp.*secret"):
            obtain_access_token()

    def test_calls_groww_get_access_token(self, monkeypatch):
        monkeypatch.setenv("GROWW_API_KEY", "myapikey")
        from app.broker import authentication
        with patch("growwapi.GrowwAPI.get_access_token", return_value="access-tok") as mock_ga:
            token = authentication.obtain_access_token(
                totp="123456", save_to_cache=False
            )
        assert token == "access-tok"
        mock_ga.assert_called_once_with(api_key="myapikey", totp="123456", secret=None)

    def test_capability_report_has_required_keys(self):
        from app.broker.authentication import capability_report
        report = capability_report()
        assert "authentication" in report
        assert "historical_data" in report
        assert "order_placement" in report
        assert "market_data_websocket" in report


# ===========================================================================
# groww_client.py tests
# ===========================================================================

class TestGrowwClientInit:

    def test_raises_without_growwapi_package(self):
        """If growwapi is not importable, GrowwClient raises RuntimeError."""
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "growwapi":
                raise ImportError("No module named 'growwapi'")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            # Need to reimport to trigger __init__
            import importlib, sys
            sys.modules.pop("app.broker.groww_client", None)
            from app.broker import groww_client as gc_module
            importlib.reload(gc_module)
            with pytest.raises(RuntimeError, match="growwapi package not installed"):
                gc_module.GrowwClient("token")


class TestGrowwClientInstruments:

    def test_get_instrument_calls_sdk(self, groww_client, mock_groww_api):
        result = groww_client.get_instrument("RELIANCE", exchange="NSE")
        mock_groww_api.get_instrument_by_exchange_and_trading_symbol.assert_called_once_with(
            "NSE", "RELIANCE"
        )
        assert result["trading_symbol"] == "RELIANCE"

    def test_get_instrument_by_groww_symbol(self, groww_client, mock_groww_api):
        result = groww_client.get_instrument_by_groww_symbol("NSE-RELIANCE")
        mock_groww_api.get_instrument_by_groww_symbol.assert_called_once_with("NSE-RELIANCE")
        assert result["groww_symbol"] == "NSE-RELIANCE"


class TestGrowwClientLiveData:

    def test_get_ltp_builds_exchange_symbols(self, groww_client, mock_groww_api):
        groww_client.get_ltp(["RELIANCE", "INFY"], exchange="NSE", segment="CASH")
        call_args = mock_groww_api.get_ltp.call_args
        exchange_symbols = call_args[0][0]
        assert "NSE_RELIANCE" in exchange_symbols
        assert "NSE_INFY" in exchange_symbols

    def test_get_ohlc_builds_exchange_symbols(self, groww_client, mock_groww_api):
        groww_client.get_ohlc(["RELIANCE"], exchange="NSE", segment="CASH")
        call_args = mock_groww_api.get_ohlc.call_args
        assert "NSE_RELIANCE" in call_args[0][0]

    def test_get_quote_passes_params(self, groww_client, mock_groww_api):
        groww_client.get_quote("RELIANCE", exchange="NSE", segment="CASH")
        mock_groww_api.get_quote.assert_called_once_with(
            "RELIANCE", "NSE", "CASH", timeout=15
        )


class TestGrowwClientOrders:

    def test_get_order_list(self, groww_client, mock_groww_api):
        result = groww_client.get_order_list(segment="CASH")
        assert "orders" in result or isinstance(result, dict)

    def test_get_order_detail(self, groww_client, mock_groww_api):
        result = groww_client.get_order_detail("GW123", segment="CASH")
        mock_groww_api.get_order_detail.assert_called_once()
        assert result["order_id"] == "GW123"

    def test_get_order_status(self, groww_client, mock_groww_api):
        result = groww_client.get_order_status("GW123", segment="CASH")
        assert result["status"] == "COMPLETE"

    def test_get_order_status_by_reference(self, groww_client, mock_groww_api):
        result = groww_client.get_order_status_by_reference("REF001", segment="CASH")
        assert result["status"] == "PENDING"

    def test_get_trade_history(self, groww_client, mock_groww_api):
        result = groww_client.get_trade_history("GW123", segment="CASH")
        assert "trades" in result


class TestGrowwClientPositionsMargin:

    def test_get_positions(self, groww_client, mock_groww_api):
        result = groww_client.get_positions(segment="CASH")
        mock_groww_api.get_positions_for_user.assert_called_once()
        assert "positions" in result

    def test_get_position(self, groww_client, mock_groww_api):
        result = groww_client.get_position("RELIANCE", segment="CASH")
        mock_groww_api.get_position_for_trading_symbol.assert_called_once_with(
            "RELIANCE", "CASH", timeout=15
        )
        assert result["qty"] == 10

    def test_get_holdings(self, groww_client, mock_groww_api):
        result = groww_client.get_holdings()
        mock_groww_api.get_holdings_for_user.assert_called_once()

    def test_get_available_margin(self, groww_client, mock_groww_api):
        result = groww_client.get_available_margin()
        assert result["available_cash"] == 50000.0

    def test_get_user_profile(self, groww_client, mock_groww_api):
        result = groww_client.get_user_profile()
        assert result["name"] == "Test User"


class TestLiveTradingBlock:

    def test_place_order_blocked(self, groww_client):
        from app.broker.groww_client import LiveTradingBlockedError
        with pytest.raises(LiveTradingBlockedError):
            groww_client.place_order()

    def test_modify_order_blocked(self, groww_client):
        from app.broker.groww_client import LiveTradingBlockedError
        with pytest.raises(LiveTradingBlockedError):
            groww_client.modify_order()

    def test_cancel_order_blocked(self, groww_client):
        from app.broker.groww_client import LiveTradingBlockedError
        with pytest.raises(LiveTradingBlockedError):
            groww_client.cancel_order()

    def test_live_trading_flag_is_false(self):
        from app.broker import groww_client
        assert groww_client._LIVE_TRADING_ENABLED is False


class TestRetryLogic:

    def test_retries_on_rate_limit(self, groww_client, mock_groww_api):
        """get_positions retries up to 3 times on GrowwAPIRateLimitException."""
        try:
            from growwapi.groww.exceptions import GrowwAPIRateLimitException
        except ImportError:
            pytest.skip("growwapi not installed")

        # Fail twice with rate limit, succeed on 3rd
        mock_groww_api.get_positions_for_user.side_effect = [
            GrowwAPIRateLimitException(),
            GrowwAPIRateLimitException(),
            {"positions": []},
        ]
        with patch("time.sleep"):  # don't actually sleep in tests
            result = groww_client.get_positions()
        assert result == {"positions": []}
        assert mock_groww_api.get_positions_for_user.call_count == 3

    def test_raises_after_max_retries(self, groww_client, mock_groww_api):
        """After 3 rate-limit failures, the exception is re-raised."""
        try:
            from growwapi.groww.exceptions import GrowwAPIRateLimitException
        except ImportError:
            pytest.skip("growwapi not installed")

        mock_groww_api.get_positions_for_user.side_effect = GrowwAPIRateLimitException()
        with patch("time.sleep"):
            with pytest.raises(GrowwAPIRateLimitException):
                groww_client.get_positions()


# ===========================================================================
# historical_data.py tests
# ===========================================================================

class TestDateChunks:

    def test_single_chunk_for_30_days(self):
        from app.market.historical_data import _date_chunks
        start = datetime(2023, 1, 1)
        end = datetime(2023, 1, 30)
        chunks = list(_date_chunks(start, end))
        assert len(chunks) == 1

    def test_two_chunks_for_31_days(self):
        from app.market.historical_data import _date_chunks
        start = datetime(2023, 1, 1)
        end = datetime(2023, 2, 1)  # 32 days
        chunks = list(_date_chunks(start, end))
        assert len(chunks) == 2

    def test_chunks_cover_full_range(self):
        from app.market.historical_data import _date_chunks
        start = datetime(2023, 1, 1)
        end = datetime(2023, 6, 30)
        chunks = list(_date_chunks(start, end))
        assert chunks[0][0] == start
        assert chunks[-1][1] == end

    def test_no_gaps_between_chunks(self):
        from app.market.historical_data import _date_chunks
        from datetime import timedelta
        start = datetime(2023, 1, 1)
        end = datetime(2023, 4, 1)
        chunks = list(_date_chunks(start, end))
        for i in range(1, len(chunks)):
            prev_end = chunks[i - 1][1]
            cur_start = chunks[i][0]
            assert cur_start == prev_end + timedelta(seconds=1)


class TestResponseToDataFrame:

    def test_converts_valid_response(self):
        from app.market.historical_data import _response_to_dataframe
        response = _make_candle_response(n=10)
        df = _response_to_dataframe(response)
        assert len(df) == 10
        assert list(df.columns) == ["timestamp", "open", "high", "low", "close", "volume"]

    def test_empty_response_returns_empty_df(self):
        from app.market.historical_data import _response_to_dataframe
        df = _response_to_dataframe({"candles": []})
        assert df.empty

    def test_missing_candles_key_returns_empty_df(self):
        from app.market.historical_data import _response_to_dataframe
        df = _response_to_dataframe({})
        assert df.empty

    def test_sorted_by_timestamp(self):
        from app.market.historical_data import _response_to_dataframe
        # Give candles out of order
        response = {
            "candles": [
                [1672650300000, 2500, 2510, 2490, 2505, 1000],
                [1672650000000, 2495, 2505, 2485, 2500, 900],
            ]
        }
        df = _response_to_dataframe(response)
        assert df.iloc[0]["timestamp"] < df.iloc[1]["timestamp"]

    def test_timestamp_is_timezone_aware(self):
        from app.market.historical_data import _response_to_dataframe
        response = _make_candle_response(n=1)
        df = _response_to_dataframe(response)
        assert df.iloc[0]["timestamp"].tzinfo is not None


class TestFetchCandlesChunked:

    def test_raises_on_inverted_dates(self):
        from app.market.historical_data import fetch_candles_chunked
        client = MagicMock()
        with pytest.raises(ValueError, match="must be"):
            fetch_candles_chunked(client, "NSE-RELIANCE", "2023-06-30", "2023-01-01")

    def test_single_chunk_calls_api_once(self, mock_groww_api):
        from app.market.historical_data import fetch_candles_chunked, CandleInterval
        mock_client = MagicMock()
        mock_client.api = mock_groww_api
        mock_groww_api.get_historical_candles.return_value = _make_candle_response(n=10)

        df = fetch_candles_chunked(
            mock_client, "NSE-RELIANCE",
            start_date="2023-01-02", end_date="2023-01-15",
            interval=CandleInterval.MIN_5,
            sleep_between_chunks=0,
        )
        mock_groww_api.get_historical_candles.assert_called_once()
        assert len(df) == 10

    def test_multi_chunk_concatenates_results(self, mock_groww_api):
        from app.market.historical_data import fetch_candles_chunked, CandleInterval
        mock_client = MagicMock()
        mock_client.api = mock_groww_api
        # Return 5 candles per chunk
        mock_groww_api.get_historical_candles.return_value = _make_candle_response(n=5, base_price=2500.0)

        df = fetch_candles_chunked(
            mock_client, "NSE-RELIANCE",
            start_date="2023-01-02", end_date="2023-03-01",  # ~59 days → 2 chunks
            interval=CandleInterval.MIN_5,
            sleep_between_chunks=0,
        )
        assert mock_groww_api.get_historical_candles.call_count == 2
        # Both chunks return same 5 candles but timestamps differ in real API;
        # our mock returns identical candles so dedup removes them → still 5
        assert len(df) == 5

    def test_uses_correct_candle_interval(self, mock_groww_api):
        from app.market.historical_data import fetch_candles_chunked, CandleInterval
        mock_client = MagicMock()
        mock_client.api = mock_groww_api

        fetch_candles_chunked(
            mock_client, "NSE-INFY",
            start_date="2023-01-02", end_date="2023-01-10",
            interval=CandleInterval.MIN_5,
            sleep_between_chunks=0,
        )
        call_kwargs = mock_groww_api.get_historical_candles.call_args[1]
        assert call_kwargs.get("candle_interval") == "5minute"

    def test_api_error_raises_runtime_error(self, mock_groww_api):
        from app.market.historical_data import fetch_candles_chunked
        mock_client = MagicMock()
        mock_client.api = mock_groww_api
        mock_groww_api.get_historical_candles.side_effect = Exception("API error")

        with pytest.raises(RuntimeError, match="Failed to fetch candles"):
            fetch_candles_chunked(
                mock_client, "NSE-RELIANCE",
                start_date="2023-01-02", end_date="2023-01-10",
                sleep_between_chunks=0,
            )

    def test_no_data_returns_empty_df(self, mock_groww_api):
        from app.market.historical_data import fetch_candles_chunked
        mock_client = MagicMock()
        mock_client.api = mock_groww_api
        mock_groww_api.get_historical_candles.return_value = {"candles": []}

        df = fetch_candles_chunked(
            mock_client, "NSE-RELIANCE",
            start_date="2023-01-07", end_date="2023-01-08",  # weekend
            sleep_between_chunks=0,
        )
        assert df.empty


class TestFetchCandlesSingle:

    def test_raises_when_range_exceeds_30_days(self):
        from app.market.historical_data import fetch_candles_single
        client = MagicMock()
        with pytest.raises(ValueError, match="exceeds the API limit"):
            fetch_candles_single(
                client, "NSE-RELIANCE",
                start_time="2023-01-01 09:15:00",
                end_time="2023-02-15 15:30:00",
            )

    def test_calls_api_with_correct_params(self, mock_groww_api):
        from app.market.historical_data import fetch_candles_single, CandleInterval
        mock_client = MagicMock()
        mock_client.api = mock_groww_api

        df = fetch_candles_single(
            mock_client, "NSE-RELIANCE",
            start_time="2023-01-02 09:15:00",
            end_time="2023-01-20 15:30:00",
            interval=CandleInterval.MIN_5,
        )
        mock_groww_api.get_historical_candles.assert_called_once_with(
            exchange="NSE",
            segment="CASH",
            groww_symbol="NSE-RELIANCE",
            start_time="2023-01-02 09:15:00",
            end_time="2023-01-20 15:30:00",
            candle_interval="5minute",
            timeout=30,
        )
        assert not df.empty


# ===========================================================================
# live_data.py tests
# ===========================================================================

class TestGetLtpRest:

    def test_returns_symbol_ltp_map(self):
        from app.market.live_data import get_ltp_rest
        mock_client = MagicMock()
        mock_client.get_ltp.return_value = {
            "NSE_RELIANCE": {"ltp": 2500.0},
            "NSE_INFY": {"ltp": 1800.5},
        }
        result = get_ltp_rest(mock_client, ["RELIANCE", "INFY"])
        assert result["RELIANCE"] == 2500.0
        assert result["INFY"] == 1800.5

    def test_missing_ltp_key_skipped(self):
        from app.market.live_data import get_ltp_rest
        mock_client = MagicMock()
        mock_client.get_ltp.return_value = {
            "NSE_RELIANCE": {"bid": 2498.0},  # no "ltp" key
        }
        result = get_ltp_rest(mock_client, ["RELIANCE"])
        assert "RELIANCE" not in result

    def test_passes_exchange_and_segment(self):
        from app.market.live_data import get_ltp_rest
        mock_client = MagicMock()
        mock_client.get_ltp.return_value = {}
        get_ltp_rest(mock_client, ["RELIANCE"], exchange="BSE", segment="CASH")
        mock_client.get_ltp.assert_called_once_with(
            symbols=["RELIANCE"], exchange="BSE", segment="CASH"
        )


class TestGetOhlcRest:

    def test_returns_ohlc_map(self):
        from app.market.live_data import get_ohlc_rest
        mock_client = MagicMock()
        mock_client.get_ohlc.return_value = {
            "NSE_RELIANCE": {"open": 2490.0, "high": 2510.0, "low": 2480.0, "close": 2505.0}
        }
        result = get_ohlc_rest(mock_client, ["RELIANCE"])
        assert result["RELIANCE"]["open"] == 2490.0
        assert result["RELIANCE"]["high"] == 2510.0


class TestGetQuoteRest:

    def test_calls_client_get_quote(self):
        from app.market.live_data import get_quote_rest
        mock_client = MagicMock()
        mock_client.get_quote.return_value = {"ltp": 2500.0}
        result = get_quote_rest(mock_client, "RELIANCE", exchange="NSE", segment="CASH")
        mock_client.get_quote.assert_called_once_with(
            trading_symbol="RELIANCE", exchange="NSE", segment="CASH"
        )
        assert result["ltp"] == 2500.0


class TestLiveDataFeed:

    def test_subscribe_ltp_calls_client(self):
        from app.market.live_data import LiveDataFeed
        mock_client = MagicMock()
        feed = LiveDataFeed(mock_client)
        feed.subscribe_ltp(["RELIANCE", "INFY"])
        mock_client.subscribe_ltp.assert_called_once()
        call_kwargs = mock_client.subscribe_ltp.call_args[1]
        instruments = call_kwargs["instruments"]
        symbols = {i["trading_symbol"] for i in instruments}
        assert "RELIANCE" in symbols
        assert "INFY" in symbols

    def test_get_ltp_snapshot_returns_cache(self):
        from app.market.live_data import LiveDataFeed
        mock_client = MagicMock()
        mock_client.subscribe_ltp.return_value = {}
        mock_client.get_ltp_snapshot.return_value = {
            "NSE_RELIANCE": {"ltp": 2500.0}
        }
        feed = LiveDataFeed(mock_client)
        # Seed the internal cache directly to test snapshot without threading
        feed._ltp_cache["RELIANCE"] = 2500.0
        snapshot = feed.get_ltp_snapshot()
        assert snapshot["RELIANCE"] == 2500.0

    def test_unsubscribe_ltp_calls_client(self):
        from app.market.live_data import LiveDataFeed
        mock_client = MagicMock()
        mock_client.subscribe_ltp.return_value = {}
        feed = LiveDataFeed(mock_client)
        feed.subscribe_ltp(["RELIANCE"])
        feed.unsubscribe_ltp(["RELIANCE"])
        mock_client.unsubscribe_ltp.assert_called_once()

    def test_unsubscribe_all_clears_subscriptions(self):
        from app.market.live_data import LiveDataFeed
        mock_client = MagicMock()
        mock_client.subscribe_ltp.return_value = {}
        feed = LiveDataFeed(mock_client)
        feed.subscribe_ltp(["RELIANCE", "INFY"])
        feed.unsubscribe_all()
        assert feed._subscribed_ltp == []