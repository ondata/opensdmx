# LOG

## 2026-02-26 (i18n)

- Translated all user-facing messages to English (CLI + rate limiter)
- Translated `tasks/todo.md` to English

## 2026-02-26 (CLI)

- CLI `istatpy` with 4 commands: `search`, `info`, `values`, `get` (Typer + Rich)
- `get` accepts dynamic filters `--DIM VALUE` via `typer.Context`
- `get` output: CSV to stdout or file (csv/parquet/json) with `--out`
- API reachability check at startup: lightweight HEAD request if no rate-limit log exists

## 2026-02-26

- Rate limiter: minimum 12s between API calls, log in OS temp dir
- Dataflow cache: `istatpy_dataflows.parquet` in OS temp dir, TTL 24h (avoids repeated heavy call in `istat_dataset()`)
- Added `pyarrow` dependency (required for `polars.to_pandas()`)

## 2026-02-26 (init)

- Created `istatpy` project with `uv init --package`
- Added `httpx`, `tenacity`, `lxml`, `polars`, `duckdb`, `plotnine`
- Implemented modules: `base.py`, `utils.py`, `discovery.py`, `retrieval.py`
- Public API exported in `__init__.py`
- All functions mirror `istatR`: same names, same signatures
  - `all_available()`, `search_dataset()`, `istat_dataset()`
  - `dimensions_info()`, `get_dimension_values()`, `get_available_values()`
  - `set_filters()`, `reset_filters()`
  - `get_data()`, `istat_get()`, `istat_timeout()`
- DataFrame: Polars (not pandas)
- Charts: plotnine (unemployment example in README)
