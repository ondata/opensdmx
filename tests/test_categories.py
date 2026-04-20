"""Tests for opensdmx.categories – thematic tree parsing and siblings."""

from __future__ import annotations

import polars as pl
import pytest

from opensdmx import categories
from opensdmx.categories import (
    CategoriesNotSupported,
    _direct_name,
    _fetch_categorisation,
    _fetch_categoryscheme,
    filter_by_category,
    siblings_of,
    supported_providers,
)
from opensdmx.utils import xml_parse


# ── fixtures ─────────────────────────────────────────────────────────

CATEGORYSCHEME_XML = b"""\
<message:Structure xmlns:message="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message"
                   xmlns:structure="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure"
                   xmlns:common="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common"
                   xmlns:xml="http://www.w3.org/XML/1998/namespace">
  <message:Structures>
    <structure:CategorySchemes>
      <structure:CategoryScheme id="AGRI" agencyID="IT1" version="1.0">
        <common:Name xml:lang="it">Agricoltura</common:Name>
        <common:Name xml:lang="en">Agriculture</common:Name>
        <structure:Category id="CROPS">
          <common:Name xml:lang="it">Coltivazioni</common:Name>
          <common:Name xml:lang="en">Crops</common:Name>
          <structure:Category id="CEREALS">
            <common:Name xml:lang="it">Cereali</common:Name>
            <common:Name xml:lang="en">Cereals</common:Name>
          </structure:Category>
        </structure:Category>
        <structure:Category id="LIVESTOCK">
          <common:Name xml:lang="it">Allevamenti</common:Name>
        </structure:Category>
      </structure:CategoryScheme>
    </structure:CategorySchemes>
  </message:Structures>
</message:Structure>
"""


CATEGORISATION_XML = b"""\
<message:Structure xmlns:message="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message"
                   xmlns:structure="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure"
                   xmlns:common="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common">
  <message:Structures>
    <structure:Categorisations>
      <structure:Categorisation id="CZ_WHEAT_CROPS">
        <structure:Source>
          <Ref id="WHEAT" class="Dataflow"/>
        </structure:Source>
        <structure:Target>
          <Ref id="CROPS.CEREALS" maintainableParentID="AGRI" class="Category"/>
        </structure:Target>
      </structure:Categorisation>
      <structure:Categorisation id="CZ_RICE_CROPS">
        <structure:Source>
          <Ref id="RICE" class="Dataflow"/>
        </structure:Source>
        <structure:Target>
          <Ref id="CROPS.CEREALS" maintainableParentID="AGRI" class="Category"/>
        </structure:Target>
      </structure:Categorisation>
      <structure:Categorisation id="CZ_COWS_LIVESTOCK">
        <structure:Source>
          <Ref id="COWS" class="Dataflow"/>
        </structure:Source>
        <structure:Target>
          <Ref id="LIVESTOCK" maintainableParentID="AGRI" class="Category"/>
        </structure:Target>
      </structure:Categorisation>
      <structure:Categorisation id="CZ_NONDF_IGNORED">
        <structure:Source>
          <Ref id="X" class="Codelist"/>
        </structure:Source>
        <structure:Target>
          <Ref id="LIVESTOCK" maintainableParentID="AGRI" class="Category"/>
        </structure:Target>
      </structure:Categorisation>
    </structure:Categorisations>
  </message:Structures>
</message:Structure>
"""


# ── _direct_name ─────────────────────────────────────────────────────

def test_direct_name_picks_requested_language():
    root, ns = xml_parse(CATEGORYSCHEME_XML)
    struct_ns = ns["structure"]
    scheme = root.find(f".//{{{struct_ns}}}CategoryScheme")
    assert _direct_name(scheme, "it", ns) == "Agricoltura"
    assert _direct_name(scheme, "en", ns) == "Agriculture"


def test_direct_name_falls_back_to_first_available():
    root, ns = xml_parse(CATEGORYSCHEME_XML)
    struct_ns = ns["structure"]
    # LIVESTOCK has only Italian Name; English request falls back
    livestock = root.find(f".//{{{struct_ns}}}Category[@id='LIVESTOCK']")
    assert _direct_name(livestock, "en", ns) == "Allevamenti"


