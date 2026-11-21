"""`run` (saved YAML queries) and the `which` capability index."""

from __future__ import annotations

from unittest.mock import patch

import httpx
import polars as pl
import yaml
from typer.main import get_command
from typer.testing import CliRunner

from opensdmx.cli import app
from opensdmx.which import WHICH_INDEX, rank_which

runner = CliRunner()


# ── run ──────────────────────────────────────────────────────────────


def _query_file(tmp_path):
    path = tmp_path / "q.yaml"
    path.write_text("dataset: NAMA_10_GDP\nprovider: eurostat\nfilters: {geo: IT}\n")
    return path


def test_run_writes_the_query_result(tmp_path):
    out = tmp_path / "out.csv"
    frame = pl.DataFrame({"geo": ["IT"], "TIME_PERIOD": ["2023"], "OBS_VALUE": [1.5]})
    with patch("opensdmx.run_query", return_value=frame) as run_query:
        result = runner.invoke(app, ["run", str(_query_file(tmp_path)), "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert run_query.call_args.args[0] == str(tmp_path / "q.yaml")
    assert pl.read_csv(out).to_dicts() == [{"geo": "IT", "TIME_PERIOD": 2023, "OBS_VALUE": 1.5}]


def test_run_missing_file_is_reported(tmp_path):
    missing = tmp_path / "nope.yaml"
    with patch("opensdmx.run_query", side_effect=FileNotFoundError(missing)):
        result = runner.invoke(app, ["run", str(missing)])
    assert result.exit_code == 1
    # Rich wraps a long path at the terminal width: compare without line breaks.
    assert f"file not found: {missing}" in " ".join(result.stderr.split())


def test_run_bad_yaml_is_reported(tmp_path):
    with patch("opensdmx.run_query", side_effect=yaml.YAMLError("mapping values are not allowed")):
        result = runner.invoke(app, ["run", str(_query_file(tmp_path))])
    assert result.exit_code == 1
    assert "Error reading YAML: mapping values are not allowed" in result.stderr


def test_run_http_413_prints_the_too_large_hint(tmp_path):
    request = httpx.Request("GET", "https://example.org/data/X")
    error = httpx.HTTPStatusError("too large", request=request, response=httpx.Response(413, request=request))
    with patch("opensdmx.run_query", side_effect=error):
        result = runner.invoke(app, ["run", str(_query_file(tmp_path))])
    assert result.exit_code == 1
    assert "HTTP 413: https://example.org/data/X" in result.stderr
    assert "Hint:" in result.stderr


# ── which ────────────────────────────────────────────────────────────


def test_which_index_lists_every_cli_command():
    """A command missing from the index is invisible to `which`, so an agent
    asking for it gets exit 2. `which` itself is the entry point, not a target;
    hidden commands (`guide`) stay out of `--help` and out of the index."""
    registered = get_command(app).commands  # type: ignore[attr-defined]
    commands = {name for name, cmd in registered.items() if not cmd.hidden} - {"which"}
    assert commands == {e["command"] for e in WHICH_INDEX}


def test_which_finds_embed_and_blacklist():
    assert rank_which("semantic embeddings", limit=1)[0]["entry"]["command"] == "embed"
    assert rank_which("unavailable datasets", limit=1)[0]["entry"]["command"] == "blacklist"
