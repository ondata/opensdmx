"""Tests for opensdmx.discovery – set_filters / reset_filters (pure logic, no HTTP)."""

from __future__ import annotations

import pytest
from opensdmx.discovery import get_dimension_values, reset_filters, set_filters


def _make_dataset(**dims) -> dict:
    """Build a minimal dataset dict for testing filter logic."""
    dimensions = {
        d: {"id": d, "position": i, "codelist_id": None}
        for i, d in enumerate(dims or ["FREQ", "GEO", "AGE"])
    }
    filters = {d: "." for d in dimensions}
    return {
        "df_id": "TEST_DF",
        "version": "1.0",
        "df_description": "Test dataset",
        "df_structure_id": "TEST_DSD",
        "dimensions": dimensions,
        "filters": filters,
    }


# ── set_filters ──────────────────────────────────────────────────────

def test_set_filters_basic():
    ds = _make_dataset(FREQ=0, GEO=1, AGE=2)
    result = set_filters(ds, FREQ="A", GEO="IT")
    assert result["filters"]["FREQ"] == "A"
    assert result["filters"]["GEO"] == "IT"
    assert result["filters"]["AGE"] == "."


def test_set_filters_case_insensitive():
    ds = _make_dataset(FREQ=0, GEO=1)
    result = set_filters(ds, freq="M", geo="DE")
    assert result["filters"]["FREQ"] == "M"
    assert result["filters"]["GEO"] == "DE"


def test_set_filters_returns_copy():
    ds = _make_dataset(FREQ=0, GEO=1)
    result = set_filters(ds, FREQ="A")
    assert result is not ds
    assert ds["filters"]["FREQ"] == "."  # original unchanged


def test_set_filters_list_value():
    ds = _make_dataset(GEO=0)
    result = set_filters(ds, GEO=["IT", "FR", "DE"])
    assert result["filters"]["GEO"] == ["IT", "FR", "DE"]


def test_set_filters_unknown_dimension_warns(caplog):
    import logging
    ds = _make_dataset(FREQ=0)
    with caplog.at_level(logging.WARNING, logger="opensdmx.discovery"):
        result = set_filters(ds, NONEXISTENT="X")
    assert any("NONEXISTENT" in r.message for r in caplog.records)
    assert "NONEXISTENT" not in result["filters"]


# ── get_dimension_values ─────────────────────────────────────────────

def test_get_dimension_values_case_insensitive():
    """get_dimension_values should accept dimension IDs regardless of case."""
    ds = _make_dataset(FREQ=0, GEO=1)
    # Add a codelist_id so it doesn't fail on missing codelist
    ds["dimensions"]["FREQ"]["codelist_id"] = None
    # Should raise ValueError for unknown dim, not for wrong case
    with pytest.raises(ValueError, match="not found"):
        get_dimension_values(ds, "NONEXISTENT")
    # Wrong case should NOT raise — it resolves to the actual key
    with pytest.raises(ValueError, match="not found"):
        get_dimension_values(ds, "NONEXISTENT_DIM")
    # Lowercase of existing dim should not raise ValueError
    try:
        get_dimension_values(ds, "freq")
    except ValueError as e:
        pytest.fail(f"get_dimension_values raised ValueError for 'freq': {e}")


# ── reset_filters ────────────────────────────────────────────────────

def test_reset_filters():
    ds = _make_dataset(FREQ=0, GEO=1)
    ds = set_filters(ds, FREQ="A", GEO="IT")
    result = reset_filters(ds)
    assert result["filters"]["FREQ"] == "."
    assert result["filters"]["GEO"] == "."


def test_reset_filters_returns_copy():
    ds = _make_dataset(FREQ=0)
    ds_filtered = set_filters(ds, FREQ="A")
    result = reset_filters(ds_filtered)
    assert result is not ds_filtered
    assert ds_filtered["filters"]["FREQ"] == "A"  # original unchanged


# ── contentconstraint 404 → availableconstraint fallback ─────────────────