def test_direct_name_does_not_capture_children_names():
    """Guard: lookup must be a direct child, not descendant."""
    root, ns = xml_parse(CATEGORYSCHEME_XML)
    struct_ns = ns["structure"]
    crops = root.find(f".//{{{struct_ns}}}Category[@id='CROPS']")
    # CROPS has nested CEREALS with its own Name; _direct_name must return CROPS' name
    assert _direct_name(crops, "it", ns) == "Coltivazioni"


# ── _fetch_categoryscheme (via monkeypatched sdmx_request_xml) ───────

def test_fetch_categoryscheme_builds_flat_rows(monkeypatch):
    monkeypatch.setattr(categories, "sdmx_request_xml", lambda path, **kw: CATEGORYSCHEME_XML)
    monkeypatch.setattr(
        categories,
        "get_provider",
        lambda: {"agency_id": "IT1", "language": "it"},
    )
    df = _fetch_categoryscheme()
    assert len(df) == 3  # CROPS, CROPS.CEREALS, LIVESTOCK
    rows = {r["cat_path"]: r for r in df.iter_rows(named=True)}

    assert set(rows) == {"CROPS", "CROPS.CEREALS", "LIVESTOCK"}
    assert rows["CROPS"]["scheme_name"] == "Agricoltura"
    assert rows["CROPS"]["cat_name"] == "Coltivazioni"
    assert rows["CROPS"]["parent_path"] == ""
    assert rows["CROPS"]["depth"] == 1
    assert rows["CROPS.CEREALS"]["parent_path"] == "CROPS"
    assert rows["CROPS.CEREALS"]["depth"] == 2


def test_fetch_categoryscheme_language_fallback(monkeypatch):
    monkeypatch.setattr(categories, "sdmx_request_xml", lambda path, **kw: CATEGORYSCHEME_XML)
    monkeypatch.setattr(
        categories,
        "get_provider",
        lambda: {"agency_id": "IT1", "language": "en"},
    )
    df = _fetch_categoryscheme()
    rows = {r["cat_path"]: r for r in df.iter_rows(named=True)}
    # LIVESTOCK has only Italian — fallback keeps IT when EN missing
    assert rows["LIVESTOCK"]["cat_name"] == "Allevamenti"
    # CROPS has both — uses EN
    assert rows["CROPS"]["cat_name"] == "Crops"


# ── _fetch_categorisation ────────────────────────────────────────────

def test_fetch_categorisation_maps_dataflow_to_category(monkeypatch):
    monkeypatch.setattr(categories, "sdmx_request_xml", lambda path, **kw: CATEGORISATION_XML)
    monkeypatch.setattr(
        categories,
        "get_provider",
        lambda: {"agency_id": "IT1"},
    )
    df = _fetch_categorisation()
    # 3 dataflow sources; the codelist source (class="Codelist") is skipped
    assert len(df) == 3
    ids = set(df["df_id"].to_list())
    assert ids == {"WHEAT", "RICE", "COWS"}
    wheat = df.filter(pl.col("df_id") == "WHEAT").row(0, named=True)
    assert wheat["scheme_id"] == "AGRI"
    assert wheat["cat_path"] == "CROPS.CEREALS"


def test_fetch_categorisation_prefixes_df_id_when_catalog_agency_differs(monkeypatch):
    """OECD-like providers (catalog_agency != agency_id) need df_id prefixed
    with the source agencyID to join with all_available() dataflow ids."""
    xml = b"""\
<message:Structure xmlns:message="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message"
                   xmlns:structure="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure"
                   xmlns:common="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common">
  <message:Structures>
    <structure:Categorisations>
      <structure:Categorisation id="CAT_WHEAT">
        <structure:Source>
          <Ref id="WHEAT" agencyID="OECD" class="Dataflow"/>
        </structure:Source>
        <structure:Target>
          <Ref id="CEREALS" maintainableParentID="AGRI"/>
        </structure:Target>
      </structure:Categorisation>
    </structure:Categorisations>
  </message:Structures>
</message:Structure>
"""
    monkeypatch.setattr(categories, "sdmx_request_xml", lambda path, **kw: xml)
    monkeypatch.setattr(
        categories,
        "get_provider",
        lambda: {"agency_id": "IT1", "catalog_agency": "all"},
    )
    df = _fetch_categorisation()
    assert len(df) == 1
    row = df.row(0, named=True)
    assert row["df_id"] == "OECD,WHEAT"
    assert row["scheme_id"] == "AGRI"
    assert row["cat_path"] == "CEREALS"


