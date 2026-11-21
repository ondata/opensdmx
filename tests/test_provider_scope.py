"""Scoped provider (`use_provider`) and saved queries that leave the caller's provider alone.

Design: `docs/design-provider-context.md`. Test names carry the acceptance-test ids.
"""

from __future__ import annotations

import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import httpx
import polars as pl
import pytest
import yaml

import opensdmx
from opensdmx import base
from opensdmx.base import (
    _bound_to_dataset,
    _build_provider,
    _provider_scope,
    _rate_limit_lock_file,
    get_cache_dir,
    get_provider,
    sdmx_request,
    set_provider,
    use_provider,
)
from tests.test_auth import _data_client

A = "https://a.example/rest"
B = "https://b.example/rest"


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    """Own cache base per test (no test served from another's cache), default restored."""
    monkeypatch.setenv("OPENSDMX_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("OPENSDMX_PROVIDER", raising=False)
    monkeypatch.delenv("OPENSDMX_AGENCY", raising=False)
    yield
    set_provider("eurostat")


def _url() -> str:
    return get_provider()["base_url"]


# ── A2: scope semantics ──────────────────────────────────────────────


def test_a2_scope_is_active_inside_and_restored_after():
    set_provider(A, agency_id="A")
    with use_provider(B, agency_id="B"):
        assert _url() == B
    assert _url() == A


def test_a2_nested_scopes_restore_in_order():
    with use_provider("istat"):
        with use_provider("ecb"):
            assert get_provider() is base.PROVIDERS["ecb"]
        assert get_provider() is base.PROVIDERS["istat"]
    assert get_provider() is base.PROVIDERS["eurostat"]


def test_a2_exception_inside_restores():
    with pytest.raises(RuntimeError):
        with use_provider("istat"):
            raise RuntimeError("boom")
    assert get_provider() is base.PROVIDERS["eurostat"]


def test_a2_invalid_name_raises_at_the_call_and_sets_nothing():
    with pytest.raises(ValueError, match="unknown provider 'nope'"):
        use_provider("nope")
    assert base._scoped_provider.get() is None


def test_a2_alias_resolves_like_the_cli():
    with use_provider("estat"):
        assert get_provider() is base.PROVIDERS["eurostat"]


def test_a2_asyncio_task_sees_the_scope():
    async def read() -> str:
        return await asyncio.create_task(asyncio.sleep(0, result=_url()))

    with use_provider(B, agency_id="B"):
        assert asyncio.run(read()) == B


# ── A3, A4: threads ──────────────────────────────────────────────────


def test_a3_two_threads_two_scopes_request_their_own_host():
    hosts: dict[str, list[str]] = {"a.example": [], "b.example": []}
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.host)
        return httpx.Response(200, text="ok")

    def worker(url: str, agency: str) -> None:
        with _provider_scope(_build_provider(url, agency_id=agency, rate_limit=0.0)):
            sdmx_request("dataflow/X")
            hosts[httpx.URL(url).host].append(_url())

    with _data_client(handler):
        threads = [
            threading.Thread(target=worker, args=(A, "A")),
            threading.Thread(target=worker, args=(B, "B")),
        ]
        [t.start() for t in threads]
        [t.join() for t in threads]

    assert sorted(seen) == ["a.example", "b.example"]
    assert hosts == {"a.example": [A], "b.example": [B]}


def test_a4_thread_without_scope_sees_the_set_provider_default():
    set_provider(A, agency_id="A")
    seen: list[str] = []
    t = threading.Thread(target=lambda: seen.append(_url()))
    t.start()
    t.join()
    assert seen == [A]


# ── A5: set_provider inside a scope ──────────────────────────────────


def test_a5_set_provider_inside_a_scope_changes_only_the_default():
    with use_provider(A, agency_id="A"):
        set_provider(B, agency_id="B")
        assert _url() == A
    assert _url() == B


# ── A6: rate limit across threads ────────────────────────────────────


def test_a6_threads_on_one_provider_are_paced():
    set_provider(A, agency_id="A", rate_limit=0.2)
    sends: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sends.append(time.monotonic())
        return httpx.Response(200, text="ok")

    with _data_client(handler):
        threads = [threading.Thread(target=lambda: sdmx_request("dataflow/X")) for _ in range(2)]
        [t.start() for t in threads]
        [t.join() for t in threads]

    sends.sort()
    assert len(sends) == 2
    assert sends[1] - sends[0] >= 0.2 - 0.01  # timer granularity


# ── A8: cache directory and lock follow the scope ────────────────────


