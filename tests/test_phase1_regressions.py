"""Regressions for the v0.14.0 architecture review — Phase 1 bug fixes.

See docs/evaluation-v0.14.0.md findings 1, 2, 3.
"""

from __future__ import annotations

import csv
import io
import json
from unittest.mock import patch

import polars as pl
from typer.testing import CliRunner

from opensdmx import cli
from opensdmx.cli import app

runner = CliRunner()


def _parse_csv(text: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(text)))


# ── Finding 1: -o csv emitted unquoted, corrupt CSV ──────────────────


def test_emit_csv_quotes_fields_containing_commas(capsys):
    """A field with a comma must not split into extra columns."""
    data = [{"a": "x", "b": "one, two, three", "c": "y"}]
    with patch.object(cli, "_output_mode", "csv"):
        cli._emit(data)
    rows = _parse_csv(capsys.readouterr().out)
    assert rows[0] == ["a", "b", "c"]
    assert rows[1] == ["x", "one, two, three", "y"]


def test_emit_csv_row_width_matches_header(capsys):
    data = [
        {"cmd": "plot", "desc": "line, bar, point"},
        {"cmd": "get", "desc": "no commas here"},
    ]
    with patch.object(cli, "_output_mode", "csv"):
        cli._emit(data)
    rows = _parse_csv(capsys.readouterr().out)
    assert len({len(r) for r in rows}) == 1, "rows disagree with header on width"


def test_emit_csv_handles_quotes_and_newlines(capsys):
    data = [{"a": 'say "hi"', "b": "line1\nline2"}]
    with patch.object(cli, "_output_mode", "csv"):
        cli._emit(data)
    rows = _parse_csv(capsys.readouterr().out)
    assert rows[1] == ['say "hi"', "line1\nline2"]


def test_emit_csv_missing_key_becomes_empty(capsys):
    """Keys are taken from the first row; absent values render empty."""
    data = [{"a": "1", "b": "2"}, {"a": "3"}]
    with patch.object(cli, "_output_mode", "csv"):
        cli._emit(data)
    rows = _parse_csv(capsys.readouterr().out)
    assert rows[2] == ["3", ""]


def test_emit_csv_stringifies_non_string_values(capsys):
    """str() semantics are unchanged from the hand-rolled serializer."""
    data = [{"cmd": "plot", "score": 5, "ok": True}]
    with patch.object(cli, "_output_mode", "csv"):
        cli._emit(data)
    rows = _parse_csv(capsys.readouterr().out)
    assert rows[1] == ["plot", "5", "True"]


def test_which_csv_output_is_valid():
    """End-to-end: `which` descriptions contain commas."""
    with patch("opensdmx.cli._check_api_reachable"):
        result = runner.invoke(app, ["-o", "csv", "which", "plot"])
    assert result.exit_code == 0
    rows = _parse_csv(result.stdout)
    assert len(rows) > 1
    assert len({len(r) for r in rows}) == 1


def test_emit_csv_nested_payload_warns_and_emits_json(capsys):
    """Dicts have no flat CSV form: still JSON, but no longer silently."""
    data = {"df_id": "X", "dimensions": [{"id": "geo"}]}
    with patch.object(cli, "_output_mode", "csv"):
        cli._emit(data)
    captured = capsys.readouterr()
    assert json.loads(captured.out) == data
    assert "no CSV form" in captured.err


def test_emit_csv_empty_list_does_not_warn(capsys):
    """An empty result is empty, not formless — stdout unchanged, no warning."""
    with patch.object(cli, "_output_mode", "csv"):
        cli._emit([])
    captured = capsys.readouterr()
    assert json.loads(captured.out) == []
    assert captured.err == ""


def test_emit_csv_prefers_dataframe_when_given(capsys):
    """The df argument still wins over the list fallback."""
    df = pl.DataFrame({"a": ["v, w"]})
    with patch.object(cli, "_output_mode", "csv"):
        cli._emit([{"ignored": "yes"}], df=df)
    rows = _parse_csv(capsys.readouterr().out)
    assert rows[0] == ["a"]
    assert rows[1] == ["v, w"]


# ── Finding 2: typer.Exit swallowed by `except Exception` ────────────


def test_get_large_dataset_guard_does_not_print_spurious_error():
    """typer.Exit subclasses RuntimeError; the handler must re-raise it."""
    fake = pl.DataFrame({"TIME_PERIOD": ["2020"], "OBS_VALUE": [1.0]})
    with (
        patch.object(cli, "_LARGE_DATASET_THRESHOLD", 0),
        patch("opensdmx.cli._check_api_reachable"),
        patch("opensdmx.load_dataset", return_value={"df_id": "X", "dimensions": {}}),
        patch("opensdmx.set_filters", side_effect=lambda ds, **k: ds),
        patch("opensdmx.get_data", return_value=fake),
    ):
        result = runner.invoke(app, ["get", "X"])

    assert result.exit_code == 1
    # The warning belongs on stderr, so assert it there specifically.
    assert "Warning:" in result.stderr
    # The spurious line must appear on neither stream: result.output is combined.
    assert "Error: 1" not in result.output


def test_get_large_dataset_message_reflects_filter_state():
    """The warning must not claim 'no filters set' when filters were passed."""
    fake = pl.DataFrame({"TIME_PERIOD": ["2020"], "OBS_VALUE": [1.0]})
    with (
        patch.object(cli, "_LARGE_DATASET_THRESHOLD", 0),
        patch("opensdmx.cli._check_api_reachable"),
        patch("opensdmx.load_dataset", return_value={"df_id": "X", "dimensions": {}}),
        patch("opensdmx.set_filters", side_effect=lambda ds, **k: ds),
        patch("opensdmx.get_data", return_value=fake),
    ):
        result = runner.invoke(app, ["get", "X", "--geo", "IT"])

    assert result.exit_code == 1
    assert "no filters set" not in result.stderr
    assert "with the current filters" in result.stderr


# ── Finding 3: codelist cache read with the wrong key ────────────────


def test_get_code_label_reads_lang_suffixed_key():
    """Values are written as '{id}:{lang}'; the bare id never matches."""
    from opensdmx.utils import _get_code_label

    rows = [{"id": "IT", "name": "Italy"}]
    seen: list[str] = []

    def fake_lookup(key: str):
        seen.append(key)
        return rows if key == "GEO:en" else None

    with (
        patch("opensdmx.db_cache.get_cached_codelist_values", side_effect=fake_lookup),
        patch("opensdmx.base.get_provider", return_value={"language": "en"}),
    ):
        assert _get_code_label("GEO", "IT") == "Italy"

    assert seen == ["GEO:en"], f"looked up {seen}, expected the lang-suffixed key"


def test_get_code_label_honours_provider_language():
    from opensdmx.utils import _get_code_label

    seen: list[str] = []

    def fake_lookup(key: str):
        seen.append(key)
        return None

    with (
        patch("opensdmx.db_cache.get_cached_codelist_values", side_effect=fake_lookup),
        patch("opensdmx.base.get_provider", return_value={"language": "it"}),
    ):
        _get_code_label("GEO", "IT")

    assert seen == ["GEO:it"]


def test_get_code_label_still_short_circuits():
    """Guards that must survive the fix: no codelist, multi-value codes."""
    from opensdmx.utils import _get_code_label

    with patch("opensdmx.db_cache.get_cached_codelist_values") as lookup:
        assert _get_code_label(None, "IT") == ""
        assert _get_code_label("GEO", "IT+FR") == ""
        lookup.assert_not_called()
