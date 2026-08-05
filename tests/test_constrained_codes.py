"""Tests for discovery.constrained_codes – pure logic, no HTTP (issue #67)."""

from __future__ import annotations

import polars as pl
from opensdmx.discovery import constrained_codes


def test_dataframe_shape() -> None:
    """The {dim: DataFrame} shape returned by get_available_values."""
    avail = {"unit": pl.DataFrame({"id": ["RCH_A"]}), "geo": pl.DataFrame({"id": ["IT", "FR"]})}
    assert constrained_codes(avail, "unit") == {"RCH_A"}
    assert constrained_codes(avail, "geo") == {"IT", "FR"}


def test_list_shape() -> None:
    """The {dim: [codes]} shape stored in the SQLite cache."""
    avail = {"unit": ["RCH_A"], "geo": ["IT", "FR"]}
    assert constrained_codes(avail, "unit") == {"RCH_A"}


def test_dimension_matching_is_case_and_dash_insensitive() -> None:
    avail = {"NA_ITEM": ["B1GQ"]}
    assert constrained_codes(avail, "na_item") == {"B1GQ"}
    assert constrained_codes(avail, "na-item") == {"B1GQ"}
    assert constrained_codes({"na_item": ["B1GQ"]}, "NA_ITEM") == {"B1GQ"}


def test_dimension_absent_returns_none() -> None:
    """Absent must not read as 'no valid codes': contentconstraint omits dimensions."""
    assert constrained_codes({"freq": ["Q"]}, "citizen") is None


def test_no_constraints_returns_none() -> None:
    assert constrained_codes(None, "unit") is None
    assert constrained_codes({}, "unit") is None


def test_empty_codes_return_none() -> None:
    """An empty entry carries no information — same as an absent one."""
    assert constrained_codes({"unit": []}, "unit") is None
    assert constrained_codes({"unit": pl.DataFrame({"id": []})}, "unit") is None


def test_dataframe_without_id_column_returns_none() -> None:
    assert constrained_codes({"unit": pl.DataFrame({"code": ["RCH_A"]})}, "unit") is None
