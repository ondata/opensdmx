"""Mocked HTTP tests for sdmx_request_csv, all_available, get_data."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import polars as pl
import pytest

from opensdmx.base import (
    _is_retryable_exception,
    _provider_cache_key,
    _rate_limit_lock_file,
    sdmx_request,
    sdmx_request_csv,
    set_provider,
)
from opensdmx.discovery import all_available
from opensdmx.retrieval import get_data


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_DATAFLOW_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<message:Structure
    xmlns:message="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message"
    xmlns:structure="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure"
    xmlns:common="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common">
  <message:Structures>
    <structure:Dataflows>
      <structure:Dataflow id="UNE_RT_M" agencyID="ESTAT" version="1.0">
        <common:Name xml:lang="en">Monthly unemployment</common:Name>
        <structure:Structure>
          <Ref id="DSD_UNE_RT_M"/>
        </structure:Structure>
      </structure:Dataflow>
    </structure:Dataflows>
  </message:Structures>
</message:Structure>"""

_CSV_CONTENT = b"FREQ,GEO,TIME_PERIOD,OBS_VALUE\nM,IT,2020-01,7.5\nM,IT,2020-04,6.8\n"


def _mock_http_client(content: bytes):
    """Return a patch for httpx.Client that serves *content* on any GET."""
    resp = MagicMock()
    resp.content = content
    resp.raise_for_status = MagicMock()

    client = MagicMock()
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    client.get = MagicMock(return_value=resp)

    return patch("opensdmx.base.httpx.Client", return_value=client)


@pytest.fixture(autouse=True)
def _use_eurostat():
    set_provider("eurostat")


# ---------------------------------------------------------------------------
# sdmx_request_csv
# ---------------------------------------------------------------------------

class TestSdmxRequestCsv:
    def test_returns_dataframe(self):
        with _mock_http_client(_CSV_CONTENT):
            df = sdmx_request_csv("data/UNE_RT_M")
        assert isinstance(df, pl.DataFrame)
        assert df.shape == (2, 4)

    def test_columns_present(self):
        with _mock_http_client(_CSV_CONTENT):
            df = sdmx_request_csv("data/UNE_RT_M")
        assert set(df.columns) == {"FREQ", "GEO", "TIME_PERIOD", "OBS_VALUE"}

    def test_time_period_is_string(self):
        """TIME_PERIOD must remain Utf8 — parsed later by get_data."""
        with _mock_http_client(_CSV_CONTENT):
            df = sdmx_request_csv("data/UNE_RT_M")
        assert df["TIME_PERIOD"].dtype == pl.Utf8


# ---------------------------------------------------------------------------
# Cross-process serialization via portalocker.Lock
# ---------------------------------------------------------------------------

class TestRateLimitLock:
    def test_portalocker_invoked_with_provider_lock_path(self, monkeypatch, tmp_path):
        """Every HTTP call must acquire the per-provider flock."""
        monkeypatch.setenv("OPENSDMX_CACHE_DIR", str(tmp_path))
        # Clear the lru_cache so the tmp_path override takes effect
        from opensdmx.base import _resolve_cache_base_cached
        _resolve_cache_base_cached.cache_clear()

        set_provider("eurostat")
        expected_path = str(_rate_limit_lock_file())
        assert str(tmp_path) in expected_path

        lock_cm = MagicMock()
        lock_cm.__enter__ = MagicMock(return_value=lock_cm)
        lock_cm.__exit__ = MagicMock(return_value=False)

        with (
            _mock_http_client(_CSV_CONTENT),
            patch("opensdmx.base.portalocker.Lock", return_value=lock_cm) as mock_lock,
        ):
            sdmx_request("data/UNE_RT_M", accept="text/csv")

        assert mock_lock.called
        called_path = mock_lock.call_args.args[0]
        assert called_path == expected_path
        assert "eurostat" in called_path

    def test_custom_provider_blank_agency_gets_url_hash_key(self):
        """Custom URL providers without agency_id must not share the 'custom' key."""
        set_provider("https://example.org/sdmx")
        key_a = _provider_cache_key()

        set_provider("https://other.example.net/api")
        key_b = _provider_cache_key()

        assert key_a != key_b
        assert key_a.startswith("custom_")
        assert key_b.startswith("custom_")


