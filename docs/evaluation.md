# Valutazione di Production-Readiness — opensdmx

Versione analizzata: `0.2.2` — commit `6886cef`

---

## Executive Summary

opensdmx è un client Python/CLI per API SDMX 2.1 con un'architettura modulare ben articolata, documentazione utente solida e una copertura provata su più provider (Eurostat, ISTAT, OECD, ECB, World Bank). La struttura dei moduli è coerente e il sistema di caching a due livelli (Parquet + SQLite) è ben progettato. Il punto più critico per la produzione è la quasi-totale assenza di test automatici (4 test su una singola funzione di configurazione, zero test su logica HTTP/XML/business). Secondariamente, il modulo AI (`guide`/`ai.py`) contiene artefatti di debug in produzione, stringhe hardcoded in italiano, e una dipendenza da API Key Gemini non documentata. Il progetto è usabile e stabile per uso personale/ricerca; prima di una distribuzione ampia su PyPI richiede almeno test di regressione di base e pulizia del codice AI.

---

## Punteggi per dimensione

| Dimensione | Punteggio | Note breve |
|---|---|---|
| Qualità del codice e architettura | 4/5 | Buona separazione, convenzioni coerenti; `cli.py` molto lungo |
| Copertura test e affidabilità | 1/5 | 4 test, zero mock HTTP/XML |
| Gestione errori e resilienza | 3/5 | Retry + rate-limit OK; 26 `except Exception` larghi |
| Documentazione | 4/5 | README completo, architettura documentata; docstring parziali |
| Packaging e distribuzione | 3/5 | PyPI presente; nessuna automazione build/publish |
| CI/CD | 1/5 | Nessun workflow GitHub Actions |
| Sicurezza | 3/5 | Nessun segreto hardcoded; Gemini API key non documentata |
| Gestione dipendenze | 3/5 | Dipendenze pesanti e non opzionali per feature AI |
| CLI UX e usabilità | 4/5 | Output Rich, errori contestuali, hint; messaggio in italiano nel `guide` |
| Edge case e robustezza | 3/5 | Cache e fallback presenti; provider non testati automaticamente |

**Punteggio complessivo: 2.9/5 — Non pronto per produzione ampia**

---

## Punti di forza

**Architettura modulare chiara.** Otto moduli con responsabilità distinte (`base.py`, `discovery.py`, `retrieval.py`, `utils.py`, `db_cache.py`, `embed.py`, `ai.py`, `cli.py`). Il flusso dati è documentato in `docs/architecture.md` e riflette il codice reale.

**Sistema di caching a due livelli.** Parquet per il catalogo dataflow (TTL 7 giorni), SQLite per strutture/codelist/vincoli (TTL 30/7 giorni). TTL configurabile via variabili d'ambiente (`OPENSDMX_*_CACHE_TTL`). Cache namespaced per provider (`~/.cache/opensdmx/{AGENCY_ID}/`).

**Retry e rate-limiting.** `sdmx_request` usa `tenacity` (3 tentativi, backoff esponenziale). Il rate limiter scrive su file temporaneo, funziona cross-processo, mostra countdown su stderr senza sporcare stdout.

**Multi-provider pulito.** `portals.json` con 8 provider; configurazione custom via URL; ogni provider può sovrascrivere endpoint, formato dati, rate limit. Il comando `--provider` funziona su tutti i sottocomandi CLI.

**README e documentazione di supporto.** README con quick-start, tabella API, esempi, sezione caching con tabella TTL, link a pypi/github/deepwiki. Documenti aggiuntivi: `architecture.md`, `cache.md`, `PRD.md`, `release.md`, `cli-test-examples.md`.

**UX CLI.** Output Rich con tabelle colorate, stderr separato da stdout (pipe-friendly), hint contestuali su errori HTTP 400/404, spinner durante operazioni lente, `--help` su tutti i comandi con esempi.

**LOG.md aggiornato.** Traccia dettagliata di ogni sessione di sviluppo; utile per audit della cronologia decisionale.

---

## Debolezze

### Critica — Test quasi assenti

Solo 4 test in `tests/test_cache_config.py`, tutti sul modulo di configurazione TTL. Nessun test su:

- parsing XML SDMX (`utils.py`, `discovery.py`)
- `parse_time_period()` — funzione pura con molti branch (YYYY, YYYY-MM, YYYY-Qn, YYYY-Sn, YYYY-Wnn, YYYY-MM-DD)
- `make_url_key()` — costruisce URL SDMX con logica di concatenazione
- `set_filters()`, `reset_filters()`, `load_dataset()` (logica di ricerca)
- `db_cache.py` — interfaccia SQLite completa
- qualsiasi mock HTTP

Una regressione in `parse_time_period` o `make_url_key` non viene rilevata automaticamente prima della release.

### Critica — Nessun CI/CD

