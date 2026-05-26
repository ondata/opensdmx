# Product Requirements Document

## Overview

opensdmx is a Python library and CLI for querying any SDMX 2.1 REST API. It provides a uniform interface to 14 configured statistical providers, including Eurostat, Eurostat Comext, ISTAT, ECB, OECD, INSEE, Deutsche Bundesbank, World Bank, ABS, BIS, IMF, ILO, UNICEF, and Derzhstat.

---

## Problem statement

Statistical data from international agencies is distributed via SDMX 2.1 REST APIs, but each provider has slightly different endpoint conventions, rate limits, and data format behaviors. Users who want to access this data face:

- Manual URL construction with cryptic positional key syntax.
- No standard way to discover available datasets or dimension values.
- Provider-specific quirks (rate limits, CSV format parameters, agency IDs).
- Disconnection between theoretical codelist values and values actually present in a dataset.
- High barrier for exploratory analysis: no natural-language entry point.

---

## Goals

- Provide a single Python API that works identically across all supported SDMX 2.1 providers.
- Expose a CLI designed for LLM orchestration: plain-text and structured output, composable commands, readable error messages.
- Enable semantic search over provider catalogs via Ollama embeddings.
- Cache all structural metadata to minimize API calls.

---

## Non-goals

- Supporting SDMX 3.x or non-REST SDMX protocols.
- Providing a data warehouse or persistent data store.
- Managing authentication (all supported providers are public).

---

## Users

- Data analysts and researchers who use SDMX data from public statistical agencies.
- Python developers integrating statistical data into pipelines or notebooks.
- Non-technical users who use the CLI for exploratory analysis.
- **AI agents and LLM-based systems** that orchestrate statistical queries programmatically — the primary design target for the CLI interface.

---

## Functional requirements

### Provider management

- Support 14 configured providers: eurostat, comext, istat, ecb, oecd, insee, bundesbank, worldbank, abs, bis, imf, ilo, unicef, derzhstat.
- Allow switching the active provider at any time via `set_provider()` or `--provider` CLI option.
- Support custom providers (any SDMX 2.1 URL + agency_id).
- Provider configuration includes: base URL, agency ID, rate limit, language preference, dataflow params, constraint endpoint, data format parameter, metadata prefix, user-agent, category support, and provider capability flags.

### Dataset discovery

- List all available datasets for the active provider (`all_available()`).
- Search datasets by keyword in their description (`search_dataset()`).
- Load a dataset object by dataflow ID, structure ID, or description (`load_dataset()`).
- Show dimension metadata including position, codelist ID, and description (`dimensions_info()`).
- Show available dimension values from the codelist (`get_dimension_values()`).
- Show values actually present in the dataset via the constraint endpoint (`get_available_values()`).

### Data retrieval

- Fetch data with optional dimension filters, period range, and observation count limits (`get_data()`, `fetch()`).
- Convert SDMX TIME_PERIOD strings to Python `date` objects automatically.
- Return data as a Polars DataFrame sorted by TIME_PERIOD ascending.
- Output to CSV, Parquet, or NDJSON from the CLI.

### Semantic search

- Build and store Ollama embedding vectors for all dataset descriptions (`embed` command / `build_embeddings()`).
- Search by semantic similarity against locally built embeddings (`semantic_search()`).
- Embeddings are stored per provider in the provider cache directory, for example `~/.cache/opensdmx/eurostat/embeddings.parquet`.

### Blacklist management (`blacklist` command)

- List datasets marked as unavailable.
- Interactively select entries to remove from the blacklist.

### Caching

- Cache the dataflow catalog as Parquet with a 7-day TTL per provider.
- Cache thematic categories as Parquet with a 7-day TTL per provider.
- Cache dimension definitions, codelist information, and codelist values in SQLite with a 30-day TTL per row.
- Cache available constraints in SQLite with a 7-day TTL per row.
- Namespace all cache files under a provider cache directory resolved from `OPENSDMX_CACHE_DIR`, the OS user cache directory, or `/tmp/opensdmx-{username}` as a fallback.

### Rate limiting and retry

- Enforce per-provider minimum intervals between API calls using a file-based mechanism.
- Retry all HTTP requests up to 3 times with exponential backoff (0.5 s – 4 s).

---

## CLI commands

| Command | Description |
|---|---|
| `opensdmx search <keyword>` | Keyword search in dataset descriptions |
| `opensdmx search --semantic <query>` | Semantic search (requires `opensdmx embed`) |
| `opensdmx embed` | Build semantic embeddings cache via Ollama |
| `opensdmx info <id>` | Show dataset metadata and dimensions |
| `opensdmx values <id> <dim>` | Show available values for a dimension |
| `opensdmx constraints <id> [dim]` | Show dimension values actually present in the data |
| `opensdmx tree` | Browse provider category schemes and category trees |
| `opensdmx siblings <id>` | Show dataflows that share categories with a dataflow |
| `opensdmx providers` | List configured providers and capability flags |
| `opensdmx which <query>` | Map a natural-language need to the most relevant command |
| `opensdmx get <id> [--DIM VALUE] [--out file]` | Download data |
| `opensdmx run <query.yaml> [--out file]` | Re-run a saved YAML query |
| `opensdmx plot <id> [--DIM VALUE] [--out file]` | Plot data as a line chart |
| `opensdmx guide <query>` | AI-guided dataset discovery and filter selection (`guide` extra) |
| `opensdmx blacklist` | Manage the unavailability blacklist |

All commands accept `--provider` / `-p` to set the active provider.

---

## Python API surface

| Function | Module |
|---|---|
| `set_provider`, `get_provider`, `set_timeout` | `base` |
| `all_available`, `search_dataset`, `load_dataset` | `discovery` |
| `dimensions_info`, `get_dimension_values`, `get_available_values` | `discovery` |
| `set_filters`, `reset_filters`, `print_dataset` | `discovery` |
| `get_data`, `fetch`, `parse_time_period` | `retrieval` |

---

## Dependencies

| Package | Purpose |
|---|---|
| `httpx` | HTTP client |
| `tenacity` | Retry logic |
| `lxml` | XML parsing |
| `polars` | DataFrames |
| `pyarrow` | Parquet serialization |
| `ollama` | Local embeddings |
| `typer` | CLI framework |
| `rich` | Terminal output formatting |
| `plotnine` | Line chart plotting |
| `numpy` | Cosine similarity computation |
| `chatlas[google]` | AI conversation with Gemini (`guide` extra) |
| `questionary` | Interactive prompts (`guide` extra) |

---

## Key design decisions

- **Provider isolation**: all cache files are namespaced per agency ID; switching providers does not affect another provider's cache.
- **File-based rate limiting**: the lock file persists across processes, preventing concurrent requests from exceeding the rate limit.
- **Positional key ordering**: dimensions in the SDMX URL key must follow the `position` field from the DSD; this is enforced by sorting at load time and preserving dict insertion order.
- **TIME_PERIOD normalization**: all SDMX time formats are converted to `date` objects so that data is sortable and plottable without user intervention.
- **Constraint endpoint flexibility**: Eurostat uses `contentconstraint` while most others use `availableconstraint`; this is a per-provider config field.
