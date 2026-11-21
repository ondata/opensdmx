"""`OPENSDMX_DEBUG` adds the traceback under the one-line CLI error.

Unset, a failure caught at the CLI boundary prints one `Error:` line and exits
1, as before. Set, the same handler also prints where the error came from.
"""

from __future__ import annotations

import ast
import pathlib
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from opensdmx.cli import app

runner = CliRunner()


def _info_with_a_bug():
    with patch("opensdmx.cli._check_api_reachable"), \
         patch("opensdmx.load_dataset", side_effect=TypeError("unexpected None")):
        return runner.invoke(app, ["info", "NAMA_10_GDP", "--provider", "eurostat"])


def test_without_debug_the_error_is_one_line(monkeypatch):
    monkeypatch.delenv("OPENSDMX_DEBUG", raising=False)
    result = _info_with_a_bug()
    assert result.exit_code == 1
    assert "Error: unexpected None" in result.stderr
    assert "Traceback" not in result.stderr


def test_with_debug_the_traceback_follows_the_error(monkeypatch):
    monkeypatch.setenv("OPENSDMX_DEBUG", "1")
    result = _info_with_a_bug()
    assert result.exit_code == 1
    assert "Error: unexpected None" in result.stderr
    assert "Traceback (most recent call last)" in result.stderr
    assert "TypeError: unexpected None" in result.stderr
    assert result.stdout == ""


def _handlers_without_debug_traceback(source: str) -> list[int]:
    """`except Exception` handlers that exit 1 without the debug traceback call."""
    missing = []
    for node in ast.walk(ast.parse(source)):
        if not (
            isinstance(node, ast.ExceptHandler)
            and isinstance(node.type, ast.Name)
            and node.type.id == "Exception"
        ):
            continue
        body = [n for stmt in node.body for n in ast.walk(stmt)]
        exits = any(
            isinstance(n, ast.Raise)
            and isinstance(n.exc, ast.Call)
            and ast.unparse(n.exc) == "typer.Exit(1)"
            for n in body
        )
        calls_helper = any(
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "print_debug_traceback"
            for n in body
        )
        if exits and not calls_helper:
            missing.append(node.lineno)
    return missing


@pytest.mark.parametrize("module", ["cli.py", "guide.py"])
def test_every_boundary_handler_offers_the_traceback(module):
    path = pathlib.Path(__file__).resolve().parents[1] / "src" / "opensdmx" / module
    assert _handlers_without_debug_traceback(path.read_text()) == []