Nessun file in `.github/workflows/`. Il processo di release è manuale (`docs/release.md`). Nessun test automatico su PR, nessuna validazione di linting o type-check, nessuna pubblicazione automatica su PyPI.

### Alta — Debug log in produzione (`ai.py:153`)

```python
with open("/tmp/guide_debug.log", "a") as _f:
    _f.write(f"\n[{datetime.datetime.now().isoformat()}]\n")
    _f.write(f"filters: {filters}\n")
    _f.write(f"df.shape: {df.shape}, columns: {list(df.columns)[:6]}\n")
```

Questo codice scrive su `/tmp/guide_debug.log` ad ogni chiamata di `_validate()` durante `guide`. Comportamento non atteso dall'utente, inquina filesystem, potenziale leak di informazioni in ambienti condivisi.

### Alta — Stringhe hardcoded in italiano in moduli core

`ai.py` e `cli.py` contengono messaggi UI in italiano che emergono anche quando il provider e l'utente sono inglesi:

- `"Nessuno scenario valido — provo con filtri minimi..."` (`ai.py:223`)
- `"(digita 'esci' o 'cambia' per tornare alla selezione dataset)"` (`ai.py:260`)
- `"{dim_id}: {bad} non disponibili. Esempi validi: {sample}"` (`ai.py:143`)
- `"Nessun dato per questa combinazione di filtri."` (`ai.py:158`)
- `"Torno alla selezione dataset..."` (`cli.py:704`)

Il LOG.md del 2026-03-31 documenta "Translated all user-facing messages to English" — la traduzione è incompleta.

### Media — Dipendenze AI obbligatorie per tutti gli utenti

`chatlas[google]`, `ollama`, `numpy`, `plotnine`, `inquirerpy`, `questionary` sono in `dependencies` (non opzionali). Un utente che vuole solo `fetch()` o `get_data()` installa Gemini SDK, Ollama client, matplotlib backend, librerie interattive. Il peso dell'installazione è significativo per un tool CLI leggero. Non ci sono extra opzionali (`[ai]`, `[plot]`).

### Media — Dipendenza da Gemini API Key non documentata

`guide` e `search --semantic` richiedono una chiave API Google (Gemini 2.5 Flash) via variabile d'ambiente (`GOOGLE_API_KEY` o equivalente `chatlas`). Questa dipendenza non è menzionata nel README né in `.env.example`. Un utente che esegue `opensdmx guide` senza configurare la chiave ottiene un errore non chiaro.

### Media — Stato globale mutabile in `base.py`

`_active_provider`, `_timeout`, `_rate_limit_context` sono variabili globali a livello di modulo. In uso single-threaded (CLI) è accettabile, ma rende il modulo non thread-safe e difficile da testare con isolamento. Ogni test che chiama `set_provider()` deve fare cleanup manuale.

### Bassa — 26 `except Exception` generici

In `cli.py` ci sono 26 catture di `Exception` generica. Alcune sono appropriate (edge guard), ma molte mascherano errori specifici (es. `httpx.ConnectError` vs `httpx.HTTPStatusError`). Il controllo `_check_api_reachable` cattura tutto silenziosamente e mostra solo un messaggio generico.

### Bassa — `cli.py` monolitico (971 righe)

Il file `cli.py` contiene tutta la logica CLI incluso il comando `guide` con 400+ righe di logica interattiva. La funzione `guide()` da sola è un buon candidato per estrazione in un modulo separato.

### Bassa — `print_dataset()` usa `print()` invece di Rich

La funzione pubblica `print_dataset()` in `discovery.py` usa `print()` bare invece di `rich.Console`, incoerente con il resto dell'output CLI.

---

## Architettura

La separazione a livelli è corretta:

```
cli.py → discovery.py / retrieval.py → base.py (HTTP)
                    ↓                       ↓
               db_cache.py              utils.py
```

`ai.py` accede direttamente a `discovery.py` e `retrieval.py`, bypass della CLI — scelta corretta per riuso. `embed.py` dipende solo da `base.py` e `discovery.py`.

Il punto debole architetturale è lo stato globale in `base.py`: `_active_provider` è un singleton implicito. Per test o uso multi-provider concorrente sarebbe meglio un oggetto `SDMXClient` esplicito, ma per la CLI monothread attuale è funzionale.

Il formato del dataset come `dict` (non dataclass/Pydantic) è semplice ma privo di type safety; un `TypedDict` o dataclass migliorerebbe l'autocompletamento IDE e la documentazione implicita.

---

## Metriche qualità codice

| Metrica | Valore |
|---|---|
| Righe totali sorgente | 2527 |
| Moduli | 8 |
| Test | 4 (1 file) |
| `except Exception` generici | 26 |
| `# type: ignore` | 11 |
| Stringhe UI in italiano (codice EN) | ~8 |
| Debug log in produzione | 1 (`/tmp/guide_debug.log`) |
| Commit totali | 41 |
| Provider supportati | 8 |

---

## Sicurezza

