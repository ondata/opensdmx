"""The `semantic` extra: importing is always safe, calling explains the install.

The Ollama client is an optional dependency, so a keyword-only install must be
able to import `opensdmx` and only find out what is missing when it actually asks
for an embedding.
"""

from __future__ import annotations

import sys

import pytest

from opensdmx import embed


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


def test_pyproject_keeps_ollama_out_of_the_hard_dependencies() -> None:
    """The install command the error suggests has to name an extra that exists."""
    import tomllib
    from pathlib import Path

    pyproject = tomllib.loads(
        Path(__file__).parent.parent.joinpath("pyproject.toml").read_text(encoding="utf-8")
    )
    project = pyproject["project"]

    assert any(dep.startswith("ollama") for dep in project["optional-dependencies"]["semantic"])
    assert not any(dep.startswith("ollama") for dep in project["dependencies"])


def test_keyword_search_does_not_need_the_ollama_client(without_ollama: None) -> None:
    """The default path must keep working on an install without the extra."""
    from opensdmx import ranking

    assert ranking.tokenize("unemployment rate")
