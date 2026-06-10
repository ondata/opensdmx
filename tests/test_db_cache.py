"""Tests for opensdmx.db_cache – SQLite cache operations with an isolated temp DB."""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest
from opensdmx import db_cache


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    """Redirect db_cache to a temporary SQLite database for every test."""
    db_file = tmp_path / "test_cache.db"
    monkeypatch.setattr(db_cache, "_get_db_path", lambda: db_file)
    monkeypatch.setattr(db_cache, "_INITIALIZED_DBS", set())


# ── cross-provider schema init (issue #42) ───────────────────────────

def test_schema_init_per_db_path(tmp_path, monkeypatch):
    """Switching DB path (new provider) must re-create the schema.

    Regression for issue #42: a global init flag skipped schema creation on
    the second provider, raising 'no such table: invalid_datasets'.
    """
    monkeypatch.setattr(db_cache, "_INITIALIZED_DBS", set())
    db_a = tmp_path / "a" / "cache.db"
    db_b = tmp_path / "b" / "cache.db"
    db_a.parent.mkdir()
    db_b.parent.mkdir()

    monkeypatch.setattr(db_cache, "_get_db_path", lambda: db_a)
    assert db_cache.get_invalid_dataset_ids() == set()

    # Second provider — a brand new DB file must still have the schema.
    monkeypatch.setattr(db_cache, "_get_db_path", lambda: db_b)
    assert db_cache.get_invalid_dataset_ids() == set()


# ── structure dims ───────────────────────────────────────────────────

def test_save_and_get_dims():
    dims = {
        "FREQ": {"id": "FREQ", "position": 1, "codelist_id": "CL_FREQ"},
        "GEO": {"id": "GEO", "position": 2, "codelist_id": "CL_GEO"},
    }
    db_cache.save_dims("DSD_TEST", dims)
    result = db_cache.get_cached_dims("DSD_TEST")
    assert result is not None
    assert set(result.keys()) == {"FREQ", "GEO"}
    assert result["FREQ"]["codelist_id"] == "CL_FREQ"
    assert result["GEO"]["position"] == 2


def test_get_dims_not_cached():
    assert db_cache.get_cached_dims("NONEXISTENT") is None


def test_get_dims_expired(monkeypatch):
    dims = {"X": {"id": "X", "position": 1, "codelist_id": None}}
    db_cache.save_dims("DSD_OLD", dims)
    # Simulate expired cache by setting TTL to 0
    monkeypatch.setattr(db_cache, "METADATA_CACHE_TTL", 0)
    assert db_cache.get_cached_dims("DSD_OLD") is None


# ── codelist info ────────────────────────────────────────────────────

def test_save_and_get_codelist_info():
    db_cache.save_codelist_info("CL_FREQ", "Frequency codelist")
    assert db_cache.is_codelist_info_cached("CL_FREQ") is True
    assert db_cache.get_cached_codelist_info("CL_FREQ") == "Frequency codelist"


def test_codelist_info_not_cached():
    assert db_cache.is_codelist_info_cached("NONEXISTENT") is False
    assert db_cache.get_cached_codelist_info("NONEXISTENT") is None


def test_codelist_info_expired(monkeypatch):
    db_cache.save_codelist_info("CL_OLD", "Old")
    monkeypatch.setattr(db_cache, "METADATA_CACHE_TTL", 0)
    assert db_cache.is_codelist_info_cached("CL_OLD") is False


# ── codelist values ──────────────────────────────────────────────────

def test_save_and_get_codelist_values():
    values = [
        {"id": "A", "name": "Annual"},
        {"id": "M", "name": "Monthly"},
    ]
    db_cache.save_codelist_values("CL_FREQ", values)
    result = db_cache.get_cached_codelist_values("CL_FREQ")
    assert result is not None
    assert len(result) == 2
    assert result[0]["id"] == "A"
    assert result[1]["name"] == "Monthly"


def test_codelist_values_not_cached():
    assert db_cache.get_cached_codelist_values("NONEXISTENT") is None


# ── available constraints ────────────────────────────────────────────

def test_save_and_get_constraints():
    constraints = {
        "FREQ": ["A", "M", "Q"],
        "GEO": ["IT", "DE"],
    }
    db_cache.save_available_constraints("une_rt_m", constraints)
    result = db_cache.get_cached_available_constraints("une_rt_m")
    assert result is not None
    assert set(result["FREQ"]) == {"A", "M", "Q"}
    assert set(result["GEO"]) == {"IT", "DE"}


def test_constraints_not_cached():
    assert db_cache.get_cached_available_constraints("NONEXISTENT") is None


def test_constraints_expired(monkeypatch):
    db_cache.save_available_constraints("df_old", {"X": ["1"]})
    monkeypatch.setattr(db_cache, "CONSTRAINTS_CACHE_TTL", 0)
    assert db_cache.get_cached_available_constraints("df_old") is None


def test_constraints_overwrite():
    db_cache.save_available_constraints("df_x", {"A": ["1", "2"]})
    db_cache.save_available_constraints("df_x", {"A": ["3"]})
    result = db_cache.get_cached_available_constraints("df_x")
    assert result["A"] == ["3"]


# ── invalid datasets ────────────────────────────────────────────────

def test_save_and_list_invalid():
    db_cache.save_invalid_dataset("BAD_DF", "broken")
    ids = db_cache.get_invalid_dataset_ids()
    assert "BAD_DF" in ids
    items = db_cache.list_invalid_datasets()
    assert any(d["df_id"] == "BAD_DF" for d in items)


def test_delete_invalid():
    db_cache.save_invalid_dataset("TO_DELETE")
    result = db_cache.delete_invalid_dataset("TO_DELETE")
    assert result is True
    assert "TO_DELETE" not in db_cache.get_invalid_dataset_ids()


def test_delete_invalid_nonexistent():
    result = db_cache.delete_invalid_dataset("DOES_NOT_EXIST")
    assert result is False


def test_invalid_empty():
    assert db_cache.get_invalid_dataset_ids() == set()
    assert db_cache.list_invalid_datasets() == []
