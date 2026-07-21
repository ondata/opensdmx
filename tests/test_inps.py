"""Tests for opensdmx.inps — the INPS hub-only adapter (offline, no network)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from opensdmx import inps

_INPS_PROVIDER = {
    "name": "INPS",
    "agency_id": "INPS",
    "language": "it",
    "hub_base_url": "https://example.test/databrowser/api/core",
    "hub_only": True,
    "hub_nodes": {"dipendenti": 3, "imprese": 4},
}

# One catalog exercising both shapes: a normal nested tree (OS15) and an
# observatory that hangs datasets directly off the top category (OS11-style).
_CATALOG = {
    "categoryGroups": [{
        "categories": [
            {
                "id": "OS15", "label": "Dipendenti",
                "datasetIdentifiers": [],
                "childrenCategories": [{
                    "id": "OS15_1", "label": "Regioni",
                    "datasetIdentifiers": ["INPS,DFB_A,1.0"],
                    "childrenCategories": [],
                }],
            },
            {
                "id": "OS11", "label": "Imprese",
                "datasetIdentifiers": ["INPS,DFB_B,1.0"],
                "childrenCategories": [],
            },
        ],
    }],
    "datasetMap": {"INPS,DFB_A,1.0": {"title": "Dataflow A"}},  # DFB_B has no title
}

_STRUCTURE = {
    "timeDimension": "TIME_PERIOD",
    "criteria": [
        {"id": "TERRITORIO", "label": "Territory of work",
         "extra": {"DataStructureRef": "INPS+CL_HIER_TERRITORIO_REG+1.0"}},
        {"id": "TIME_PERIOD", "label": "Anno"},
        {"id": "INDICATORI", "label": "Indicatori", "extra": {}},
    ],
}


@pytest.fixture
def _inps(monkeypatch):
    """Make the INPS provider active for functions that read get_provider()."""
    monkeypatch.setattr(inps, "get_provider", lambda: _INPS_PROVIDER)


# ── pure helpers ──────────────────────────────────────────────────────────

def test_bare_df_id():
    assert inps._bare_df_id("INPS,DFB_ST_DIP_ATECO_REG_01,1.0") == "DFB_ST_DIP_ATECO_REG_01"
    assert inps._bare_df_id("PLAIN") == "PLAIN"


def test_codelist_from_ref():
    assert inps._codelist_from_ref("INPS+CL_HIER_TERRITORIO_REG+1.0") == "CL_HIER_TERRITORIO_REG"
    assert inps._codelist_from_ref(None) is None
    assert inps._codelist_from_ref("noplus") is None


def test_leaf_labels():
    labels = inps._leaf_labels({3: _CATALOG})
    assert labels["DFB_A"] == "Regioni"   # leaf category label
    assert labels["DFB_B"] == "Imprese"   # top category holding the dataset


# ── all_available ─────────────────────────────────────────────────────────

def test_all_available_parses_catalog(_inps):
    with patch.object(inps, "_fetch_catalogs", return_value={3: _CATALOG}), \
         patch.object(inps, "_save_index") as save_index:
        df = inps.all_available()

    rows = {r["df_id"]: r for r in df.iter_rows(named=True)}
    assert set(rows) == {"DFB_A", "DFB_B"}
    assert rows["DFB_A"]["df_description"] == "Dataflow A"      # from datasetMap.title
    assert rows["DFB_B"]["df_description"] == "Imprese"         # fallback: leaf label
    assert rows["DFB_A"]["version"] == "1.0"
    assert rows["DFB_A"]["df_structure_id"] is None
    assert rows["DFB_A"]["has_constraint"] is True
    # df->node index persisted as a side effect
    saved = save_index.call_args[0][0]
    assert saved == {"DFB_A": 3, "DFB_B": 3}


# ── load_categories ───────────────────────────────────────────────────────

def test_load_categories_schemes_and_hierarchy(_inps):
    with patch.object(inps, "_fetch_catalogs", return_value={3: _CATALOG}):
        cats, cz = inps.load_categories()

    # Each observatory top category is a scheme.
    assert set(cats["scheme_id"].to_list()) == {"OS15", "OS11"}
    # OS11 (no children, datasets directly attached) still yields a depth-1 category.
    os11 = cats.filter(cats["scheme_id"] == "OS11")
    assert os11.height == 1
    assert os11["depth"].to_list() == [1]
    # categorisation maps each dataflow to its category path.
    cz_map = {r["df_id"]: r["cat_path"] for r in cz.iter_rows(named=True)}
    assert cz_map["DFB_A"] == "OS15_1"
    assert cz_map["DFB_B"] == "OS11"


# ── get_dimensions ────────────────────────────────────────────────────────

def test_get_dimensions_excludes_time_and_orders(_inps):
    with patch.object(inps, "_node_for_df", return_value=3), \
         patch.object(inps, "_hub_json", return_value=_STRUCTURE):
        dims = inps.get_dimensions("DFB_A")

    assert list(dims) == ["TERRITORIO", "INDICATORI"]   # TIME_PERIOD excluded, ordered
    assert dims["TERRITORIO"]["position"] == 1
    assert dims["TERRITORIO"]["codelist_id"] == "CL_HIER_TERRITORIO_REG"
    assert dims["TERRITORIO"]["description"] == "Territory of work"
    assert dims["INDICATORI"]["position"] == 2
    assert dims["INDICATORI"]["codelist_id"] is None


# ── territory hierarchy expansion ─────────────────────────────────────────

def test_collect_dim_records_expands_non_selectable_parent(_inps):
    def fake_partial(node, ds_full, dim_id, parent=None):
        if parent is None:
            return [{"id": "ITC", "name": "Nord-ovest", "isSelectable": False}]
        if parent == "ITC":
            return [
                {"id": "ITC4", "name": "Lombardia", "isSelectable": True},
                {"id": "ITC1", "name": "Piemonte", "isSelectable": True},
            ]
        return []

    with patch.object(inps, "_partial_codelist", side_effect=fake_partial):
        records = inps._collect_dim_records(3, "INPS,DFB_A,1.0", "TERRITORIO")

    ids = {r["id"]: r["name"] for r in records}
    assert ids == {"ITC4": "Lombardia", "ITC1": "Piemonte"}   # parent ITC dropped
