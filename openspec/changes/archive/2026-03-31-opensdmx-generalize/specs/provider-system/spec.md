## ADDED Requirements

### Requirement: Built-in provider presets
Il sistema SHALL includere preset built-in per `eurostat` e `istat` con base_url, agency_id, rate_limit e language preconfigurati. Eurostat SHALL essere il provider di default.

#### Scenario: Default provider è eurostat
- **WHEN** il pacchetto viene importato senza chiamare `set_provider()`
- **THEN** tutte le chiamate API usano `https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1` con agency_id `ESTAT`

#### Scenario: Preset istat disponibile
- **WHEN** l'utente chiama `set_provider("istat")`
- **THEN** le chiamate API usano `https://esploradati.istat.it/SDMXWS/rest` con agency_id `IT1` e rate_limit 13s

### Requirement: Provider custom via URL
Il sistema SHALL permettere di configurare un provider custom passando base_url e agency_id a `set_provider()`.

#### Scenario: Provider custom
- **WHEN** l'utente chiama `set_provider(base_url="https://mysdmx.org/rest", agency_id="XYZ")`
- **THEN** le chiamate API usano il base_url e agency_id forniti

### Requirement: Rate limit per provider
Il sistema SHALL applicare rate limiting separato per ogni provider, usando il valore `rate_limit` del provider attivo. Il file temporaneo SHALL essere `{tmp}/opensdmx_{agency_id}_rate_limit.log`.

#### Scenario: Rate limit ISTAT
- **WHEN** il provider attivo è `istat` e l'ultima chiamata è avvenuta da meno di 13 secondi
- **THEN** la chiamata successiva aspetta il tempo rimanente prima di procedere

#### Scenario: Rate limit Eurostat non blocca
- **WHEN** il provider attivo è `eurostat` (rate_limit=0.5s) e l'ultima chiamata è avvenuta da più di 0.5 secondi
- **THEN** la chiamata successiva parte immediatamente

### Requirement: Lingua descrizioni configurabile
Il sistema SHALL usare la lingua configurata nel provider (`language` field) per le descrizioni dei dataflow. Se la lingua non è disponibile, SHALL fare fallback a `en`.

#### Scenario: Lingua italiana per ISTAT
- **WHEN** il provider attivo è `istat` e il dataflow ha un Name con `xml:lang="it"`
- **THEN** `all_available()` restituisce la descrizione in italiano nella colonna `df_description`

#### Scenario: Lingua inglese per Eurostat
- **WHEN** il provider attivo è `eurostat`
- **THEN** `all_available()` restituisce la descrizione in inglese nella colonna `df_description`

### Requirement: CLI flag --provider
La CLI SHALL accettare `--provider` su tutti i comandi (`list`, `search`, `get`, `guide`, `blacklist`). Il valore può essere un nome preset (`eurostat`, `istat`) o un URL custom con `--agency` flag aggiuntivo.

#### Scenario: CLI con provider esplicito
- **WHEN** l'utente esegue `opensdmx list --provider istat`
- **THEN** il comando usa il provider ISTAT per listare i dataflow

#### Scenario: CLI default provider
- **WHEN** l'utente esegue `opensdmx list` senza `--provider`
- **THEN** il comando usa eurostat come provider

### Requirement: Funzioni pubbliche rinominate
Le funzioni pubbliche SHALL usare nomi generici senza prefisso `istat_`:
- `istat_dataset` → `load_dataset`
- `istat_get` → `fetch`
- `istat_timeout` → `set_timeout`

#### Scenario: API pubblica generica
- **WHEN** l'utente importa `opensdmx` e chiama `opensdmx.fetch("une_rt_m")`
- **THEN** il sistema recupera i dati dal provider attivo (default: eurostat)