import httpx
from unittest.mock import patch

_ISTAT_PROVIDER = {
    "name": "ISTAT",
    "base_url": "https://esploradati.istat.it/SDMXWS/rest",
    "agency_id": "IT1",
    "rate_limit": 15.0,
    "language": "it",
    "constraint_endpoint": "contentconstraint",
    "constraint_fallback_timeout": 30,
    "constraint_params": {"references": "none"},
}


def _istat_dataset():
    dims = {
        "FREQ": {"id": "FREQ", "position": 1, "codelist_id": "CL_FREQ"},
        "REF_AREA": {"id": "REF_AREA", "position": 2, "codelist_id": "CL_AREA"},
        "DATA_TYPE": {"id": "DATA_TYPE", "position": 3, "codelist_id": "CL_DATA"},
    }
    return {
        "df_id": "TEST_ISTAT_DF",
        "version": "1.0",
        "df_description": "Test ISTAT Dataset",
        "df_structure_id": "TEST_DSD",
        "dimensions": dims,
        "filters": {d: "." for d in dims},
    }


def _http_404():
    req = httpx.Request("GET", "http://x")
    resp = httpx.Response(404, request=req)
    return httpx.HTTPStatusError("404", request=req, response=resp)


def test_get_available_values_contentconstraint_200():
    """contentconstraint returns 200 — normal path, no fallback."""
    from opensdmx.discovery import get_available_values

    fake_parsed = {"FREQ": ["A"], "DATA_TYPE": ["VAL1"]}

    with patch("opensdmx.discovery.get_provider", return_value=_ISTAT_PROVIDER), \
         patch("opensdmx.db_cache.get_cached_available_constraints", return_value=None), \
         patch("opensdmx.db_cache.save_available_constraints"), \
         patch("opensdmx.discovery.sdmx_request_xml", return_value=b"<xml/>") as mock_req, \
         patch("opensdmx.discovery._parse_constraint_xml", return_value=fake_parsed):
        result = get_available_values(_istat_dataset())

    assert set(result.keys()) == {"FREQ", "DATA_TYPE"}
    called_path = mock_req.call_args[0][0]
    assert called_path.startswith("contentconstraint/")


def test_get_available_values_contentconstraint_404_fallback_success():
    """contentconstraint returns 404 → falls back to availableconstraint successfully."""
    from opensdmx.discovery import get_available_values

    fallback_parsed = {"FREQ": ["A"], "REF_AREA": ["082053", "ITG12"], "DATA_TYPE": ["INC"]}

    def fake_request(path, **kwargs):
        if "contentconstraint" in path:
            raise _http_404()
        return b"<xml/>"

    with patch("opensdmx.discovery.get_provider", return_value=_ISTAT_PROVIDER), \
         patch("opensdmx.db_cache.get_cached_available_constraints", return_value=None), \
         patch("opensdmx.db_cache.save_available_constraints"), \
         patch("opensdmx.discovery.sdmx_request_xml", side_effect=fake_request), \
         patch("opensdmx.discovery._parse_constraint_xml", return_value=fallback_parsed):
        result = get_available_values(_istat_dataset())

    assert "REF_AREA" in result
    assert result["REF_AREA"].to_series().to_list() == ["082053", "ITG12"]


def test_get_available_values_contentconstraint_404_both_fallbacks_timeout():
    """contentconstraint 404 → availableconstraint timeout → serieskeysonly timeout → ConstraintsTimeout raised."""
    from opensdmx.discovery import ConstraintsTimeout, get_available_values

    def fake_xml_request(path, **kwargs):
        if "contentconstraint" in path:
            raise _http_404()
        raise httpx.TimeoutException("timeout")

    with patch("opensdmx.discovery.get_provider", return_value=_ISTAT_PROVIDER), \
         patch("opensdmx.db_cache.get_cached_available_constraints", return_value=None), \
         patch("opensdmx.db_cache.save_available_constraints"), \
         patch("opensdmx.discovery.sdmx_request_xml", side_effect=fake_xml_request), \
         patch("opensdmx.base.sdmx_request", side_effect=httpx.TimeoutException("timeout")):
        with pytest.raises(ConstraintsTimeout):
            get_available_values(_istat_dataset())


