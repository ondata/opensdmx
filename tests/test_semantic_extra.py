"""The `semantic` extra: importing is always safe, calling explains the install.

The Ollama client is an optional dependency, so a keyword-only install must be
able to import `opensdmx` and only find out what is missing when it actually asks
for an embedding.
"""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from opensdmx import embed
from opensdmx.cli import app

runner = CliRunner()


@pytest.fixture(scope="session")
def pyproject() -> dict:
    """Parsed `pyproject.toml`, shared by the packaging tests."""
    import tomllib
    from pathlib import Path

    return tomllib.loads(
        Path(__file__).parent.parent.joinpath("pyproject.toml").read_text(encoding="utf-8")
    )


@pytest.fixture
def without_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make `import ollama` fail, the way an install without the extra does."""
    monkeypatch.setitem(sys.modules, "ollama", None)


@pytest.mark.usefixtures("without_ollama")
def test_require_ollama_points_at_the_extra() -> None:
    with pytest.raises(ImportError, match=r"opensdmx\[semantic\]"):
        embed._require_ollama()


@pytest.mark.usefixtures("without_ollama")
def test_semantic_search_explains_the_missing_extra() -> None:
    with pytest.raises(ImportError, match=r"opensdmx\[semantic\]") as excinfo:
        embed.semantic_search("unemployment")

    assert "ollama pull" in str(excinfo.value)


@pytest.mark.usefixtures("without_ollama")
def test_build_embeddings_explains_the_missing_extra() -> None:
    with pytest.raises(ImportError, match=r"opensdmx\[semantic\]"):
        embed.build_embeddings(progress=False)


def test_pyproject_keeps_ollama_out_of_the_hard_dependencies(pyproject: dict) -> None:
    """The install command the error suggests has to name an extra that exists."""
    project = pyproject["project"]

    assert any(dep.startswith("ollama") for dep in project["optional-dependencies"]["semantic"])
    assert not any(dep.startswith("ollama") for dep in project["dependencies"])


@pytest.mark.usefixtures("without_ollama")
def test_search_semantic_cli_prints_the_install_hint() -> None:
    """The CLI output must name the extra: Rich would parse `[semantic]` as markup."""
    # The app's startup callback pings the provider when no rate-limit file exists;
    # the repo's other CLI tests patch it out so nothing here touches the network.
    with patch("opensdmx.cli._check_api_reachable"):
        result = runner.invoke(app, ["search", "--semantic", "unemployment"])

    assert result.exit_code == 1
    assert 'opensdmx[semantic]' in result.output
    assert "uv tool install" in result.output


@pytest.mark.usefixtures("without_ollama")
def test_embed_cli_prints_the_install_hint() -> None:
    """Same contract for `opensdmx embed`: the hint names the extra unescaped."""
    with patch("opensdmx.cli._check_api_reachable"):
        result = runner.invoke(app, ["embed"])

    assert result.exit_code == 1
    assert 'opensdmx[semantic]' in result.output


def test_keyword_search_does_not_need_the_ollama_client(without_ollama: None) -> None:
    """The default path must keep working on an install without the extra.

    Runs the real keyword search over a stub catalog: hiding the client only proves
    something if a search actually happens.
    """
    from tests.test_discovery import _fake_context, _search_with_context

    results = _search_with_context(
        "unemployment", _fake_context({"UNEMP": "Unemployment monthly"})
    )

    assert not results.is_empty()
    assert results["df_id"][0] == "UNEMP"


def test_pyproject_keeps_ollama_in_the_guide_extra(pyproject: dict) -> None:
    """`run_guide` calls `semantic_search`, so `[guide]` has to bring the client."""
    extras = pyproject["project"]["optional-dependencies"]

    for extra in ("semantic", "guide"):
        assert any(dep.startswith("ollama") for dep in extras[extra]), extra
