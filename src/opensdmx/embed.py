"""Semantic search via Ollama embeddings."""

from __future__ import annotations

import httpx
import numpy as np
import polars as pl

from .base import get_cache_dir

_EMBED_MODEL = "nomic-embed-text-v2-moe"


def _embed_cache_path():
    return get_cache_dir() / "embeddings.parquet"


def _check_ollama() -> None:
    """Raise RuntimeError if Ollama server is unreachable or the embed model is missing."""
    import ollama

    try:
        models = ollama.list().models
    except (httpx.ConnectError, httpx.HTTPError, OSError):
        raise RuntimeError(
            "Ollama server not reachable. Start it with:  ollama serve\n"
            "Tip: use keyword search instead:  opensdmx search <keyword>"
        )
    available = [m.model for m in models if m.model is not None]
    # accept exact match or model name without tag (e.g. "nomic-embed-text-v2-moe:latest")
    if not any(m == _EMBED_MODEL or m.startswith(_EMBED_MODEL + ":") for m in available):
        raise RuntimeError(
            f"Ollama model '{_EMBED_MODEL}' not found (available: {', '.join(available) or 'none'}).\n"
            f"Pull it with:  ollama pull {_EMBED_MODEL}\n"
            f"Tip: use keyword search instead:  opensdmx search <keyword>"
        )


def _embed(texts: list[str]) -> np.ndarray:
    """Embed a list of texts via Ollama. Returns (N, dim) float32 array."""
    import ollama

    response = ollama.embed(model=_EMBED_MODEL, input=texts)
    return np.array(response.embeddings, dtype=np.float32)


def _category_context_for_embed() -> pl.DataFrame:
    """Aggregate scheme_name + cat_name per df_id from the cached category tree.

    Only uses the local cache — never triggers a live fetch. If the category
    cache files are not yet present (provider doesn't support categories, or
    user hasn't run `opensdmx tree` yet), returns an empty DataFrame and the
    embedding falls back to df_id + description only.
    """
    empty = pl.DataFrame({"df_id": [], "cat_context": []}, schema={"df_id": pl.Utf8, "cat_context": pl.Utf8})

    from .categories import _categories_cache_path, _categorisation_cache_path

    cats_path = _categories_cache_path()
    csation_path = _categorisation_cache_path()
    if not cats_path.exists() or not csation_path.exists():
        return empty

    categories_df = pl.read_parquet(cats_path)
    categorisation_df = pl.read_parquet(csation_path)

    if categorisation_df.is_empty():
        return empty

    return (
        categorisation_df.join(
            categories_df.select(["scheme_id", "scheme_name", "cat_path", "cat_name"]),
            on=["scheme_id", "cat_path"],
            how="left",
        )
        .with_columns(
            pl.concat_str(
                [pl.col("scheme_name").fill_null(""), pl.col("cat_name").fill_null("")],
                separator=" ",
            ).str.strip_chars().alias("ctx")
        )
        .group_by("df_id")
        .agg(pl.col("ctx").str.concat(" ").alias("cat_context"))
    )


def build_embeddings(progress: bool = True) -> None:
    """Encode all catalog descriptions and save to the provider's cache directory.

    Requires Ollama running locally with the ``nomic-embed-text-v2-moe`` model pulled.
    Start Ollama with ``ollama serve`` and pull the model with
    ``ollama pull nomic-embed-text-v2-moe`` before calling this function.
    Must be re-run whenever the provider changes or new datasets are available.

    Args:
        progress: if True, print progress messages (default: True)

    Raises:
        RuntimeError: if Ollama is not reachable or the model is not available
        RuntimeError: if no datasets are found for the current provider
    """
    from .discovery import all_available

    _check_ollama()
    catalog = all_available()
    if catalog.is_empty():
        raise RuntimeError("No datasets found. Check your provider or network connection.")

    cat_context = _category_context_for_embed()
    catalog_with_cats = catalog.join(cat_context, on="df_id", how="left").with_columns(
        pl.col("cat_context").fill_null("")
    )

    ids = catalog_with_cats["df_id"].to_list()
    descriptions = catalog_with_cats["df_description"].fill_null("").to_list()
    cat_contexts = catalog_with_cats["cat_context"].to_list()
    texts = [
        " ".join(part for part in (df_id, desc, cat_ctx) if part).strip()
        for df_id, desc, cat_ctx in zip(ids, descriptions, cat_contexts)
    ]

    if progress:
        n_with_cats = sum(1 for c in cat_contexts if c)
        if n_with_cats:
            print(f"Enriching {n_with_cats}/{len(texts)} descriptions with cached category context.")
        else:
            print("No category cache found — embedding df_id + description only. "
                  "Run `opensdmx tree` first for richer embeddings on providers that support categories.")
        print(f"Embedding {len(texts)} descriptions with {_EMBED_MODEL}...")

    vectors = _embed([f"search_document: {t}" for t in texts])
    cache_path = _embed_cache_path()

    rows = [
        {"df_id": df_id, "embedding": vec.tolist()}
        for df_id, vec in zip(ids, vectors)
    ]
    df = pl.DataFrame(rows, schema={"df_id": pl.Utf8, "embedding": pl.List(pl.Float32)})
    df.write_parquet(cache_path)

    if progress:
        dim = vectors.shape[1] if vectors.ndim > 1 else 0
        print(f"Saved: {cache_path} ({len(rows)} rows, dim={dim})")


def semantic_search(query: str, n: int = 10) -> pl.DataFrame:
    """Return top-N datasets by semantic similarity to a natural-language query.

    Requires Ollama running locally and embeddings built with :func:`build_embeddings`.

    Args:
        query: natural-language query (e.g. ``"unemployment by country"``).
        n: number of results to return (default: 10).

    Returns:
        Polars DataFrame with columns ``df_id``, ``df_description``, ``score`` (cosine similarity).

    Raises:
        RuntimeError: if Ollama is not reachable or the model is not available.
        FileNotFoundError: if the embeddings cache does not exist (run :func:`build_embeddings` first).
    """
    from .discovery import all_available

    _check_ollama()
    cache_path = _embed_cache_path()
    if not cache_path.exists():
        raise FileNotFoundError(
            "Embeddings cache not found. Run: opensdmx embed"
        )

    embed_df = pl.read_parquet(cache_path)
    if embed_df.is_empty():
        cache_path.unlink(missing_ok=True)
        raise FileNotFoundError(
            "Embeddings cache is empty (corrupted). Run: opensdmx embed"
        )
    doc_vecs = np.array(embed_df["embedding"].to_list(), dtype=np.float32)

    query_vec = _embed([f"search_query: {query}"])[0]

    # Cosine similarity
    query_norm = query_vec / (np.linalg.norm(query_vec) + 1e-10)
    doc_norms = doc_vecs / (np.linalg.norm(doc_vecs, axis=1, keepdims=True) + 1e-10)
    scores = doc_norms @ query_norm

    # Request more candidates to compensate for filtered-out invalid datasets
    top_idx = np.argsort(scores)[::-1][:n * 2]

    catalog = all_available()
    catalog_map = {
        row["df_id"]: row["df_description"]
        for row in catalog.iter_rows(named=True)
    }

    results = []
    for i in top_idx:
        df_id = embed_df["df_id"][int(i)]
        if df_id not in catalog_map:
            continue  # skip invalid or removed datasets
        results.append({
            "df_id": df_id,
            "df_description": catalog_map[df_id],
            "score": float(scores[i]),
        })
        if len(results) == n:
            break
    return pl.DataFrame(results, schema={
        "df_id": pl.Utf8,
        "df_description": pl.Utf8,
        "score": pl.Float32,
    })
