"""Regressions for the v0.14.0 architecture review — Phase 2 deduplication.

See docs/evaluation-v0.14.0.md findings 5, 6, 13, 17.
"""

from __future__ import annotations


import polars as pl
import pytest
import yaml
from unittest.mock import patch

from opensdmx import discovery
from opensdmx.base import PROVIDERS, get_provider, set_provider, set_provider_from_env
from opensdmx.retrieval import run_query


@pytest.fixture(autouse=True)
def _restore_provider():
    """Provider is module-global state; put it back after each test."""
    from opensdmx import base

    saved = base._active_provider
    yield
    base._active_provider = saved


def _write_query(tmp_path, **extra) -> str:
    q = {"dataset": "TEST_DF", "filters": {}, **extra}
    path = tmp_path / "q.yaml"
    path.write_text(yaml.dump(q))
    return str(path)


# ── Finding 5: run_query lacked the CLI's provider resolution ────────


def test_set_provider_from_env_applies_and_resolves_alias(monkeypatch):
    set_provider("eurostat")
    monkeypatch.setenv("OPENSDMX_PROVIDER", "istat")
    assert set_provider_from_env() is True
    assert get_provider()["agency_id"] == PROVIDERS["istat"]["agency_id"]


def test_set_provider_from_env_noop_when_unset(monkeypatch):
    set_provider("eurostat")
    monkeypatch.delenv("OPENSDMX_PROVIDER", raising=False)
    assert set_provider_from_env() is False
    assert get_provider()["agency_id"] == PROVIDERS["eurostat"]["agency_id"]


def test_run_query_honours_env_when_file_has_no_provider(tmp_path, monkeypatch):
    """The divergence this phase closes: the CLI honoured the env var, the
    library silently stayed on the default provider."""
    qfile = _write_query(tmp_path)
    monkeypatch.setenv("OPENSDMX_PROVIDER", "istat")
    set_provider("eurostat")

    seen: list[str] = []

    def spy_load(dataset_id):
        seen.append(get_provider()["agency_id"])
        raise RuntimeError("stop after provider resolution")

    with patch("opensdmx.retrieval.load_dataset", side_effect=spy_load):
        with pytest.raises(RuntimeError):
            run_query(qfile)

    assert seen == [PROVIDERS["istat"]["agency_id"]]


def test_run_query_provider_argument_wins_over_file(tmp_path, monkeypatch):
    qfile = _write_query(tmp_path, provider="eurostat")
    monkeypatch.delenv("OPENSDMX_PROVIDER", raising=False)

    seen: list[str] = []

    def spy_load(dataset_id):
        seen.append(get_provider()["agency_id"])
        raise RuntimeError("stop")

    with patch("opensdmx.retrieval.load_dataset", side_effect=spy_load):
        with pytest.raises(RuntimeError):
            run_query(qfile, provider="istat")

    assert seen == [PROVIDERS["istat"]["agency_id"]]


def test_run_query_file_provider_wins_over_env(tmp_path, monkeypatch):
    qfile = _write_query(tmp_path, provider="eurostat")
    monkeypatch.setenv("OPENSDMX_PROVIDER", "istat")

    seen: list[str] = []

    def spy_load(dataset_id):
        seen.append(get_provider()["agency_id"])
        raise RuntimeError("stop")

    with patch("opensdmx.retrieval.load_dataset", side_effect=spy_load):
        with pytest.raises(RuntimeError):
            run_query(qfile)

    assert seen == [PROVIDERS["eurostat"]["agency_id"]]


# ── Review follow-up: provider resolution edge cases ─────────────────


def test_resolve_provider_expands_alias():
    from opensdmx.base import resolve_provider

    set_provider("istat")
    resolve_provider("estat")
    assert get_provider()["agency_id"] == PROVIDERS["eurostat"]["agency_id"]


def test_resolve_provider_rejects_unknown_name():
    from opensdmx.base import resolve_provider

    with pytest.raises(ValueError, match="unknown provider 'eurostatt'"):
        resolve_provider("eurostatt")


def test_resolve_provider_accepts_url_with_agency():
    from opensdmx.base import resolve_provider

    resolve_provider("https://example.org/sdmx", agency_id="MYAG")
    assert get_provider()["base_url"] == "https://example.org/sdmx"
    assert get_provider()["agency_id"] == "MYAG"


def test_set_provider_from_env_rejects_typo(monkeypatch):
    """A typo used to become a bogus custom provider and fail later obscurely."""
    monkeypatch.setenv("OPENSDMX_PROVIDER", "eurostatt")
    with pytest.raises(ValueError, match="unknown provider"):
        set_provider_from_env()


def test_run_query_file_alias_beats_env(tmp_path, monkeypatch):
    """`provider: estat` in the file must win over OPENSDMX_PROVIDER."""
    qfile = _write_query(tmp_path, provider="estat")
    monkeypatch.setenv("OPENSDMX_PROVIDER", "istat")
    set_provider("istat")

    seen: list[str] = []

    def spy_load(dataset_id):
        seen.append(get_provider()["agency_id"])
        raise RuntimeError("stop")

    with patch("opensdmx.retrieval.load_dataset", side_effect=spy_load):
        with pytest.raises(RuntimeError):
            run_query(qfile)

    assert seen == [PROVIDERS["eurostat"]["agency_id"]]


