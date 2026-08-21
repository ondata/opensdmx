# LOG

## 2026-08-21 - docs: realign the public record of how search actually works

- **The state, measured, not assumed.** `search --semantic` ships and works: Ollama with `nomic-embed-text-v2-moe`, a hardcoded constant in `embed.py`, no flag and no fallback backend. The index is built **on demand, per provider**, by `opensdmx embed` into `<cache>/<provider>/embeddings.parquet` — nothing is precomputed and nothing ships. Latency on ISTAT (4,896 dataflows): ~10 s on the first query of a session while Ollama loads the model, ~1 s after. What differs per provider is the *corpus*, not the capability: `df_prose` comes from a `data/descriptions/<provider>.parquet` inside the wheel and only `istat.parquet` exists, so elsewhere the embedded document is id + title + category context.
- **Why the docs had drifted.** July and August improved the corpus (category context v0.17.0, `df_keywords` v0.19.0, harvested prose v0.20.0, `df_notes`) while the engine stayed on Ollama. Each document written along the way described a different intended future in the present tense and none was amended when that future changed.
- **The self-contained-backend plan is a direction, not an approved plan, and now says so.** Its premise is falsified: the 2026-07-16 plan named `google/embeddinggemma-300m` with `multilingual-e5-small` as fallback and fastembed 0.8.0 exposes neither; the plan document is gone; and fastembed had already been tried and reverted on 2026-03-31 with a *different* model (`nomic-embed-text-v1.5-Q`) for poor Italian quality. `docs/future-ideas.md` now states which model each result used, so the "reverted" and "validated" entries stop reading as a contradiction. No candidate has been scored against the targets `docs/search.md` sets (MRR 0.135 to beat BM25, ~0.327 to replace nomic) — issue #77.
- **Corrections to public claims.** README: keyword default 20 → 50; "exact substring match on dataset title" → the scored token match on title, ID and category name; semantic "10 most similar" → 50; "The model is fixed" → the model is fixed *within a release*, and the index does not record which model built it (#57); the 3.4× figure now names its metric (S@10, 57% vs 17%). `docs/PRD.md` and `references/istat-flow.md` still said search matches "descriptions" — the same wording `LOG.md` records fixing on 2026-07-16; dataflows expose an SDMX `Name`.
- **`--semantic` no longer drops flags in silence.** `--category`, `--page` and `--all` were accepted and ignored — the semantic branch returns before the code that reads them — so a user who restricted a search to a category read results drawn from the whole catalogue with no signal. They now fail with an explicit error. `--n` and `--grep` are unaffected. The "cache not found" message now says the index is per-provider and suggests the right `--provider`. Ollama-unreachable was already reported distinctly, since `_check_ollama()` runs first.
- **The skill was routing agents to the weaker arm.** `SKILL.md` told the agent to offer `--semantic` only after keyword returned fewer than 3 results, and priced it at "10-30 s". Measured on ISTAT: on naturally-phrased questions the keyword scorer reaches MRR 0.041 against 0.252 for semantic, and on English queries against Italian metadata keyword search finds essentially nothing. Routing is now conditional — where an index exists and the question is in natural language, semantic goes first; otherwise the `tree`-first default stands. Latency and the top-N figure corrected.
- **Removed from the repository**: `docs/evaluation.md`, `docs/evaluation-v0.14.0.md`, `docs/evaluation-v0.2.6.md`. Dated audits of superseded versions, kept public by an accident of `.gitignore` ordering; `evaluation.md` still told readers that `search --semantic` needs a Google API key, removed on 2026-04-03. Untracked, not deleted.
- Issue #53 (ISTAT descriptions from METADATA_API) closed — shipped in v0.20.0 and refreshed monthly since. Opened #75 (`[semantic]` extra), #76 (BM25 on `search_dataset`), #77 (static retriever).
- Gate: ruff clean, mypy strict clean on 15 files, 384 tests green (5 new, covering the rejected flag combinations). `skills/sdmx-explorer/` updated (SKILL.md + `references/thematic-tree.md` + `references/istat-flow.md`).

## 2026-08-19 - v0.22.3 - fix: `tree` probes the category tree of an unlisted provider

- A provider given as a URL (`--provider https://.../rest`) got `Active provider does not expose /categoryscheme` even when it does: `categories_supported` is a *declared* capability of the 15 providers in `portals.json`, and a custom dict never carries the key, so the falsy default was read as a denial. The gate now fires only when a listed provider declares `false`; an undeclared provider is probed live and an `httpx.HTTPStatusError` is translated into `CategoriesNotSupported` naming the URL and the status code.
- Second cause on the same path: `catalog_agency` fell back to `agency_id`, empty for a custom URL, producing `categoryscheme//ALL/latest` → 404. A single `_catalog_agency()` helper falls back to the `ALL` wildcard for both structure calls. The cross-agency `df_id` prefixing still compares the *configured* `catalog_agency`, so no listed provider changes behaviour.
- Verified live: `opensdmx tree --provider https://nsidisseminate-stat.nbb.be/rest --depth 1` renders the 9 NBB schemes (`ECO` 50 dataflows, `INT_ECO` 53, …). `--provider worldbank` still refuses with the provider list, and `--provider https://api.worldbank.org/v2/sdmx/rest` reports the HTTP 403 with its URL.
- `category_context()` (used opportunistically by `search` and `embed`) is cache-only, so no discovery path can now trigger a 1-2 minute build.
- Gate: ruff clean, mypy strict clean on 15 files, 379 tests green. `skills/sdmx-explorer/` updated (SKILL.md + `references/thematic-tree.md`).

## 2026-08-19 - v0.22.2 - fix: interoperable retry for `availableconstraint` on NBB

- Reproduced the cause on `https://nsidisseminate-stat.nbb.be/rest`: with the implicit `references=none`, `constraints EXR` gets HTTP 200 plus a malformed HTML error page; without the parameter it gets 57,735 bytes of valid SDMX-XML. A parse error on `availableconstraint` now triggers a single retry that drops `references` and nothing else — no URL-based special cases, and the first request is unchanged.
- The retry is limited to `lxml.etree.XMLSyntaxError`: no retry on success, on `contentconstraint`, or for providers with `constraint_params={}`. If the second parse fails too, the flow ends after two calls and keeps the cause in the logs. The CLI no longer invents the claim that the endpoint may be unsupported when it gets an empty result.
- Live before/after check with isolated caches: Eurostat `PRC_HICP_MANR`, ABS `CPI`, BIS `WS_LONG_CPI` and IMF `IMF.RES,WEO` all stay exit 0 with identical dimension counts. NBB `EXR` goes from exit 1 to exit 0 and returns `DATA_DOMAIN=27`, `REF_AREA=1`, `INDICATOR=945`, `COUNTERPART_AREA=3`, `FREQ=4`.
- Gate: ruff clean on `src/` and `tests/`, mypy strict clean on 15 files, 376 tests green. The historical 404 of `get EXR --REF_AREA BE` remains non-reproducible and out of scope.

## 2026-08-18 - v0.22.1 - fix: v0.22.0 was unimportable on a fresh install

- fix(cli): `from click.core import ParameterSource` (added with `OPENSDMX_OUTPUT` in PR #70) crashed every fresh install of v0.22.0 with `ModuleNotFoundError: No module named 'click'`. typer 0.27 dropped its click dependency, and `click` was never declared in `pyproject.toml` — it only ever arrived transitively. The origin of the `--output` value is now read by comparing the parameter source **by name**, so both typer's own enum and click's work and neither is imported.
- The bug shipped because `uv.lock` still pinned typer 0.24.1, which pulls click in: the whole suite passed against a package no user could install. The lock now tracks typer 0.27.1, so the tests exercise what people actually get, and `tests/test_cli.py` no longer imports `click.exceptions.Exit` either — it uses `typer.Exit`.
- Added a guard test asserting `src/opensdmx/cli.py` imports no `click`.
- Verified on a clean venv with typer 0.27.1 and no click installed: the CLI imports, and an invalid value still names its source (`invalid OPENSDMX_OUTPUT value 'jsn'` from the environment, `invalid --output value 'jsn'` from the flag).

## 2026-08-18 - v0.22.0 - `providers` coverage column (issue #18, PR #71)

- feat(providers): `opensdmx providers` gains a `coverage` column — the share of a provider's cached dataflow catalog that has a category assigned. `categories_supported` only said whether a tree exists; it never said whether the tree reaches everything, and a dataflow with no `Categorisation` is invisible to `tree` while being perfectly reachable by `search`. OECD sits around 89%, so tree-only exploration there silently misses one dataflow in ten. Contributed by @deepusnath.
- Reads only the on-disk `dataflows.parquet` / `categorisation.parquet` of each provider and never fetches: `?` when nothing is cached yet, `-` where there is no tree. Categorised ids the catalog no longer lists are ignored — the two caches expire independently and counting them pushed the ratio past 100%.
- The table rounds **down**. `{pct:.0f}` printed Eurostat's 99.90% as `100%`, hiding the ~9 uncategorised dataflows behind the very column meant to reveal them; "almost complete" is the misleading case, not the harmless one.
- docs: documented in `README.md`, `docs/providers.md`, `skills/sdmx-explorer/SKILL.md` (Step 1b, where the tree-vs-search decision is actually made) and the `providers` docstring, so the three states are explained where they are read.
- Known cosmetic limit, not introduced here: below ~100 terminal columns the table is too dense and truncates values (`100%` → `10…`), as `agency` and `categories` already did on `main`.
- v0.22.0 ships both of today's features: this column and the `OPENSDMX_OUTPUT` env var below (issue #8, PR #70), which had not been released yet.

## 2026-08-18 - `OPENSDMX_OUTPUT` env var (issue #8)

- feat(cli): `--output` now reads `OPENSDMX_OUTPUT`, so a user who always wants JSON can `export OPENSDMX_OUTPUT=json` instead of typing `-o json` on every call — the ask in issue #8. Resolution order is explicit flag > env var > `table`. **The project default is unchanged**: `table` stays the default for everyone, and flipping it project-wide remains a separate decision (the reporter never answered whether the table output caused real friction).
- fix(cli): an invalid value now names the source that supplied it — `invalid OPENSDMX_OUTPUT value 'jsn'` when it came from the environment, `invalid --output value 'jsn'` when it came from the flag. Blaming a flag the user never typed would have been the natural regression here.
- docs: env var documented in `README.md`, `.env.example`, the `--help` banner and `skills/sdmx-explorer/SKILL.md`.
- Pre-existing, untouched: `ruff check` reports 4 findings in `scripts/` (`monitor_latency.py`, `test_istat_endpoints.py`) — unrelated to this change.

## 2026-08-17 - Wayfinder: territorial capability of ISTAT dataflows

- Local map in `tasks/wayfinder/istat-territorial-capability-map.md`: either a verdict verified against the archive, or an explicitly labelled metadata estimate with no live calls; never an inference about the coverage of a given query.
- Verified what already exists: the `Constraints Archive` workflow refreshes the ISTAT archive daily, and the derived view holds 3,275 rows, 180 of them `REF_AREA` dataflows whose maximum level is `comune`, checked between 2026-07-16 and 2026-08-10. A live check of `101_1039` took ~38 s over 5,632 `REF_AREA` codes, so it cannot sit in a synchronous request.
- Research on metadata fallbacks: with no archive entry, only an ID matching `_COM_` / `_COM<digit>` or a title containing `com.` supports a defensible municipal estimate (26/26 among the verified dataflows). Every other signal stays `unknown` — never "regional only".

## 2026-08-10 - v0.21.1 - fix `siblings` e hint d'installazione di `guide` (PR #69)

- fix(siblings): `siblings une_rt_m` falliva con "not categorized" mentre `siblings UNE_RT_M` funzionava — `siblings_of()` filtrava `df_id` a match esatto, mentre `load_dataset()` normalizza il case ovunque. Ora il match è case-insensitive, marcatore `→` compreso, e un ID inesistente dà l'errore standard con exit 1 invece di un exit 0 silenzioso indistinguibile da "esiste ma non è categorizzato".
- fix(guide): l'hint stampava `pip install opensdmx` senza `[guide]`. La stringa nel sorgente era giusta: Rich leggeva le parentesi quadre come markup e scartava il tag senza controparte. Chi seguiva l'hint installava senza `questionary` e tornava allo stesso messaggio, in loop. Escapato in entrambi i call site.
- refactor(discovery): nuova `resolve_dataflow()` — match sul catalogo dataflow e nient'altro. `siblings` la usa perché ha bisogno del solo `df_id` canonico; `load_dataset()` ci si appoggia e aggiunge le dimensioni, così le regole di matching restano in un punto solo. **Dai rilievi di review**: risolvere via `load_dataset()` scaricava la datastructure per dimensioni mai usate, aggiungendo una richiesta a ogni lookup e facendo fallire un dataflow categorizzato quando l'endpoint DSD era giù.
- La risoluzione dell'ID in `siblings` è **best-effort**: `ValueError` (catalogo caricato, ID davvero assente) mantiene l'errore standard; qualunque altro errore prosegue con l'ID grezzo, perché `siblings_of` tollera di proposito un catalogo dataflow irraggiungibile e degrada a descrizioni vuote. Anche questo da un rilievo di review, sul primo fix.
- Due guardie di regressione: `siblings` non deve toccare la datastructure (tutti i test girano con `_get_dimensions` che solleva) e non deve arrendersi se `all_available()` fallisce.
- Il test dell'hint `guide` sostituiva `err_console` globalmente senza ripristinarlo, lasciando una Console bufferizzata per tutta la sessione: ora `patch.object`.
- Suite 352 → 354, ruff e mypy puliti.

## 2026-08-10 - eval: retrieval keyword vs semantico su ISTAT (54 query)

- Nuovo eval mirato al solo layer di ricerca (nessun agente, nessun giudice LLM): `eval/retrieval.py` + gold set `eval/goldset/retrieval.yaml`, 27 bisogni informativi scritti alla cieca × 2 lingue, gold come famiglia di df_id.
- Cinque bracci: keyword attuale, stesso scorer su testo esteso, BM25 su testo esteso, semantico nomic, hybrid RRF non pesato.
- Risultato: il semantico vince nettamente (MRR 0,327 vs 0,073; Success@10 57% vs 17%). Il testo in più aiuta il lessicale solo con lo scorer giusto: allo scorer attuale non serve (0,075, `_score_results` premia i documenti lunghi), a un BM25 vale +85% (0,135) — ma il semantico resta 2,4× il BM25 sullo stesso testo. In inglese su metadati italiani ogni braccio lessicale è a terra (0,012-0,054) e il semantico tiene (0,310); sulla query naive BM25 non aiuta affatto. L'RRF non pesato peggiora.
- Ricaduta pratica non prevista: sostituire lo scorer di `search_dataset` con BM25 sul testo esteso vale +85% di MRR senza modelli né dipendenze nuove.
- Ricostruita la cache embedding ISTAT, ferma al 24 luglio e quindi antecedente al cambio di ricetta del testo embeddato (`d8f7dcc`).
- Report: `eval/results/2026-08-10/retrieval.md`. Impianto e passi aperti: `tasks/todo-retrieval-eval.md`.
- Nuovo `docs/search.md` **tracciato**: documento di riferimento sulla ricerca — i due percorsi, il testo che ciascuno indicizza (non è lo stesso), il registro delle misure (#52 del 2026-07-20 e l'eval di oggi) e cosa resta aperto. Serviva perché `tasks/`, `eval/` e `docs/eval.md` sono gitignored: fin qui nel repo non c'era traccia del perché la ricerca è fatta così. Linkato dal README accanto a `docs/descriptions.md`.
- `tasks/todo-search-context.md` diceva ancora "not started" mentre #52 è chiusa e in produzione dalla v0.17.0: corretto in DONE, con il rimando a `docs/search.md` come documento di riferimento.

## 2026-08-09 - docs: sezione "Human analyst quickstart" nel README (R7 della valutazione)

- Aggiunta sezione per l'utente umano dopo il CLI quick start: tre flussi reali da analista (disoccupazione giovanile con `--labels`, PIL pro capite riproducibile via `--query-file`/`run`, HICP con `plot`) e le tre regole che salvano tempo (dimensioni a valore singolo esplicite, `--labels` sempre, salvare le query riusabili).
- Tutti i comandi citati verificati end-to-end contro Eurostat prima di pubblicarli (nessun esempio inventato).
- Niente codice: solo README.

## 2026-08-09 - fix: l'hint d'installazione di `guide` perdeva `[guide]` (P3 della valutazione)

- Sintomo: `opensdmx guide` diceva `Run: pip install opensdmx` (senza `[guide]`) anche se il sorgente conteneva la stringa giusta — un fix che non installa `questionary` e va in loop.
- Causa radice: il messaggio passava per Rich, che interpreta `[guide]` come markup e scarta il tag senza controparte. Non era una stringa sbagliata: era renderizzata male.
- Fix: escape `\[guide]` nei due call site (`guide.py` run_guide e `cli.py` blacklist).
- Test di regressione: `test_guide_missing_extra_hint_shows_bracket` (blocca l'import di questionary, cattura la Console su buffer, verifica che `[guide]` sopravviva al rendering). 352 passed, ruff/mypy puliti.

## 2026-08-09 - fix: `siblings` case-insensitive + exits 1 on failure (da valutazione v0.21.0)

- `siblings une_rt_m` falliva con "not categorized" mentre `siblings UNE_RT_M` funzionava: `siblings_of()` filtrava `df_id` a match esatto, mentre `load_dataset()` normalizza il case ovunque. Viluppo: match case-insensitive in `siblings_of` (`str.to_uppercase()`) e comparazione `is_target` normalizzata, così il marker `→` colpisce la riga giusta anche con input minuscolo.
- `siblings` ora risolve l'ID via `load_dataset()` prima della lookup categorie: distingue "ID inesistente" (errore standard `Could not find dataset`, exit 1) da "esiste ma non categorizzato" (exit 1, non più 0 silenzioso).
- Test: `test_siblings_of_case_insensitive` (library) + 4 CLI test (lowercase, json, not-found, not-categorized); 351 passed, ruff/mypy puliti.

## 2026-08-09 - Valutazione usabilità v0.21.0 (prospettiva analista socio-economico)

- Nuovo doc `docs/evaluation-v0.21.0.md`: valutazione hands-on della CLI da utente analista Eurostat (disoccupazione, PIL pro capite, HICP, NUTS2, popolazione), con tempi misurati e casi d'errore verificati.
- Punti forti: sub-second su cache calda (0.3-0.8 s), `constraints` fedele alla realtà di campo (verificato: l'API rifiuta `Y15-24` su UNE_RT_M esattamente come il CLI), errori autoesplicativi, `--labels`, riproducibilità YAML (`--query-file`/`run`), `plot` out-of-the-box.
- Problemi aperti: `search "unemployment"` seppellisce UNE_RT_M al #58/146 (ranking per occorrenze, non per importanza); `siblings` case-sensitive con exit code 0 sul fallimento; hint d'installazione `guide` errato (serve `pip install "opensdmx[guide]"`); nessun intervallo temporale in `info`; niente stima righe nel guard di `get`; warning plotnine su stderr.
- Proposte R1-R6 (senza cambiare architettura): boost ranking senza LLM, fix `siblings`, fix hint `guide`, `info` con periodo quando noto, stima `~N righe` nel guard, silenziare plotnine. R1 (ranking) a maggior ritorno per l'utente umano.

## 2026-08-05 - feat: `values` cross-references the dataflow's constraints (#67, #66)

- Returning the whole codelist was never wrong — a codelist is a shared definition, not one dataflow's inventory. What was missing is the link to `constraints`: of the 759 `CL_UNIT` codes listed for `PRC_HICP_MANR`, exactly one (`RCH_A`) is usable as a filter there, with no signal in the output.
- feat(values): the output now carries that link. When the dataflow's constraints are already cached, each row gets an `in_dataflow` flag (`true`/`false`, `null` when unknown) plus a coverage footer; otherwise a pointer to `opensdmx constraints`. Both paths are a **local cache read** — zero extra network calls, so the cheap command stays cheap.
- `in_dataflow` is a real field in JSON and CSV, and the CSV header no longer changes shape with cache state (caught in review: the column used to disappear when membership was unknown).
- No filtering added to `values`: `constraints <df> <dim>` already returns exactly the codes present, byte-identically. `values` keeps showing the whole codelist *with* the valid ones marked — the view `constraints` cannot give.
- feat(get/plot): the 400/404 hint now also names the dimensions left unfiltered instead of only blaming filter values (#66).
- #66 as filed does not reproduce: `contentconstraint/ESTAT/LFSQ_URGAN` returns `citizen` today and the repro `get` exits 0 with data — most likely a stale partial constraint cache entry (7-day TTL). Closed as not reproducible.
- New `discovery.constrained_codes()` (pure, case/dash-insensitive, `None` when the dimension is unknown) + 17 tests.

## 2026-08-05 - eval: agent-loop evaluation harness (DeepEval, Target C)

- New `eval/` package (not in core deps; `deepeval` behind the `[eval]` extra) that scores the **agent loop** — an LLM orchestrating the opensdmx CLI with the `sdmx-explorer` skill — end-to-end. Plan in `tasks/todo-deepeval-agent-loop.md`.
- **Gold set** `eval/goldset/cases.yaml`: 10 cases across eurostat/oecd/imf/ecb/istat, tagged by `failure_mode` (discovery / filters / provenance / value-rounding). Every canonical_query validated live (returns rows).
- **Deterministic core** (no LLM judge — the point of opensdmx): `QueryConvergenceMetric` (agent's declared provider+dataset == gold) + `ValueCorrectnessMetric` (re-run the agent's declared query AND the gold canonical query live, compare cells within tolerance). Judge metrics (`Faithfulness`, `GEval`) on GLM-5.2/ZAI behind `--judge`.
- **Routing**: agents Claude+Gemini via OpenRouter (`OPENROUTER_API_KEY`); judge GLM-5.2 via ZAI (`ZAI_API_KEY`, neutral). Freemium `GEMINI_API_KEY` only an optional fallback (`GEMINI_RPM` throttle).
- Agent harness (`eval/agent.py`) runs the skill as system prompt, exposes a `run_opensdmx` tool, and asks for a final structured `ANSWER={...}` block; `eval/shims/` is a PATH shim that tees every opensdmx call to JSONL (retrieval context + convergence analysis).
- **Verified end-to-end**: Claude seed case (StatGPT IMF WEO) → real discovery 23 steps → `QueryConvergence 1.0 / ValueCorrectness 1.0`, matching the StatGPT figures.
- **Filed 2 CLI issues found in validation**: #66 `constraints` omits dimensions that `info` shows (lfsq_urgan `citizen`) → misleading "check filter values"; #67 `values` returns codelist codes not present in the dataflow (HICP `unit`) → invalid filters.
- Run: `uv run python -m eval.run --model all`, report in `eval/results/<date>/`.

## 2026-08-04 - spike: embedding-only semantic search over ISTAT descriptions

- Prototype `tmp/semantic_route_test.py`: fastembed (multilingual MiniLM, ONNX/CPU) + cosine over the 3,949 harvested descriptions. No LLM, no API.
- 16–18 ms per query after a one-time ~155 s corpus embedding (~6 MB cache). Birth/inflation/road-accident queries nail top-5; out-of-domain query correctly rejected by a 0.45 threshold.
- Validates the approved fastembed self-contained semantics plan; findings + current bibliography in `docs/future-ideas.md`.

## 2026-07-25 - feat: territorial dimension from the GEO_ID annotation

- feat(discovery): capture `GEO_ID` into a new `df_geo_dim` catalog column — the
  territorial dimension ISTAT names on a dataflow when it is not the default
  `ITTER107`/`REF_AREA` (e.g. `RESIDENCE_TERR`).
- feat(constraints_archive): the nightly territorial classifier now treats as
  territorial the default dimensions **plus the distinct `df_geo_dim` names
  discovered across the catalog**, applying each name wherever it occurs. Gated on
  the dimension name only — never on code shape (`ECOICOP_2` has 6-digit codes but
  is not geography). Recovers 77 previously-invisible dataflows (incl. births `25_74`)
  while correctly excluding the 31 `ECOICOP` dataflows.
- Verified in a dry run over `data/constraints/istat.parquet`: classifiable dataflows
  1,749 → 1,826; `RESIDENCE_TERR` discovered from `GEO_ID`; `ECOICOP` not included.

## 2026-07-25 - feat: consume LAST_UPDATE / DATAFLOW_NOTES / ATTACHED_DATA_FILES

- feat(discovery): three new nullable catalog columns read from ISTAT's `annotations`
  block at zero extra network cost — `df_last_update` (LAST_UPDATE, 4,511 dataflows),
  `df_notes` (DATAFLOW_NOTES, 144), `df_bulk_files` (ATTACHED_DATA_FILES, 365). Stored
  as published (LAST_UPDATE mixes ISO 8601 and MM/dd/yyyy; bulk files are `URL|LABEL`).
- feat(embed): fold `df_notes` into the embedded document text so semantic search can
  match a dataset by its methodological caveats (e.g. province-boundary changes that
  break time-series comparability). `df_last_update`/`df_bulk_files` are captured, not embedded.
- infra: optional catalog columns backfilled via one `_ensure_catalog_columns()` helper
  (legacy cache + hub-only INPS), replacing the growing per-column if-chain.
- Verified: coverage 4,511 / 144 / 365; a notes-only query now reaches the dataflow.
  Follow-ups (out of scope): normalise `df_last_update`, surface `df_bulk_files` in
  `info`/`get`, and the GEO_ID territorial change.

## 2026-07-25 - refactor: single-pass annotation reader

- refactor(discovery): replace the text-only `_keyword_annotation` walker with
  `_annotations(node, language)` → `dict[type, Annotation(title, text, url)]`, one
  pass over the node. Fixes the latent bug that the old reader saw only
  `AnnotationText`, while most ISTAT annotations (LAST_UPDATE, LAYOUT_*, GEO_ID, …)
  carry their value in `AnnotationTitle` — pointing the old reader at them returned
  `None` silently. Presence-only annotations (e.g. READY_FOR_PRODUCTION) map to an
  all-`None` `Annotation` so membership tests work; type strings match literally
  (`LINkEDDATAFLOWNODE`, lowercase k). `_keyword_annotation` kept as a thin wrapper.
- refactor(portals): declare consumed annotations in one `annotations` block
  (`{stable_key: {type, value: text|title|presence}}`) instead of per-annotation
  top-level keys; ISTAT migrated (`keywords`, `metadata_url`). The METADATA_API
  service keys stay separate. No `if provider ==`.
- refactor(scripts): the descriptions harvester drops its `_annotation_text` copy and
  reads METADATA_URL through the shared reader.
- Enabling change only: no new annotation is consumed and behaviour is unchanged —
  verified end-to-end (ISTAT `df_keywords` still 144/4899, identical) and by the
  untouched keyword tests. Unlocks LAST_UPDATE, DATAFLOW_NOTES, ATTACHED_DATA_FILES,
  hidden-flag labelling (see `docs/istat/databrowser-annotations.md`) at zero net cost.

## 2026-07-25 - research: ISTAT dataflow annotations (SDMX Istat Toolkit)

- docs: add `docs/istat/databrowser-annotations.md` — census of the SDMX annotations
  ISTAT publishes on its dataflows, from exploring the SDMX Istat Toolkit site. One
  catalog call: 4,899 dataflows, 29 distinct annotation types in use, of which
  opensdmx reads 2 (`LAYOUT_DATAFLOW_KEYWORDS`, `METADATA_URL`).
- finding: esploradati runs the **StatKit Data Browser**, not `.Stat Suite` — the
  manual (§3.7, p. 36) names `app/databrowserhub/api/core`, our `hub_base_url`.
  `docs/istat/hub-api.md` and `docs/inps/middleware-api.md` carry the wrong platform.
- finding: 643 dataflows (13.1%) are flagged non-production or hidden by ISTAT and we
  expose them all — 14.1% of real search hits. Probed `CPI` (flagged, returns current
  data): the flag means catalog visibility, not data availability, so the remedy is to
  label and deprioritize, never to filter.
- unused signals worth a pass: `LAST_UPDATE` (92.1%, mixed ISO / `dd/mm/yyyy`),
  `LAYOUT_ROW`/`COLUMN`/`FILTER` (~80%, the publisher's own pivot), `DATAFLOW_NOTES`
  (145 methodological caveats), `ATTACHED_DATA_FILES` (366 bulk CSV/zip downloads).
- no code change in this pass.

## 2026-07-24 - v0.20.0 - real ISTAT descriptions from METADATA_API (embeddings)

- feat(descriptions): harvest the authentic dataflow descriptions ISTAT shows on
  EsploraDati — never present in the SDMX structure — via the `METADATA_URL`
  annotation → `METADATA_API` (`DATA_SOURCE`). New `scripts/descriptions_archive.py`
  reads the annotation for the whole catalog in one call, de-duplicates by the
  shared `reportId` (3,974 linked dataflows → 622 unique reports, 6.3×), fetches
  each report once, HTML-cleans the prose, and writes a bundled resource
  `src/opensdmx/data/descriptions/istat.parquet` (**3,949 dataflows described, ~81%**).
- feat(embed): fold the harvested description into the embedded document text when
  the provider resource is present; guarded, so providers/checkouts without it are
  byte-identical to before. Read locally — no metadata request at embedding time.
- feat(portals): ISTAT declares the channel (`metadata_annotation`,
  `metadata_api_path`, `metadata_description_attribute`); generic, no per-provider `if`.
  `metadataSetId`/`reportId`/`BaseUrlMDA` are derived from the live annotation.
- infra: monthly GitHub Action refreshes the resource; the metadata API is a
  service distinct from the rate-limited SDMX endpoint.
- Context: ISTAT declined to add `<common:Description>` to the DSD (2026-07-23), but
  the prose was already reachable through this separate channel. This is the primary
  description lever (81%); deterministic DSD composition (the ~19% tail + other
  providers) and optional LLM prose are declared follow-ups. No runtime LLM.

## 2026-07-24 - v0.19.0 - richer embeddings: ingest LAYOUT_DATAFLOW_KEYWORDS

- feat(discovery): parse an optional per-dataflow keyword annotation into a new
  nullable `df_keywords` column on the dataflows cache. Providers opt in by
  declaring `keyword_annotation` in `portals.json` (only ISTAT:
  `LAYOUT_DATAFLOW_KEYWORDS`); others never call the parser. New helper
  `_keyword_annotation()` matches on the `AnnotationType` child text
  (namespace-agnostic), returns the text for the provider language with en
  fallback. Zero extra network cost — same `GET /dataflow/IT1` already made.
- feat(embed): append `df_keywords` to the embedded document text when present
  (guarded on column existence for backward-compat with older caches).
- Where present, the keyword layer is rich — expanded dimensions, periodicity,
  and territorial granularity (`provincia, comune…`) — so it also helps the
  REF_AREA granularity question. But coverage is thin: **144/4899 ISTAT
  dataflows (2.9%)**. Deliberately not wired into keyword search (low impact).
- Context: ISTAT declined (2026-07-23) to populate `<common:Description>` on the
  DSD, so descriptive text must come from within opensdmx. `cat_description` is
  effectively empty everywhere (0.1% ISTAT, 0% Eurostat); the real broad lever
  remains offline synthetic descriptions (separate task).
- Verified: full suite green (307), ruff clean, live refresh confirmed the
  column populates (2.9%) and the embedded text carries the keywords.

## 2026-07-21 - v0.18.0 - INPS provider (hub-only)

- feat(provider): added **INPS** — the first *hub-only* provider. Its classic SDMX-REST endpoint is WAF-blocked, so opensdmx talks exclusively to the `.Stat Suite` DataBrowser middleware (`https://opendata.inps.it/databrowser/api/core`, JSON over GET+POST). All INPS logic lives in a dedicated `inps.py` adapter; core functions delegate via a single `if provider.get("hub_only")` branch — no scattered `if provider ==` checks.
- The middleware is split into four *nodes* (observatories: pensioni, dipendenti, imprese, politiche occupazionali); `hub_nodes` in `portals.json` holds the `code→nodeId` map, and a `df_id→node` index is built once from the four catalogs and cached as Parquet.
- `providers`/`tree`/`search`/`info`/`constraints`/`get` all work. Discovery reads catalog+structure+PartialCodelists; `get` downloads the full dataflow as SDMX-CSV (the middleware has no server-side filter) and filters client-side (dimensions + a by-year period window), mirroring Derzhstat's `data_key_format:"empty"`. `last_n`/`first_n` unavailable.
- infra: `base.sdmx_request` gained `_method`/`_json_body`/`_base_url` so hub POST calls inherit rate-limit/retry/file-lock. `dimensions_info` now prefers a description carried on the dimension (the hub's per-dimension label), falling back to the codelist description for the other providers.
- Verified live end-to-end: RAL media Lombardia 2021 = **27,285 €** (matches a manual cross-check), `--labels` resolves Italian names. Full test suite green, ruff clean, zero changes to any other provider's path.
- docs: `docs/inps/middleware-api.md` (endpoint reference), `docs/providers.md` + skill `references/providers.md` updated.

## 2026-07-20 - v0.17.0 - search matches the category context

- feat(search): keyword search now also matches the **category name** a dataflow belongs to. ISTAT titles are often leaf labels — `Sesso`, `Età`, `Lazio` — and 1,622 of 4,879 dataflows (33%) share a title with another. `search "disoccupati mensili" --provider istat` went from 2 results to 6, the four new ones being the dataflows that actually hold the data.
- feat(search): results print the category as context (`Disoccupati - dati mensili › Sesso, età`), suppressed when the title already contains it. `info` gained a `Category:` line. `-o json|csv` carry a separate `category` field, so a machine gets the parts and a human the composed line.
- **Not ISTAT-specific.** The context comes from the category cache, and `categories_supported` holds for 9 of 14 providers. Eurostat `search "consumer prices"` went from 33 to 66 results. Providers without categories, and users who never ran `opensdmx tree`, keep the previous behaviour exactly — verified on IMF.
- refactor: `_category_context_for_embed()` moved to `categories.category_context()`, gaining an `include_scheme` flag and a `cat_primary` column. Embeddings keep scheme+category as before; search uses the category alone, since a scheme like "Lavoro e retribuzioni" would match nearly everything under it. New shared `utils.compose_title()`.
- **Rejected on measurement.** The issue proposed deriving a parent title from the ISTAT id pattern `{parent}_DF_{dsd}_{n}`. Measured first: on the 3,460 dataflows having both, the parent title **is** the category name in 51% of cases, and contained in it in another 4% — an ISTAT-specific id parser would have rebuilt data the catalogue already carries and already feeds to the embeddings. The 45% where the parent says something else, typically the vintage, stays uncovered and is documented in #52.
- `--grep` deliberately still applies to title and ID only, so documented recipes return the same rows. `tree` and `siblings` are untouched: both already group by category, so a per-row prefix would be pure duplication.
- test: 4 new cases, including a regression guard that an absent category cache leaves results byte-identical. Suite 276 → 280.
- fix: `str.concat` → `str.join`, silencing a polars DeprecationWarning that the wider use of this code path made frequent.
- Review follow-up: `compose_title` used a substring test, so the category `Age` was silently dropped from the title `Average earnings`; now a casefolded prefix match, pinned by tests. CSV output regained its typed frame — without it `score` was stringified and the column set depended on whether the category cache existed, making the schema a function of local state.
- Filed while planning this: #57 (the embeddings index records neither the model nor the text that built it, so it cannot report staleness) and #58 (the 45% of ISTAT dataflows whose parent title carries a vintage the category does not).

## 2026-07-20 - v0.16.0 - tree: stop dropping flags silently

- **BREAKING** fix(cli): `tree --category X` and `tree --show-dataflows` without `--scheme` now exit 1 instead of silently printing the scheme list with exit 0. The `scheme is None` branch returned before any tree-shaping flag was read, so three flags were accepted and discarded — `--category`'s own help text already claimed "requires --scheme", an intent never enforced.
- feat(cli): `--depth` now acts without `--scheme`. The provider is the root of the tree and the scheme list is level 1, so `--depth N` uniformly means "N levels below the current root" and the special case disappears. `--depth 2` renders one tree per scheme with its top-level categories; ISTAT goes from 45 to 314 lines. `--depth 1` and the no-flag default keep printing the same scheme table — deliberate, since `skills/sdmx-explorer` documents `tree --depth 1` as the entry point of the guided workflow.
- refactor(cli): the ASCII render block moved into `_render_tree_block()` so the no-scheme path reuses it per scheme rather than reimplementing it.
- Rendering shifts with depth: level 1 is the `n_df` table, level 2+ the ASCII tree. Accepted, no row-count warning — whoever types `--depth 3` asked for the big tree.
- test: 5 new cases in `tests/test_cli.py`, including a regression guard that no-scheme `--depth 1` output stays identical to the no-flag output, and a dedicated two-scheme fixture covering the one-tree-per-scheme loop the single-scheme fixture could not reach. Suite 271 → 276.
- docs: `tree` docstring and `skills/sdmx-explorer/SKILL.md` state the root/level model; plan in `tasks/todo-tree-depth.md`.

## 2026-07-18 - v0.15.0 - strict filter matching

- fix(discovery): `set_filters` now treats `-` and `_` as equivalent when matching dimension names, so `--na-item` reaches the `NA_ITEM` dimension. CLI convention is dashes, SDMX ids use underscores; matching was already case-insensitive, this extends the same leniency.
- **BREAKING** fix(discovery): an unknown filter name now raises `ValueError` instead of being dropped with a log line. The old behaviour ran the query unfiltered and put the only signal on stderr — for a tool whose primary consumer reads stdout, that returned wrong data with no indication. Verified: `opensdmx get NAMA_10_GDP --geo IT --na-item B1GQ ...` used to emit 20+ `na_item` values when one was asked for. The error carries a `difflib` suggestion and the available dimension list.
- **Correction to the Phase 2 record.** That refactor claimed `plot` had degraded by not capturing `set_filters` warnings. It had not. `catch_warnings` genuinely appeared in `get`/`run` and not `plot`, but **nothing in the package calls `warnings.warn`** — the messages come from `logger.warning` via logging, independently. Confirmed by running `plot` at the v0.14.1 tag: same output. The claim was verified only in the after state, never the before.
- refactor(cli): removed the dead `catch_warnings` blocks from `_load_and_filter` and `run`. They captured nothing, and Phase 2 had preserved them faithfully rather than deleting them — the opposite of that phase's purpose.
- test: replaced `test_load_and_filter_surfaces_set_filters_warnings`, which passed only because its own mock raised a warning the real code never raises. 5 new tests on dash matching, the raise, the suggestion and the available list. Suite 264 → 268.
- docs: `docs/evaluation-v0.14.0.md` finding 6 carries the correction inline; new finding 20 documents the filter bug.

## 2026-07-18 - Phase 2: remove duplication

- refactor(retrieval, cli): `opensdmx run` reimplemented `retrieval.run_query()` — public API, exported in `__all__` — and the copies had diverged. The CLI honoured `OPENSDMX_PROVIDER` and accepted `--provider`; the library did neither, so the same YAML file behaved differently depending on the caller. `run_query()` gains a `provider` argument and the env fallback; the CLI now calls it. **Behaviour change for library users**: a query file with no `provider` field now respects `OPENSDMX_PROVIDER` instead of silently staying on the default.
- feat(base): `set_provider_from_env()` — resolves `OPENSDMX_PROVIDER` including aliases, so library entry points and the CLI agree. `set_provider()` alone never resolved aliases.
- refactor(cli): extracted `_load_and_filter()` and `_fetch_frame()`. The `load_dataset → set_filters → get_data → enrich_with_labels` pipeline was written three times, and the `plot` copy had already degraded — it did not capture `set_filters` warnings, so a suspicious filter value was reported by `get` and silently ignored by `plot`. Verified: `plot` now surfaces it.
- refactor(cli): extracted `_write_output()`, duplicated between `get` and `run` down to a one-word difference in the error string (`unsupported output format` vs `unsupported format`). `run` now uses the former wording.
- perf(discovery): `parse_bulk_constraints()` builds the tree once. `_extract_bulk_long_ids` and `_parse_bulk_constraint_xml` each called `xml_parse()` on the same bulk contentconstraint bytes — the largest XML the library fetches — for two full tree builds and two namespace scans.
- chore(db_cache): deleted `bulk_constraint_fetch` and `bulk_constraint_index`. Written on every catalog rebuild, never read: their only reader had no callers. The signal travels in the `has_constraint` column of `dataflows.parquet`.
- test: 15 regressions in `tests/test_phase2_dedup.py`. Suite 243 → 258, ruff and mypy strict green, real-CLI smoke on `get --query-file`, `run` and `plot`.

## 2026-07-18 - v0.14.1

- release: patch shipping the four Phase 1 bug fixes below. Most user-visible is `-o csv`, which emitted corrupt CSV whenever a field contained a comma — `which` and `providers` both do. No API change.

## 2026-07-18 - architecture review + Phase 1 bug fixes

- docs: full architecture review in `docs/evaluation-v0.14.0.md` — data flow, 19 findings ranked by severity, refactoring strategy in 4 phases, plus an explicit "verified correct, do not change" list. Plan in `tasks/todo-architecture-review.md`.
- fix(cli): `-o csv` emitted corrupt CSV — `_emit` joined fields with `","` and no quoting, so any description containing a comma split into extra columns (`which`, `providers`). Now delegates to Polars `write_csv()`; `str()` semantics preserved.
- fix(cli): `-o csv` on a nested payload (`info`, `constraints` summary, `siblings`) fell back to JSON silently. Still JSON — there is no faithful flat form — but now says so on stderr. Two deliberate behaviour additions, not restorations: that stderr warning is new (an empty list is exempt — it is empty, not formless), and a present-but-`None` value now renders as an empty cell instead of the literal `None`. stdout is byte-identical to before in every other case.
- fix(cli): the large-dataset guard raised `typer.Exit(1)` inside a `try` whose `except Exception` caught it (`typer.Exit` subclasses `RuntimeError`), appending a spurious `Error: 1` after a correct warning. Handler now re-raises `typer.Exit`.
- fix(cli): that warning said "no filters set" unconditionally, even when filters were passed.
- fix(utils, ai): codelist values are cached under `{codelist_id}:{lang}` but were read with the bare id, so `_get_code_label` and the AI label map returned nothing on every provider — verified against the live cache (zero rows under a bare key). The AI context was listing raw codes with no labels.
- chore(deps): declared `pandas` (imported at `cli.py:1456,1473`, previously resolved only transitively via plotnine); removed `duckdb`, declared since v0.2.6 and never imported.
- test: 14 regressions in `tests/test_phase1_regressions.py`. Suite 229 → 243, ruff and mypy strict green, real-CLI smoke on `search` and `get`.

## 2026-07-17 - v0.14.0

- release: export types to consumers via the `py.typed` marker (PEP 561) and full `mypy --strict` coverage across the package. No runtime or behaviour change.

## 2026-07-17 - mypy strict complete + py.typed

- ci: `cli` converted to strict and the gradual opt-out override removed — `strict = true` now covers all 14 modules with no exemptions. Typer commands get `-> None`, helpers typed (`_status_ctx -> Iterator[None]`, `_filter_by_grep`/`_emit` over `pl.DataFrame`), dicts parametrised.
- plotnine ships `py.typed` but leaves its public API (`aes`, `geom_*`, `theme`) unannotated → dedicated `follow_imports = "skip"` override so its calls aren't flagged; `chatlas` kept typed (used for the `_ai_structured` TypeVar).
- feat: added the `py.typed` marker (PEP 561), verified present in the built wheel — downstream users importing `opensdmx` now get the exported types.
- Verified: mypy strict green (14 files), ruff clean, 229 tests, real CLI smoke (`providers`, `get --output csv`).

## 2026-07-17 - mypy strict (gradual)

- ci: switched `[tool.mypy]` to `strict = true` with a per-module opt-out list so strict is adopted one module at a time. Converted the small/pure modules now — `ai`, `embed`, `which`, `hub`, `retrieval` (plus the already-clean `cache_config`, `guide`, `__init__`) are strict-clean; `categories`, `utils`, `db_cache`, `base`, `discovery`, `cli` stay exempted with the specific strict flags relaxed (tracked TODO in the config comment).
- fix(types): precise generics (`dict[str, Any]`, `list[dict[str, str]]`), missing param/return annotations, and Any-return coercions via typed locals; no new `# type: ignore`.
- `mypy`, `ruff`, and the 229-test suite all green; runtime smoke (`which`, package import) ok.

## 2026-07-17 - mypy type-checking

- ci: added mypy to the dev tooling. `[tool.mypy]` in `pyproject.toml` (pragmatic baseline: default checks + `warn_unused_ignores`/`warn_redundant_casts`), dev deps `mypy`, `types-PyYAML`, `lxml-stubs`, `pandas-stubs`; `uv run mypy` step in `ci.yml` next to ruff.
- fix(types): resolved the real type errors surfaced — `ai._ai_structured` now generic (`TypeVar` bound to `BaseModel`), dropping 11 stale `# type: ignore`; `discovery` dataflow records typed via a `TypedDict` (df_id always `str`); `params`/`ns`/`constraint_timeout` annotations; `which.rank_which` scored list typed.
- `mypy`, `ruff`, and the 229-test suite all green.

## 2026-07-16 - search --grep

- feat(cli): `search` gains `--grep`, the case-insensitive regex post-filter already available on `values` and `constraints`. Closes the gap that forced a shell pipe for whole-word matching (searching `comuni` on ISTAT also matched "comunitari", "comunicazione").
- fix(cli): a malformed `--grep` pattern now reports a readable error instead of raising a regex traceback — applies to `search`, `values` and `constraints` via the shared `_filter_by_grep` helper.
- fix(cli): `search` help said "dataset descriptions"; it matches titles and IDs, and dataflows expose a title (SDMX `Name`), not a description.
- docs: README command table + example, `skills/sdmx-explorer` search step.
- test: 4 regressions covering whole-word filtering, ID matching, invalid pattern, no-match exit.

## 2026-07-16 - incremental constraints archive

- feat(data): public per-provider constraints archive in `data/constraints/` (parquet + status CSV), grown incrementally by `scripts/constraints_archive.py` — budgeted daily probes instead of bulk sweeps.
- ISTAT probed via the databrowser hub bulk endpoint (~1 s/dataflow, no DSD call, outside the 15 s SDMX rate limiter); other providers via `load_dataset()` + `get_available_values()` with built-in pacing.
- Derived view `istat_territorial.csv`: territorial granularity per dataflow (nazionale → comune) classified from ITTER107/REF_AREA codes — answers "which ISTAT datasets have municipal detail?" offline.
- ci: `constraints-archive.yml` daily workflow (istat + eurostat budgets, opensdmx cache restore, commits on change).
- chore: deleted unused bulk scaffolding (`schema_export.py`, `update_istat_schema.py`, `update_all_schemas.py`, `cache_maintenance.py`, `rate_limit_helper.py`, `example_cron.sh`); rewrote `scripts/README.md`.

## 2026-07-16 - PR 48 null coverage fix

- fix(search): OR fallback coverage treats a null description token match as false, preserving coverage from tokens that match the dataset ID.
- test: added a null-description regression to ensure a two-token ID match ranks above a one-token match.

## 2026-07-16 - workflow cleanup

- ci: removed duplicate automatic Claude Code PR review; Greptile and Copilot remain the automatic reviewers.
- ci: Claude on-demand now triggers only from issue and normal PR conversation comments containing `@claude`, avoiding skipped runs for every inline review reply or review submission.

## 2026-07-16 - PR 48 review fixes

- fix(search): treat search tokens as literal text, preventing malformed or broad regular-expression matches from user input.
- fix(search): in OR fallback results, rank datasets by the number of distinct matched tokens before the existing relevance score; repeated occurrences of one token no longer outrank broader matches.
- test: added regression coverage for literal regex characters, helper case normalization, and token-coverage ranking. `224 passed`; ruff clean.

## 2026-07-16 — search: OR fallback fixes AND-only zero-results bug

- fix: `search_dataset()` (`discovery.py`) combined all keyword tokens with AND and returned nothing when a single token was unmatched; now falls back to OR (any token) when AND is empty, so one stray token no longer wipes the result set. Relevance scoring (`_score_results`) keeps full-token matches on top. Extracted `_token_match_expr()` helper.
- test: added AND/OR fallback cases to `tests/test_discovery.py` (mocked catalog, no network). Full suite 221 passed, ruff clean.
- verified on real Eurostat cache: `"unemployment youth aardvark"` went from 0 → 123 results, top hits still the youth-unemployment dataflows.

## 2026-07-15 — Google Doc export

- docs: exported the requested Google Doc to Markdown with `gwsb drive files export`; saved as `tmp/google-doc.md`
- docs: reviewed the ISTAT conference abstract against the local `istat_mcp_server` implementation; drafted a minimally edited 1,109-character revision in `tmp/abstract-revised.md`

## 2026-06-14 — v0.12.1 — SOCKS proxy support (Claude Cowork)

- fix: dependency `httpx>=0.28.1` → `httpx[socks]>=0.28.1`, bundling `socksio`. opensdmx now works out of the box inside sandboxes that route all traffic through a SOCKS proxy (e.g. the Claude Cowork sandbox); previously any network call raised `ImportError`
- docs: README Installation note + `sdmx-explorer` SKILL.md setup note documenting the SOCKS/sandbox case and the one-shot manual patch (`uv pip install ... socksio "httpx[socks]"`) for installs older than 0.12.1
- skill: bumped `sdmx-explorer` to v1.3

## 2026-06-13 — v0.12.0 — codelist hierarchy in cache

- feat: the `codelist_values` cache now stores each code's `code_parent` (`<Parent>` ref) and `code_order` (`ORDER` annotation); populated at parse time, no extra request
- feat: new `get_codelist_hierarchy(ds, dim)` accessor returns `(id, name, parent, order)`, exported from the package; `get_dimension_values` output is unchanged (still `(id, name)`)
- cache: in-place migration adds the two columns to pre-existing `codelist_values` tables (no wipe); `save_codelist_values` now inserts by explicit columns. Note: codelists cached before this upgrade keep null parent/order until re-fetched on TTL expiry — delete `cache.db` to refresh immediately
- cross-provider: providers with flat/unordered codelists (e.g. Eurostat) yield null parent/order; verified ISTAT `CL_ITTER107` (12,471 codes → 12,465 parents, 12,471 orders) and Eurostat geo (4,292 codes, all null)
- test: 4 new tests in `test_codelist_hierarchy.py` (parsing, regression guard, save/read round-trip, in-place migration)

## 2026-06-13 — v0.11.0

- feat: `opensdmx get --labels` appends a `<dim>_label` column with the human-readable name for each dimension code (resolved from the codelist cache, in the provider's language); codes are preserved, label column mirrors the data column case + `_label`. Inspired by rsdmx's `as.data.frame(labels=TRUE)`
- feat: the `--labels` choice is serialized to the YAML query file and honored by `opensdmx run`
- core: new `enrich_with_labels(dataset, data)` helper in `retrieval.py`, exported from the package
- docs: document `--labels` in README and the `sdmx-explorer` skill (SKILL.md, visualization.md Rule 5, duckdb-setup.md)
- test: 5 new tests in `test_labels.py` (enrichment, no-codelist, unmapped→null, query-file round-trip)

## 2026-06-10 — v0.10.4

- fix: SQLite schema is now initialized per DB file path instead of via a single module-level `_DB_INITIALIZED` flag (#42); switching provider (e.g. `eurostat` → `oecd`) no longer crashes with `no such table: invalid_datasets`
- fix: harden the schema guard — key on the resolved absolute path (avoids relative-path/CWD aliasing) and re-create the schema when the DB file did not exist before connecting (covers `cache.db` deleted during a long-lived process)
- test: add `test_schema_init_per_db_path` regression covering the two-provider scenario

## 2026-05-26 — evaluation

- docs: align operational documentation with current code — provider count/list, ISTAT 15s rate limit, 7d/30d cache TTLs, provider-key cache paths, rate-limit lock behavior, and `guide` extra dependency split
- docs: add current project evaluation for v0.10.3 in `docs/evaluation-v0.10.3.md`; verification: `207 passed`, `ruff check src/` passed, full-repo ruff has minor test/script lint issues
- note: strongest next priorities are documentation drift cleanup, dependency slimming, full-repo lint hygiene, and closing stale OpenSpec state

## 2026-05-23 — v0.10.3

- feat: add `which` command — natural-language capability lookup; resolves a query to the best matching command from a curated index; exit code 2 on no confident match (agent-friendly); supports `-o json` for pipeline use
- feat: add ILO (ILOSTAT) and UNICEF portals — ILO uses standard `Accept: text/csv`, UNICEF uses `format=csvdata`; both support lastN and categories; constraints disabled for ILO (endpoint returns 500/413)

## 2026-05-22 — v0.10.1

- fix: patch `_check_api_reachable` in all 9 `test_tree_*` tests — missing mock caused real HTTP requests to ISTAT in CI, where the provider is unreachable, making every tree test fail before the data mock could take effect

## 2026-05-22 — v0.10.0

- feat: add `has_constraint` boolean column to dataflow catalog (`dataflows.parquet`) — populated at catalog-build time via a single bulk `contentconstraint` call for providers that support it (currently ISTAT); `get_available_values()` skips the per-dataflow CC_ call when the catalog confirms no static constraint exists, avoiding repeated 60s+ timeout attempts on large dataflows
- fix: pre-existing key-mismatch bug in bulk constraint parser — `_DF_`-truncation produced short ids (e.g. `41_269`) that didn't match full-form catalog entries (e.g. `41_269_DF_DCIS_INCIDENTISTR1_1`); new `_extract_bulk_long_ids` helper and `_match_catalog_id` resolver handle both catalog id formats correctly
- fix: constraint values for full-form catalog ids now correctly cached under the right key
- chore: document Eurostat bulk CC 405 via `constraint_bulk_supported: false` in `portals.json`

## 2026-05-21 — v0.9.4

- fix: bulk CSV download no longer crashes when REF_AREA contains string codes like `IT` — `infer_schema_length=0` and `null_values=[]` prevent Polars from misinterpreting dimension codes as numeric or null; closes #32
- fix: `"Could not find dataset"` error now names the active provider and suggests `--provider` alternatives; closes #33
- fix: large-dataset warning now explains that `--yes` triggers a single wildcard REST request, not chunked calls; closes #35
- fix: `Saved:` and `Query saved:` messages moved from stdout to stderr for clean pipeline use; partial #34

## 2026-05-14 — v0.9.3

- fix: `opensdmx values` now returns labels in the provider's configured language (was always returning English); closes #31
- fix: codelist cache is now language-aware — same codelist cached separately per language to prevent cross-language contamination

## 2026-05-10 — v0.9.2

- feat: `--provider estat` now accepted as alias for `eurostat` — aliases are declared in `portals.json` under the `"aliases"` field and resolved automatically at CLI startup

## 2026-05-10 — Errata corrige: v0.9.0 / v0.9.1 hub fast path is unreliable for `REF_AREA` on ISTAT

Empirical verification on 2026-05-10 against `esploradati.istat.it` shows that the
"hub fast path" introduced in v0.9.0 does **not** solve the territorial-dimension
discovery problem on ISTAT. The release notes implied a generic fix; the fix is real
only for small coded dimensions.

What was tested (two datasets: `22_289_DF_DCIS_POPRES1_24` "Tutti i comuni per
singola età" — 6 dimensions, and `41_269_DF_DCIS_INCIDENTISTR1_1` "Incidenti
stradali" — 10 dimensions):

- SDMX REST `availableconstraint/{df}` — HTTP 000, 60 s timeout (as documented).
- SDMX REST `contentconstraint/IT1/BL_…` — HTTP 404 in 1.2 s.
- SDMX REST `dataflow/?references=actualconstraint` — HTTP 200 in ~5 s, but `REF_AREA`
  is **absent** from the `CubeRegion` (explicit `<NOT_DISPLAYED title="NOTE_REF_AREA">`
  annotation on the population dataflow; silently absent on the incidents one).
- SDMX REST `dataflow/?references=all&detail=referencepartial` — HTTP 200 in 34 s,
  9.4 MB. The returned `CL_ITTER107` codelist contains 12,471 codes — **identical**
  to the full codelist (`codelist/IT1/CL_ITTER107/?references=none` → 12,471 codes
  too).
- Hub `column/REF_AREA/partial/values` — HTTP 200 in ~6 s, 12,471 codes, response
  body **byte-identical** between the population and incidents datasets
  (1,209,463 B). The `isSelectable: true` and `isDefault: false` flags are uniform
  across all 12,471 codes and carry no discovery information.

Implications:

- For dimensions where ISTAT populates an actual content constraint (FREQ,
  DATA_TYPE, SEX, AGE, MARITAL_STATUS, MONTH, …) the hub fast path remains
  correct: it returns the codes actually used.
- For `REF_AREA` (and likely for any large coded dimension) the hub returns the
  full codelist regardless of which territorial granularity the dataset actually
  exposes. `opensdmx constraints <df> REF_AREA --provider istat` therefore reports
  values that are **not all queryable**, while presenting them as if they were.
- There is currently no documented or undocumented endpoint on ISTAT that returns
  "the territorial codes actually used in dataset X". Discovery must rely on
  out-of-band signals (dataflow naming, category tree) plus a probe
  `GET /data/{key}?lastNObservations=1` at the candidate granularity.

Documentation: `docs/istat/hub-api.md` updated today — caveats added to the bulk
and per-dimension endpoint sections, two new sections added: "Officially
documented SDMX REST constraint endpoints" (`references=actualconstraint`,
`references=all&detail=referencepartial`) and "Critical limitation: REF_AREA
discovery on ISTAT" with the full comparison table.

Follow-ups (not yet done):

- Print a runtime warning from `opensdmx constraints <df> REF_AREA` on ISTAT when
  the response is the full codelist, so users do not mistake it for filtered
  data.
- Open a tracking issue mirroring this errata.
- Consider amending the v0.9.0 release notes on GitHub with a link back to this
  entry.

## 2026-05-10 — v0.9.1: fix(hub): use bulk `columns/partial/values` endpoint for ISTAT discovery

- fix(hub): replace 10 sequential `column/{dim}/partial/values` calls with a single
  `columns/partial/values` (plural) request that returns all dimensions at once (~2 s vs
  10–15 s). Discovered via Playwright network inspection: the Data Browser UI has always
  used the bulk endpoint; opensdmx was using the slower per-dimension variant.
- fix(hub): add `_get_all_dimension_values_via_hub_bulk()` — falls back to sequential
  per-dimension calls only when the bulk response is incomplete.
- test(hub): 7 new tests covering bulk parsing, TIME_PERIOD exclusion, error paths, and
  the bulk-first / sequential-fallback dispatch logic. Suite: 195 tests, all pass.
- docs(istat): `docs/istat/hub-api.md` updated — bulk endpoint documented as preferred
  path, single-dim endpoint moved to fallback section.

## 2026-05-10 — v0.9.0: feat(istat): `.Stat Suite` hub fast path for `get_available_values`

- feat(hub): new `src/opensdmx/hub.py` module wrapping the `.Stat Suite` databrowser hub
  API (`/databrowserhub/api/core/nodes/{node}/datasets/{id}/column/{dim}/partial/values`).
  Per-dimension JSON lookups in ~500 ms, never go through the slow
  `availableconstraint`/`serieskeysonly` cross-join. Reference: `docs/istat/hub-api.md`.
- feat(discovery): `get_available_values()` tries the hub right after the SQLite cache
  and before the existing bulk + availableconstraint + serieskeysonly chain. Hub usage
  is opt-in per provider via `hub_base_url` in `portals.json`; on any hub failure (HTTP
  error, parse error, partial result) the original chain runs unchanged.
- feat(portals): ISTAT gains `hub_base_url`, `hub_node_id`, `hub_dataset_agency`,
  `hub_timeout`. No other provider is touched — Eurostat, OECD, ECB, ABS, BIS, IMF,
  Bundesbank, INSEE, World Bank, Comext, Derzhstat all keep their existing path
  byte-for-byte. `OPENSDMX_DISABLE_HUB=1` opts out at runtime.
- fix(istat): `41_270_DF_DCIS_MORTIFERITISTR1_1` (11 dimensions, ~573 k observations)
  now resolves all dimension values in ~7 s end-to-end. Previously: timeout on
  `availableconstraint` after 30 s, timeout on `serieskeysonly` after 30 s, no usable
  output. Verified live on 2026-05-10.
- test: 21 new tests in `tests/test_hub.py` covering enable/disable, URL/identifier
  build, JSON parsing, error fallback (HTTP error, timeout, malformed JSON, partial
  failure), TIME_PERIOD exclusion, graceful contract for direct calls on non-hub
  providers, and discovery integration on both ISTAT-like and non-hub providers.
  Two existing ISTAT regression tests in `test_http.py` opt out of the hub explicitly
  so they keep guarding the SDMX-REST availableconstraint and bulk contentconstraint
  codepaths. Total: 186 tests pass.

## 2026-05-10 — v0.8.0: feat: split rate limiter for data vs structure requests (issue #2)

- feat(base): `_use_split_rate_limit(is_data)` — returns True only when `is_data=True` and the provider defines `data_rate_limit`. Keeps the unified timer for all providers without that key, preserving identical behavior for ISTAT, Eurostat, Derzhstat, and all others.
- feat(base): `_rate_limit_file` / `_rate_limit_lock_file` / `_rate_limit_check` accept `is_data=False`. When split is active, data calls use `{provider}.data.log` + `{provider}.data.lock`; structure calls keep `{provider}.log` + `{provider}.lock` — fully independent clocks and locks.
- feat(base): `sdmx_request` gains `_is_data=False` kwarg, propagated to the rate-limit machinery inside `_do_request`.
- feat(base): all three data paths in `sdmx_request_csv` pass `_is_data=True` (World Bank JSON, Eurostat SDMX-CSV, generic CSV).
- feat(portals): OECD gains `"data_rate_limit": 60` (1 data download/min, per official OECD docs). Structure calls (search, info, constraints) are unthrottled.
- test: 6 new tests in `TestSplitRateLimit` covering split/no-split detection, lock file naming, and correct lock selection per call type. Updated two existing `_rate_limit_check` mocks to accept the new `is_data` kwarg. Total: 165 tests pass.

## 2026-05-10 — v0.7.1: fix(abs): constraint_params: {} to avoid 500 on availableconstraint

- fix(portals): added `constraint_params: {}` to ABS entry — the server returns 500
  when `references=none` is sent as query parameter (default for all providers);
  omitting all params gives 200 and correct constraint data.
- probe(issue #27): BIS, Derzhstat, IMF already work via `availableconstraint` without
  any portals.json change; the original probe only tested `contentconstraint`, which
  those providers don't implement. ABS was the only broken case.
- Updated `tmp/contentconstraint-probe.md` with current findings.

## 2026-05-09 — v0.7.0: serieskeysonly fallback for constraints timeout

- feat(discovery): `_parse_serieskeys_xml()` parses GenericData `detail=serieskeysonly` responses into `{dim_id: [unique sorted values]}`.
- feat(discovery): `_fallback_serieskeysonly()` sends an all-wildcard data request with `detail=serieskeysonly` when `availableconstraint` times out. Results are cached in SQLite identically to normal constraint data.
- feat(discovery): both `ConstraintsTimeout` catch-points in `get_available_values()` now chain to `_fallback_serieskeysonly` before re-raising — covers both the bulk path and the contentconstraint-404 path.
- feat(cli): updated `ConstraintsTimeout` error message to mention that both fallbacks were attempted.
- test: added `test_parse_serieskeys_xml`, `test_get_available_values_serieskeysonly_fallback`, updated existing timeout test to reflect double-fallback chain. All 159 tests pass.

## 2026-05-09 — ISTAT bulk contentconstraint cache

- feat(discovery): `_fetch_and_cache_bulk_constraints` fetches `contentconstraint/{agency_id}` in one call, parses all 73 constraints (43 unique short df_ids), and populates `available_constraints` for each covered dataflow. Multiple constraints for the same df_id are merged by union per dimension.
- feat(discovery): `get_available_values` now uses a bulk index for providers with `constraint_bulk_supported: true`. For covered df_ids: returns cached bulk data instantly. For uncovered df_ids (~99 % of ISTAT catalog): skips the 404 roundtrip entirely and goes straight to `_fallback_availableconstraint`.
- feat(db_cache): two new SQLite tables — `bulk_constraint_fetch` (records last bulk fetch per agency, TTL 7 days) and `bulk_constraint_index` (set of short df_ids covered per agency).
- feat(portals): added `constraint_bulk_supported: true` to ISTAT entry.
- docs: added P-ISTAT-02 to `docs/provider-proposals.md` — request to extend `contentconstraint` coverage from 43 to all 4,836 ISTAT dataflows.
- Bonus: bulk merge reveals `REF_AREA` (139 regional/provincial codes) for `DCIS_POPRES1` — previously reported as absent. Now cached automatically.

## 2026-05-09 — contentconstraint 404 → availableconstraint fallback

- fix(discovery): `get_available_values` now falls back to `availableconstraint` when `contentconstraint` returns 404. Previously, a 404 was silently swallowed (logged as a warning, returned `{}`), leaving the user with no constraint data and no recovery path. Now: if the provider uses `contentconstraint` and gets 404, `_fallback_availableconstraint` constructs the all-wildcard SDMX key (`N-1` dots for `N` dimensions) and retries against the `availableconstraint` endpoint.
- feat(portals): added `constraint_fallback_timeout: 30` to the ISTAT entry. The fallback uses a shorter 30 s timeout (vs. the normal constraint timeout) to fail fast on datasets where `availableconstraint` is also slow (e.g. large municipal datasets like road accident data). On timeout, `ConstraintsTimeout` is raised — the same exception already handled by the CLI.
- refactor(discovery): extracted `_parse_constraint_xml(content)` helper, reused by both the primary path and the fallback. Eliminates duplicated KeyValue parsing logic.
- test: 3 new unit tests in `tests/test_discovery.py` covering contentconstraint-200, contentconstraint-404→fallback-200, and contentconstraint-404→fallback-timeout — all mocked, no network calls.

Note: the road-accident dataset (`41_270_DF_DCIS_MORTIFERITISTR1_1`) that motivated this fix will still raise `ConstraintsTimeout` on the fallback (its `availableconstraint` endpoint is slow regardless of timeout). For that dataset the only reliable path remains Fallback B: probe GET with a narrow time range + `duckdb DISTINCT REF_AREA` (documented in `skills/sdmx-explorer/references/istat-flow.md`).

## 2026-05-09 (v0.6.7 — issue #24)

- feat(istat): switch ISTAT to `contentconstraint` — `opensdmx constraints` on ISTAT goes from always timing out on large municipal datasets (e.g. `22_289_DF_DCIS_POPRES1_24` ~77 s before timeout) to **sub-second** response. Probed 6 providers (Eurostat baseline + ISTAT + ABS + BIS + IMF + Derzhstat) and only ISTAT gains from the switch in this iteration; the other 4 either return 404/401/204 on `contentconstraint`. Probe details in `tmp/contentconstraint-probe.md`. Removed from the ISTAT entry the obsolete `constraint_path_suffix`, `constraint_params`, `constraint_timeout` and `constraint_max_retries` (those were specific to `availableconstraint`).
- feat(cli): inline hint for dimensions absent from `contentconstraint`. ISTAT's `contentconstraint` does not expose `REF_AREA` (8k+ comuni would inflate the payload). The `constraints` summary table now shows missing dimensions with `–` and a hint pointing at the codelist endpoint:

  ```
  REF_AREA  –  not in contentconstraint — use: opensdmx values 22_289_DF_DCIS_POPRES1_24 REF_AREA
  ```

  In `--output json` mode each dimension entry carries a `source` field (`"constraint"` or `"missing"`) and missing entries include a `hint` field with the exact follow-up command. Single-dim mode (`opensdmx constraints <df> REF_AREA`) emits the same hint instead of a hard error and exits 0.
- docs(skill): rewrite `sdmx-explorer/references/istat-flow.md` for the `contentconstraint` flow (no more 30 s timeout warnings). Update `SKILL.md` constraints section with the missing-dim pattern, `source`/`hint` JSON fields, and a `jq` recipe to list dims that need a `values` follow-up.

## 2026-05-09 (v0.6.6)

- refactor(discovery): per-provider `constraint_timeout` / `constraint_max_retries` in `portals.json` instead of hardcoded values in `discovery.py`. Previously the 30 s + 1-attempt fast-fail was applied to **every** provider with `constraints_supported: true` (Eurostat, ABS, BIS, IMF, Derzhstat), silently disabling the 3-retry policy for transient failures (5xx, NetworkError, TimeoutException) on backends that aren't slow. Now only ISTAT carries the override (`constraint_timeout: 30`, `constraint_max_retries: 1`); all other providers keep the module timeout (300 s) and 3 retries. Precedence: `OPENSDMX_AVAILCONSTRAINT_TIMEOUT` env var > provider config > module default. CLI advisory generalized: gating on `provider.constraint_timeout` instead of `agency_id == "IT1"`.
- feat(discovery): dedicated short timeout for the `availableconstraint` endpoint, configurable via `OPENSDMX_AVAILCONSTRAINT_TIMEOUT`. When the provider's availability backend is slow or unresponsive (documented case: ISTAT, TTFB > 180 s with zero bytes received), `opensdmx constraints` / `values` now fail fast instead of waiting up to 3 × 300 s on the global timeout. New `ConstraintsTimeout` exception parallel to `ConstraintsUnavailable`, exported from the package root. CLI prints a yellow advisory with the exact env var override.
- feat(http): `sdmx_request` / `sdmx_request_xml` accept optional `_timeout` and `_max_retries` keyword overrides for per-call control of the HTTP timeout and retry attempts.
- ux: ISTAT pre-warning before the first uncached constraints call now reflects the actual per-call timeout and the no-retry behavior (was a stale "30–120 s" estimate inherited from the old global-timeout regime).
- docs: add `docs/provider-proposals.md` — empirically verified provider-side issues (P-ISTAT-01: `availableconstraint` key filter accepted but ignored, `contentconstraint` available at 0.66 s; see issue #24).
- docs(skill): update `sdmx-explorer/references/istat-flow.md` — expand Step 3 with timeout behavior, `OPENSDMX_AVAILCONSTRAINT_TIMEOUT` env var, empirical findings on key filter, and concrete fallback flow for municipal-level datasets.

## 2026-05-08 (v0.6.5)

- fix(http): retry only on transient failures in `sdmx_request` — the previous `@retry` decorator had no `retry=` predicate, so tenacity retried on **any** exception, including `httpx.HTTPStatusError` for 4xx codes. On rate-limit-by-IP providers (e.g. ISTAT) this could turn a single 429 into three back-to-back hits and amplify the risk of a multi-day ban. Now retries are restricted to `httpx.TimeoutException`, `httpx.NetworkError`, `httpx.RemoteProtocolError`, and 5xx server errors (excluding 501 Not Implemented). Predicate exposed as `_is_retryable_exception` for testing.

## 2026-05-03 (v0.6.4)

- ux: `constraints` summary table now shows a tip to use `--output json` for the full list of values

## 2026-05-03 (v0.6.3)

- fix: force `OBS_VALUE` to `pl.Float64` in CSV parsing — Polars inferred `i64` from the first 10 000 rows and crashed on the first float value past the inference window (reported on Derzhstat `DF_POPULATION_BIRTH`)
- fix: apply dimension filters client-side for portals with `data_key_format: "empty"` (e.g. Derzhstat) — previously `--DIM VALUE` flags were silently ignored, causing full-dataset downloads instead of filtered results
- fix: force UTF-8 on stdout/stderr on Windows (`sys.platform == "win32"`) to prevent `UnicodeEncodeError` in PowerShell/cmd when Rich tables emit non-ASCII characters (Cyrillic labels, box-drawing)
- fix(portals): update Derzhstat description — wildcard dots in key-filter path return 404; dimension filters are now applied client-side after download

## 2026-05-01

- feat: add `--header "Name: Value"` option (repeatable) to `get`, `constraints`, `values`, `info`, `tree` commands — allows passing custom HTTP headers per invocation (e.g. API keys required in headers, not query string)
- feat: expose `set_extra_headers()` / `get_extra_headers()` in Python public API (`opensdmx.base`, re-exported from `opensdmx`)
- Extra headers merge over defaults; `User-Agent` is protected and cannot be overridden via `--header`

## 2026-04-29 (v0.6.1)

- fix: always parse `OBS_FLAG`, `OBS_STATUS`, `CONF_STATUS` as strings in CSV responses — Polars was inferring these SDMX observation attribute columns as `i64`, crashing when a provider returned flag codes such as `c` (confidential); confirmed on Derzhstat `DF_SALARY_PAYMENT_STATUS`

## 2026-04-29 (v0.6.0 — Nadiia)

- feat: add `OPENSDMX_USER_AGENT` env var to override the HTTP `User-Agent` header globally
- feat: add `user_agent` field to portal entries in `portals.json` — per-portal default User-Agent
- feat: add `data_key_format` field to portal entries (`"dots"` default | `"empty"`) — controls whether the SDMX dimension key segment is appended to data URLs; providers that reject the dot notation (e.g. Derzhstat) use `"empty"`
- feat: add `derzhstat` preset portal (State Statistics Service of Ukraine, agency SSSU) — 112+ dataflows including consumer prices and wages, accessible without authentication

> Named after [Nadiia Babynska-Virna](https://www.linkedin.com/posts/nadiia-babynska-virna_opendata-localai-sdmx-ugcPost-7455051404538347520-MB39), whose work on building a local MCP server for Ukrainian statistics identified these blockers and inspired this release.

## 2026-04-20 (v0.5.1)

- fix(tree): `opensdmx tree` no longer downloads the full dataflow catalog
  during the stale-categorisation warning path on first run; the warning now
  uses cached dataflows only, so `Loading category tree...` does not stay
  active for unrelated network work
- docs: add an explicit subrelease section to `docs/release.md`
- tests: add regression coverage to ensure `load_categories()` does not call
  `all_available()` when no dataflow cache is present

## 2026-04-20 (tree-first phase 3B.1 — Category.description)

- feat: parse `Category.description` alongside `Category.name` and expose
  it as `cat_description` in both the cache schema and `--output json|csv`
- feat: ASCII tree appends the description dimmed+italic after the cat_id
  marker when populated — helps disambiguate opaque cat_ids when the
  provider fills the field
- note: ISTAT populates `Description` on ~1/1200 categories; Eurostat and
  OECD usage varies by scheme. For categories without `Description`,
  rendering is unchanged
- cache: the loader invalidates caches missing the new `cat_description`
  column, forcing a fresh fetch on first use after upgrade
- tests: 1 new pytest; 21/21 passing

## 2026-04-20 (tree-first phase 3A)

- feat: `opensdmx tree --show-dataflows` (alias `-l`) inlines dataflow
  leaves under each category in the ASCII rendering, labelled `[df:ID]`.
  Uses `all_available()` for dataflow descriptions — all data come from
  cache, no extra HTTP fetch. Stderr warning if output exceeds 200 dfs.
- feat: the flag shortcuts the `tree --category X` + `search "" --category X`
  sequence when the user has picked a terminal branch — one command
  instead of two. JSON/CSV outputs remain categories-only (warning to
  stderr if `--show-dataflows` is combined with `--output json/csv`).
- skill: documents the shortcut and advises against using it on broad
  branches where it floods the output
- tests: 2 new pytest cases (df leaf rendering + regression safety);
  20/20 passing

## 2026-04-20 (tree-first phase 2)

- feat: ASCII `tree` rendering now prefixes category IDs as `[cat:ID]`
  (instead of `[ID]`) to disambiguate them from dataflow IDs
- feat: `tree --category` error messages label dataflow IDs as `[df:ID]`
  and category IDs as `[cat:ID]`, so the kind travels with the identifier
  when copied between terminals
- skill: `sdmx-explorer` documents the `[cat:]`/`[df:]` convention
- tests: 1 new pytest verifies the `[cat:...]` prefix in ASCII output;
  existing tests unchanged (18/18 passing)
- CSV/JSON outputs unchanged — raw `cat_id`/`df_id` columns preserved;
  the prefix lives only in ASCII rendering and error messages

## 2026-04-20 (tree-first phase 1)

- fix: `opensdmx tree --category` now resolves categories by `cat_path` (previously only matched root-level cat_ids whose `cat_id == cat_path`; nested categories silently returned an empty subtree)
- fix: `--depth` is relative to `--category` when set — `--depth 1` always means "node + direct children", fixing the `OutOfBoundsError` crash when the chosen category sat deeper than the absolute depth limit
- fix: passing a dataflow ID to `--category` now yields a clear message ("is a dataflow, not a category") with suggested `info`, `search --category`, and `tree --category` commands using the parent category. When the dataflow is categorised only under a different scheme, the hint surfaces the scheme mismatch instead of pointing at an unrelated cat_id.
- fix: `[cat_id]` labels in tree rendering now survive Rich markup — escaping the opening bracket makes them visible on Eurostat (where cat_ids like `t_bop_6` were previously consumed as style tags)
- fix: empty subtree guard prints a descriptive message instead of crashing at `.row(0)` on an empty polars frame
- skill: `sdmx-explorer` promotes `tree` as primary discovery path (Step 1b); keyword `search` demoted to Step 1c fallback; new hierarchical drill-down protocol mandates `--depth 1` at every level to avoid dumping large trees; new "cat_id vs df_id" guidance
- tests: 4 new pytest cases on `tree` error paths and relative-depth semantics

## 2026-04-20 (v0.4.4)

- fix: semantic search now uses `search_document:` / `search_query:` prefixes required by `nomic-embed-text-v2-moe` (without prefixes the model returned essentially random rankings on short queries)
- feat: embedding text now includes `df_id` and (when the category cache is populated) the dataflow's scheme/category names — dramatically improves recall on short titles (e.g. `Prezzi al consumo` → `CPI Prezzi al consumo Prezzi`)
- docs: README documents richer embeddings via `opensdmx tree` and adds tips on writing better semantic queries

## 2026-04-20 (v0.4.3)

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
