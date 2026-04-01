## Context

`istatpy` è una libreria Python che accede ai dati statistici tramite API SDMX 2.1. Tutta la configurazione (base URL, agency ID, rate limit) è hardcoded per ISTAT. Il codice core è già quasi completamente generico: usa path SDMX standard (`dataflow/`, `datastructure/`, `codelist/`, `data/`). Il refactor richiede principalmente di parametrizzare la configurazione e rinominare il pacchetto.

## Goals / Non-Goals

**Goals:**
- Supportare qualsiasi endpoint SDMX 2.1 tramite un sistema di provider configurabili
- Preset built-in per `eurostat` (default) e `istat`
- Cache namespaced per provider
- CLI provider-aware con `--provider` flag
- Zero codice SDMX da riscrivere (path già compatibili)
- Rename pulito: pacchetto, CLI, funzioni pubbliche

**Non-Goals:**
- SDMX 3.0 (fuori scope)
- Supporto async
- Backward compat con API `istat_*`
- Auto-discovery di provider sconosciuti

## Decisions

### D1: Sistema provider come dict globale con active pointer

Il provider attivo è un dict in `base.py` con chiave `_active_provider`. `set_provider(name_or_dict)` cambia il puntatore globale. Alternativa considerata: classe `Provider` con istanze — scartata perché il codice esistente è stateless/funzionale e richiederebbe refactor massiccio.

```python
PROVIDERS = {
    "eurostat": {"base_url": "...", "agency_id": "ESTAT", "rate_limit": 0.5, "language": "en"},
    "istat":    {"base_url": "...", "agency_id": "IT1",   "rate_limit": 13.0, "language": "it"},
}
_active_provider = "eurostat"

def set_provider(name_or_url, agency_id=None, rate_limit=0.5, language="en"):
    ...
```

### D2: Cache path dinamica per provider

`CACHE_DIR` diventa una funzione `get_cache_dir()` che restituisce `~/.cache/opensdmx/{agency_id}/`. Ogni provider ha il suo parquet e SQLite separati. Alternativa: cache condivisa con colonna provider — scartata per complessità e rischio di collisioni su ID dataflow identici tra provider diversi.

### D3: CLI flag `--provider` come opzione globale

Aggiunto come option su ogni comando Typer. Se non specificato, usa il provider attivo (default: eurostat). Alternativa: sottocomando `opensdmx istat list` — scartata perché meno ergonomica.

### D4: Nessun alias `istat_*`

Breaking change accettato. Non ha senso mantenere alias con il rename del pacchetto.

### D5: `df_description_it` rimosso, lingua da provider config

La colonna `df_description_it` era specifica di ISTAT. Eurostat ha 24 lingue. La colonna descrizione diventa `df_description` nella lingua configurata dal provider (`language` field). Se il provider è `istat`, si tenta `it` con fallback `en`.

## Risks / Trade-offs

- **Rate limit globale condiviso**: se l'utente chiama provider diversi in sequenza, il rate limit di ISTAT (13s) potrebbe bloccare chiamate Eurostat veloci. → Il rate limit è per-provider (file temp separato per agency_id)
- **`datastructure/ALL/{id}`**: Eurostat potrebbe non rispondere a `ALL` come agencyId per le strutture. → Usare `agency_id` del provider come fallback se `ALL` restituisce errore
- **`availableconstraint` non supportato da tutti**: Eurostat usa `contentconstraint` in SDMX 2.1. → Gestire 404 con `warnings.warn` come già fatto oggi

## Migration Plan

1. Rename repo GitHub: `istatPy` → `opensdmx`
2. Aggiornare `pyproject.toml`: name, scripts entry point
3. Refactor `base.py`: provider system
4. Aggiornare `db_cache.py`: cache path dinamica
5. Aggiornare `discovery.py`, `retrieval.py`: usa provider attivo
6. Aggiornare `cli.py`: `--provider` flag, entry point `opensdmx`
7. Aggiornare `__init__.py`: nuovi nomi export
8. Aggiornare `ai.py`: system prompt provider-aware
9. Update `README.md` e `LOG.md`

Rollback: il vecchio codice è su git, basta tornare al commit pre-refactor.

## Open Questions

- Eurostat: verificare se `datastructure/ALL/{id}` funziona o serve `ESTAT/{id}`
- Rate limit file separato per provider: usare `/tmp/opensdmx_{agency_id}_rate_limit.log`?
