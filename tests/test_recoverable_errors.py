"""Best-effort fallbacks catch only the failures they exist for.

Each site below used to catch `Exception` and fall back in silence, so a
network error, a damaged cache and a programming bug all looked the same.
Each pair of tests pins both halves: a recoverable failure (network, disk,
damaged cache) still takes the fallback, and a bug (`TypeError`) propagates.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import ExitStack
from unittest.mock import patch

import httpx
import polars as pl
import pytest
from typer.testing import CliRunner

from opensdmx.categories import _drop_stale
from opensdmx.cli import _category_of, app
from opensdmx.discovery import _resolve_codelist_from_concept, _with_category_context
from tests.test_cli import _fake_categories_dfs, _no_dsd_fetch, _siblings_catalog_df

runner = CliRunner()

_NETWORK = httpx.ConnectError("provider down")
_DAMAGED = pl.exceptions.ComputeError("parquet: invalid magic")
_BUG = TypeError("unexpected None")


# ── discovery._resolve_codelist_from_concept ─────────────────────────


def test_concept_codelist_network_error_warns_and_returns_none(caplog):
    with patch("opensdmx.discovery.sdmx_request_xml", side_effect=_NETWORK), \
         caplog.at_level(logging.WARNING, logger="opensdmx.discovery"):
        assert _resolve_codelist_from_concept("CS_X", "IMF", "FREQ") is None
    assert "Could not read concept scheme IMF/CS_X for the codelist of FREQ" in caplog.text


def test_concept_codelist_bug_propagates():
    with patch("opensdmx.discovery.sdmx_request_xml", side_effect=_BUG), \
         pytest.raises(TypeError):
        _resolve_codelist_from_concept("CS_X", "IMF", "FREQ")


# ── discovery._with_category_context ─────────────────────────────────


def test_search_category_context_damaged_cache_keeps_titles():
    datasets = pl.DataFrame({"df_id": ["DF_X"], "df_description": ["Desc"]})
    with patch("opensdmx.categories.category_context", side_effect=_DAMAGED):
        assert _with_category_context(datasets).equals(datasets)


def test_search_category_context_bug_propagates():
    datasets = pl.DataFrame({"df_id": ["DF_X"], "df_description": ["Desc"]})
    with patch("opensdmx.categories.category_context", side_effect=_BUG), \
         pytest.raises(TypeError):
        _with_category_context(datasets)


# ── cli._category_of ─────────────────────────────────────────────────


def test_category_label_damaged_cache_is_blank():
    with patch("opensdmx.categories.category_context", side_effect=_DAMAGED):
        assert _category_of("DF_X") == ""


def test_category_label_bug_propagates():
    with patch("opensdmx.categories.category_context", side_effect=_BUG), \
         pytest.raises(TypeError):
        _category_of("DF_X")


# ── categories._drop_stale ───────────────────────────────────────────


def test_drop_stale_unreadable_catalog_keeps_rows():
    _, categorisation = _fake_categories_dfs()
    with patch("opensdmx.discovery._load_cached_dataflows", side_effect=OSError("disk")):
        assert _drop_stale(categorisation).equals(categorisation)


def test_drop_stale_bug_propagates():
    _, categorisation = _fake_categories_dfs()
    with patch("opensdmx.discovery._load_cached_dataflows", side_effect=_BUG), \
         pytest.raises(TypeError):
        _drop_stale(categorisation)


# ── cli tree --show-dataflows ────────────────────────────────────────


def _invoke_tree(all_available_error):
    with patch("opensdmx.cli._check_api_reachable"), \
         patch("opensdmx.categories.load_categories", return_value=_fake_categories_dfs()), \
         patch("opensdmx.discovery.all_available", side_effect=all_available_error):
        return runner.invoke(
            app, ["tree", "--scheme", "S1", "--show-dataflows", "--provider", "istat"]
        )


def test_tree_dataflows_catalog_outage_warns_and_blanks_descriptions():
    result = _invoke_tree(_NETWORK)
    assert result.exit_code == 0, result.output
    assert "[df:DF_X]" in result.stdout
    assert "dataflow catalog unavailable, descriptions left blank" in result.stderr


def test_tree_dataflows_bug_propagates():
    result = _invoke_tree(_BUG)
    assert isinstance(result.exception, TypeError)


# ── cli siblings: catalog load and hidden-id reload ──────────────────


def _invoke_siblings(*, all_available=None, resolve=None):
    with ExitStack() as stack:
        stack.enter_context(patch("opensdmx.cli._check_api_reachable"))
        stack.enter_context(
            patch("opensdmx.categories.load_categories", return_value=_fake_categories_dfs())
        )
        stack.enter_context(patch("opensdmx.discovery._get_dimensions", side_effect=_no_dsd_fetch))
        if all_available is None:
            stack.enter_context(
                patch("opensdmx.discovery.all_available", return_value=_siblings_catalog_df())
            )
        else:
            stack.enter_context(patch("opensdmx.discovery.all_available", side_effect=all_available))
        if resolve is not None:
            stack.enter_context(patch("opensdmx.discovery.resolve_dataflow", side_effect=resolve))
        return runner.invoke(app, ["siblings", "df_x", "--provider", "istat"])


def test_siblings_catalog_bug_propagates():
    result = _invoke_siblings(all_available=_BUG)
    assert isinstance(result.exception, TypeError)


def test_siblings_reload_failure_warns_and_uses_raw_id():
    result = _invoke_siblings(resolve=_NETWORK)
    assert result.exit_code == 0, result.output
    assert "DF_X" in result.stdout
    assert "dataflow catalog reload failed, using the ID as given" in result.stderr


def test_siblings_reload_bug_propagates():
    result = _invoke_siblings(resolve=_BUG)
    assert isinstance(result.exception, TypeError)


def test_siblings_locked_cache_db_falls_back():
    """sqlite3 errors are not OSError: a locked cache.db must still fall back."""
    result = _invoke_siblings(all_available=sqlite3.OperationalError("database is locked"))
    assert result.exit_code == 0, result.output
    assert "dataflow catalog unavailable" in result.stderr


def test_siblings_reload_bad_json_is_not_reported_as_not_found():
    """A malformed hub reply (JSONDecodeError is a ValueError) is a reload
    failure, not "ID not found"."""
    result = _invoke_siblings(resolve=json.JSONDecodeError("Expecting value", "", 0))
    assert result.exit_code == 0, result.output
    assert "dataflow catalog reload failed" in result.stderr
