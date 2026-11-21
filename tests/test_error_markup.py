"""Exception text printed through Rich must not be read as markup.

Rich treats `[...]` as a style tag: `install opensdmx[semantic]` printed as
`install opensdmx`, and a message containing `[/x]` raised `MarkupError` inside
the error handler itself.
"""

from __future__ import annotations

import ast
import pathlib
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from opensdmx.cli import app

runner = CliRunner()


@pytest.mark.parametrize(
    "message",
    ["install opensdmx[semantic] first", "unexpected closing [/x] in reply"],
)
def test_search_error_keeps_square_brackets(message):
    with patch("opensdmx.cli._check_api_reachable"), \
         patch("opensdmx.search_dataset", side_effect=ValueError(message)):
        result = runner.invoke(app, ["search", "gdp", "--provider", "eurostat"])
    assert result.exit_code == 1
    # A MarkupError would also exit 1, but without printing the message.
    assert message in result.stderr


def test_info_error_keeps_square_brackets():
    message = "dimension [freq] not in the structure"
    with patch("opensdmx.cli._check_api_reachable"), \
         patch("opensdmx.load_dataset", side_effect=ValueError(message)):
        result = runner.invoke(app, ["info", "NAMA_10_GDP", "--provider", "eurostat"])
    assert result.exit_code == 1
    assert message in result.stderr


def _unescaped_prints(source: str) -> list[int]:
    """Lines of `print(...)` calls that interpolate a caught exception as is.

    Walks the syntax tree, not the text, so a call split over several lines is
    seen whole. Inside each `except ... as name`, any f-string argument of a
    `print` call that formats `name` directly (`{e}`, `{e!s}`) is an offender;
    `{rich.markup.escape(str(e))}` formats a call, not the name, and passes.
    """
    offenders = []
    for handler in ast.walk(ast.parse(source)):
        if not isinstance(handler, ast.ExceptHandler) or handler.name is None:
            continue
        for call in (n for stmt in handler.body for n in ast.walk(stmt)):
            if not (
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Attribute)
                and call.func.attr == "print"
            ):
                continue
            for value in (n for arg in call.args for n in ast.walk(arg)):
                if (
                    isinstance(value, ast.FormattedValue)
                    and isinstance(value.value, ast.Name)
                    and value.value.id == handler.name
                ):
                    offenders.append(call.lineno)
    return offenders


def test_scan_catches_a_multiline_unescaped_print():
    source = (
        "try:\n"
        "    pass\n"
        "except ValueError as e:\n"
        "    err_console.print(\n"
        "        \"[yellow]Warning:[/yellow] catalog unavailable: \"\n"
        "        f\"{e}\"\n"
        "    )\n"
    )
    assert _unescaped_prints(source) == [4]


def test_scan_accepts_an_escaped_print():
    source = (
        "try:\n"
        "    pass\n"
        "except ValueError as e:\n"
        "    err_console.print(f\"Error: {rich.markup.escape(str(e))}\")\n"
    )
    assert _unescaped_prints(source) == []


def test_no_rich_print_interpolates_an_exception_unescaped():
    src = pathlib.Path(__file__).resolve().parents[1] / "src" / "opensdmx"
    offenders = [
        f"{path.name}:{line}"
        for path in sorted(src.glob("*.py"))
        for line in _unescaped_prints(path.read_text())
    ]
    assert offenders == [], "wrap the exception in rich.markup.escape(str(e)): " + ", ".join(offenders)
