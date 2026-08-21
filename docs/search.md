# Dataset search: how it works and what was measured

How `opensdmx search` finds a dataflow, why it is shaped this way, and what the measurements say. This is design rationale and a running record of the evidence — the runnable parts live in `src/opensdmx/discovery.py`, `src/opensdmx/embed.py`, and `src/opensdmx/categories.py`.

Companion documents: [Dataflow descriptions for semantic search](descriptions.md) for where the descriptive text comes from, and [Architecture](architecture.md) for the module layout.

## Current state (v0.22.3)

Both paths described below ship today. Concretely:

- **Keyword search needs nothing.** It reads the local dataflow cache and works offline for every provider.
- **Semantic search runs on [Ollama](https://ollama.com) with `nomic-embed-text-v2-moe`.** The model is a constant in `embed.py`; there is no flag, environment variable or fallback backend. Without a reachable Ollama server the command fails and points you back to the keyword path.
- **The semantic index is built on demand, per provider**, by `opensdmx embed`, into `<cache>/<provider>/embeddings.parquet`. Every provider can be indexed. Nothing is precomputed and nothing ships in the package.
- **What differs per provider is the corpus, not the capability.** `df_prose` — the largest source of text by far — is read from a `data/descriptions/<provider>.parquet` shipped inside the wheel, and today only `istat.parquet` exists. Elsewhere the embedded document falls back to id, title and category context. The measurements below were run on ISTAT and should be read as the ceiling, not as a per-provider promise.
- **Latency**, ISTAT, 4,896 dataflows: about 10 s on the first query of a session (Ollama loading the model), then ~1 s. The cost is the model load, not the similarity maths.
- **Flags are not shared between the two paths.** Under `--semantic` only `--n` and `--grep` apply; `--category`, `--page` and `--all` belong to the keyword path.

The rest of this document explains why it is shaped this way and what the numbers say.

## The problem search has to solve

A user asks for "how many people live in Italy" and the catalogue answers with 4,896 ISTAT dataflows whose titles read `Coltivazioni`, `Superfici e produzione - dati in complesso`, `Lazio`, `Età di lei e di lui`. Titles alone carry very little: many are leaf labels that only make sense under their parent topic, and SDMX `<common:Description>` — the field that should hold the long text — is not populated by every provider (ISTAT does not populate it at all).

So search cannot be "grep the title". Every improvement below is about finding more text to match against, or matching it better.

## The two paths

| | keyword | semantic |
|---|---|---|
| command | `opensdmx search <words>` | `opensdmx search --semantic <question>` |
| entry point | `discovery.search_dataset` | `embed.semantic_search` |
| method | case-insensitive token match, AND with OR fallback, synthetic relevance score | cosine similarity over embeddings |
| requires | nothing (local cache only) | Ollama running + `opensdmx embed` run once |

### What each path indexes — they are not the same text

This asymmetry matters for any comparison between the two, and is easy to miss:

| text | keyword | semantic |
|---|---|---|
| `df_id` | yes | yes |
| `df_description` (the SDMX `Name`) | yes | yes |
| `cat_context` (category names) | yes, without the scheme | yes, with the scheme |
| `df_prose` (harvested reference metadata) | **no** | **yes** |
| `df_keywords` (`LAYOUT_DATAFLOW_KEYWORDS`) | **no** | **yes** |
| `df_notes` (`DATAFLOW_NOTES`) | **no** | **yes** |

On ISTAT the gap is at its widest: `df_description` averages a handful of words, while `df_prose` averages ~1,600 characters and covers 81% of the catalogue. The harvested prose ships inside the package (`data/descriptions/istat.parquet`, 109 KB) and is read offline — but only by the embedding path.

### The keyword scorer

`_score_results` awards, per query token: `+3` if it appears in `df_id`, `+2` if it appears in the first 60 characters of the description, `+1` **per occurrence**, `+1` if it appears in the category context. Tokens are combined with AND; if that returns nothing, it falls back to OR so a single unmatched token cannot wipe out the result set.

Two properties of this scorer are worth stating explicitly, because they set the limits of the keyword path: **all words weigh the same** (a match on "per" counts like a match on "consumi"), and **occurrences are summed with no length denominator**, so on long documents the score grows with length rather than with relevance.

## What has been measured

The project's rule on search is to measure before implementing. Twice now, that has changed the design.

### 2026-07-20 — category context (issue #52, shipped in v0.17.0)

The proposal was to derive a parent title from the ISTAT id pattern `{parent}_DF_{dsd}_{n}` and add it to the searchable text. Measured first: on the 3,460 ISTAT dataflows having both a parent and a category, the parent title **is** the category name in 51% of cases and is contained in it in a further 4%. An ISTAT-specific id parser would have rebuilt data the catalogue already carries.

Implemented instead: match against the category names from the local category cache (populated by `opensdmx tree`), which is provider-neutral. The 45% where the parent says something genuinely different — typically the vintage — remains uncovered.

### 2026-08-10 — keyword vs semantic retrieval

A retrieval-only eval, with no agent and no LLM judge: 27 information needs written blind in two physically separate passes (queries first with `gold: null`, saved to disk; gold filled in afterwards), each in Italian and English, 54 queries, gold as a *family* of df_ids, single deep cutoff of 50 for every arm.

Five arms, on ISTAT:

| arm | MRR | S@10 |
|---|---|---|
| A — current keyword | 0.073 | 16.7% |
| A′ — same scorer, extended text | 0.075 | 13.0% |
| A″ — BM25, extended text | 0.135 | 24.1% |
| **B — semantic (nomic-embed-text-v2-moe)** | **0.327** | **57.4%** |
| D — unweighted RRF of A and B | 0.231 | 46.3% |

What it establishes:

- **Semantic search wins by a wide margin** — 4.5× the current keyword path on MRR, and it finds the right dataflow in the top 10 for 57% of queries against 17%.
- **The advantage is not merely "more text".** Handing the harvested prose to the *current* scorer changes nothing (A′ ≈ A, within noise at n=54) because that scorer rewards long documents. Handing it to BM25 nearly doubles the baseline. But semantic still scores 2.4× BM25 **on identical text**, so a real part of the gap is the embeddings, not the corpus.
- **Cross-language is where lexical matching simply cannot compete.** ISTAT metadata is in Italian; on English queries the keyword path scores 0.012 and BM25 0.054, while semantic holds at 0.310 — the same level it reaches in Italian.
- **Register matters as much as language.** On technical phrasing BM25 recovers a lot of ground (0.237 vs 0.107); on natural phrasing it gains nothing at all (0.040 vs 0.041) while semantic scores 6×. When the user does not know the statistical vocabulary, refining word matching has nothing to work with.
- **Unweighted RRF hurts.** Fusing as equals with an arm that misses three times out of four drags down top ranks (0.231 vs 0.327). Note however that D has *fewer* misses than B: the flaw is the equal weighting, not the idea of a hybrid.

Caveats recorded with the result: the gold families were compiled with regex matching over `df_description || prose`, and `prose` is indexed by B and not by A, so **the construction bias favours the semantic arm** — B's margin should be read as an upper bound until a `doc-first` block is added. Absolute values are low for every arm, partly because gold families are narrow on generic needs; the comparison *between* arms is unaffected since the gold is identical for all.

## What follows from this

1. **Semantic search deserves to be available by default**, not behind a flag that requires a running Ollama server. These numbers are the empirical case for a self-contained backend — but as of 2026-08-21 that is a direction, not an approved plan. The plan drafted on 2026-07-16 named `google/embeddinggemma-300m` with `multilingual-e5-small` as fallback, and fastembed 0.8.0 exposes neither, so its premise no longer holds. An earlier attempt to move off Ollama (fastembed with `nomic-embed-text-v1.5-Q`, 2026-03-31) was reverted for poor quality on Italian queries. No candidate backend has yet been scored against the targets in point 4, which is what would settle it.
2. **Replacing the keyword scorer with BM25 over the extended text is a small, self-contained win** — roughly +85% MRR on ISTAT, no model, no server, no new dependency, works offline on the cache that already ships. The corpus is already on disk; only the lexical path does not read it.
3. **Do not promote unweighted RRF.** A hybrid, if wanted, must be weighted towards the semantic arm and re-measured.
4. **A static retriever now has a target to beat**: 0.135 to justify itself over BM25, and something near 0.327 to replace nomic. If a quantized static model reaches it, semantic search becomes shippable inside the package without Ollama and without onnxruntime.

Open, in order: BM25 on `search_dataset`; the `doc-first` counterweight block in the gold set; measuring the extended-text gain on providers other than ISTAT (only ISTAT has harvested prose today); the static-model arm.

## Where the working material lives

The numbers above are reproduced here in full precisely because the artifacts that
produced them are **not in this repository** — `tasks/`, `eval/` and `docs/eval.md`
are gitignored. The paths below are a note to whoever holds the working copy, not
links a reader can follow; nothing in this document depends on opening them.

- `tasks/todo-retrieval-eval.md` — the eval plan, its arms and open items
- `eval/goldset/retrieval.yaml` — the gold set, with the construction protocol and the gold rule in its header
- `eval/retrieval.py` — the harness
- `eval/results/<date>/retrieval.{md,json}` — report and raw per-query ranks
- `docs/eval.md`, `eval/run.py` — the separate end-to-end agent-loop eval

One practical note for anyone rerunning this: df_ids like `151_914` **must be quoted** in YAML. PyYAML follows YAML 1.1 and reads them as the integer 151914, so gold comparison silently fails and every arm scores near zero. The harness now aborts if a gold entry is not a string.
