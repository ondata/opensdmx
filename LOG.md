# LOG

## 2026-04-03 (2)

- Fix: removed production debug log (`/tmp/guide_debug.log`) from `ai.py`
- Fix: `get_name_by_lang` crashed on XML without "common" namespace
- Feat: test suite from 4 to 35 tests — coverage on `utils.py`, `parse_time_period()`, `make_url_key()`
- Feat: CI with GitHub Actions (pytest + ruff on push/PR)
- Production-readiness evaluation in `docs/evaluation.md`

## 2026-04-03

- Feat: cache TTL configurabile via env vars (`OPENSDMX_DATAFLOWS_CACHE_TTL`, `OPENSDMX_METADATA_CACHE_TTL`, `OPENSDMX_CONSTRAINTS_CACHE_TTL`); default sensati, `.env.example` aggiunto
- Feat: setup testing con pytest, primi test su `cache_config`
- Feat: CLI agent-friendly — `guide --yes --dataset` (non-interactive, auto-download), `blacklist --remove`, fail-fast for missing embeddings, examples with default provider note in all `--help`

## 2026-04-02 (3)

- Fix `guide`: removed `lookup_dimension_values` from AI model — now uses only constraint values
- Fix `guide`: "tutti"/"all" → selects TOTAL if available, otherwise no filter (never all individual codes)
- Feat `guide`: new flow — AI reads all constraints on first turn and proposes 2-3 tested scenarios; user chooses or customises dimension by dimension

## 2026-04-02 (2)

- Fix: `_rate_limit_check` now writes to `sys.stderr` instead of `print()` — avoids polluting stdout in pipes
- Fix: HTTP errors now show status code and URL; suggest `opensdmx constraints` on 400/404; use `reraise=True` in tenacity to avoid wrapping in `RetryError`
- Refactor: extracted `_parse_extra_filters()` — removes duplication between `get` and `plot`
- Feat: `get`/`plot` support multiple values per dimension: `--geo IT --geo FR` → `IT+FR` in URL
- Fix: removed hardcoded `curl` from `guide` results panel

## 2026-04-02

- `opensdmx` with no arguments shows version + help (instead of doing nothing)

- Fix OECD provider support: `search`, `info`, `constraints`, `get` now work
  - `portals.json`: added `catalog_agency: "all"` (endpoint `/dataflow/all`) and `constraint_params: {}` (no `references=none` which returned 500)
  - `discovery.py`: uses `catalog_agency` for catalog path; saves `df_id` as `{agencyID},{id}` (e.g. `OECD.SDD.STES,DSD_STES@DF_CLI`) to correctly build data URLs
  - Eurostat and ISTAT providers unchanged

## 2026-04-01 (2)

- New `opensdmx constraints <dataflow_id> [dimension]` CLI command
  - No dimension: summary table (`dimension_id`, `n_values`, `sample` first 3 codes)
  - With dimension: full `id`/`name` table of codes actually present, labels from codelist
  - `--provider` flag supported; empty result surfaces as explicit error
  - Reuses existing `get_available_values()` + 7-day SQLite cache — zero new infrastructure

## 2026-04-01

- ISTAT CLI tests completed: `search`, `info`, `values`, `get`, `get --out`, `get --last-n`, `get` multiple values, `plot`, `plot` with options — all ok
- Reference dataset: `168_2` with `DATA_TYPE=13`, `MEASURE=4`, `REF_AREA=IT`, `COICOP_REV_ISTAT=00`
- Fix bug: `plot` ignored `--start-period`/`--end-period` (treated as dimensions); added as typer options and passed to `get_data()` — aborruso/opensdmx#1
- Updated `docs/cli-test-examples.md` with correct ISTAT example

## 2026-03-31 (2)