# ---------------------------------------------------------------------------
# all_available
# ---------------------------------------------------------------------------

class TestAllAvailable:
    def test_parses_dataflow_id(self, tmp_path):
        cache = tmp_path / "dataflows.parquet"
        with (
            _mock_http_client(_DATAFLOW_XML),
            patch("opensdmx.discovery._load_cached_dataflows", return_value=None),
            patch("opensdmx.discovery._dataflow_cache_path", return_value=cache),
            patch("opensdmx.discovery._filter_invalid", side_effect=lambda df: df),
        ):
            df = all_available()

        assert df["df_id"][0] == "UNE_RT_M"

    def test_parses_description(self, tmp_path):
        cache = tmp_path / "dataflows.parquet"
        with (
            _mock_http_client(_DATAFLOW_XML),
            patch("opensdmx.discovery._load_cached_dataflows", return_value=None),
            patch("opensdmx.discovery._dataflow_cache_path", return_value=cache),
            patch("opensdmx.discovery._filter_invalid", side_effect=lambda df: df),
        ):
            df = all_available()

        assert df["df_description"][0] == "Monthly unemployment"

    def test_parses_structure_id(self, tmp_path):
        cache = tmp_path / "dataflows.parquet"
        with (
            _mock_http_client(_DATAFLOW_XML),
            patch("opensdmx.discovery._load_cached_dataflows", return_value=None),
            patch("opensdmx.discovery._dataflow_cache_path", return_value=cache),
            patch("opensdmx.discovery._filter_invalid", side_effect=lambda df: df),
        ):
            df = all_available()

        assert df["df_structure_id"][0] == "DSD_UNE_RT_M"

    def test_writes_parquet_cache(self, tmp_path):
        cache = tmp_path / "dataflows.parquet"
        with (
            _mock_http_client(_DATAFLOW_XML),
            patch("opensdmx.discovery._load_cached_dataflows", return_value=None),
            patch("opensdmx.discovery._dataflow_cache_path", return_value=cache),
            patch("opensdmx.discovery._filter_invalid", side_effect=lambda df: df),
        ):
            all_available()

        assert cache.exists()


# ---------------------------------------------------------------------------
# get_data
# ---------------------------------------------------------------------------

class TestGetData:
    def _unsorted_df(self):
        return pl.DataFrame({
            "FREQ": ["M", "M"],
            "GEO": ["IT", "IT"],
            "TIME_PERIOD": ["2020-Q2", "2020-Q1"],
            "OBS_VALUE": [6.8, 7.5],
        })

    def test_sorts_by_time_period(self):
        dataset = {"df_id": "UNE_RT_M", "filters": {"FREQ": "M", "GEO": "IT"}}
        with patch("opensdmx.retrieval.sdmx_request_csv", return_value=self._unsorted_df()):
            result = get_data(dataset)

        # Q1 should come before Q2 after sorting
        assert result["OBS_VALUE"][0] == pytest.approx(7.5)
        assert result["OBS_VALUE"][1] == pytest.approx(6.8)

    def test_passes_start_period(self):
        dataset = {"df_id": "UNE_RT_M", "filters": {}}
        stub = pl.DataFrame({"OBS_VALUE": [1.0]})

        with patch("opensdmx.retrieval.sdmx_request_csv", return_value=stub) as mock_csv:
            get_data(dataset, start_period="2020")

        _, kwargs = mock_csv.call_args
        assert kwargs.get("startPeriod") == "2020"

    def test_passes_end_period(self):
        dataset = {"df_id": "UNE_RT_M", "filters": {}}
        stub = pl.DataFrame({"OBS_VALUE": [1.0]})

        with patch("opensdmx.retrieval.sdmx_request_csv", return_value=stub) as mock_csv:
            get_data(dataset, end_period="2021")

        _, kwargs = mock_csv.call_args
        assert kwargs.get("endPeriod") == "2021"

    def test_passes_last_n_observations(self):
        dataset = {"df_id": "UNE_RT_M", "filters": {}}
        stub = pl.DataFrame({"OBS_VALUE": [1.0]})

        with patch("opensdmx.retrieval.sdmx_request_csv", return_value=stub) as mock_csv:
            get_data(dataset, last_n_observations=5)

        _, kwargs = mock_csv.call_args
        assert kwargs.get("lastNObservations") == 5