def test_fetch_categorisation_no_prefix_when_catalog_agency_matches(monkeypatch):
    """When catalog_agency == agency_id, df_id stays unprefixed."""
    xml = b"""\
<message:Structure xmlns:message="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message"
                   xmlns:structure="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure"
                   xmlns:common="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common">
  <message:Structures>
    <structure:Categorisations>
      <structure:Categorisation id="CAT_WHEAT">
        <structure:Source>
          <Ref id="WHEAT" agencyID="IT1" class="Dataflow"/>
        </structure:Source>
        <structure:Target>
          <Ref id="CEREALS" maintainableParentID="AGRI"/>
        </structure:Target>
      </structure:Categorisation>
    </structure:Categorisations>
  </message:Structures>
</message:Structure>
"""
    monkeypatch.setattr(categories, "sdmx_request_xml", lambda path, **kw: xml)
    monkeypatch.setattr(
        categories,
        "get_provider",
        lambda: {"agency_id": "IT1"},
    )
    df = _fetch_categorisation()
    assert df.row(0, named=True)["df_id"] == "WHEAT"


# ── supported_providers ──────────────────────────────────────────────

def test_supported_providers_reads_portals_json():
    supported = supported_providers()
    assert "istat" in supported
    assert "eurostat" in supported
    # These are marked unsupported
    assert "imf" not in supported
    assert "worldbank" not in supported


# ── siblings_of (via monkeypatched load_categories + all_available) ──

@pytest.fixture
def sample_cache(monkeypatch):
    """Inject in-memory DataFrames for load_categories() and all_available()."""
    cats_df = pl.DataFrame(
        [
            {"scheme_id": "AGRI", "scheme_name": "Agricoltura",
             "cat_id": "CROPS", "cat_path": "CROPS", "cat_name": "Coltivazioni",
             "parent_path": "", "depth": 1},
            {"scheme_id": "AGRI", "scheme_name": "Agricoltura",
             "cat_id": "CEREALS", "cat_path": "CROPS.CEREALS", "cat_name": "Cereali",
             "parent_path": "CROPS", "depth": 2},
            {"scheme_id": "AGRI", "scheme_name": "Agricoltura",
             "cat_id": "LIVESTOCK", "cat_path": "LIVESTOCK", "cat_name": "Allevamenti",
             "parent_path": "", "depth": 1},
        ],
        schema=categories.CATEGORIES_SCHEMA,
    )
    cz_df = pl.DataFrame(
        [
            {"df_id": "WHEAT", "scheme_id": "AGRI", "cat_path": "CROPS.CEREALS"},
            {"df_id": "RICE", "scheme_id": "AGRI", "cat_path": "CROPS.CEREALS"},
            {"df_id": "OATS", "scheme_id": "AGRI", "cat_path": "CROPS.CEREALS"},
            {"df_id": "COWS", "scheme_id": "AGRI", "cat_path": "LIVESTOCK"},
            # WHEAT also cross-listed in LIVESTOCK (multi-membership)
            {"df_id": "WHEAT", "scheme_id": "AGRI", "cat_path": "LIVESTOCK"},
        ],
        schema=categories.CATEGORISATION_SCHEMA,
    )
    dataflows_df = pl.DataFrame(
        [
            {"df_id": "WHEAT", "df_description": "Wheat production"},
            {"df_id": "RICE", "df_description": "Rice harvest"},
            {"df_id": "OATS", "df_description": "Oats yield"},
            {"df_id": "COWS", "df_description": "Cattle census"},
        ],
        schema={"df_id": pl.Utf8, "df_description": pl.Utf8},
    )
    monkeypatch.setattr(categories, "load_categories", lambda: (cats_df, cz_df))

    import opensdmx.discovery as discovery_mod
    monkeypatch.setattr(discovery_mod, "all_available", lambda: dataflows_df)
    return cats_df, cz_df, dataflows_df