- `portals.json`: added `data_format_param` for Eurostat (`SDMX-CSV`); fixes `get`/`plot` commands that returned 406
- `base.py`: `sdmx_request_csv` now uses `format=` query param when provider has `data_format_param`, else `Accept: text/csv` (ISTAT and others)
- `embed.py`: query expansion via Gemini before embedding (`_expand_query`); translates to English + adds synonyms; default on, `--no-expand` to skip, `--verbose` to show expanded query
- Tried replacing Ollama with `fastembed` (`nomic-ai/nomic-embed-text-v1.5-Q`) — reverted: quality inferior especially for Italian queries; `nomic-embed-text-v2-moe` via Ollama remains the embedding backend
- Added `docs/cli-test-examples.md` with all non-AI CLI examples (Eurostat tested, ISTAT pending)

## 2026-03-31

- New `portals.json` bundled with 8 SDMX portals (eurostat, istat, ecb, oecd, insee, bundesbank, worldbank, abs)
- `base.py`: `PROVIDERS` loaded from JSON with `_DEFAULTS` merge; custom providers get defaults too
- `discovery.py`: `dataflow_params`, `constraint_endpoint`, `datastructure_agency` read from provider config
- Fixed XML namespace normalization (`s`/`c`/`m` → `structure`/`common`/`message`) for cross-portal compat
- Fixed `_check_api_reachable`: catches all exceptions, uses GET not HEAD
- Added spinner to CLI commands (`search`, `info`, `values`, `get`)
- `guide`/`search --semantic`: prompts to build embeddings if cache missing
- `embed.py`: guards against empty catalog and corrupted cache
- Renamed package `istatpy` → `opensdmx`; CLI entry point `istatpy` → `opensdmx`
- New provider system: `set_provider("eurostat"|"istat"|url)`, `get_provider()`; default is Eurostat (`ESTAT`)
- Cache namespaced per provider: `~/.cache/opensdmx/{AGENCY_ID}/dataflows.parquet` + `cache.db`
- Rate limit per-provider (Eurostat: 0.5s, ISTAT: 13s); temp file `/tmp/opensdmx_{agency_id}_rate_limit.log`
- `istat_dataset` → `load_dataset`; `istat_get` → `fetch`; `istat_timeout` → `set_timeout`
- Removed `df_description_it` column; description language driven by provider config
- All CLI commands accept `--provider` / `-p` flag
- `ai.py` system prompt is now provider-aware (references `agency_id`, language-agnostic rules)
- `embed.py` updated: cache path dynamic per provider, removed `df_description_it`
- `README.md` rewritten for `opensdmx` with Eurostat as default

## 2026-02-28

- `cli.py guide`: final result also shows `istatpy get` command alongside URL and curl
- `db_cache.py`: added `description` column to `invalid_datasets` (auto migration); `save_invalid_dataset` now accepts description; added `list_invalid_datasets()` and `delete_invalid_dataset()`
- `cli.py`: new `blacklist` command — lists blacklisted datasets and allows removal via interactive checkbox
- `docs/database.md`: new file with schema of all cache files (parquet + SQLite) and Mermaid ER diagram
- `README.md`: link to `docs/database.md` in Caching section; added `blacklist` to commands table

## 2026-02-28 (availableconstraint cache + combo validation)

- `db_cache.py`: new `available_constraints` table; get/save cached for 7 days
- `discovery.py`: `get_available_values()` now uses SQLite cache; simplified endpoint (`references=none`)
- `ai.py`: `lookup_actual_values` uses `get_available_values()` (cached) instead of raw sample; removed initial sample fetch
- `cli.py guide` step 6b: code validation against `availableconstraint` (more reliable than codelist)
- `cli.py guide` step 6c: filter combination validation with real sample (`lastNObservations=1` + active filters); warn if 404

## 2026-02-28 (real data codes in guide)

- `ai.py`: added `lookup_actual_values(dimension_id)` tool — samples real data with `lastNObservations=1` at session start; returns actual values (e.g. `UNEMP`, `1`, `2`) instead of theoretical codelist codes (e.g. `UNEM_TI`, `M`, `F`)
- `lookup_dimension_values` kept for text descriptions; system prompt specifies filters use only `lookup_actual_values`
- Sample downloaded once at session start (single extra API call)

