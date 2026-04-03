"""Tests for parse_time_period – SDMX time period string parsing."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest
from opensdmx.retrieval import parse_time_period


def _parse(values: list[str | None]) -> list[date | None]:
    """Helper: parse a list of time-period strings and return dates."""
    s = pl.Series("tp", values, dtype=pl.Utf8)
    result = parse_time_period(s)
    return result.to_list()


# ── Annual ───────────────────────────────────────────────────────────

def test_annual():
    assert _parse(["2023"]) == [date(2023, 1, 1)]


# ── Monthly ──────────────────────────────────────────────────────────

def test_monthly():
    assert _parse(["2023-06"]) == [date(2023, 6, 1)]


# ── Quarterly ────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "value, expected",
    [
        ("2023-Q1", date(2023, 1, 1)),
        ("2023-Q2", date(2023, 4, 1)),
        ("2023-Q3", date(2023, 7, 1)),
        ("2023-Q4", date(2023, 10, 1)),
    ],
)
def test_quarterly(value, expected):
    assert _parse([value]) == [expected]


# ── Semester ─────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "value, expected",
    [
        ("2023-S1", date(2023, 1, 1)),
        ("2023-S2", date(2023, 7, 1)),
    ],
)
def test_semester(value, expected):
    assert _parse([value]) == [expected]


# ── Weekly ───────────────────────────────────────────────────────────

def test_weekly():
    results = _parse(["2023-W01"])
    assert results[0] is not None
    assert results[0].year == 2023
    assert results[0].month == 1


# ── Daily ────────────────────────────────────────────────────────────

def test_daily():
    assert _parse(["2023-06-15"]) == [date(2023, 6, 15)]


# ── None / invalid ──────────────────────────────────────────────────

def test_none_value():
    assert _parse([None]) == [None]


def test_invalid_value():
    assert _parse(["not-a-date"]) == [None]


# ── Mixed series ─────────────────────────────────────────────────────

def test_mixed_series():
    results = _parse(["2023", "2023-Q2", "2023-06-15", None])
    assert results == [date(2023, 1, 1), date(2023, 4, 1), date(2023, 6, 15), None]
