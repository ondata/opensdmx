"""Exception text printed through Rich must not be read as markup.

Rich treats `[...]` as a style tag: `install opensdmx[semantic]` printed as
`install opensdmx`, and a message containing `[/x]` raised `MarkupError` inside
the error handler itself.
"""

from __future__ import annotations

import pathlib
import re
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


# A Rich print whose f-string interpolates an exception variable as is.
_UNESCAPED = re.compile(r"print\(\s*f[\"'].*\{(e|_e|err|exc|ex)\}")


def test_no_rich_print_interpolates_an_exception_unescaped():
    src = pathlib.Path(__file__).resolve().parents[1] / "src" / "opensdmx"
    offenders = [
        f"{path.name}:{n}"
        for path in sorted(src.glob("*.py"))
        for n, line in enumerate(path.read_text().splitlines(), 1)
        if _UNESCAPED.search(line)
    ]
    assert offenders == [], "wrap the exception in rich.markup.escape(str(e)): " + ", ".join(offenders)