## 2026-02-28 (invalid dataset filtering)

- `db_cache.py`: added `invalid_datasets` table; `save_invalid_dataset()`, `get_invalid_dataset_ids()`
- `discovery.py`: `all_available()` automatically filters invalid datasets
- `cli.py` `guide`: API availability check moved BEFORE AI session (after dataset confirmation); if unavailable → mark as invalid, return to selection without wasting AI time

## 2026-02-28 (period filters + obs limits)

- `get_data`/`istat_get`: added `first_n_observations` (`firstNObservations` SDMX) alongside `last_n_observations`
- CLI `get`: added `--start-period`, `--end-period`, `--last-n`, `--first-n` options
- `ai.py`: system prompt hardened — AI MUST call `lookup_dimension_values` before proposing any code, no invented codes

## 2026-02-28 (bug fixes)

- Fix `make_url_key`: "." values now mapped to empty string → correct SDMX URL (`A....` instead of `A........`)
- `guide_session`: chatlas warnings suppressed; `_chat()` helper handles `get_last_turn()` None-safe
- `FilterItem.codes: list[str]`: multi-value support for dimensions (e.g. SEX = M+F)
- Filter validation in `guide`: checks each code individually against actual values
- `lookup_dimension_values` tool: AI verifies codes autonomously without delegating to user
- Cache moved to `~/.cache/istatpy/`; `df_description_it` added to catalog

## 2026-02-28 (it description)

- Added `df_description_it` to dataflows (Italian name from SDMX `Name xml:lang="it"`)
- `embed.py`: embedding text = `"en / it"` for better semantic search in Italian
- `semantic_search()`: also returns `df_description_it`
- `guide`: shows Italian description in dataset selection list

## 2026-02-28 (cache dir)

- Cache moved from `/tmp/` to `~/.cache/istatpy/` (persistent across reboots)
- `base.py`: added `CACHE_DIR = Path.home() / ".cache" / "istatpy"` with `mkdir`
- `db_cache.py`, `discovery.py`, `embed.py`: use `CACHE_DIR` instead of `tempfile.gettempdir()`

## 2026-02-28 (guide)

- Replaced `wizard` and `ask` with `guide`: semantic search + multi-turn AI conversation for filters
- `ai.py`: removed `find_dataset`/`find_filters`; added `guide_session(ds, objective)` — chatlas multi-turn with Gemini, extracts filters with user confirmation
- `cli.py`: removed `wizard` and `ask` commands; added `guide [query]` — paginated dataset selection + interactive AI session + final SDMX URL
- `docs/PRD.md`: created PRD for guide flow

## 2026-02-28

- `istatpy ask [objective]`: full AI flow — finds dataset via semantic search, then filters; step-by-step confirmation (dataset → filters → download); `--out` option
- `ai.py`: `find_dataset()` (uses `search_datasets` tool) + `find_filters()` (uses `get_values_for_dimension` tool); two separate calls for progressive confirmation
- deps: added `chatlas[google]>=0.7` to `pyproject.toml`

## 2026-02-27

- `embed.py`: vector embeddings via ollama `nomic-embed-text-v2-moe` (768 dim), cached in `/tmp/istatpy_embeddings.parquet` (~11MB)
- `istatpy embed`: builds embeddings cache; `istatpy search --semantic`: cross-language semantic search
- `db_cache.py`: SQLite cache `/tmp/istatpy_cache.db` (TTL 7d) for dimensions and codelist values — cold 52s → cached 0.0s
- Fix: use `ALL` instead of `IT1` as agency on `datastructure` and `codelist` endpoints (fixes 404 on cross-agency datasets)
- `istatpy wizard`: interactive dataset discovery, paginated results, fuzzy value filtering (InquirerPy), auto-select DATA_DOMAIN, SDMX URL output

- Rate limit: countdown timer (updates every 0.2s), interval raised to 13s

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
