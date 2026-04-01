## ADDED Requirements

### Requirement: Cache directory namespaced per provider
Il sistema SHALL mantenere directory di cache separate per ogni provider, basate sull'`agency_id`. Il path SHALL essere `~/.cache/opensdmx/{agency_id}/`.

#### Scenario: Cache Eurostat separata da ISTAT
- **WHEN** l'utente usa prima eurostat poi istat
- **THEN** i file parquet e SQLite di ESTAT sono in `~/.cache/opensdmx/ESTAT/` e quelli di IT1 in `~/.cache/opensdmx/IT1/`

#### Scenario: Cache path dinamica
- **WHEN** `set_provider("istat")` viene chiamato
- **THEN** `get_cache_dir()` restituisce `~/.cache/opensdmx/IT1/`

### Requirement: Parquet dataflow namespaced
Il file parquet dei dataflow SHALL essere `~/.cache/opensdmx/{agency_id}/dataflows.parquet` (non più `istatpy_dataflows.parquet`).

#### Scenario: File parquet per provider
- **WHEN** `all_available()` viene chiamato con provider eurostat
- **THEN** il cache file è `~/.cache/opensdmx/ESTAT/dataflows.parquet`

### Requirement: SQLite cache namespaced
Il database SQLite SHALL essere `~/.cache/opensdmx/{agency_id}/cache.db` (non più `istatpy_cache.db`).

#### Scenario: SQLite separato per provider
- **WHEN** il provider attivo è `istat`
- **THEN** `db_cache` usa `~/.cache/opensdmx/IT1/cache.db`

### Requirement: Colonna df_description_it rimossa
La colonna `df_description_it` SHALL essere rimossa dal DataFrame restituito da `all_available()`. La descrizione nella lingua del provider è in `df_description`.

#### Scenario: Schema DataFrame senza colonna italiana
- **WHEN** `all_available()` viene chiamato con qualsiasi provider
- **THEN** il DataFrame ha colonne `df_id`, `version`, `df_description`, `df_structure_id` (senza `df_description_it`)
