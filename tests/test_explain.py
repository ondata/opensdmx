"""Tests for --explain: the execution plan, printed without executing.

The contract: the plan goes to stderr, stdout stays empty, and no request is
made — not even a reachability probe. Everything here runs with httpx mocked
out, so any call that reaches it fails the test instead of the network.
"""

from __future__ import annotations

import sys
from unittest.mock import patch

import polars as pl
import pytest
from typer.testing import CliRunner

from opensdmx.base import ExplainStop, set_explain, sdmx_request
from opensdmx.categories import load_categories
from opensdmx.cli import app, main
from opensdmx.discovery import all_available

runner = CliRunner()

_EUROSTAT = "https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1"


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    """Fresh cache dir, a known provider, and no inherited output mode."""
    from opensdmx.base import set_provider

    monkeypatch.setenv("OPENSDMX_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("OPENSDMX_PROVIDER", raising=False)
    monkeypatch.delenv("OPENSDMX_OUTPUT", raising=False)
    set_provider("eurostat")  # other test modules leave istat active
    yield
    set_explain(False)  # a plan mode left on would silence the next test


@pytest.fixture(autouse=True)
def _no_reachability_probe():
    """The CLI callback pings the provider on the first run: stub it here.

    `_startup` reads the flag off argv (a plan must work while the provider is
    unreachable), and CliRunner's argv is pytest's, so the stub is what keeps
    these tests hermetic; `test_startup_skips_the_reachability_probe` covers the
    argv check itself.
    """
    with patch("opensdmx.cli._check_api_reachable"):
        yield


# ── the request funnel ───────────────────────────────────────────────


def test_explain_stops_before_httpx(capsys):
    set_explain(True)
    with patch("opensdmx.base.httpx.Client") as client:
        with pytest.raises(ExplainStop):
            sdmx_request("data/NAMA_10_GDP", startPeriod="2020", _is_data=True)
    client.assert_not_called()
    err = capsys.readouterr().err
    assert f"[would fetch] GET {_EUROSTAT}/data/NAMA_10_GDP?startPeriod=2020" in err


def test_explain_plans_a_post_body(capsys):
    """A POST hub call must show its method and the JSON it would send."""
    set_explain(True)
    with patch("opensdmx.base.httpx.Client") as client:
        with pytest.raises(ExplainStop):
            sdmx_request(
                "nodes/2/datasets/INPS,X,1.0/data",
                accept="application/json",
                _base_url="https://hub.example/api/core",
                _method="POST",
                _json_body={"datasetId": "INPS,X,1.0"},
            )
    client.assert_not_called()
    err = capsys.readouterr().err
    assert (
        '[would fetch] POST https://hub.example/api/core/nodes/2/datasets/INPS,X,1.0/data'
        ' {"datasetId":"INPS,X,1.0"}' in err
    )


def test_explain_covers_the_hub_client(capsys):
    """The StatKit hub builds its own httpx client, outside `sdmx_request`."""
    from opensdmx.base import set_provider
    from opensdmx.hub import _hub_get_json

    set_provider("istat")
    set_explain(True)
    with patch("opensdmx.hub.httpx.Client") as client:
        with pytest.raises(ExplainStop):
            _hub_get_json("datasets/IT1,22_289,1.0/columns/partial/values", 5.0)
    client.assert_not_called()
    assert (
        "[would fetch] GET https://esploradati.istat.it/databrowserhub/api/core"
        "/nodes/1/datasets/IT1,22_289,1.0/columns/partial/values" in capsys.readouterr().err
    )


def test_cache_hits_are_reported_only_under_explain(capsys):
    """The flag gates the [cached] lines: a normal hit stays silent."""
    with patch("opensdmx.discovery._load_cached_dataflows", return_value=_catalog()):
        df = all_available()
    assert df["df_id"].to_list() == ["NAMA_10_GDP"]  # the cache hit really happened
    assert "[cached]" not in capsys.readouterr().err

    set_explain(True)
    with patch("opensdmx.discovery._load_cached_dataflows", return_value=_catalog()):
        all_available()
    assert f"[cached]      GET {_EUROSTAT}/dataflow/ESTAT?detail=allstubs&references=none" in capsys.readouterr().err


# ── the CLI ──────────────────────────────────────────────────────────


def _catalog() -> pl.DataFrame:
    """The catalog frame `all_available` reads back from its Parquet cache."""
    return pl.DataFrame(
        {
            "df_id": ["NAMA_10_GDP"],
            "version": ["1.0"],
            "df_description": ["Gross domestic product"],
            "df_structure_id": ["NAMA_10_GDP"],
            "has_constraint": [True],
        }
    )


def test_get_explain_lists_every_cached_step_and_the_data_url(capsys, monkeypatch):
    """Warm catalog and warm structure: the data URL is computable and shown.

    The acceptance case of #74: cached vs network on one plan, and the data URL
    that only exists because `make_url_key` could read the cached dimension order.
    """
    dims = {
        "FREQ": {"id": "FREQ", "position": 0, "codelist_id": "CL_FREQ"},
        "GEO": {"id": "GEO", "position": 1, "codelist_id": "CL_GEO"},
    }
    monkeypatch.setattr(
        sys,
        "argv",
        ["opensdmx", "get", "NAMA_10_GDP", "--FREQ", "A", "--explain", "-p", "eurostat"],
    )
    with patch("opensdmx.discovery._load_cached_dataflows", return_value=_catalog()), \
         patch("opensdmx.db_cache.get_cached_dims", return_value=dims), \
         patch("opensdmx.base.httpx.Client") as client:
        with pytest.raises(SystemExit) as stopped:
            main()
    assert stopped.value.code == 0
    client.assert_not_called()
    captured = capsys.readouterr()
    assert captured.out == ""
    assert f"[cached]      GET {_EUROSTAT}/dataflow/ESTAT?detail=allstubs&references=none" in captured.err
    assert f"[cached]      GET {_EUROSTAT}/datastructure/ESTAT/NAMA_10_GDP" in captured.err
    # FREQ=A and GEO unfiltered -> key `A.`, built from the cached dimension order;
    # the size probe is the first request when --last-n/--first-n are not given.
    assert (
        f"[would fetch] GET {_EUROSTAT}/data/NAMA_10_GDP/A.?format=SDMX-CSV&lastNObservations=1"
        in captured.err
    )


def test_inps_plan_starts_at_the_hub_catalog(capsys, monkeypatch):
    """A POST-based hub provider: the plan is the hub's own first request."""
    monkeypatch.setattr(
        sys, "argv", ["opensdmx", "values", "PENSIONI", "X", "--explain", "-p", "inps"]
    )
    with patch("opensdmx.base.httpx.Client") as client:
        with pytest.raises(SystemExit) as stopped:
            main()
    assert stopped.value.code == 0
    client.assert_not_called()
    assert (
        "[would fetch] GET https://opendata.inps.it/databrowser/api/core/nodes/2/catalog"
        in capsys.readouterr().err
    )


def test_write_output_writes_no_file_under_explain(tmp_path):
    """The frame writers are guarded too: --explain means no data, no file."""
    from opensdmx.cli import _emit, _write_output

    out = tmp_path / "data.csv"
    set_explain(True)
    _write_output(pl.DataFrame({"a": [1]}), out)
    _write_output(pl.DataFrame({"a": [1]}), None)
    _emit([{"a": 1}])
    assert not out.exists()


def test_plot_explain_writes_no_chart(tmp_path, monkeypatch, capsys):
    """plot with a local file has no request to plan: it writes nothing either."""
    csv = tmp_path / "series.csv"
    csv.write_text("TIME_PERIOD,OBS_VALUE\n2020,1\n2021,2\n")
    png = tmp_path / "chart.png"
    monkeypatch.setattr(
        sys, "argv", ["opensdmx", "plot", str(csv), "--out", str(png), "--explain"]
    )
    with pytest.raises(SystemExit) as stopped:
        main()
    assert stopped.value.code == 0
    assert not png.exists()
    assert capsys.readouterr().out == ""


def test_search_explain_keeps_stdout_empty_in_every_output_mode():
    """Cached-only run: the plan is the output, the results are not."""
    for output in ("table", "json", "csv"):
        with patch("opensdmx.discovery._load_cached_dataflows", return_value=_catalog()):
            result = runner.invoke(
                app, ["-o", output, "search", "gdp", "--explain", "-p", "eurostat"]
            )
        assert result.stdout == "", f"-o {output} wrote {result.stdout!r} to stdout"
        assert f"[cached]      GET {_EUROSTAT}/dataflow/ESTAT?detail=allstubs&references=none" in result.stderr


def test_cached_categories_are_reported(capsys):
    from opensdmx.categories import CATEGORISATION_SCHEMA, CATEGORIES_SCHEMA

    set_explain(True)
    with patch(
        "opensdmx.categories._load_cached",
        return_value=(
            pl.DataFrame(schema=CATEGORIES_SCHEMA),
            pl.DataFrame(schema=CATEGORISATION_SCHEMA),
        ),
    ):
        load_categories()
    err = capsys.readouterr().err
    assert f"[cached]      GET {_EUROSTAT}/categoryscheme/ESTAT/ALL/latest" in err
    assert f"[cached]      GET {_EUROSTAT}/categorisation/ESTAT/ALL/latest" in err


def test_main_exits_zero_when_a_plan_stops_at_a_request(capsys, monkeypatch):
    """A plan that stops at a request is a clean exit, and says nothing more."""
    monkeypatch.setattr(
        sys, "argv", ["opensdmx", "values", "NAMA_10_GDP", "FREQ", "--explain", "-p", "eurostat"]
    )
    with patch("opensdmx.discovery._load_cached_dataflows", return_value=_catalog()), \
         patch("opensdmx.base.httpx.Client") as client:
        with pytest.raises(SystemExit) as stopped:
            main()
    assert stopped.value.code == 0
    client.assert_not_called()
    err = capsys.readouterr().err
    assert f"[would fetch] GET {_EUROSTAT}/datastructure/ESTAT/NAMA_10_GDP" in err
    assert "no request would be made" not in err


def test_main_reports_a_plan_that_needs_no_request(capsys, monkeypatch):
    """Everything cached: click exits 0 and the plan says so, once."""
    monkeypatch.setattr(
        sys, "argv", ["opensdmx", "search", "gdp", "--explain", "-p", "eurostat"]
    )
    with patch("opensdmx.discovery._load_cached_dataflows", return_value=_catalog()):
        with pytest.raises(SystemExit) as done:
            main()
    assert done.value.code == 0
    err = capsys.readouterr().err
    assert "explain: no provider request would be made." in err
    assert "would fetch" not in err


def test_startup_skips_the_reachability_probe_under_explain(monkeypatch):
    """argv is checked, not the parsed option: the probe runs before the command."""
    monkeypatch.setattr(sys, "argv", ["opensdmx", "providers", "--explain"])
    with patch("opensdmx.cli._check_api_reachable") as probe:
        runner.invoke(app, ["providers"])
    probe.assert_not_called()


def test_explain_mode_does_not_leak_into_the_next_command(monkeypatch):
    """A command without --explain must not inherit a previous plan mode."""
    from opensdmx.base import is_explain

    monkeypatch.setattr(sys, "argv", ["opensdmx", "search", "gdp", "--explain"])
    with patch("opensdmx.discovery._load_cached_dataflows", return_value=_catalog()):
        runner.invoke(app, ["search", "gdp", "--explain", "-p", "eurostat"])
        assert is_explain()  # the mode is on for this process...
        monkeypatch.setattr(sys, "argv", ["opensdmx", "providers"])
        result = runner.invoke(app, ["providers"])
    assert not is_explain()  # ...and the next callback drops it
    # `providers` is local-only: its table must still reach stdout.
    assert "ISTAT" in result.stdout
