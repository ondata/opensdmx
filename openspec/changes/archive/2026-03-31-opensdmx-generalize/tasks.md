## 1. Package Rename

- [x] 1.1 Update `pyproject.toml`: name `opensdmx`, scripts entry point `opensdmx`
- [x] 1.2 Rename source directory `src/istatpy/` → `src/opensdmx/`
- [x] 1.3 Update all internal imports from `istatpy` to `opensdmx`

## 2. Provider System (base.py)

- [x] 2.1 Replace `_config` with `PROVIDERS` dict containing `eurostat` and `istat` presets
- [x] 2.2 Add `_active_provider` global pointer, default `"eurostat"`
- [x] 2.3 Implement `set_provider(name_or_url, agency_id=None, rate_limit=0.5, language="en")`
- [x] 2.4 Implement `get_provider()` returning active provider dict
- [x] 2.5 Update `get_base_url()` and `get_agency_id()` to use active provider
- [x] 2.6 Make rate limit file path per-provider: `/tmp/opensdmx_{agency_id}_rate_limit.log`
- [x] 2.7 Make rate limit interval use `provider["rate_limit"]` instead of hardcoded 13s

## 3. Cache Namespacing (db_cache.py + discovery.py)

- [x] 3.1 Replace `CACHE_DIR` constant with `get_cache_dir()` function returning `~/.cache/opensdmx/{agency_id}/`
- [x] 3.2 Update `_DATAFLOW_CACHE` in `discovery.py` to use `get_cache_dir()`
- [x] 3.3 Update SQLite db path in `db_cache.py` to use `get_cache_dir()`
- [x] 3.4 Remove `df_description_it` column from `all_available()` output
- [x] 3.5 Update `all_available()` to use provider's `language` for `df_description`

## 4. Public API Rename

- [x] 4.1 Rename `istat_dataset` → `load_dataset` in `discovery.py`
- [x] 4.2 Rename `istat_get` → `fetch` in `retrieval.py`
- [x] 4.3 Rename `istat_timeout` → `set_timeout` in `base.py`
- [x] 4.4 Update `__init__.py`: new export names, add `set_provider`, `get_provider`

## 5. CLI Update (cli.py)

- [x] 5.1 Add `--provider` option to `list` command
- [x] 5.2 Add `--provider` option to `search` command
- [x] 5.3 Add `--provider` option to `get` command
- [x] 5.4 Add `--provider` option to `guide` command
- [x] 5.5 Add `--provider` option to `blacklist` command
- [x] 5.6 Each command calls `set_provider(provider)` before executing logic
- [x] 5.7 Update all `istat_*` references in CLI to new names

## 6. AI Guide Update (ai.py)

- [x] 6.1 Update system prompt to reference active provider name (not hardcoded "ISTAT")
- [x] 6.2 Update any hardcoded ISTAT-specific references in prompts

## 7. Documentation

- [x] 7.1 Rewrite `README.md` for `opensdmx` with Eurostat as default example
- [x] 7.2 Update `LOG.md` with this change
- [x] 7.3 Update docstrings: remove "ISTAT" references, use generic language
