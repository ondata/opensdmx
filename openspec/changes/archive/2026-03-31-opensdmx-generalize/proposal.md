## Why

`istatpy` è hardcoded sull'API ISTAT. Generalizzarlo a qualsiasi endpoint SDMX 2.1 (con Eurostat come default) lo rende utile per chiunque lavori con statistiche europee e internazionali, non solo italiane.

## What Changes

- **BREAKING** Rename pacchetto: `istatpy` → `opensdmx`
- **BREAKING** Rename CLI entry point: `istatpy` → `opensdmx`
- **BREAKING** Rename funzioni pubbliche: `istat_dataset` → `load_dataset`, `istat_get` → `fetch`, `istat_timeout` → `set_timeout`
- Nuovo sistema provider: preset named (`eurostat`, `istat`) + custom URL
- Default provider cambia da ISTAT a Eurostat (`ESTAT`)
- Cache namespaced per provider: `~/.cache/opensdmx/{AGENCY_ID}/`
- Rate limiting configurabile per provider (ISTAT: 13s, Eurostat: 0.5s)
- CLI riceve flag `--provider` su tutti i comandi
- `ai.py` system prompt diventa provider-aware
- Lingua descrizioni configurabile per provider (ISTAT: `it`, Eurostat: `en`)

## Capabilities

### New Capabilities

- `provider-system`: sistema di provider SDMX con preset named, custom URL, rate limit e lingua configurabili per provider; funzione `set_provider()` e `get_provider()`
- `provider-cache`: cache (parquet + SQLite) namespaced per provider agency_id

### Modified Capabilities

*(nessuna spec esistente)*

## Impact

- `base.py`: riscrittura `_config` → `PROVIDERS` dict + active provider
- `discovery.py`: usa provider attivo per base_url e agency_id; cache path diventa per-provider
- `retrieval.py`: rename `istat_get` → `fetch`
- `db_cache.py`: `CACHE_DIR` diventa dinamico per provider
- `cli.py`: aggiunta `--provider` a tutti i comandi; entry point `opensdmx`
- `__init__.py`: aggiornamento exports
- `ai.py`: system prompt provider-aware
- `pyproject.toml`: rename pacchetto e script entry point
- Repo GitHub: rinominare da `istatPy` a `opensdmx`
