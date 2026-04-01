# LOG

## 2026-04-01 (2)

- New `opensdmx constraints <dataflow_id> [dimension]` CLI command
  - No dimension: summary table (`dimension_id`, `n_values`, `sample` first 3 codes)
  - With dimension: full `id`/`name` table of codes actually present, labels from codelist
  - `--provider` flag supported; empty result surfaces as explicit error
  - Reuses existing `get_available_values()` + 7-day SQLite cache — zero new infrastructure

## 2026-04-01

- Test CLI ISTAT completati: `search`, `info`, `values`, `get`, `get --out`, `get --last-n`, `get` valori multipli, `plot`, `plot` con opzioni — tutti ok
- Dataset di riferimento: `168_2` con `DATA_TYPE=13`, `MEASURE=4`, `REF_AREA=IT`, `COICOP_REV_ISTAT=00`
- Fix bug: `plot` ignorava `--start-period`/`--end-period` (trattati come dimensioni); aggiunti come opzioni typer e passati a `get_data()` — aborruso/opensdmx#1
- Aggiornato `docs/cli-test-examples.md` con esempio ISTAT corretto

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

- `cli.py guide`: risultato finale mostra anche comando `istatpy get` oltre all'URL e al curl
- `db_cache.py`: aggiunta colonna `description` a `invalid_datasets` (migration automatica); `save_invalid_dataset` ora accetta description; aggiunte `list_invalid_datasets()` e `delete_invalid_dataset()`
- `cli.py`: nuovo comando `blacklist` — lista i dataset in lista nera e permette rimozione con checkbox interattivo
- `docs/database.md`: nuovo file con schema di tutti i file di cache (parquet + SQLite) e diagramma ER Mermaid
- `README.md`: link a `docs/database.md` nella sezione Caching; aggiunto `blacklist` nella tabella comandi

## 2026-02-28 (availableconstraint cache + combo validation)

- `db_cache.py`: nuova tabella `available_constraints`; get/save cached per 7gg
- `discovery.py`: `get_available_values()` ora usa cache SQLite; endpoint semplificato (`references=none`)
- `ai.py`: `lookup_actual_values` usa `get_available_values()` (cached) invece del sample raw; rimozione fetch sample iniziale
- `cli.py guide` step 6b: validazione codici su `availableconstraint` (più affidabile della codelist)
- `cli.py guide` step 6c: validazione combinazione filtri con sample reale (`lastNObservations=1` + filtri attivi); avviso se 404

## 2026-02-28 (real data codes in guide)

- `ai.py`: aggiunto tool `lookup_actual_values(dimension_id)` — campiona dati reali con `lastNObservations=1` all'avvio sessione; restituisce valori effettivi (es. `UNEMP`, `1`, `2`) invece di codici codelist teorici (es. `UNEM_TI`, `M`, `F`)
- `lookup_dimension_values` resta per le descrizioni testuali; system prompt specifica che i filtri usano solo `lookup_actual_values`
- Il campione viene scaricato una volta sola all'inizio della sessione (un'unica chiamata API extra)

## 2026-02-28 (invalid dataset filtering)

- `db_cache.py`: aggiunta tabella `invalid_datasets`; `save_invalid_dataset()`, `get_invalid_dataset_ids()`
- `discovery.py`: `all_available()` filtra automaticamente i dataset invalidi
- `cli.py` `guide`: check disponibilità API spostato PRIMA della sessione AI (dopo conferma dataset); se non disponibile → segna come invalido, torna alla selezione senza sprecare tempo AI

## 2026-02-28 (period filters + obs limits)

- `get_data`/`istat_get`: aggiunto `first_n_observations` (`firstNObservations` SDMX) affiancato a `last_n_observations`
- CLI `get`: aggiunte opzioni `--start-period`, `--end-period`, `--last-n`, `--first-n`
- `ai.py`: system prompt rafforzato — l'AI DEVE chiamare `lookup_dimension_values` prima di proporre qualsiasi codice, non inventare codici

## 2026-02-28 (bug fixes)

- Fix `make_url_key`: valori "." ora mappati a stringa vuota → URL SDMX corretto (`A....` invece di `A........`)
- `guide_session`: warning chatlas soppressi; `_chat()` helper gestisce `get_last_turn()` None-safe
- `FilterItem.codes: list[str]`: supporto multi-valore per dimensioni (es. SEX = M+F)
- Validazione filtri in `guide`: controlla ogni codice singolarmente contro i valori reali
- `lookup_dimension_values` tool: l'AI verifica autonomamente i codici senza delegare all'utente
- Cache spostata in `~/.cache/istatpy/`; `df_description_it` aggiunta al catalogo

## 2026-02-28 (it description)

- Aggiunta `df_description_it` ai dataflow (nome italiano da SDMX `Name xml:lang="it"`)
- `embed.py`: testo embedding = `"en / it"` per migliore ricerca semantica in italiano
- `semantic_search()`: restituisce anche `df_description_it`
- `guide`: mostra descrizione italiana nella lista selezione dataset

## 2026-02-28 (cache dir)

- Cache spostata da `/tmp/` a `~/.cache/istatpy/` (persistente tra reboot)
- `base.py`: aggiunta `CACHE_DIR = Path.home() / ".cache" / "istatpy"` con `mkdir`
- `db_cache.py`, `discovery.py`, `embed.py`: usano `CACHE_DIR` invece di `tempfile.gettempdir()`

## 2026-02-28 (guide)

- Sostituiti `wizard` e `ask` con `guide`: ricerca semantica + conversazione AI multi-turn per filtri
- `ai.py`: rimossi `find_dataset`/`find_filters`; aggiunto `guide_session(ds, objective)` — chatlas multi-turn con Gemini, estrae filtri a conferma utente
- `cli.py`: rimossi comandi `wizard` e `ask`; aggiunto `guide [query]` — selezione paginata dataset + sessione AI interattiva + URL SDMX finale
- `docs/PRD.md`: creato PRD del flusso guide

## 2026-02-28

- `istatpy ask [objective]`: full AI flow — trova dataset via semantic search, poi filtri; conferma step-by-step (dataset → filtri → download); `--out` option
- `ai.py`: `find_dataset()` (usa `search_datasets` tool) + `find_filters()` (usa `get_values_for_dimension` tool); due chiamate separate per conferma progressiva
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