@pytest.mark.parametrize("default", ["eurostat", B], ids=["preset_default", "custom_default"])
def test_a8_cache_dir_and_lock_file_follow_the_scope(default):
    """A preset default is the case the old direct read of `_active_provider` got wrong."""
    set_provider(default, agency_id="B")
    default_dir, default_lock = get_cache_dir(), _rate_limit_lock_file()
    with use_provider(A, agency_id="A"):
        assert get_cache_dir().name == "A"
        assert _rate_limit_lock_file().name.startswith("A.")
    assert get_cache_dir() == default_dir and default_dir.name == ("eurostat" if default == "eurostat" else "B")
    assert _rate_limit_lock_file() == default_lock


def test_a8_two_scoped_threads_use_two_lock_files():
    locks: dict[str, str] = {}

    def worker(url: str, agency: str) -> None:
        with _provider_scope(_build_provider(url, agency_id=agency, rate_limit=0.0)):
            locks[agency] = _rate_limit_lock_file().name

    threads = [threading.Thread(target=worker, args=(A, "A")), threading.Thread(target=worker, args=(B, "B"))]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert locks["A"] != locks["B"]


# ── A7: run_query runs on the file's provider, caller unchanged ──────


def _spy_run_query(monkeypatch):
    """Run the real run_query with the provider-dependent steps recorded."""
    calls: list[tuple[str, str]] = []
    ds = {"df_id": "DF", "filters": {}, "dimensions": {}}

    def load_dataset(dataset_id):
        calls.append(("load_dataset", _url()))
        return ds

    def get_data(dataset, **_):
        calls.append(("get_data", _url()))
        return pl.DataFrame({"OBS_VALUE": [1.0]})

    def enrich_with_labels(dataset, data):
        calls.append(("enrich_with_labels", _url()))
        return data

    monkeypatch.setattr("opensdmx.retrieval.load_dataset", load_dataset)
    monkeypatch.setattr("opensdmx.retrieval.get_data", get_data)
    monkeypatch.setattr("opensdmx.retrieval.enrich_with_labels", enrich_with_labels)
    return calls


def _write(tmp_path, query: dict) -> str:
    path = tmp_path / "q.yaml"
    path.write_text(yaml.dump(query))
    return str(path)


@pytest.mark.parametrize(
    "query, kwargs, env, expected",
    [
        ({"dataset": "DF", "provider_url": B, "agency_id": "B"}, {}, None, B),
        ({"dataset": "DF", "provider": "bundesbank"}, {}, None, base.PROVIDERS["bundesbank"]["base_url"]),
        ({"dataset": "DF"}, {"provider": B}, None, B),
        ({"dataset": "DF"}, {}, B, B),
        ({"dataset": "DF", "provider_url": B, "agency_id": "B", "labels": True}, {}, None, B),
    ],
    ids=["provider_url", "alias", "argument", "env", "labels"],
)
def test_a7_run_query_uses_the_file_provider_and_leaves_the_caller_alone(
    tmp_path, monkeypatch, query, kwargs, env, expected
):
    if env:
        monkeypatch.setenv("OPENSDMX_PROVIDER", env)
        monkeypatch.setenv("OPENSDMX_AGENCY", "B")
    calls = _spy_run_query(monkeypatch)
    set_provider(A, agency_id="A")
    with use_provider(A, agency_id="A"):
        opensdmx.run_query(_write(tmp_path, query), **kwargs)
        assert _url() == A
    assert _url() == A
    steps = ["load_dataset", "get_data"] + (["enrich_with_labels"] if query.get("labels") else [])
    assert calls == [(step, expected) for step in steps]


def test_a7_run_query_without_provider_runs_on_the_current_one(tmp_path, monkeypatch):
    calls = _spy_run_query(monkeypatch)
    with use_provider(A, agency_id="A"):
        opensdmx.run_query(_write(tmp_path, {"dataset": "DF"}))
    assert calls == [("load_dataset", A), ("get_data", A)]