Nessun segreto hardcoded nel sorgente. Il file `.env.example` non contiene API key (solo TTL). La comunicazione avviene via HTTPS verso API pubbliche. Il rate-limiter usa file in `/tmp` — vettore di attacco potenziale solo in ambienti condivisi multi-utente (race condition sul file). Gemini API key è implicita nell'ambiente: se esposta in logs di CI/CD (es. GitHub Actions output), potrebbe essere visibile — ma nessun CI è configurato quindi non è un rischio attivo.

---

## Dipendenze

```
httpx, tenacity, lxml, polars, pyarrow, rich, typer   ← core funzionale
duckdb                                                 ← importato ma non usato nel sorgente attuale (inferito)
numpy, plotnine                                        ← AI/plot (non opzionali)
ollama, chatlas[google]                               ← AI (non opzionali)
inquirerpy, questionary                               ← UI interattiva guide (non opzionali)
```

`duckdb` è in `dependencies` ma non appare in nessun `import` nei moduli core (`grep -r "import duckdb"` — zero risultati). Potenziale dipendenza residua da una versione precedente.

Versioni minime molto recenti (`polars>=1.38.1`, `duckdb>=1.4.4`): limita compatibilità ma garantisce API stabili.

---

## Raccomandazioni prioritizzate

### P0 — Bloccanti per qualsiasi distribuzione pubblica

**1. Rimuovere il debug log da `ai.py:153-157`.**
Il blocco `open("/tmp/guide_debug.log", "a")` va eliminato. Quattro righe, zero impatto funzionale.

**2. Aggiungere CI con GitHub Actions.**
Workflow minimo: `pytest` su push/PR. Estendibile con `ruff` e type-check.

### P1 — Alta priorità

**3. Aggiungere test per funzioni pure critiche.**
`parse_time_period()`, `make_url_key()`, `set_filters()`, `get_name_by_lang()` sono testabili senza mock HTTP. Seguono casi d'angolo noti (YYYY-Wnn, filtri multipli `+`, case-insensitive).

**4. Documentare il requisito Gemini API Key.**
Aggiungere al README una sezione "AI features require a Google Gemini API key" con istruzioni per `GOOGLE_API_KEY`. Aggiungere al `.env.example`.

**5. Tradurre le stringhe italiane residue.**
`ai.py:143,158,223,232,253,260,302` e `cli.py:704` — testo UI in italiano in un tool che si presenta come internazionale.

### P2 — Media priorità

**6. Rendere le dipendenze AI/plot opzionali.**
Introdurre extras in `pyproject.toml`:

```toml
[project.optional-dependencies]
ai = ["ollama>=0.6.1", "chatlas[google]>=0.7", "inquirerpy>=0.3.4", "questionary>=2.1.1"]
plot = ["plotnine>=0.15.3", "numpy>=2.4.2"]
```

Il core (`search`, `info`, `constraints`, `get`) non richiede Ollama né Gemini.

**7. Verificare e rimuovere `duckdb` se inutilizzato.**
`duckdb>=1.4.4` è in dependencies ma non importato nel codice attuale. Se non serve, va rimosso.

**8. Estrarre `guide()` da `cli.py`.**
Le 400+ righe del comando `guide` meritano un modulo `cli_guide.py` separato per migliorare la leggibilità e la testabilità.

### P3 — Bassa priorità

**9. Sostituire `print_dataset()` con output Rich.**
Incoerente con il resto della CLI; usa `rich.Console` come gli altri comandi.

**10. Tipizzare il dataset dict come `TypedDict`.**
Migliora autocompletamento IDE, riduce i `# type: ignore`.

**11. Considerare `SDMXClient` come oggetto esplicito.**
Rimuove lo stato globale, abilita uso multi-provider in library mode senza effetti collaterali.

---

## Analisi ipotesi iniziali

| Ipotesi | Esito |
|---|---|
| Architettura modulare coerente | **Confermata** — 8 moduli con responsabilità distinte, flusso documentato |
| Test coverage inadeguata | **Confermata** — 4 test, 1 modulo, zero HTTP/XML |
| Dipendenze ben gestite | **Parzialmente confermata** — versioni recenti, ma nessun extra opzionale; `duckdb` potenzialmente orfano |
| CI/CD assente | **Confermata** — nessun workflow |
| Qualità UX CLI alta | **Confermata** — Rich output, stderr separato, hint contestuali |

---

## Domande aperte

- `duckdb` è effettivamente usato (es. in script non inclusi nel package)? Se no, va rimosso.
- `guide` è destinato all'uso pubblico o rimane nascosto (`hidden=True` in CLI)? Se hidden, la priorità di pulizia scende.
- I provider `insee`, `bundesbank`, `abs` sono stati testati manualmente? Non compaiono in `cli-test-examples.md`.
- La scelta di `gemini-2.5-flash` hardcoded in `ai.py:167` e `embed.py:83` è intenzionale? Renderlo configurabile aumenterebbe la portabilità.
