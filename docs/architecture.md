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
  1. _apply_provider(provider)          → base.py  resolve_provider()
  2. Validate the output file extension, if supplied
  3. load_dataset(dataset_id)           → discovery.py
       ├─ all_available()               → dataflows.parquet (7d default TTL)
       └─ _get_dimensions(struct_id)    → discovery.py, SQLite via db_cache.py (30d default TTL)
  4. set_filters(ds, **filters)         → discovery.py  (case-insensitive)
  5. get_data(ds, ...)                  → retrieval.py (size probe when applicable, then download)
       └─ make_url_key(filters)         → utils.py
       └─ sdmx_request_csv(path)        → base.py  (HTTP, rate limit, retry)
       └─ parse_time_period(series)     → retrieval.py
  6. _write_output(df, out)             → CSV to stdout, or file by extension + confirmation on stderr
```

### Semantic search flow

```
opensdmx search --semantic "unemployment"
         |
         v
cli.py  search()
  1. embed.semantic_search(query, n)
       └─ embed_df = read_parquet(embeddings.parquet)
       └─ embed._embed([query])         → Ollama nomic-embed-text-v2-moe
       └─ cosine similarity → top-N results
  2. all_available()                    → filter invalid datasets
  3. Print table with df_id, description, score
```

What text each dataflow is embedded from — and why the descriptions are harvested offline into a shipped resource — is documented in [Dataflow descriptions for semantic search](descriptions.md).

---

## Cache layers

opensdmx uses two cache layers, both stored under the provider cache directory. By default this is the OS user cache directory plus the provider key, for example `~/.cache/opensdmx/eurostat/` on Linux. `OPENSDMX_CACHE_DIR` can override the base directory, and `/tmp/opensdmx-{username}` is used only as a fallback if no preferred cache location is writable.

### Parquet files (file-based, TTL-based invalidation)

| File | Content | Default TTL |
|---|---|---|
| `dataflows.parquet` | Full provider dataset catalog | 7 days |
| `categories.parquet` | Category tree | 7 days |
| `categorisation.parquet` | Dataflow-to-category links | 7 days |
| `embeddings.parquet` | Ollama embedding vectors per dataset | No expiry (manual rebuild via `opensdmx embed`) |
| `inps_df_index.parquet` | INPS dataflow-to-node/version index | Rebuilt with the INPS catalog |

The dataflow catalog expires based on its modification time and the configured TTL. Its `has_constraint` column records bulk constraint probe coverage, not a separate SQLite table.

### SQLite database (`cache.db`, TTL-based per row)

Structure, codelist, and constraint metadata and the blacklist share one SQLite database per cache directory. Expiring rows use `cached_at`. The default TTL is 30 days for structure and codelists and 7 days for available constraints. The blacklist uses `marked_at` and does not expire.

| Table | Content |
|---|---|
| `structure_dims` | Dimension definitions (id, position, codelist_id) per DSD |
| `codelist_info` | Human-readable description of each codelist |
| `codelist_values` | Code ID, name, and optional parent and order |
| `available_constraints` | Codes present in a dataset, resolved via the provider's constraint sources |
| `invalid_datasets` | Blacklist entries; no expiry, but removable |

See the [cache reference](cache.md) for the full schema and TTL overrides, and the [constraints specification](../openspec/specs/constraints-command/spec.md) for source selection and fallbacks.

---

## Provider abstraction

A provider value selects a provider. It is either:

- A **preset key** (string) referencing an entry in `PROVIDERS` (loaded from `portals.json`).
- A **custom dict** with at minimum `base_url` and `agency_id`.

Three layers decide which provider value is in effect, highest first:

1. the provider stored in a dataset dict (`ds["provider"]`, set by `load_dataset`), for the functions that take the dataset (`get_data`, `dimensions_info`, `get_dimension_values`, `get_codelist_hierarchy`, `get_available_values`, `enrich_with_labels`);
2. a scope opened with `use_provider(...)` (a `ContextVar`, so per thread and per `asyncio` task; a new thread does not inherit it), also used by `run_query`;
3. the process default, `_active_provider` in `base.py`, set by `set_provider()`.

`_current_provider_value()` returns the value in effect and is the only reader of `_active_provider`; `_set_default_provider()` is its only writer. `get_provider()` always returns a dict with all fields (merged with `_DEFAULTS` at load time for preset providers). This dict is consumed by every HTTP helper (`sdmx_request`, `sdmx_request_csv`) and, through `_provider_cache_key()`, by the cache path resolver (`get_cache_dir`) and the rate-limit lock, so cache files and pacing follow the provider in effect.

The cache directory is `<cache-base>/<key>/`. Presets use their canonical name; custom URL providers use `agency_id` if set or a short URL hash otherwise. Two custom URLs with the same explicit agency share the directory. See the [cache reference](cache.md) for base path resolution.

All CLI commands accept a `--provider` / `-p` option that sets the process default through `resolve_provider()` (aliases, unknown-name check, `OPENSDMX_AGENCY` fallback) before executing. The CLI runs one provider per process.