def test_siblings_of_single_category(sample_cache):
    groups = siblings_of("RICE")
    assert len(groups) == 1
    g = groups[0]
    assert g["cat_path"] == "CROPS.CEREALS"
    assert g["cat_name"] == "Cereali"
    assert g["scheme_name"] == "Agricoltura"
    assert len(g["siblings"]) == 3
    target = next(s for s in g["siblings"] if s["is_target"])
    assert target["df_id"] == "RICE"
    others = {s["df_id"] for s in g["siblings"] if not s["is_target"]}
    assert others == {"WHEAT", "OATS"}


def test_siblings_of_multi_membership(sample_cache):
    """WHEAT is in both CROPS.CEREALS and LIVESTOCK → two groups."""
    groups = siblings_of("WHEAT")
    assert len(groups) == 2
    paths = sorted(g["cat_path"] for g in groups)
    assert paths == ["CROPS.CEREALS", "LIVESTOCK"]
    livestock = next(g for g in groups if g["cat_path"] == "LIVESTOCK")
    ids = {s["df_id"] for s in livestock["siblings"]}
    assert ids == {"WHEAT", "COWS"}


def test_siblings_of_unknown_returns_empty(sample_cache):
    assert siblings_of("DOES_NOT_EXIST") == []


# ── filter_by_category ───────────────────────────────────────────────

def test_filter_by_category_exact_path(sample_cache):
    df = filter_by_category("CROPS.CEREALS")
    assert len(df) == 3
    assert set(df["df_id"].to_list()) == {"WHEAT", "RICE", "OATS"}


def test_filter_by_category_leaf_id(sample_cache):
    """Match by trailing segment: `CEREALS` resolves to CROPS.CEREALS."""
    df = filter_by_category("CEREALS")
    assert len(df) == 3
    assert set(df["df_id"].to_list()) == {"WHEAT", "RICE", "OATS"}


def test_filter_by_category_no_match(sample_cache):
    df = filter_by_category("NOPE")
    assert df.is_empty()


# ── CategoriesNotSupported ───────────────────────────────────────────

def test_load_categories_raises_when_unsupported(monkeypatch):
    monkeypatch.setattr(
        categories,
        "get_provider",
        lambda: {"agency_id": "TEST", "categories_supported": False},
    )
    with pytest.raises(CategoriesNotSupported) as excinfo:
        categories.load_categories()
    # Hint must list at least one of the supported providers
    assert "istat" in str(excinfo.value) or "eurostat" in str(excinfo.value)


def test_load_categories_does_not_fetch_dataflows_for_stale_check_without_cache(monkeypatch):
    """First tree run should not download the full dataflow catalog just to warn."""
    cats_df = pl.DataFrame(
        {
            "scheme_id": ["S1"],
            "scheme_name": ["Scheme one"],
            "cat_id": ["CAT_A"],
            "cat_path": ["CAT_A"],
            "cat_name": ["Cat A"],
            "cat_description": [""],
            "parent_path": [""],
            "depth": [1],
        },
        schema_overrides={"depth": pl.Int32},
    )
    cz_df = pl.DataFrame({"df_id": ["DF_X"], "scheme_id": ["S1"], "cat_path": ["CAT_A"]})

    monkeypatch.setattr(
        categories,
        "get_provider",
        lambda: {"agency_id": "TEST", "categories_supported": True},
    )
    monkeypatch.setattr(categories, "_load_cached", lambda: None)
    monkeypatch.setattr(categories, "_fetch_categoryscheme", lambda: cats_df)
    monkeypatch.setattr(categories, "_fetch_categorisation", lambda: cz_df)
    monkeypatch.setattr(categories.pl.DataFrame, "write_parquet", lambda self, path: None)

    def _boom():
        raise AssertionError("all_available() should not be called during stale warning")

    monkeypatch.setattr("opensdmx.discovery._load_cached_dataflows", lambda: None)
    monkeypatch.setattr("opensdmx.discovery.all_available", _boom)

    loaded_cats, loaded_cz = categories.load_categories()
    assert loaded_cats.equals(cats_df)
    assert loaded_cz.equals(cz_df)