# ---------------------------------------------------------------------------
# Extra headers in sdmx_request
# ---------------------------------------------------------------------------

class TestExtraHeaders:
    def _get_headers_sent(self, mock_client_class):
        """Extract the headers dict from the last client.get() call."""
        client_instance = mock_client_class.return_value
        call_kwargs = client_instance.get.call_args
        return call_kwargs[1]["headers"]

    def test_extra_header_forwarded(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENSDMX_CACHE_DIR", str(tmp_path))
        from opensdmx.base import set_extra_headers
        set_extra_headers({"X-Api-Key": "secret"})
        try:
            with _mock_http_client(b"") as mock_client_class:
                sdmx_request("data/TEST")
            assert self._get_headers_sent(mock_client_class).get("X-Api-Key") == "secret"
        finally:
            set_extra_headers({})

    def test_user_agent_not_overridable(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENSDMX_CACHE_DIR", str(tmp_path))
        from opensdmx.base import set_extra_headers
        set_extra_headers({"User-Agent": "hacker"})
        try:
            with _mock_http_client(b"") as mock_client_class:
                sdmx_request("data/TEST")
            assert self._get_headers_sent(mock_client_class)["User-Agent"] != "hacker"
        finally:
            set_extra_headers({})

    def test_accept_overridable(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENSDMX_CACHE_DIR", str(tmp_path))
        from opensdmx.base import set_extra_headers
        set_extra_headers({"Accept": "application/json"})
        try:
            with _mock_http_client(b"") as mock_client_class:
                sdmx_request("data/TEST")
            assert self._get_headers_sent(mock_client_class)["Accept"] == "application/json"
        finally:
            set_extra_headers({})


# ---------------------------------------------------------------------------
# Retry behavior — only retry transient failures, never 4xx
# ---------------------------------------------------------------------------

def _http_status_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "http://test/example")
    response = httpx.Response(status, request=request)
    return httpx.HTTPStatusError(f"{status}", request=request, response=response)


def _mock_client_raising_on_status(exc: Exception):
    """Mock httpx.Client where get() returns a response whose raise_for_status raises exc."""
    resp = MagicMock()
    resp.content = b""
    resp.raise_for_status = MagicMock(side_effect=exc)

    client = MagicMock()
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    client.get = MagicMock(return_value=resp)

    return patch("opensdmx.base.httpx.Client", return_value=client)


def _mock_client_raising_on_get(exc: Exception):
    """Mock httpx.Client where get() itself raises (e.g. timeout, network error)."""
    client = MagicMock()
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    client.get = MagicMock(side_effect=exc)

    return patch("opensdmx.base.httpx.Client", return_value=client)


class TestIsRetryableExceptionPredicate:
    """Unit tests for the retry predicate, independent of HTTP plumbing."""

    def test_429_not_retryable(self):
        assert _is_retryable_exception(_http_status_error(429)) is False

    def test_403_not_retryable(self):
        assert _is_retryable_exception(_http_status_error(403)) is False

    def test_404_not_retryable(self):
        assert _is_retryable_exception(_http_status_error(404)) is False

    def test_401_not_retryable(self):
        assert _is_retryable_exception(_http_status_error(401)) is False

    def test_500_retryable(self):
        assert _is_retryable_exception(_http_status_error(500)) is True

    def test_502_retryable(self):
        assert _is_retryable_exception(_http_status_error(502)) is True

    def test_503_retryable(self):
        assert _is_retryable_exception(_http_status_error(503)) is True

    def test_504_retryable(self):
        assert _is_retryable_exception(_http_status_error(504)) is True

    def test_501_not_retryable(self):
        """501 Not Implemented is deterministic — retrying never helps."""
        assert _is_retryable_exception(_http_status_error(501)) is False

    def test_connect_timeout_retryable(self):
        assert _is_retryable_exception(httpx.ConnectTimeout("timeout")) is True

    def test_read_timeout_retryable(self):
        assert _is_retryable_exception(httpx.ReadTimeout("timeout")) is True

    def test_connect_error_retryable(self):
        assert _is_retryable_exception(httpx.ConnectError("conn refused")) is True

    def test_unknown_exception_not_retryable(self):
        """Don't retry on non-network exceptions (programming bugs, etc.)."""
        assert _is_retryable_exception(ValueError("bad value")) is False
        assert _is_retryable_exception(RuntimeError("oops")) is False


class TestRetryBehavior:
    """Integration-level: count actual HTTP attempts through sdmx_request."""

    @pytest.fixture(autouse=True)
    def _fast_retry(self, monkeypatch):
        """Disable backoff waits so retry tests stay fast.

        The @retry decorator on _do_request is rebuilt on every sdmx_request call,
        so patching wait_exponential at the module name resolves before the
        decorator is constructed.
        """
        from tenacity import wait_none
        monkeypatch.setattr("opensdmx.base.wait_exponential", lambda **kwargs: wait_none())

    def test_429_makes_one_call_no_retry(self, tmp_path, monkeypatch):
        """A 429 must NOT trigger retries — would amplify the rate-limit hit."""
        monkeypatch.setenv("OPENSDMX_CACHE_DIR", str(tmp_path))
        with _mock_client_raising_on_status(_http_status_error(429)) as mock_client_class:
            with pytest.raises(httpx.HTTPStatusError):
                sdmx_request("data/TEST")
        client_instance = mock_client_class.return_value
        assert client_instance.get.call_count == 1

    def test_403_makes_one_call_no_retry(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENSDMX_CACHE_DIR", str(tmp_path))
        with _mock_client_raising_on_status(_http_status_error(403)) as mock_client_class:
            with pytest.raises(httpx.HTTPStatusError):
                sdmx_request("data/TEST")
        client_instance = mock_client_class.return_value
        assert client_instance.get.call_count == 1

    def test_404_makes_one_call_no_retry(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENSDMX_CACHE_DIR", str(tmp_path))
        with _mock_client_raising_on_status(_http_status_error(404)) as mock_client_class:
            with pytest.raises(httpx.HTTPStatusError):
                sdmx_request("data/TEST")
        client_instance = mock_client_class.return_value
        assert client_instance.get.call_count == 1

    def test_503_retries_three_times(self, tmp_path, monkeypatch):
        """5xx is transient — retry up to 3 attempts, then propagate."""
        monkeypatch.setenv("OPENSDMX_CACHE_DIR", str(tmp_path))
        with _mock_client_raising_on_status(_http_status_error(503)) as mock_client_class:
            with pytest.raises(httpx.HTTPStatusError):
                sdmx_request("data/TEST")
        client_instance = mock_client_class.return_value
        assert client_instance.get.call_count == 3

    def test_connect_timeout_retries_three_times(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENSDMX_CACHE_DIR", str(tmp_path))
        with _mock_client_raising_on_get(httpx.ConnectTimeout("slow")) as mock_client_class:
            with pytest.raises(httpx.ConnectTimeout):
                sdmx_request("data/TEST")
        client_instance = mock_client_class.return_value
        assert client_instance.get.call_count == 3

    def test_connect_error_retries_three_times(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENSDMX_CACHE_DIR", str(tmp_path))
        with _mock_client_raising_on_get(httpx.ConnectError("refused")) as mock_client_class:
            with pytest.raises(httpx.ConnectError):
                sdmx_request("data/TEST")
        client_instance = mock_client_class.return_value
        assert client_instance.get.call_count == 3
