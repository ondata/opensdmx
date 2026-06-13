from __future__ import annotations

from unittest.mock import patch

import polars as pl

from opensdmx.retrieval import enrich_with_labels
from opensdmx.utils import build_query_dict


def _dataset() -> dict:
    return {
        "df_id": "TEST_DF",
        "version": "1.0",
        "df_description": "Test",
        "df_structure_id": "TEST_DSD",
        "dimensions": {
            "GEO": {"id": "GEO", "position": 1, "codelist_id": "CL_GEO"},
            "SEX": {"id": "SEX", "position": 2, "codelist_id": "CL_SEX"},
        },
        "filters": {"GEO": ".", "SEX": "."},
    }


def _fake_values(dataset, dim_id):
    data = {
        "GEO": [("IT", "Italy"), ("DE", "Germany")],
        "SEX": [("T", "Total")],
    }[dim_id.upper()]
    return pl.DataFrame(
        {"id": [r[0] for r in data], "name": [r[1] for r in data]},
        schema={"id": pl.Utf8, "name": pl.Utf8},
    )


def test_enrich_adds_label_columns_preserving_codes_and_order():
    # lowercase columns mimic Eurostat SDMX-CSV output
    df = pl.DataFrame({
        "geo": ["IT", "DE", "IT"],
        "sex": ["T", "T", "T"],
        "TIME_PERIOD": ["2020", "2020", "2021"],
        "OBS_VALUE": [1.0, 2.0, 3.0],
    })
    with patch("opensdmx.discovery.get_dimension_values", side_effect=_fake_values):
        out = enrich_with_labels(_dataset(), df)

    # codes preserved, order preserved
    assert out["geo"].to_list() == ["IT", "DE", "IT"]
    # label columns mirror the actual data column case + _label
    assert "geo_label" in out.columns
    assert "sex_label" in out.columns
    assert out["geo_label"].to_list() == ["Italy", "Germany", "Italy"]
    assert out["sex_label"].to_list() == ["Total", "Total", "Total"]


def test_enrich_dimension_without_codelist_adds_no_column():
    ds = _dataset()
    ds["dimensions"]["GEO"]["codelist_id"] = None
    df = pl.DataFrame({"geo": ["IT"], "sex": ["T"], "OBS_VALUE": [1.0]})
    with patch("opensdmx.discovery.get_dimension_values", side_effect=_fake_values):
        out = enrich_with_labels(ds, df)
    assert "geo_label" not in out.columns
    assert "sex_label" in out.columns


def test_enrich_unmapped_code_yields_null_label():
    df = pl.DataFrame({"geo": ["IT", "ZZ"], "OBS_VALUE": [1.0, 2.0]})
    ds = _dataset()
    del ds["dimensions"]["SEX"]
    with patch("opensdmx.discovery.get_dimension_values", side_effect=_fake_values):
        out = enrich_with_labels(ds, df)
    assert out["geo_label"].to_list() == ["Italy", None]


def test_build_query_dict_serializes_labels():
    ds = _dataset()
    with patch("opensdmx.utils._get_code_label", return_value=""):
        q = build_query_dict(ds=ds, filters={}, labels=True)
    assert q["labels"] is True

    with patch("opensdmx.utils._get_code_label", return_value=""):
        q2 = build_query_dict(ds=ds, filters={})
    assert q2["labels"] is False


def test_run_query_honors_labels(tmp_path):
    import yaml

    qfile = tmp_path / "q.yaml"
    qfile.write_text(yaml.dump({
        "provider": "eurostat",
        "dataset": "TEST_DF",
        "filters": {"GEO": {"value": "IT"}},
        "labels": True,
    }))

    ds = _dataset()
    df = pl.DataFrame({"geo": ["IT"], "sex": ["T"], "OBS_VALUE": [1.0]})

    with patch("opensdmx.base.set_provider"), \
         patch("opensdmx.retrieval.load_dataset", return_value=ds), \
         patch("opensdmx.retrieval.set_filters", return_value=ds), \
         patch("opensdmx.retrieval.get_data", return_value=df), \
         patch("opensdmx.discovery.get_dimension_values", side_effect=_fake_values):
        from opensdmx.retrieval import run_query
        out = run_query(str(qfile))

    assert "geo_label" in out.columns
    assert out["geo_label"].to_list() == ["Italy"]