# ── _parse_serieskeys_xml ─────────────────────────────────────────────

_SERIESKEYS_XML = b"""<?xml version="1.0" encoding="utf-8"?>
<message:GenericData
  xmlns:generic="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/data/generic"
  xmlns:message="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message">
  <message:DataSet>
    <generic:Series>
      <generic:SeriesKey>
        <generic:Value id="FREQ" value="A"/>
        <generic:Value id="REF_AREA" value="082053"/>
        <generic:Value id="DATA_TYPE" value="KILLINJ"/>
        <generic:Value id="RESULT" value="F"/>
      </generic:SeriesKey>
    </generic:Series>
    <generic:Series>
      <generic:SeriesKey>
        <generic:Value id="FREQ" value="A"/>
        <generic:Value id="REF_AREA" value="082053"/>
        <generic:Value id="DATA_TYPE" value="KILLINJ"/>
        <generic:Value id="RESULT" value="M"/>
      </generic:SeriesKey>
    </generic:Series>
    <generic:Series>
      <generic:SeriesKey>
        <generic:Value id="FREQ" value="A"/>
        <generic:Value id="REF_AREA" value="082053"/>
        <generic:Value id="DATA_TYPE" value="ROADACC"/>
        <generic:Value id="RESULT" value="9"/>
      </generic:SeriesKey>
    </generic:Series>
  </message:DataSet>
</message:GenericData>"""


def test_parse_serieskeys_xml():
    from opensdmx.discovery import _parse_serieskeys_xml
    result = _parse_serieskeys_xml(_SERIESKEYS_XML)
    assert result["FREQ"] == ["A"]
    assert result["REF_AREA"] == ["082053"]
    assert result["DATA_TYPE"] == ["KILLINJ", "ROADACC"]
    assert result["RESULT"] == ["9", "F", "M"]


def test_get_available_values_serieskeysonly_fallback():
    """contentconstraint 404 → availableconstraint timeout → serieskeysonly succeeds."""
    from unittest.mock import MagicMock
    from opensdmx.discovery import get_available_values

    def fake_xml_request(path, **kwargs):
        if "contentconstraint" in path:
            raise _http_404()
        raise httpx.TimeoutException("timeout")

    fake_resp = MagicMock()
    fake_resp.content = _SERIESKEYS_XML

    with patch("opensdmx.discovery.get_provider", return_value=_ISTAT_PROVIDER), \
         patch("opensdmx.db_cache.get_cached_available_constraints", return_value=None), \
         patch("opensdmx.db_cache.save_available_constraints"), \
         patch("opensdmx.discovery.sdmx_request_xml", side_effect=fake_xml_request), \
         patch("opensdmx.base.sdmx_request", return_value=fake_resp):
        result = get_available_values(_istat_dataset())

    assert "FREQ" in result
    assert "DATA_TYPE" in result
    assert result["DATA_TYPE"].to_series().to_list() == ["KILLINJ", "ROADACC"]


# ── get_dimension_values — language handling ──────────────────────────

_BILINGUAL_CODELIST_XML = b"""<?xml version="1.0" encoding="utf-8"?>
<message:Structure
  xmlns:message="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message"
  xmlns:structure="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure"
  xmlns:common="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common"
  xmlns:xml="http://www.w3.org/XML/1998/namespace">
  <message:Structures>
    <structure:Codelists>
      <structure:Codelist id="CL_TIPO_ALLOGGIO2" agencyID="IT1" version="1.0">
        <common:Name xml:lang="en">Accommodation type</common:Name>
        <common:Name xml:lang="it">Tipo di alloggio</common:Name>
        <structure:Code id="ALL">
          <common:Name xml:lang="en">total collective accommodation establishments</common:Name>
          <common:Name xml:lang="it">totale esercizi ricettivi</common:Name>
        </structure:Code>
        <structure:Code id="HOTELLIKE">
          <common:Name xml:lang="en">hotels and similar establishments</common:Name>
          <common:Name xml:lang="it">esercizi alberghieri</common:Name>
        </structure:Code>
      </structure:Codelist>
    </structure:Codelists>
  </message:Structures>
</message:Structure>
"""

