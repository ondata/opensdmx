# Architecture Overview

opensdmx is a Python package and CLI for querying any SDMX 2.1 REST API. It is organized as a set of focused modules with a clear data flow.

---

## Design philosophy

opensdmx is designed first and foremost as a **CLI tool for LLM orchestration**. The primary "user" is an AI agent that reads stdout and composes commands step by step — not a Python developer importing objects.

This shapes every architectural decision:

- **Output is plain text or structured data (CSV, JSON), never Python objects.** An LLM reads stdout; it does not need a `DataMessage` or a `StructureMessage`.
- **`print` over return values where the caller is an agent.** Direct output is intentional — the CLI is designed to speak to an AI orchestrating it.
- **No rich object model.** Complexity justified in a Python library (URN parsing, MRO-based dispatch, message hierarchies) is unnecessary overhead here.
- **Readable, self-contained error messages.** When something goes wrong, the agent must understand why from the CLI output alone — no stack traces, no internal paths.

opensdmx works as a standalone CLI and as an importable Python library, but design trade-offs are resolved in favour of the agent-orchestration use case.

---

## Module map

| Module | Responsibility |
|---|---|
| `base.py` | Provider registry, HTTP client, rate limiting, retry logic |
| `discovery.py` | Dataset listing, structure parsing, filter management |
| `retrieval.py` | Data fetching, TIME_PERIOD conversion |
| `utils.py` | XML parsing helpers, SDMX URL key builder |
| `db_cache.py` | SQLite cache for dimensions, codelists, constraints, blacklist |
| `embed.py` | Ollama embeddings for semantic search |
| `ai.py` | AI-guided discovery session (chatlas + Gemini) |
| `cli.py` | Typer CLI: search, info, values, get, plot, embed, blacklist |
| `__init__.py` | Public API surface — re-exports from the modules above |
| `portals.json` | Bundled provider configuration file |

---

## Data flow

### CLI command to output

```
User runs: opensdmx get une_rt_m --freq M --geo IT --out data.csv
         |
         v
cli.py  get()
  1. _apply_provider(provider)          → base.py  set_provider()
  2. load_dataset(dataset_id)           → discovery.py
       └─ all_available()               → dataflows.parquet cache (24h TTL)
            └─ sdmx_request_xml()       → base.py  (HTTP, rate limit, retry)
       └─ _get_dimensions(struct_id)    → db_cache.py  (SQLite, 7d TTL)
            └─ sdmx_request_xml()
  3. set_filters(ds, **filters)         → discovery.py  (case-insensitive)
  4. get_data(ds, ...)                  → retrieval.py
       └─ make_url_key(filters)         → utils.py
       └─ sdmx_request_csv(path)        → base.py  (HTTP, rate limit, retry)
       └─ parse_time_period(series)     → retrieval.py
  5. df.write_csv(out)                  → Polars
```

### Semantic search flow

```
opensdmx search --semantic "unemployment"
         |
         v
cli.py  search()
  1. embed.semantic_search(query, n)
       └─ embed_df = read_parquet(embeddings.parquet)
       └─ embed._expand_query(query)    → chatlas + Gemini (LLM query expansion)
       └─ embed._embed([expanded])      → Ollama nomic-embed-text-v2-moe
       └─ cosine similarity → top-N results
  2. all_available()                    → filter invalid datasets
  3. Print table with df_id, description, score
```

---

## Cache layers

opensdmx uses two cache layers, both stored under `~/.cache/opensdmx/{AGENCY_ID}/`.

### Parquet files (file-based, TTL-based invalidation)

| File | Content | TTL |
|---|---|---|
| `dataflows.parquet` | Full provider dataset catalog | 24 hours |
| `embeddings.parquet` | Ollama embedding vectors per dataset | No expiry (manual rebuild via `opensdmx embed`) |

The dataflow cache is invalidated by comparing `os.path.getmtime` to the current time. The embeddings file has no automatic expiry; it must be rebuilt explicitly.

### SQLite database (`cache.db`, TTL-based per row)

All structured metadata is stored in a single SQLite database per provider. Each table has a `cached_at` column (Unix timestamp). Rows older than **7 days** are treated as expired and re-fetched.

| Table | Content |
|---|---|
| `structure_dims` | Dimension definitions (id, position, codelist_id) per DSD |
| `codelist_info` | Human-readable description of each codelist |
| `codelist_values` | Individual code entries (id, name) for each codelist |
| `available_constraints` | Codes actually present in a dataset (from constraint endpoint) |
| `invalid_datasets` | Datasets that failed API availability checks (permanent) |

See `docs/cache.md` for the full schema.

---

## Provider abstraction

The active provider is stored as a module-level variable `_active_provider` in `base.py`. It can be either:

- A **preset key** (string) referencing an entry in `PROVIDERS` (loaded from `portals.json`).
- A **custom dict** with at minimum `base_url` and `agency_id`.

`set_provider(name_or_url, ...)` switches the active provider. If `name_or_url` is in the `PROVIDERS` dict, it is used directly. Otherwise it is treated as a base URL and a custom dict is built from the provided parameters.

`get_provider()` always returns a dict with all fields (merged with `_DEFAULTS` at load time for preset providers). This dict is consumed by every HTTP helper (`sdmx_request`, `sdmx_request_csv`) and by the cache path resolver (`get_cache_dir`).

The cache directory is `~/.cache/opensdmx/{agency_id}/`, so each provider gets an isolated namespace for all its Parquet and SQLite files.

All CLI commands accept a `--provider` / `-p` option that calls `set_provider()` before executing.
