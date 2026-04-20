# LOG

## 2026-04-20

- feat: `tree --category <cat_id>` — browse subtree rooted at a category (requires `--scheme`)
- fix: `tree --scheme` now shows hint when a category ID is passed instead of a scheme ID (suggests correct `--scheme --category`)
- fix: `load_dataset` now case-insensitive for `df_id` and `df_structure_id` — `opensdmx info cpi` and `opensdmx info CPI` both work
- docs: add `### Thematic tree` section in README with real Eurostat 3-step tutorial (schemes → tree browse → category filter); shows cat_id retrieval via CSV output and `search --category` delta (502 → 1 result)

## 2026-04-19

- fix: use SDMX 2.1 structure Accept header in `sdmx_request_xml`; fixes OECD returning JSON on `/dataflow` (closes #15); unblocks `all_available`/`search` on OECD and fills `df_description` in `siblings` output
- feat: add thematic category tree (SDMX categoryscheme + categorisation) via new `opensdmx tree` command (ASCII in table mode, flat JSON/CSV otherwise); `--scheme` renders tree, `--depth` limits nesting
- feat: add `--category` filter to `opensdmx search` (leaf id or dotted path); matches dataflow through categorisation
- feat: add `opensdmx siblings <df_id>` — shows dataflow siblings in each category (one group per membership); surfaces related variants that text search misses
- feat: new `src/opensdmx/categories.py` with two-parquet cache (`categories.parquet`, `categorisation.parquet`), lazy fetch on first `tree` call, 7-day TTL via `CATEGORIES_CACHE_TTL`, stale-df warning to stderr
- feat: add `categories_supported` flag to `portals.json` (true: eurostat, istat, ecb, oecd, insee, abs, bis; false: comext, bundesbank, worldbank, imf) + new column in `opensdmx providers`
- chore: add read-only MCP tool allowlist to `.claude/settings.local.json` (mempalace search/get/list, playwright network/snapshot/screenshot, chrome-devtools network tools)

## 2026-04-15

- chore: bump version to v0.3.34
- perf: memoize `_resolve_cache_base()` via `functools.lru_cache`, keyed on `OPENSDMX_CACHE_DIR`, so the write-probe runs at most once per process instead of on every HTTP request
- test: isolate `TestRateLimitLock` via `monkeypatch` + `tmp_path` (`OPENSDMX_CACHE_DIR` override) so it no longer writes under the real user cache dir
- docs: fix `_rate_limit_check()` docstring to reference the per-user rate-limit dir instead of `/tmp`
- chore: bump version to v0.3.33
- fix: move rate-limit lock and timestamp files from the shared system tempdir to the per-user cache base (via `platformdirs`), avoiding cross-user interference on multi-tenant hosts; cross-OS by construction
- fix: derive provider cache/lock key from base URL hash when custom provider has no `agency_id`, so two such providers don't share the same lock and get serialized together
- test: cover cross-process flock — assert `portalocker.Lock` is called with the per-provider lock path
- chore: bump version to v0.3.32
- fix: serialize HTTP calls per provider with `portalocker` flock, so the rate limit holds across concurrent processes (parallel timestamp-file readers could previously defeat it)
- chore: bump ISTAT rate_limit 13s → 15s for a safer margin
- chore: bump version to v0.3.31
- fix(istat): use `/all/all?mode=available` for constraints endpoint, returning only codes actually present in each dataflow (removes ambiguity between multiple "total" codes like `T` vs `9` for SEX)
- feat(cli): warn before first (slow) ISTAT constraints call; warning suppressed on cache hits
- fix: rate limiter records timestamp at HTTP call start (not end), so the 13s interval is measured from request sent, not response received

## 2026-04-11

- feat: add Eurostat Comext as named provider (`--provider comext`) for DS-prefixed datasets
- fix: cache and rate-limit keys now use provider alias instead of agency_id, preventing collision between eurostat and comext (both ESTAT)

## 2026-04-10

- chore: bump version to v0.3.27
- fix: replace warnings.warn with logging.warning in discovery.py and base.py
- chore: bump version to v0.3.26
- feat(search): add spinner during semantic search
- feat(plot): add xkcd theme support via --theme xkcd

## 2026-04-09

- chore: bump version to v0.3.25
- feat: expose `__version__` via `importlib.metadata`
- fix: replace `assert` with proper error handling in guide.py
- chore: add PyPI classifiers and keywords to pyproject.toml

## 2026-04-07 (17)

- chore: bump version to v0.3.24
- docs(skill): update sdmx-explorer with providers capability columns

## 2026-04-07 (16)

- chore: bump version to v0.3.23
- feat(providers): fill all capability columns from probe run; fix probe_providers.sh (IMF filters, OECD dataset)

## 2026-04-07 (15)

- chore: bump version to v0.3.22
- feat(scripts): add probe_providers.sh — tests constraints and last_n for all built-in providers, saves report to tmp/

## 2026-04-07 (14)

- feat(providers): add constraints and last_n capability columns; mark known support in portals.json

## 2026-04-07 (13)

- chore: bump version to v0.3.21

## 2026-04-07 (12)

- fix(discovery): resolve codelist from concept scheme when DSD lacks LocalRepresentation (fixes `values` for IMF provider)

## 2026-04-07 (11)

- chore: bump version to v0.3.20

## 2026-04-07 (10)

- feat(cli): add --grep flag to `values` and `constraints` commands — filters codelist/constraint results by regex (case-insensitive, matches id or name)

## 2026-04-07 (9)

- docs(validation): update validation-statgpt.md — add Round 2 (IMF WEO, 3 agents, 42/42 match); now covers both OECD and WEO convergence tests

## 2026-04-07 (8)

- chore: bump version to v0.3.19

## 2026-04-07 (7)

- feat(portals): add IMF as built-in provider (`--provider imf`) — base URL `https://api.imf.org/external/sdmx/2.1`, agency `IMF.RES`, `catalog_agency=all`; WEO dataflow confirmed working (3 dimensions: COUNTRY, INDICATOR, FREQUENCY)
- docs(readme): add framing paragraph on AI+statistics accuracy problem, citing IMF StatGPT paper (2026)
- docs(validation): add `docs/validation-statgpt.md` — public validation doc inspired by StatGPT paper; 3-agent convergence test (42/42 identical values), cross-source accuracy, repeatability with provenance metadata; linked from README
- docs(validation): add `tmp/statgpt-tests/REPORT.md` — full technical report with all 8 tests

## 2026-04-07 (6)

- fix(worldbank): handle missing observation values (`[,0]` → `[null,0]`) in SDMX-JSON responses — World Bank API returns invalid JSON for null observations

## 2026-04-07 (5)

- feat(plot): add `--theme` option — supports `minimal` (default), `bw`, `classic`, `538`, `tufte`, `void`, `dark`, `light`, `gray`
- docs(skill): add `--theme` to visualization.md options table
- chore: bump version to v0.3.17

## 2026-04-07 (4)

- feat(plot): add `--geom heatmap` using `geom_tile` — `--x` = columns, `--color` = rows, `--y` = fill intensity
- docs(skill): add heatmap to visualization.md geom table
- chore: bump version to v0.3.16

## 2026-04-07 (3)

- feat(plot): add `--x-all` flag to force all x-axis tick labels on discrete axes (e.g. quarterly labels) — uses `scale_x_discrete(limits=...)`, works with `--facet` and `--color`
- docs(skill): update visualization.md with `--x-all`, `--rotate-x`, `--colors` options and "missing x-axis labels" fix
- chore: bump version to v0.3.15

## 2026-04-07 (2)

- fix(cache): switch SQLite journal mode from WAL to DELETE — WAL creates `-wal`/`-shm` files that cause "database is locked" errors when accessing the cache across WSL/Windows filesystem boundaries (closes #7)
- chore: bump version to v0.3.14

## 2026-04-07

- fix(cache): SQLite connections were never closed — replaced raw `sqlite3.connect` context manager with proper open/commit/close pattern, added WAL mode and timeout to prevent lock contention
- chore: bump version to v0.3.13

## 2026-04-06 (5)

- fix(plot): `--geom barh` now renders correctly — fixed axis swap (`--x` = value, `--y` = category), prevented numeric value column from being cast to string, and corrected axis labels after `coord_flip`
- docs(skill): update visualization.md — document `barh` axis convention (`--x` = value, `--y` = category)

## 2026-04-06 (4)

- docs(skill): human-readable labels required in charts (Rule 5 in visualization.md)
- docs(skill): generalize Rule 3 — never mix individual units with aggregates
- docs(skill): add filter coherence principle to SKILL.md (individual vs. aggregate codes)

## 2026-04-06 (3)

- chore: bump version to v0.3.10

## 2026-04-06 (2)

- feat(cache): flexible cache directory — `OPENSDMX_CACHE_DIR` env var, `platformdirs` (XDG on Linux, OS-native on macOS/Windows), `/tmp/opensdmx-{user}` fallback if nothing is writable (closes #6)

## 2026-04-06

- fix(cache): all SQLite `save_*` calls wrapped in isolated try/except — cache failures no longer discard successfully fetched API data
- fix(values): `opensdmx values` no longer fails with "readonly database" when cache write fails; returns data anyway
- fix(constraints): `opensdmx constraints` warning message now distinguishes cache errors from API errors

## 2026-04-05

- feat(plot): add `--rotate-x N` flag to rotate x-axis labels by N degrees
- feat(plot): add `--colors 'hex1,hex2,...'` flag for custom categorical color palettes
- fix(plot): bar/barh charts now display integer years (e.g. 2022) correctly instead of as dates (2022-01-01)
- docs(skill): update sdmx-explorer skill — fix facet note in SKILL.md, add x-axis label overlap fix in visualization.md
- docs(skill): add `references/color-guide.md` with Okabe-Ito and Set2 palettes, colorblind rules, and plotnine snippets
- docs(skill): add `references/cli-templates.md` with ready-to-use parameter combinations for common chart scenarios

## 2026-04-05

- feat(info): show Eurostat dataflow page URL in `opensdmx info` output (table and JSON mode)
- feat(portals): add `dataflow_page_url` field to Eurostat entry in portals.json

## 2026-04-05

- feat(plot): `--facet` / `--ncol` options for `facet_wrap` (small multiples)
- feat(plot): `--time` alias for `--x` (more intuitive column name override)
- fix(plot): `schema_overrides` now uses the actual `--x` column name instead of hardcoded `TIME_PERIOD`
- fix(plot): error message now lists only the missing column(s) instead of both
- docs(skill): update visualization.md with facet options and small-multiples guidance

## 2026-04-05

- feat: machine-to-machine output — global `--output table|json|csv` flag on all metadata commands (`search`, `info`, `values`, `constraints`, `providers`); stdout = pure structured data, stderr = errors/warnings; spinners suppressed in non-table mode
- feat: relevance ranking for standard search — multi-token AND filter on `df_description` + `df_id`, synthetic score (id match ×3, start-of-desc ×2, occurrence count ×1), results sorted by score
- feat: search default page size 20→50
- feat: search table now shows `score` column

## 2026-04-04 (14)

- docs: expand semantic search section in README with comparison table, 3 real examples, and sample output
- feat: add --all and --page to search command (paginate cache results)
- chore: bump version to v0.3.2
- feat: expose `run_query()`, `semantic_search()`, `build_embeddings()` in public Python API
- docs: add `sdmx-explorer` skill installation guide (`docs/skill/README.md`) with screenshots
- docs: add missing functions to Python API table in README
- docs: improve docstrings for `semantic_search` and `build_embeddings`

## 2026-04-04 (13)

- test: add test_cli.py with 12 tests for _parse_extra_filters, _apply_provider, CLI commands
- fix: World Bank provider now works for data requests (closes #5)
  - add `data_accept` field in portals.json → sends correct Accept header for SDMX-JSON
  - add `data_path_suffix: "/"` → trailing slash required by WB API to avoid 307 redirect
  - add `follow_redirects=True` to httpx.Client (global fix)
  - add `_parse_sdmx_json()` parser for SDMX-JSON 1.0 responses
  - handle World Bank non-standard key order (dimensions sorted by keyPosition descending)

## 2026-04-04 (12)

- chore: bump version to v0.3.0
- feat: add `--query-file` option to `get` command — saves query as YAML for later reuse
- feat: add `run` command — executes a query from a YAML file, output to stdout or `--out`
- feat: YAML captures provider alias, provider_url, agency_id, filters with labels from cache
- feat: `run` resolves provider via alias → URL+agency_id fallback chain
- feat: add `build_query_dict()` helper in `utils.py`
- dep: add `pyyaml` dependency
- docs: update README with query file workflow and `run` command
- docs: update sdmx-explorer skill to suggest saving queries as YAML templates

## 2026-04-04 (11)

- chore: bump version to v0.2.9
- feat: add BIS (Bank for International Settlements) as built-in provider

## 2026-04-04 (10)

- chore: bump version to v0.2.8
- feat: add `providers` command listing curated SDMX providers with alias, name, description, agency
- feat: add `description` field to all 8 providers in portals.json

## 2026-04-04 (9)

- chore: bump version to v0.2.7
- refactor: extract guide() logic to guide.py; cli.py -358 lines
- feat: add [guide] optional extras (chatlas, questionary); remove dead deps (duckdb, inquirerpy)
- test: add 11 mocked HTTP tests (sdmx_request_csv, all_available, get_data)
- fix: replace silent except Exception with specific exception types in discovery, embed, cli, guide

## 2026-04-04 (8)

- chore: bump version to v0.2.6

## 2026-04-04 (7)

- fix(bundesbank): add datastructure_agency=BBK to portals.json (ALL not accepted by Bundesbank API)
- fix(utils): handle default xmlns (prefix=None) in xml_parse() for known canonical namespaces — fixes World Bank WDI discovery

## 2026-04-04 (6)

- fix(utils): xml_parse() now collects namespaces from all elements (not just root) — fixes World Bank support where `structure` ns is declared on a child element — closes #4

## 2026-04-04 (5)

- fix(bundesbank): add `metadata_prefix: "metadata"` to portals.json; add `_struct_path()` helper in discovery.py to prepend prefix to dataflow/datastructure/codelist paths — fixes #3

## 2026-04-04 (4)

- Test: full workflow tested for `oecd`, `bundesbank`, `worldbank` providers
- OECD: all 5 steps work (search, info, values, constraints, get)
- OECD: official rate limit is 60 data downloads/hour — applies to `get` only, not structure/metadata calls (search, info, values, constraints); current `rate_limit: 0.5` in portals.json is fine
- ECB, Eurostat: no rate limit officially documented
- Bundesbank: all steps fail — `/rest/dataflow/BBK` returns 404 ("Unknown path"); API routing broken
- World Bank: all steps fail — `xml_parse()` misses namespaces declared on child elements (not root); `WDI` dataflow exists but never discovered

## 2026-04-04 (3)

- Feat: `get` warns when dataset has >5,000 series and no filters/limits are set
- Feat: `get --yes` / `-y` flag to bypass large-dataset confirmation
- Probe request (`lastNObservations=1`) used to count series before full download

## 2026-04-04 (2) — v0.2.5

- Fix: Polars dtype crash on mixed TIME_PERIOD (e.g. ECB ICP) — force Utf8 in CSV read
- Fix: `--out` with unsupported extension (e.g. `.xlsx`) now raises clear error instead of silent wrong write
- Fix: `--geom scatter` accepted as alias for `point` in `plot`
- Fix: invalid `--provider` name shows clean error with list of valid providers
- Fix: dimension ID in `values` and `get` is now case-insensitive (e.g. `FREQ` = `freq`)
- Fix: `UserWarning` for unknown dimension replaced with rich console warning
- Fix: `blacklist --remove` reports "Not found" when entry doesn't exist (was always "Removed")
- Fix: `search --n` now works in keyword mode too (was semantic-only)
- Fix: default plot filename now uses dataset ID/stem instead of `chart.png`
- Fix: local CSV plot: TIME_PERIOD parsed as date so `scale_x_date` applies correctly
- Feat: `OPENSDMX_PROVIDER` and `OPENSDMX_AGENCY` env vars for session-wide provider config
- Feat: custom SDMX URL accepted as `--provider` value (`agency_id` now optional)
- Feat: `search` shows total match count in table title (e.g. "10 of 8037")
- Feat: `search --n` default raised from 10 to 20
- Tests: 57 → 64 tests (new: `test_base.py`, extended `test_db_cache`, `test_discovery`)
- Docs: README updated — providers, env vars, output formats, examples

## 2026-04-04

- ECB deep test: P1 URL bug (get without filters) NOT reproduced — resolved or was dataset-specific
- ECB deep test: P1 duplicates in `values` NOT reproduced — resolved
- New bug found: `get ICP --provider ecb` crashes with Polars dtype inference error on YYYY-MM TIME_PERIOD
- Results documented in `tmp/ecb-test-results.md`, evaluation updated in `tmp/cli-evaluation.md`

## 2026-04-03 (4)

- Fix: CI workflow — add ruff to dev dependencies, fix f-string and F401 lint errors
- Fix: configure ruff to ignore E402 (intentional import patterns)
- Feat: `plot` command accepts local files (.csv, .tsv, .parquet) as input

## 2026-04-03 (3)

- Translate all remaining Italian UI strings in `ai.py` and `cli.py` to English
- Remove Gemini-based query expansion from semantic search — now Ollama-only
- Remove `--no-expand` and `--verbose` CLI flags from `search --semantic`
- Add synonym tip to `search` help and README
- Document `GOOGLE_API_KEY` requirement in `.env.example` (for `guide` only)
- Add 22 tests: `test_discovery.py` (set/reset_filters), `test_db_cache.py` (all SQLite cache ops)

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