def test_a6_cold_cache_threads_resolve_the_same_cache_base(tmp_path, monkeypatch):
    """Two threads resolving the cache base at once must agree on it, or one of them
    takes another rate-limit lock and its first request is not paced. The probe file
    used to have a fixed name, so the two threads could unlink each other's probe."""
    for i in range(400):
        cache = tmp_path / f"c{i}"
        cache.mkdir()
        monkeypatch.setenv("OPENSDMX_CACHE_DIR", str(cache))  # cold: a new cache key
        start = threading.Barrier(2)
        bases: list[str] = []

        def resolve() -> None:
            start.wait()
            bases.append(str(base._resolve_cache_base()))

        threads = [threading.Thread(target=resolve) for _ in range(2)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        assert bases == [str(cache), str(cache)]


# ── Phase 2: a dataset carries its provider (A1, A8, A9, A10) ────────

_DIMS = {"FREQ": {"id": "FREQ", "position": 1, "codelist_id": "CL_FREQ"}}


def _load(url: str, agency: str) -> dict:
    """A dataset loaded under a custom provider, with catalog and DSD stubbed."""
    row = {"df_id": "DF", "version": "1.0", "df_description": "d", "df_structure_id": "DSD"}
    set_provider(url, agency_id=agency, rate_limit=0.0)
    with patch("opensdmx.discovery.resolve_dataflow", return_value=row), \
         patch("opensdmx.discovery._get_dimensions", return_value=_DIMS):
        return opensdmx.load_dataset("DF")


def _hosts_of(call) -> list[str]:
    hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hosts.append(request.url.host)
        return httpx.Response(404, text="not found")

    with _data_client(handler):
        try:
            call()
        except Exception:  # the 404 may surface as an error; only the host matters
            pass
    return hosts


def test_load_dataset_records_its_provider():
    row = {"df_id": "DF", "version": "1.0", "df_description": "d", "df_structure_id": "DSD"}
    with patch("opensdmx.discovery.resolve_dataflow", return_value=row), \
         patch("opensdmx.discovery._get_dimensions", return_value=_DIMS):
        set_provider("bundesbank")
        assert opensdmx.load_dataset("DF")["provider"] == "bundesbank"
        set_provider(A, agency_id="A")
        ds = opensdmx.load_dataset("DF")
    assert ds["provider"] == base._active_provider
    assert ds["provider"] is not base._active_provider


@pytest.mark.parametrize(
    "call",
    [
        lambda ds: opensdmx.dimensions_info(ds),
        lambda ds: opensdmx.get_dimension_values(ds, "FREQ"),
        lambda ds: opensdmx.get_codelist_hierarchy(ds, "FREQ"),
        lambda ds: opensdmx.get_available_values(ds),
        lambda ds: opensdmx.get_data(ds),
        lambda ds: opensdmx.enrich_with_labels(ds, pl.DataFrame({"FREQ": ["A"], "OBS_VALUE": [1.0]})),
    ],
    ids=["dimensions_info", "get_dimension_values", "get_codelist_hierarchy",
         "get_available_values", "get_data", "enrich_with_labels"],
)
def test_a1_bound_functions_request_the_dataset_provider(call):
    ds = _load(A, "A")
    set_provider(B, agency_id="B", rate_limit=0.0)  # a different default
    hosts = _hosts_of(lambda: call(ds))
    assert hosts and set(hosts) == {"a.example"}


def test_a8_cache_dir_follows_the_dataset_inside_a_bound_call():
    @_bound_to_dataset
    def cache_name(dataset):
        return get_cache_dir().name

    ds = _load(A, "A")
    set_provider(B, agency_id="B")
    with use_provider("eurostat"):
        assert cache_name(ds) == "A"  # the dataset wins over the scope too
        assert cache_name(dataset=ds) == "A"  # bound when passed by keyword
    assert get_cache_dir().name == "B"


def test_a9_dataset_without_provider_uses_the_current_one():
    @_bound_to_dataset
    def url(dataset):
        return _url()

    set_provider(B, agency_id="B")
    assert url({"df_id": "DF"}) == B


def test_a9_unknown_stored_preset_raises():
    @_bound_to_dataset
    def noop(dataset):
        return None

    with pytest.raises(ValueError, match="unknown provider 'gone' stored in dataset"):
        noop({"provider": "gone"})
    with pytest.raises(TypeError):
        noop({"provider": 42})


def test_a9_filters_keep_the_provider_key():
    ds = _load(A, "A")
    assert opensdmx.set_filters(ds, FREQ="A")["provider"] == ds["provider"]
    assert opensdmx.reset_filters(ds)["provider"] == ds["provider"]


def test_a10_datasets_mapped_over_a_pool_request_their_own_host():
    ds_a, ds_b = _load(A, "A"), _load(B, "B")
    set_provider("eurostat")
    hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hosts.append(request.url.host)
        return httpx.Response(404, text="not found")

    def fetch(ds):
        try:
            opensdmx.get_data(ds)
        except Exception:
            pass

    with _data_client(handler), ThreadPoolExecutor(2) as pool:
        list(pool.map(fetch, [ds_a, ds_b]))
    assert sorted(set(hosts)) == ["a.example", "b.example"]


def test_a1_saved_query_records_the_dataset_provider():
    """`get --query-file` writes the provider of the dataset, not the active one."""
    from opensdmx.utils import build_query_dict

    ds = _load(A, "A")
    set_provider(B, agency_id="B")
    query = build_query_dict(ds, {})
    assert (query["provider_url"], query["agency_id"]) == (A, "A")
