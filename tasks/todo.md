# istatPy - Development Plan

## Goal
Python port of the R package `istatR`, managed with `uv`.
ISTAT SDMX REST API: `https://esploradati.istat.it/SDMXWS/rest`

## Project structure
```
istatPy/
├── pyproject.toml
├── README.md
├── LOG.md
├── tasks/todo.md
└── src/
    └── istatpy/
        ├── __init__.py
        ├── base.py       # API config, HTTP functions
        ├── utils.py      # XML helpers, make_url_key
        ├── discovery.py  # all_available, search_dataset, IstatDataset
        └── retrieval.py  # get_data, istat_get, parse_time_period
```

## Dependencies
- `httpx` - HTTP (with retry via `tenacity`)
- `lxml` - XML parsing with namespace support
- `polars` - DataFrame (instead of tibble/dplyr)
- `duckdb` - SQL queries on data
- `plotnine` - static charts

## Phases

### Phase 1 - Project setup
- [x] `uv init istatPy` in parent directory
- [x] Add dependencies with `uv add`
- [x] Create `src/istatpy/` structure

### Phase 2 - base.py
- [x] Config: `BASE_URL`, `AGENCY_ID`, `TIMEOUT`
- [x] `istat_timeout()` - get/set timeout
- [x] `istat_request()` - HTTP with retry (3 attempts)
- [x] `istat_request_xml()` - XML response with namespace
- [x] `istat_request_csv()` - CSV response → Polars DataFrame

### Phase 3 - utils.py
- [x] `xml_text_safe()` - safe XML text extraction
- [x] `xml_attr_safe()` - safe XML attribute extraction
- [x] `make_url_key()` - builds SDMX filter key
- [x] `get_name_by_lang()` - name by language from XML

### Phase 4 - discovery.py
- [x] `all_available()` - list all ISTAT datasets
- [x] `search_dataset(keyword)` - search by keyword
- [x] Standalone functions (not a class):
  - `istat_dataset()` - create dataset dict
  - `print_dataset()` - print summary
  - `dimensions_info()` - dimension metadata
  - `get_dimension_values()` - available values
  - `get_available_values()` - all available values
  - `set_filters()` - set filters
  - `reset_filters()` - reset filters
- [x] `_get_dimensions()` - internal

### Phase 5 - retrieval.py
- [x] `parse_time_period(x)` - parse SDMX formats: YYYY, YYYY-MM, YYYY-Qn, YYYY-Sn, YYYY-Wnn, YYYY-MM-DD
- [x] `get_data(dataset, ...)` - fetch data with filters
- [x] `istat_get(dataflow_id, ...)` - all-in-one shortcut

### Phase 6 - __init__.py
- [x] Export public API

### Phase 7 - Documentation
- [x] README.md with examples (including unemployment plot with plotnine)
- [x] LOG.md

---

## Phase 8 - Rate limiting + Dataflow cache

### Context
ISTAT enforces a limit of **5 queries/minute per IP**. Exceeding it triggers a block lasting 1-2 days.

### Part 1 — Rate limiter in `base.py`

- [x] Add `_rate_limit_check()` to `base.py`
  - Stores last call timestamp in OS temp dir (`istatpy_rate_limit.log`)
  - If `elapsed < 12s`: prints warning and `time.sleep(12 - elapsed)`
  - Overwrites the log with the current timestamp after each call
- [x] Call `_rate_limit_check()` inside `_do_request()` in `istat_request()`

### Part 2 — Dataflow list cache in `discovery.py`

- [x] Add `_load_cached_dataflows()` to `discovery.py`
  - Cache in OS temp dir (`istatpy_dataflows.parquet`), TTL 24h
  - If file exists and is < 24h old: read parquet (0 API calls)
  - If expired or missing: call API, save parquet, return DataFrame
- [x] `all_available()` uses the cache

---

## Phase 9 - CLI

### Goal
Implement an `istatpy` CLI with 4 commands using Typer + Rich.

### Part 1 — Dependencies
- [x] `uv add typer rich`

### Part 2 — Create `src/istatpy/cli.py`
- [x] Typer app with 4 commands:
  - `search <keyword>` → Rich table with df_id + df_description
  - `info <dataset_id>` → Rich panel with metadata + dimensions table
  - `values <dataset_id> <dim>` → Rich table with id + name
  - `get <dataset_id> [--DIM VALUE ...] [--out FILE]` → CSV to stdout or file (csv/parquet/json)
- [x] Error handling with Rich messages and `raise typer.Exit(1)`
- [x] API reachability check at startup (lightweight HEAD request if no rate-limit log)

### Part 3 — Update `__init__.py`
- [x] Import `main` from `cli.py`

### Part 4 — Tests
- [x] `uv run istatpy --help`
- [x] `uv run istatpy search --help`
- [x] `uv run istatpy info --help`
- [x] `uv run istatpy values --help`
- [x] `uv run istatpy get --help`

### Part 5 — LOG.md
- [x] Update LOG.md

---

## Review

- 4-module structure: `base`, `utils`, `discovery`, `retrieval`
- API mirrors istatR: same functions, same names
- Dataset represented as a Python `dict` (equivalent to R S3 list)
- DataFrame: Polars instead of tibble
- HTTP: httpx + tenacity for automatic retry
- XML: lxml with namespace-aware XPath
- `parse_time_period` handles all SDMX formats via Polars `map_elements`
- `set_filters` and `reset_filters` return a new dict (immutability)
- README includes full example with plotnine