_EUROSTAT_PROVIDER = {
    "name": "Eurostat",
    "base_url": "https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1",
    "agency_id": "ESTAT",
    "rate_limit": 0.5,
    "language": "en",
}


def _dataset_with_codelist(codelist_id: str = "CL_TIPO_ALLOGGIO2") -> dict:
    dims = {"TYPE_ACCOMMODATION": {"id": "TYPE_ACCOMMODATION", "position": 1, "codelist_id": codelist_id}}
    return {
        "df_id": "TEST_DF",
        "version": "1.0",
        "df_description": "Test",
        "df_structure_id": "TEST_DSD",
        "dimensions": dims,
        "filters": {"TYPE_ACCOMMODATION": "."},
    }


def test_get_dimension_values_returns_italian_labels():
    """With provider language='it', labels must come from xml:lang='it'."""
    from opensdmx.discovery import get_dimension_values

    saved_keys = []

    def fake_save(key, records):
        saved_keys.append(key)

    with patch("opensdmx.discovery.get_provider", return_value=_ISTAT_PROVIDER), \
         patch("opensdmx.discovery.sdmx_request_xml", return_value=_BILINGUAL_CODELIST_XML), \
         patch("opensdmx.db_cache.get_cached_codelist_values", return_value=None), \
         patch("opensdmx.db_cache.save_codelist_values", side_effect=fake_save):
        df = get_dimension_values(_dataset_with_codelist(), "TYPE_ACCOMMODATION")

    names = dict(zip(df["id"].to_list(), df["name"].to_list()))
    assert names["ALL"] == "totale esercizi ricettivi"
    assert names["HOTELLIKE"] == "esercizi alberghieri"
    assert saved_keys == ["CL_TIPO_ALLOGGIO2:it"]


def test_get_dimension_values_returns_english_labels():
    """With provider language='en', labels must come from xml:lang='en'."""
    from opensdmx.discovery import get_dimension_values

    with patch("opensdmx.discovery.get_provider", return_value=_EUROSTAT_PROVIDER), \
         patch("opensdmx.discovery.sdmx_request_xml", return_value=_BILINGUAL_CODELIST_XML), \
         patch("opensdmx.db_cache.get_cached_codelist_values", return_value=None), \
         patch("opensdmx.db_cache.save_codelist_values"):
        df = get_dimension_values(_dataset_with_codelist(), "TYPE_ACCOMMODATION")

    names = dict(zip(df["id"].to_list(), df["name"].to_list()))
    assert names["ALL"] == "total collective accommodation establishments"
    assert names["HOTELLIKE"] == "hotels and similar establishments"


def test_get_dimension_values_cache_keys_differ_by_language():
    """Cache key must include language so Italian and English sessions don't share entries."""
    from opensdmx.discovery import get_dimension_values

    keys_used = []

    def fake_get_cache(key):
        keys_used.append(key)
        return None

    with patch("opensdmx.discovery.get_provider", return_value=_ISTAT_PROVIDER), \
         patch("opensdmx.discovery.sdmx_request_xml", return_value=_BILINGUAL_CODELIST_XML), \
         patch("opensdmx.db_cache.get_cached_codelist_values", side_effect=fake_get_cache), \
         patch("opensdmx.db_cache.save_codelist_values"):
        get_dimension_values(_dataset_with_codelist(), "TYPE_ACCOMMODATION")

    with patch("opensdmx.discovery.get_provider", return_value=_EUROSTAT_PROVIDER), \
         patch("opensdmx.discovery.sdmx_request_xml", return_value=_BILINGUAL_CODELIST_XML), \
         patch("opensdmx.db_cache.get_cached_codelist_values", side_effect=fake_get_cache), \
         patch("opensdmx.db_cache.save_codelist_values"):
        get_dimension_values(_dataset_with_codelist(), "TYPE_ACCOMMODATION")

    assert keys_used[0] == "CL_TIPO_ALLOGGIO2:it"
    assert keys_used[1] == "CL_TIPO_ALLOGGIO2:en"
    assert keys_used[0] != keys_used[1]


