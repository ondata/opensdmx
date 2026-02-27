"""Semantic search via Ollama embeddings."""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import polars as pl

_EMBED_CACHE = Path(tempfile.gettempdir()) / "istatpy_embeddings.parquet"
_EMBED_MODEL = "nomic-embed-text-v2-moe"


def _embed(texts: list[str]) -> np.ndarray:
    """Embed a list of texts via Ollama. Returns (N, dim) float32 array."""
    import ollama

    response = ollama.embed(model=_EMBED_MODEL, input=texts)
    return np.array(response.embeddings, dtype=np.float32)


def build_embeddings(progress: bool = True) -> None:
    """Encode all catalog descriptions and save to /tmp/istatpy_embeddings.parquet."""
    from .discovery import all_available

    catalog = all_available()
    ids = catalog["df_id"].to_list()
    descriptions = catalog["df_description"].fill_null("").to_list()

    if progress:
        print(f"Embedding {len(descriptions)} descriptions with {_EMBED_MODEL}...")

    vectors = _embed(descriptions)

    rows = [
        {"df_id": df_id, "embedding": vec.tolist()}
        for df_id, vec in zip(ids, vectors)
    ]
    df = pl.DataFrame(rows, schema={"df_id": pl.Utf8, "embedding": pl.List(pl.Float32)})
    df.write_parquet(_EMBED_CACHE)

    if progress:
        print(f"Saved: {_EMBED_CACHE} ({len(rows)} rows, dim={vectors.shape[1]})")


def semantic_search(query: str, n: int = 10) -> pl.DataFrame:
    """Return top-N datasets by semantic similarity to query."""
    from .discovery import all_available

    if not _EMBED_CACHE.exists():
        raise FileNotFoundError(
            "Embeddings cache not found. Run: istatpy embed"
        )

    embed_df = pl.read_parquet(_EMBED_CACHE)
    doc_vecs = np.array(embed_df["embedding"].to_list(), dtype=np.float32)

    query_vec = _embed([query])[0]

    # Cosine similarity
    query_norm = query_vec / (np.linalg.norm(query_vec) + 1e-10)
    doc_norms = doc_vecs / (np.linalg.norm(doc_vecs, axis=1, keepdims=True) + 1e-10)
    scores = doc_norms @ query_norm

    top_idx = np.argsort(scores)[::-1][:n]

    catalog = all_available()
    catalog_map = {
        row["df_id"]: row["df_description"]
        for row in catalog.iter_rows(named=True)
    }

    results = [
        {
            "df_id": embed_df["df_id"][int(i)],
            "df_description": catalog_map.get(embed_df["df_id"][int(i)], ""),
            "score": float(scores[i]),
        }
        for i in top_idx
    ]
    return pl.DataFrame(results, schema={"df_id": pl.Utf8, "df_description": pl.Utf8, "score": pl.Float32})
