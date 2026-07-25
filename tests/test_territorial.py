"""Tests for the nightly territorial classifier (scripts/constraints_archive.py):
GEO_ID-discovered dimensions are classified by name, never by code shape."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import patch

import polars as pl

_SPEC = importlib.util.spec_from_file_location(
    "constraints_archive",
    Path(__file__).resolve().parents[1] / "scripts" / "constraints_archive.py",
)
archive = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(archive)


def test_discovered_territorial_dims_reads_geo_dim():
    catalog = pl.DataFrame({"df_id": ["A", "B", "C"], "df_geo_dim": ["RESIDENCE_TERR", None, "RESIDENCE_TERR"]})
    with patch.object(archive.opensdmx, "all_available", return_value=catalog):
        assert archive._discovered_territorial_dims() == {"RESIDENCE_TERR"}


def test_rebuild_classifies_by_name_not_by_code_shape(tmp_path, monkeypatch):
    # Archive: a RESIDENCE_TERR dataflow with ITTER-format codes, and an ECOICOP_2
    # dataflow whose 6-digit codes look municipal but are a consumption classification.
    arch = pl.DataFrame(
        {
            "df_id": ["BIRTHS", "BIRTHS", "BIRTHS", "PRICES"],
            "dimension_id": ["RESIDENCE_TERR", "RESIDENCE_TERR", "RESIDENCE_TERR", "ECOICOP_2"],
            "code_id": ["IT", "ITC4", "015146", "011111"],
        }
    )
    status = {
        "BIRTHS": {"df_description": "Nati vivi", "checked_at": "2026-07-25"},
        "PRICES": {"df_description": "Prezzi", "checked_at": "2026-07-25"},
    }
    catalog = pl.DataFrame({"df_id": ["BIRTHS"], "df_geo_dim": ["RESIDENCE_TERR"]})

    monkeypatch.setattr(archive, "DATA_DIR", tmp_path)
    with patch.object(archive.opensdmx, "all_available", return_value=catalog):
        archive.rebuild_istat_territorial(arch, status)

    out = pl.read_csv(tmp_path / "istat_territorial.csv")
    ids = out["df_id"].to_list()
    # RESIDENCE_TERR is discovered → BIRTHS classified at its deepest level (comune)
    assert "BIRTHS" in ids
    assert out.filter(pl.col("df_id") == "BIRTHS")["max_level"][0] == "comune"
    # ECOICOP_2 is not a territorial name → PRICES is not classified, despite 6-digit codes
    assert "PRICES" not in ids
