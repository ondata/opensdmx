"""Regression tests for embedding index provenance with no Ollama server."""

from datetime import datetime, timedelta

import numpy as np
import polars as pl
import pytest

from opensdmx import discovery, embed


@pytest.fixture
def index_path(tmp_path, monkeypatch):
    path = tmp_path / "embeddings.parquet"
    catalog = pl.DataFrame({"df_id": ["A"], "df_description": ["Dataset A"]})
    monkeypatch.setattr(discovery, "all_available", lambda: catalog)
    monkeypatch.setattr(embed, "_embed_cache_path", lambda: path)
    monkeypatch.setattr(embed, "_check_ollama", lambda: None)
    monkeypatch.setattr(embed, "_embed", lambda texts: np.array([[1, 0]] * len(texts)))
    return path


def test_current_index_records_provenance_and_search_is_silent(index_path, monkeypatch, caplog):
    monkeypatch.setattr(embed, "_category_context_for_embed", lambda: pl.DataFrame(
        schema={"df_id": pl.String, "cat_context": pl.String}
    ))
    monkeypatch.setattr(embed, "_descriptions_for_embed", lambda: pl.DataFrame(
        schema={"df_id": pl.String, "description": pl.String}
    ))
    embed.build_embeddings(progress=False)

    metadata = pl.read_parquet_metadata(index_path)
    assert metadata["opensdmx.embed.model"] == embed._EMBED_MODEL
    assert metadata["opensdmx.embed.text_version"] == embed._EMBED_TEXT_VERSION
    assert datetime.fromisoformat(metadata["opensdmx.embed.built_at"]).utcoffset() == timedelta(0)
    assert embed.semantic_search("test")["df_id"].to_list() == ["A"]
    assert not caplog.records


@pytest.mark.parametrize("stale_field", [None, "model", "text_version"])
def test_stale_index_warns_once_and_keeps_results(index_path, stale_field, caplog):
    metadata = None
    if stale_field is not None:
        metadata = {
            "opensdmx.embed.model": embed._EMBED_MODEL,
            "opensdmx.embed.text_version": embed._EMBED_TEXT_VERSION,
            "opensdmx.embed.built_at": "2026-01-01T00:00:00+00:00",
        }
        metadata[f"opensdmx.embed.{stale_field}"] = "old"
    pl.DataFrame({"df_id": ["A"], "embedding": [[1.0, 0.0]]}).write_parquet(
        index_path, metadata=metadata
    )

    for _ in range(2):
        assert embed.semantic_search("test")["df_id"].to_list() == ["A"]

    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) == 1
    assert "opensdmx embed" in warnings[0].getMessage()
    assert str(index_path) not in warnings[0].getMessage()


def test_incompatible_vector_dimensions_explain_how_to_rebuild(index_path):
    pl.DataFrame({"df_id": ["A"], "embedding": [[1.0, 0.0, 0.0]]}).write_parquet(index_path)

    with pytest.raises(RuntimeError, match="dimensions.*opensdmx embed"):
        embed.semantic_search("test")