def test_run_query_custom_url_keeps_agency(tmp_path, monkeypatch):
    """`--provider <url>` must not blank the agency the environment supplies."""
    qfile = _write_query(tmp_path)
    monkeypatch.setenv("OPENSDMX_AGENCY", "MYAG")
    monkeypatch.delenv("OPENSDMX_PROVIDER", raising=False)

    seen: list[str] = []

    def spy_load(dataset_id):
        seen.append(get_provider()["agency_id"])
        raise RuntimeError("stop")

    with patch("opensdmx.retrieval.load_dataset", side_effect=spy_load):
        with pytest.raises(RuntimeError):
            run_query(qfile, provider="https://example.org/sdmx")

    assert seen == ["MYAG"]


def test_run_query_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        run_query("/nonexistent/query.yaml")


def test_run_query_missing_dataset_field_raises(tmp_path):
    path = tmp_path / "q.yaml"
    path.write_text(yaml.dump({"filters": {}}))
    with pytest.raises(ValueError, match="dataset"):
        run_query(str(path))


# ── Finding 6 (corrected): filter errors must reach the caller ───────


def test_load_and_filter_propagates_set_filters_error():
    """A bad filter must reach the caller, which turns it into a CLI error.

    This replaces a test that asserted `warnings.warn` output was captured.
    That test passed only because its mock raised a warning: nothing in the
    package uses the warnings module, so the machinery it exercised never
    fired in production. See docs/evaluation-v0.14.0.md, finding 6.
    """
    from opensdmx import cli

    def strict_set_filters(ds, **kwargs):
        raise ValueError("unknown dimension(s): 'geoo'")

    with (
        patch("opensdmx.load_dataset", return_value={"df_id": "X", "dimensions": {}}),
        patch("opensdmx.set_filters", side_effect=strict_set_filters),
    ):
        with pytest.raises(ValueError, match="geoo"):
            cli._load_and_filter("X", {"geoo": "IT"})


def test_load_and_filter_skips_set_filters_when_no_filters():
    from opensdmx import cli

    with (
        patch("opensdmx.load_dataset", return_value={"df_id": "X"}),
        patch("opensdmx.set_filters") as sf,
    ):
        cli._load_and_filter("X", {})
    sf.assert_not_called()


# ── Shared output writer ─────────────────────────────────────────────


def test_write_output_dispatches_on_suffix(tmp_path):
    from opensdmx import cli

    df = pl.DataFrame({"a": [1, 2]})
    for suffix, reader in ((".csv", pl.read_csv), (".parquet", pl.read_parquet)):
        out = tmp_path / f"data{suffix}"
        cli._write_output(df, out)
        assert reader(out).height == 2


def test_write_output_rejects_unknown_suffix(tmp_path, capsys):
    import typer

    from opensdmx import cli

    with pytest.raises(typer.Exit):
        cli._write_output(pl.DataFrame({"a": [1]}), tmp_path / "data.xlsx")
    assert "unsupported output format" in capsys.readouterr().err


def test_write_output_to_stdout_when_out_is_none(capsys):
    from opensdmx import cli

    cli._write_output(pl.DataFrame({"a": ["v, w"]}), None)
    assert '"v, w"' in capsys.readouterr().out


# ── Finding 17: the bulk contentconstraint XML was parsed twice ──────

_CC_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<mes:Structure xmlns:mes="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message"
               xmlns:str="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure"
               xmlns:com="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common">
  <mes:Structures>
    <str:ContentConstraints>
      <str:ContentConstraint id="CC1">
        <str:ConstraintAttachment>
          <str:Dataflow><Ref id="12_60_DF_DCCV_CONSACQUA_2"/></str:Dataflow>
        </str:ConstraintAttachment>
        <str:CubeRegion>
          <com:KeyValue id="REF_AREA">
            <com:Value>IT</com:Value>
            <com:Value>ITC1</com:Value>
          </com:KeyValue>
        </str:CubeRegion>
      </str:ContentConstraint>
    </str:ContentConstraints>
  </mes:Structures>
</mes:Structure>"""


def test_parse_bulk_constraints_returns_both_views():
    long_ids, parsed = discovery.parse_bulk_constraints(_CC_XML)
    assert long_ids == {"12_60_DF_DCCV_CONSACQUA_2"}
    assert parsed == {"12_60": {"REF_AREA": ["IT", "ITC1"]}}


def test_parse_bulk_constraints_builds_the_tree_once():
    """The whole point: one xml_parse call, not two."""
    with patch(
        "opensdmx.discovery.xml_parse", wraps=discovery.xml_parse
    ) as spy:
        discovery.parse_bulk_constraints(_CC_XML)
    assert spy.call_count == 1


def test_parse_bulk_constraints_tolerates_empty_document():
    long_ids, parsed = discovery.parse_bulk_constraints(
        b'<?xml version="1.0"?><root/>'
    )
    assert long_ids == set()
    assert parsed == {}
