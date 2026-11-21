"""Parsing paths that the suite used to skip.

- `discovery._get_dimensions`: the datastructure (DSD) parsing behind `info`
  and `get` on every REST provider; the other tests only hit its cache.
- `base.sdmx_request_csv` with `data_accept`: the SDMX-JSON data path, used by
  World Bank, including the repair of its sparse `[,` arrays.
"""

from __future__ import annotations

import pathlib
from types import SimpleNamespace
from unittest.mock import patch

import polars as pl
import pytest

from opensdmx import db_cache
from opensdmx.base import sdmx_request_csv, set_provider
from opensdmx.discovery import _get_dimensions


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    """A fresh cache.db per test, as in `test_db_cache.py`: the DSD tests check
    call counts, which a structure cached by an earlier run would bypass."""
    monkeypatch.setattr(db_cache, "_get_db_path", lambda: tmp_path / "cache.db")
    monkeypatch.setattr(db_cache, "_INITIALIZED_DBS", set())


@pytest.fixture
def provider():
    """Switch provider for one test, then restore the default."""
    yield set_provider
    set_provider("eurostat")


# ── datastructure parsing ────────────────────────────────────────────

_DSD = b"""<?xml version="1.0" encoding="UTF-8"?>
<message:Structure
    xmlns:message="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message"
    xmlns:structure="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure"
    xmlns:common="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common">
  <message:Structures>
    <structure:DataStructures>
      <structure:DataStructure id="DSD_TEST" agencyID="ESTAT" version="1.0">
        <structure:DataStructureComponents>
          <structure:DimensionList id="DimensionDescriptor">
            <structure:Dimension id="GEO" position="2">
              <structure:LocalRepresentation>
                <structure:Enumeration><Ref id="CL_GEO" agencyID="ESTAT"/></structure:Enumeration>
              </structure:LocalRepresentation>
            </structure:Dimension>
            <structure:Dimension id="FREQ" position="1">
              <structure:ConceptIdentity>
                <Ref id="FREQ" maintainableParentID="CS_TEST" agencyID="ESTAT"/>
              </structure:ConceptIdentity>
            </structure:Dimension>
            <structure:Dimension position="3"/>
            <structure:Dimension id="NOPOS">
              <structure:LocalRepresentation>
                <structure:Enumeration><Ref id="CL_NOPOS"/></structure:Enumeration>
              </structure:LocalRepresentation>
            </structure:Dimension>
          </structure:DimensionList>
        </structure:DataStructureComponents>
      </structure:DataStructure>
    </structure:DataStructures>
  </message:Structures>
</message:Structure>
"""


def test_dsd_dimensions_parsed_and_ordered_by_position():
    with patch("opensdmx.discovery.sdmx_request_xml", return_value=_DSD), \
         patch("opensdmx.discovery._resolve_codelist_from_concept", return_value="CL_FREQ") as concept:
        dims = _get_dimensions("DSD_TEST_ORDER")

    # Sorted by position; no id → skipped; no position → dropped.
    assert list(dims) == ["FREQ", "GEO"]
    assert dims["GEO"] == {"id": "GEO", "position": 2, "codelist_id": "CL_GEO"}
    # FREQ has no LocalRepresentation: the codelist comes from the concept scheme.
    assert dims["FREQ"]["codelist_id"] == "CL_FREQ"
    concept.assert_called_once_with("CS_TEST", "ESTAT", "FREQ")


def test_dsd_dimensions_are_cached_after_the_first_fetch():
    with patch("opensdmx.discovery.sdmx_request_xml", return_value=_DSD) as fetch, \
         patch("opensdmx.discovery._resolve_codelist_from_concept", return_value="CL_FREQ"):
        first = _get_dimensions("DSD_TEST_CACHE")
        second = _get_dimensions("DSD_TEST_CACHE")
    assert first == second
    fetch.assert_called_once()


def test_dsd_request_uses_the_provider_datastructure_agency(provider):
    provider("bundesbank")
    with patch("opensdmx.discovery.sdmx_request_xml", return_value=_DSD) as fetch, \
         patch("opensdmx.discovery._resolve_codelist_from_concept", return_value=None):
        _get_dimensions("DSD_TEST_AGENCY")
    path = fetch.call_args.args[0]
    assert path == "metadata/datastructure/BBK/DSD_TEST_AGENCY"


# ── SDMX-JSON data (World Bank) ──────────────────────────────────────

# A real World Bank reply, fetched through opensdmx on 2026-11-21:
# `data/WB,WDI,1.0/A.SP_POP_TOTL.ITA+FRA+DEU/`, 2022-2023. World Bank writes
# the series key in DESCENDING keyPosition order: `2:0:0` is REF_AREA=DEU
# (keyPosition 2), SERIES=0, FREQ=0. The parser relies on that.
_WB_REPLY = (pathlib.Path(__file__).parent / "data" / "worldbank_wdi_sp_pop_totl.json").read_text()


def _json_response(text):
    return SimpleNamespace(text=text, content=text.encode(), headers={}, status_code=200)


def test_worldbank_json_becomes_a_long_table(provider):
    provider("worldbank")
    with patch("opensdmx.base.sdmx_request", return_value=_json_response(_WB_REPLY)) as req:
        df = sdmx_request_csv("data/WB,WDI,1.0/A.SP_POP_TOTL.ITA+FRA+DEU")

    # World Bank needs its JSON Accept header and the trailing slash.
    assert req.call_args.args[0].endswith("/")
    assert req.call_args.kwargs["accept"].startswith("application/vnd.sdmx.data+json")

    assert df.height == 6
    assert set(df["FREQ"]) == {"A"} and set(df["SERIES"]) == {"SP_POP_TOTL"}
    values = {(r["REF_AREA"], r["TIME_PERIOD"]): r["OBS_VALUE"] for r in df.to_dicts()}
    assert values[("ITA", "2022")] == 59013667
    assert values[("FRA", "2023")] == 68372286
    assert values[("DEU", "2023")] == 83287273
    assert df.schema["OBS_VALUE"] == pl.Float64


def test_worldbank_sparse_array_is_repaired(provider):
    """World Bank leaves the value out of an observation array (`[,0]`), which
    is not valid JSON: the parser rewrites `[,` to `[null,`. Simulated on the
    real reply by blanking DEU 2023."""
    provider("worldbank")
    sparse = _WB_REPLY.replace('"1":[83287273,0]', '"1":[,0]')
    assert sparse != _WB_REPLY
    with patch("opensdmx.base.sdmx_request", return_value=_json_response(sparse)):
        df = sdmx_request_csv("data/WB,WDI,1.0/A.SP_POP_TOTL.ITA+FRA+DEU")
    row = df.filter((pl.col("REF_AREA") == "DEU") & (pl.col("TIME_PERIOD") == "2023"))
    assert row["OBS_VALUE"].to_list() == [None]


def test_worldbank_json_without_observations_is_an_empty_frame(provider):
    provider("worldbank")
    empty = '{"structure": {"dimensions": {"series": [], "observation": []}}, "dataSets": []}'
    with patch("opensdmx.base.sdmx_request", return_value=_json_response(empty)):
        assert sdmx_request_csv("data/WB,WDI,1.0/A.XXX.YYY").is_empty()
