"""BM25 relevance ranking for keyword search.

The previous scorer summed raw token occurrences with no length denominator and
weighed every query word the same, so long titles outranked relevant ones and a
stopword counted like the topic. Measured on two blind gold sets (ISTAT 54
queries, Eurostat 48), that cost roughly half the achievable MRR:

    provider   scorer      MRR     monolingual MRR
    eurostat   previous    0.086   0.172
    eurostat   BM25        0.155   0.310
    istat      previous    0.073   0.133
    istat      BM25        0.138   0.217

BM25 fixes both defects by construction: `idf` down-weights common terms, and
`b` normalises for document length.

**Prefix awareness.** Plain BM25 matches whole tokens, which would silently drop
prefix search — `search comun` goes from 605 results to none. So a query token
with no exact match in the vocabulary expands to the terms it *prefixes*
(`comun` reaches `comuni` and `comunali`, not `incomunicabile`), and those
expanded terms contribute at half weight so an exact hit always outranks a
prefix hit.
"""

from __future__ import annotations

import re
from collections import Counter

import numpy as np
import polars as pl

# Okapi BM25 defaults. k1 saturates term frequency, b controls how much document
# length is normalised. Both are corpus-independent here: length normalisation is
# relative to the corpus average, so providers with very different title lengths
# (unicef averages 2.6 words, abs 13.7) need no per-provider tuning.
K1 = 1.5
B = 0.75

# Field boosts, carried over from the previous scorer: a token in the id, or in
# the opening of the title where the topic tends to be, means more than one
# buried in a breakdown label. Expressed in units of the query's mean idf so they
# stay on the same scale as the BM25 contribution.
ID_BOOST = 3.0
HEAD_BOOST = 2.0
HEAD_CHARS = 60

# Weight of a term reached by prefix expansion rather than by an exact match.
PREFIX_WEIGHT = 0.5

# Underscore excluded on purpose: `\w` would swallow it and tokenise UNE_RT_M as a
# single term, so a query for "une" or "rt" would never match an id exactly. Dataflow
# ids are underscore-separated across every provider (LFSI_NEET_A, 151_914_DF_DCCV_...).
_WORD = re.compile(r"[^\W_]+")


def tokenize(text: str) -> list[str]:
    return _WORD.findall(text.lower())


class BM25Index:
    """In-memory BM25 index over a set of documents.

    Built per search call: measured 0.14 s on the largest catalogue (Eurostat,
    8150 dataflows) and 0.43 s on ISTAT's extended text, against a command whose
    Python import alone costs ~1.9 s. Querying is 5-18 ms. No disk index, hence
    nothing to invalidate when the dataflow or category cache refreshes.
    """

    def __init__(self, docs: list[str], ids: list[str], *, k1: float = K1, b: float = B):
        self.ids = ids
        self.k1, self.b = k1, b

        tokens = [tokenize(doc or "") for doc in docs]
        self.lengths = np.array([len(t) for t in tokens], dtype=np.float32)
        avgdl = float(self.lengths.mean()) if len(self.lengths) else 0.0
        # An empty corpus makes mean() NaN, and NaN is truthy: guard explicitly or
        # every score silently becomes NaN.
        self.avgdl = avgdl if np.isfinite(avgdl) and avgdl > 0 else 1.0

        self.postings: dict[str, list[tuple[int, int]]] = {}
        for i, doc_tokens in enumerate(tokens):
            for term, tf in Counter(doc_tokens).items():
                self.postings.setdefault(term, []).append((i, tf))

        n = len(docs) or 1
        self.idf = {
            term: float(np.log((n - len(posting) + 0.5) / (len(posting) + 0.5) + 1.0))
            for term, posting in self.postings.items()
        }
        self.vocabulary = list(self.postings)

        self._id_tokens = [set(tokenize(i or "")) for i in ids]
        self._head_tokens = [set(tokenize((d or "")[:HEAD_CHARS])) for d in docs]

    def _expand(self, token: str) -> list[str]:
        """Terms this query token matches: itself, or the terms it prefixes."""
        if token in self.postings:
            return [token]
        return [term for term in self.vocabulary if term.startswith(token)]

    def scores(self, query: str) -> np.ndarray:
        scores = np.zeros(len(self.ids), dtype=np.float32)
        query_tokens = tokenize(query)
        if not query_tokens:
            return scores

        all_idfs: list[float] = []
        for query_token in query_tokens:
            exact = query_token in self.postings
            for term in self._expand(query_token):
                all_idfs.append(self.idf[term])
                weight = 1.0 if exact else PREFIX_WEIGHT
                posting = self.postings[term]
                idx = np.fromiter((i for i, _ in posting), dtype=np.int64, count=len(posting))
                tf = np.fromiter((f for _, f in posting), dtype=np.float32, count=len(posting))
                denom = tf + self.k1 * (
                    1 - self.b + self.b * self.lengths[idx] / self.avgdl
                )
                scores[idx] += weight * self.idf[term] * tf * (self.k1 + 1) / denom

        unit = float(np.mean(all_idfs)) if all_idfs else 1.0
        for i in np.nonzero(scores > 0)[0]:
            id_hits = sum(
                1 for t in query_tokens if any(t in term for term in self._id_tokens[i])
            )
            head_hits = sum(
                1 for t in query_tokens if any(t in term for term in self._head_tokens[i])
            )
            scores[i] += (
                unit * (ID_BOOST * id_hits + HEAD_BOOST * head_hits) / len(query_tokens)
            )
        return scores


def rank(
    catalog: pl.DataFrame,
    candidates: pl.DataFrame,
    keyword: str,
    *,
    text_columns: list[str],
) -> pl.DataFrame:
    """Score `candidates` against `keyword`, ranked highest first.

    The index is built over the **whole** catalog, not over the candidate set:
    idf is a property of the corpus, and a candidate set selected by the query
    already contains the query's terms in every row, which would flatten their
    idf to nothing and throw away the signal BM25 exists to provide.

    Every candidate row is returned. Some score zero — a token matched only
    inside a longer word and prefix expansion did not reach it — and those sort
    last, so the caller's result count is preserved.
    """
    if not tokenize(keyword) or candidates.is_empty():
        return candidates.with_columns(pl.lit(0.0, dtype=pl.Float32).alias("score"))

    index = BM25Index(_documents(catalog, text_columns), catalog["df_id"].to_list())
    scores = dict(zip(index.ids, index.scores(keyword).tolist()))

    return candidates.with_columns(
        pl.col("df_id")
        .replace_strict(scores, default=0.0, return_dtype=pl.Float32)
        .alias("score")
    ).sort("score", descending=True)


def _documents(datasets: pl.DataFrame, text_columns: list[str]) -> list[str]:
    present = [c for c in text_columns if c in datasets.columns]
    if not present:
        return [""] * datasets.height
    joined = pl.concat_str(
        [pl.col(c).fill_null("") for c in present], separator=" "
    )
    return datasets.select(joined.alias("_doc"))["_doc"].to_list()