# ── search_dataset AND/OR fallback ───────────────────────────────────

import polars as pl  # noqa: E402
from opensdmx.discovery import _token_match_expr, search_dataset  # noqa: E402


def _fake_catalog() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "df_id": ["UNEMP", "BIRTHS", "GDP"],
            "version": ["1.0", "1.0", "1.0"],
            "df_description": [
                "Unemployment rate by age",
                "Live births by region",
                "Gross domestic product",
            ],
            "df_structure_id": ["DSD_U", "DSD_B", "DSD_G"],
        }
    )


def test_search_and_match_all_tokens():
    """All tokens present → AND path returns the single matching row."""
    with patch("opensdmx.discovery.all_available", return_value=_fake_catalog()):
        res = search_dataset("unemployment age")
    assert res["df_id"].to_list() == ["UNEMP"]


def test_search_or_fallback_when_and_empty():
    """One token missing → AND is empty, OR fallback still finds partial matches."""
    with patch("opensdmx.discovery.all_available", return_value=_fake_catalog()):
        res = search_dataset("unemployment nonexistenttoken")
    # AND would be empty (no row has 'nonexistenttoken'); OR must recover UNEMP.
    assert "UNEMP" in res["df_id"].to_list()


def test_search_or_fallback_ranks_full_match_first():
    """OR fallback keeps the row matching more tokens on top via the relevance score."""
    with patch("opensdmx.discovery.all_available", return_value=_fake_catalog()):
        # 'births' matches only BIRTHS; 'region' matches only BIRTHS too → both in BIRTHS.
        # 'gross' matches only GDP. AND is empty; OR returns BIRTHS + GDP, BIRTHS first.
        res = search_dataset("births region gross")
    ids = res["df_id"].to_list()
    assert set(ids) == {"BIRTHS", "GDP"}
    assert ids[0] == "BIRTHS"


def test_search_or_fallback_prioritizes_token_coverage():
    """A multi-token match outranks repeated occurrences of one token."""
    catalog = pl.DataFrame(
        {
            "df_id": ["REPEATED", "COVERED"],
            "version": ["1.0", "1.0"],
            "df_description": ["alpha " * 20, "alpha beta"],
            "df_structure_id": ["DSD_R", "DSD_C"],
        }
    )
    with patch("opensdmx.discovery.all_available", return_value=catalog):
        res = search_dataset("alpha beta missing")
    assert res["df_id"].to_list() == ["COVERED", "REPEATED"]


def test_search_treats_regex_characters_as_literal_tokens():
    """User tokens are literal text rather than regular expressions."""
    catalog = _fake_catalog().with_columns(
        pl.when(pl.col("df_id") == "GDP")
        .then(pl.lit("GDP [provisional]"))
        .otherwise(pl.col("df_description"))
        .alias("df_description")
    )
    with patch("opensdmx.discovery.all_available", return_value=catalog):
        res = search_dataset("[")
    assert res["df_id"].to_list() == ["GDP"]


def test_token_match_expr_normalizes_token_case():
    """The helper remains case-insensitive when used independently."""
    df = pl.DataFrame({"df_id": ["UPPER"], "df_description": ["Example"]})
    assert df.filter(_token_match_expr("UPPER")).height == 1


def test_search_no_match_returns_empty():
    """No token matches anything → empty result even after OR fallback."""
    with patch("opensdmx.discovery.all_available", return_value=_fake_catalog()):
        res = search_dataset("zzz qqq")
    assert res.is_empty()
