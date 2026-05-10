"""Tests for opensdmx.hub — `.Stat Suite` hub integration."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

from opensdmx.hub import (
    _dataset_identifier,
    _hub_node_url,
    get_available_values_via_hub,
    get_dimension_values_via_hub,
    is_hub_enabled,
)


_HUB_PROVIDER = {
    "name": "ISTAT",
    "agency_id": "IT1",
    "language": "it",
    "hub_base_url": "https://example.test/databrowserhub/api/core",
    "hub_node_id": "1",
    "hub_dataset_agency": "IT1",
    "hub_timeout": 5.0,
}

_NON_HUB_PROVIDER = {
    "name": "Eurostat",
    "agency_id": "ESTAT",
    "language": "en",
}


def _dataset(df_id="TEST_DF", version="1.0", **dims):
    if not dims:
        dims = {"FREQ": 0, "REF_AREA": 1}
    dimensions = {
        d: {"id": d, "position": pos, "codelist_id": None}
        for d, pos in dims.items()
    }
    return {
        "df_id": df_id,
        "version": version,
        "df_description": "test",
        "df_structure_id": "TEST_DSD",
        "dimensions": dimensions,
        "filters": {d: "." for d in dimensions},
    }


# ── is_hub_enabled ───────────────────────────────────────────────────────

def test_is_hub_enabled_true_when_configured():
    assert is_hub_enabled(_HUB_PROVIDER) is True


def test_is_hub_enabled_false_for_non_hub_provider():
    assert is_hub_enabled(_NON_HUB_PROVIDER) is False


def test_is_hub_enabled_false_when_disabled_via_env(monkeypatch):
    monkeypatch.setenv("OPENSDMX_DISABLE_HUB", "1")
    assert is_hub_enabled(_HUB_PROVIDER) is False


def test_is_hub_enabled_reads_active_provider_when_no_arg():
    """When called without an explicit provider, falls back to base.get_provider()."""
    with patch("opensdmx.hub.get_provider", return_value=_HUB_PROVIDER):
        assert is_hub_enabled() is True
    with patch("opensdmx.hub.get_provider", return_value=_NON_HUB_PROVIDER):
        assert is_hub_enabled() is False


# ── _hub_node_url ─────────────────────────────────────────────────────────

def test_hub_node_url_strips_trailing_slash():
    p = {**_HUB_PROVIDER, "hub_base_url": "https://example.test/api/core/"}
    with patch("opensdmx.hub.get_provider", return_value=p):
        assert _hub_node_url() == "https://example.test/api/core/nodes/1"


def test_hub_node_url_uses_node_id():
    p = {**_HUB_PROVIDER, "hub_node_id": "42"}
    with patch("opensdmx.hub.get_provider", return_value=p):
        assert _hub_node_url().endswith("/nodes/42")


# ── _dataset_identifier ───────────────────────────────────────────────────

def test_dataset_identifier_with_explicit_agency():
    with patch("opensdmx.hub.get_provider", return_value=_HUB_PROVIDER):
        assert _dataset_identifier("DF_X", "1.0") == "IT1,DF_X,1.0"


def test_dataset_identifier_falls_back_to_agency_id():
    p = {k: v for k, v in _HUB_PROVIDER.items() if k != "hub_dataset_agency"}
    with patch("opensdmx.hub.get_provider", return_value=p):
        assert _dataset_identifier("DF_X", "1.0") == "IT1,DF_X,1.0"


def test_dataset_identifier_default_version():
    with patch("opensdmx.hub.get_provider", return_value=_HUB_PROVIDER):
        assert _dataset_identifier("DF_X", None) == "IT1,DF_X,1.0"


# ── get_dimension_values_via_hub ──────────────────────────────────────────

_HUB_VALUES_PAYLOAD = {
    "criteria": [
        {
            "id": "REF_AREA",
            "values": [
                {"id": "IT", "name": "Italia", "isSelectable": True},
                {"id": "ITC4", "name": "Lombardia", "isSelectable": True},
                {"id": "015146", "name": "Milano", "isSelectable": True},
            ],
        }
    ],
    "obsCount": 12345,
}


def _mock_client_with_response(status: int = 200, payload: dict | None = None,
                               raise_exc: Exception | None = None):
    """Build a context-manager mock for httpx.Client that returns a fixed response."""
    client = MagicMock()

    if raise_exc is not None:
        client.get.side_effect = raise_exc
    else:
        resp = MagicMock()
        resp.status_code = status
        if status >= 400:
            req = httpx.Request("GET", "http://x")
            err_resp = httpx.Response(status, request=req)
            resp.raise_for_status.side_effect = httpx.HTTPStatusError(
                f"{status}", request=req, response=err_resp
            )
        else:
            resp.raise_for_status.return_value = None
        resp.json.return_value = payload or {}
        client.get.return_value = resp

    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=client)
    cm.__exit__ = MagicMock(return_value=False)
    return cm, client


def test_get_dimension_values_via_hub_parses_ids():
    cm, client = _mock_client_with_response(payload=_HUB_VALUES_PAYLOAD)
    with patch("opensdmx.hub.get_provider", return_value=_HUB_PROVIDER), \
         patch("opensdmx.hub.httpx.Client", return_value=cm):
        result = get_dimension_values_via_hub("DF_X", "REF_AREA")

    assert result == ["IT", "ITC4", "015146"]
    args, kwargs = client.get.call_args
    url = args[0]
    assert "/datasets/IT1,DF_X,1.0/column/REF_AREA/partial/values" in url
    assert kwargs["headers"]["Accept"] == "application/json"
    assert kwargs["headers"]["userlang"] == "it"


def test_get_dimension_values_via_hub_returns_empty_on_http_error():
    cm, _ = _mock_client_with_response(status=500)
    with patch("opensdmx.hub.get_provider", return_value=_HUB_PROVIDER), \
         patch("opensdmx.hub.httpx.Client", return_value=cm):
        assert get_dimension_values_via_hub("DF_X", "REF_AREA") == []


def test_get_dimension_values_via_hub_returns_empty_on_timeout():
    cm, _ = _mock_client_with_response(raise_exc=httpx.TimeoutException("slow"))
    with patch("opensdmx.hub.get_provider", return_value=_HUB_PROVIDER), \
         patch("opensdmx.hub.httpx.Client", return_value=cm):
        assert get_dimension_values_via_hub("DF_X", "REF_AREA") == []


def test_get_dimension_values_via_hub_returns_empty_on_bad_json_shape():
    cm, _ = _mock_client_with_response(payload={"unexpected": "shape"})
    with patch("opensdmx.hub.get_provider", return_value=_HUB_PROVIDER), \
         patch("opensdmx.hub.httpx.Client", return_value=cm):
        assert get_dimension_values_via_hub("DF_X", "REF_AREA") == []


# ── get_available_values_via_hub ──────────────────────────────────────────

def test_get_available_values_via_hub_iterates_dimensions():
    """Each dimension is queried via hub; results merged into one dict."""
    calls = []

    def fake_get_dim(df_id, dim_id, version=None, **kwargs):
        calls.append(dim_id)
        return {"FREQ": ["A", "M"], "REF_AREA": ["IT", "FR"]}.get(dim_id, [])

    with patch("opensdmx.hub.get_provider", return_value=_HUB_PROVIDER), \
         patch("opensdmx.hub.get_dimension_values_via_hub", side_effect=fake_get_dim):
        result = get_available_values_via_hub(_dataset(FREQ=1, REF_AREA=2))

    assert calls == ["FREQ", "REF_AREA"]
    assert result == {"FREQ": ["A", "M"], "REF_AREA": ["IT", "FR"]}


def test_get_available_values_via_hub_aborts_on_partial_failure():
    """If any dimension returns empty, return {} so caller falls through."""
    def fake_get_dim(df_id, dim_id, version=None, **kwargs):
        return ["A"] if dim_id == "FREQ" else []

    with patch("opensdmx.hub.get_provider", return_value=_HUB_PROVIDER), \
         patch("opensdmx.hub.get_dimension_values_via_hub", side_effect=fake_get_dim):
        result = get_available_values_via_hub(_dataset(FREQ=1, REF_AREA=2))

    assert result == {}


def test_get_available_values_via_hub_excludes_time_period():
    """TIME_PERIOD must not be queried via hub (not a codelist dimension)."""
    calls = []

    def fake_get_dim(df_id, dim_id, version=None, **kwargs):
        calls.append(dim_id)
        return ["X"]

    ds = _dataset(FREQ=1, TIME_PERIOD=2)
    with patch("opensdmx.hub.get_provider", return_value=_HUB_PROVIDER), \
         patch("opensdmx.hub.get_dimension_values_via_hub", side_effect=fake_get_dim):
        get_available_values_via_hub(ds)
    assert "TIME_PERIOD" not in calls


def test_get_available_values_via_hub_returns_empty_when_provider_not_configured():
    """Direct call with a non-hub provider returns {} (graceful contract)."""
    with patch("opensdmx.hub.get_provider", return_value=_NON_HUB_PROVIDER):
        assert get_available_values_via_hub(_dataset(FREQ=1, REF_AREA=2)) == {}


def test_get_dimension_values_via_hub_returns_empty_when_provider_not_configured():
    """Direct call with a non-hub provider returns [] (graceful contract)."""
    with patch("opensdmx.hub.get_provider", return_value=_NON_HUB_PROVIDER):
        assert get_dimension_values_via_hub("DF_X", "REF_AREA") == []


# ── integration with discovery.get_available_values ───────────────────────

def test_get_available_values_uses_hub_when_enabled(tmp_path, monkeypatch):
    """When hub is enabled and returns values, the existing SDMX REST chain is skipped."""
    # Isolate cache so we don't hit a stale entry from a previous run.
    monkeypatch.setenv("OPENSDMX_CACHE_DIR", str(tmp_path))

    from opensdmx.discovery import get_available_values

    hub_payload = {"FREQ": ["A"], "REF_AREA": ["IT"]}

    sdmx_request_called = MagicMock()

    with patch("opensdmx.discovery.get_provider", return_value=_HUB_PROVIDER), \
         patch("opensdmx.db_cache.get_cached_available_constraints", return_value=None), \
         patch("opensdmx.db_cache.save_available_constraints"), \
         patch("opensdmx.hub.get_available_values_via_hub", return_value=hub_payload), \
         patch("opensdmx.discovery.sdmx_request_xml", side_effect=sdmx_request_called):
        result = get_available_values(_dataset(FREQ=1, REF_AREA=2))

    assert "FREQ" in result and "REF_AREA" in result
    assert result["REF_AREA"].to_series().to_list() == ["IT"]
    sdmx_request_called.assert_not_called()


def test_get_available_values_falls_through_when_hub_returns_empty():
    """Hub failure → existing chain runs unchanged."""
    from opensdmx.discovery import get_available_values

    fake_parsed = {"FREQ": ["A"]}

    with patch("opensdmx.discovery.get_provider", return_value=_HUB_PROVIDER), \
         patch("opensdmx.db_cache.get_cached_available_constraints", return_value=None), \
         patch("opensdmx.db_cache.save_available_constraints"), \
         patch("opensdmx.hub.get_available_values_via_hub", return_value={}), \
         patch("opensdmx.discovery.sdmx_request_xml", return_value=b"<xml/>"), \
         patch("opensdmx.discovery._parse_constraint_xml", return_value=fake_parsed):
        result = get_available_values(_dataset(FREQ=1, REF_AREA=2))

    assert "FREQ" in result


def test_get_available_values_skips_hub_for_non_hub_provider():
    """Non-hub providers (Eurostat etc.) never trigger hub code paths."""
    from opensdmx.discovery import get_available_values

    fake_parsed = {"FREQ": ["A"], "GEO": ["IT"]}
    hub_called = MagicMock()

    eurostat_provider = {
        "name": "Eurostat",
        "agency_id": "ESTAT",
        "language": "en",
        "constraint_endpoint": "contentconstraint",
        "constraint_params": {"references": "none"},
    }

    with patch("opensdmx.discovery.get_provider", return_value=eurostat_provider), \
         patch("opensdmx.db_cache.get_cached_available_constraints", return_value=None), \
         patch("opensdmx.db_cache.save_available_constraints"), \
         patch("opensdmx.hub.get_available_values_via_hub", side_effect=hub_called), \
         patch("opensdmx.discovery.sdmx_request_xml", return_value=b"<xml/>"), \
         patch("opensdmx.discovery._parse_constraint_xml", return_value=fake_parsed):
        get_available_values(_dataset(FREQ=1, GEO=2))

    hub_called.assert_not_called()
