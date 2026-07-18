# Architecture review — v0.14.0

Independent review of the whole package: reverse-engineered data flow, then a search for bad architecture decisions, duplicate logic, performance bottlenecks, scalability risks and maintainability issues.

Baseline at review time: ruff clean, `mypy --strict` green on 14 modules, 229 tests passing in 9.3 s. Every finding below was verified against the running code — several were reproduced empirically, and the ones that turned out to be false alarms are listed explicitly at the end.

---

## Verdict

The codebase is in good structural health. 5.483 lines of source against 3.333 lines of tests, strict typing with no exemptions, CI running lint + types + tests, and a documented design philosophy that is actually followed in the code. This is not a legacy rescue.

What the review found instead is a specific and consistent pattern: **the core library is sound, and the defects cluster at the edges** — the CLI presentation layer, the packaging metadata, and three places where a second implementation of an existing behaviour was written by hand instead of calling the first one. Two of those edge defects are user-visible bugs that ship today.

---

## Clean architecture breakdown

### Layers, as actually built

```
cli.py (1666)          presentation — Typer commands, rendering, exit codes
   |
   +-- __init__.py     public façade — 25 re-exported names
   |
   +-- discovery.py (960)   catalog, structure parsing, filters, constraint resolution
   |   retrieval.py (228)   data fetch, TIME_PERIOD conversion, label enrichment
   |   categories.py (361)  category tree
   |   which.py (99)        command routing hints
   |   embed.py (214)       semantic search
   |   ai.py (365) + guide.py (396)   optional LLM-guided session
   |
   +-- base.py (439)        transport — provider registry, HTTP, rate limit, retry
   |   hub.py (211)         ISTAT databrowser fast path        <-- BYPASSES base.py
   |
   +-- db_cache.py (311)    SQLite cache
       cache_config.py (25) TTL constants
       utils.py (152)       XML helpers, SDMX key builder
```

The layering is clean with **one documented exception and one undocumented one**. The documented exception is that the CLI reaches past the façade into `discovery`/`db_cache`/`categories` for symbols the façade does not export — a gap in the public API rather than an abuse. The undocumented exception is `hub.py`, covered below.

### The cache design is correct and should not be redesigned

Two layers, and the split follows a consistent rule:

- **Parquet** for whatever is read *in full* every time — catalog, category tree, embeddings. Columnar, whole-table scan, TTL by file mtime.
- **SQLite** for keyed point lookups with independent per-row TTL — dimensions, codelists, constraints, blacklist.

That is the right split for this workload. Measured: catalog read 5,8 ms warm, `get_cached_dims()` 0,75 ms, SQLite connect+PRAGMA+close 0,29 ms. Largest table observed is 40.456 rows / 7,6 MB — three to four orders of magnitude below where SQLite starts to care.

Every hot query already filters on a **prefix of its table's primary key**, so all of them use the autoindex and are O(log n). There is no missing index. Do not add one.

### Where the time actually goes

The dominant cost is network round-trips and rate-limit sleeps; everything local is noise.

| Path | Cost |
|---|---|
| Cold `get` on ISTAT (4 serialized calls, `rate_limit=15 s`) | **~60 s of pure sleeping** before the first byte of data |
| Same path on Eurostat (`rate_limit=0.5 s`) | ~2 s |
| Warm `search` end to end | 0,50 s — of which 282 ms is interpreter + imports |
| Cosine similarity, 9.000 × 768 | < 10 ms |

Two conclusions follow. First, the cache layers are doing exactly the job they exist to do, and the measured warm path is dominated by the fixed import floor, not by any cache operation. Second, **brute-force similarity search is the correct choice at this corpus size** — an ANN index would add a dependency, a build step and an invalidation problem to save single-digit milliseconds. The real latency in `semantic_search` is the Ollama round-trip, not the maths.

---

## Critical problem areas

### Tier 1 — user-visible bugs, verified by reproduction

**1. `-o csv` emits corrupt CSV.** `cli.py:90-95`

When `_emit` receives a list of dicts without a Polars frame, it serializes by hand with `",".join(str(...))` — no quoting, no escaping. Any field containing a comma breaks the row.

```
$ opensdmx -o csv which "plot"
command,score,description,group                                    <- 4 fields
plot,5,Visualize a time series as a line, bar, barh, point, ...    <- 8 fields
```

Affects `providers` and `which`. Polars is already imported in this module; the manual serialization is avoidable in its entirety.

**2. `typer.Exit(1)` swallowed, printing a spurious `Error: 1`.** `cli.py:1182`

The large-dataset guard raises `typer.Exit(1)` inside the `try` opened at line 1156, whose `except Exception` at 1198 catches it — `typer.Exit` inherits from `RuntimeError`. The exit code survives, but the user sees a garbage `Error: 1` line appended to a correct warning. For a CLI whose primary consumer is an LLM reading stdout, that is a false error signal.

An AST scan of all 51 `raise typer.Exit` sites confirms **1182 is the only one** caught by a broad handler. The defect is isolated, not systemic.

**3. Codelist cache is written under one key and read under another.** `utils.py:77`, `ai.py:79`

- Written as `f"{codelist_id}:{lang}"` — `discovery.py:564`, the only writer.
- Read as bare `codelist_id` — `utils.py:77` and `ai.py:79`.

Verified against the live cache: every stored key carries the suffix, and there are **zero rows without it**. Both lookups therefore return `None` unconditionally, always, on every provider.

Consequence: `ai.py:81` never builds its label map, so the context handed to the AI lists raw codes with no human-readable names — a silent regression in the one feature that most depends on them. No error, no failing test. `discovery.py:543` reads with the correct key, which is why this was never noticed.

Blast radius is narrow — the AI path is behind the optional `[guide]` extra, and `utils._get_code_label` only feeds the `description` field of saved YAML query files — which is why this is rated below the two CLI bugs despite being unconditional. Note the fix is two lines, not one: `get_provider` is not in scope in `utils.py` and needs a lazy import alongside the existing one.

This also explains a stale claim in `docs/cache.md`: the ER diagram declares a foreign key from `codelist_info` to `codelist_values`, and that join can never match (`AGE` vs `AGE:en`).

### Tier 2 — architectural

**4. `hub.py` bypasses the entire transport layer.** `hub.py:92`

`_hub_get_json` builds its own `httpx.Client` instead of going through `base.sdmx_request`. It therefore has **no portalocker rate-limit lock, no timestamp write, no tenacity retry, and no `_extra_headers`** — while duplicating the one thing it did copy, User-Agent resolution. Worse, `hub.py:200-211` falls back to a sequential loop firing N unthrottled GETs.

This project documents ISTAT as banning IPs for 1-2 days on rate-limit violations. This is the single code path that can burst requests at ISTAT with zero throttling.

**The ban-scope question resolves against us.** `portals.json` puts both endpoints on the *same host*: SDMX at `https://esploradati.istat.it/SDMXWS/rest`, hub at `https://esploradati.istat.it/databrowserhub/api/core`. A per-IP block at that host applies to both paths, so an unthrottled hub loop can plausibly trigger the ban that the SDMX limiter exists to prevent.

**Severity revised down to Medium after review.** This finding was first rated High on the assumption that the daily constraints-archive job is production. It is not — that job is an experiment, outside the main product. That matters because the two consumers of the hub have very different burst profiles:

| Consumer | Requests | Frequency |
|---|---|---|
| Product (`constraints`, `values` on ISTAT, via `discovery.py:849`) | 1 bulk call, or 5-10 in the per-dimension fallback | one per user command, interactive |
| `scripts/constraints_archive.py` | the same, **× thousands of dataflows** | daily, in a loop |

The ban risk lives almost entirely in the second, and the second is a test. What remains in the *product* path is narrower but still real: no tenacity retry, so a transient hub failure surfaces as a user-visible error instead of being retried; no `_extra_headers`, so `--header` never reaches the hub; and the per-dimension fallback at `hub.py:200-211` fires 5-10 unpaced requests.

**The obvious fix is still wrong, for a better reason.** Routing `_hub_get_json` through `base.sdmx_request` would impose ISTAT's 15 s SDMX rate limit on the hub. The original argument against this was that it would make the archive job 15× slower — which carries little weight once the archive is understood as an experiment. The argument that does hold is about the product: it would add 15 s to every interactive `opensdmx constraints` on ISTAT, turning a ~1 s response into a ~16 s one. That is a genuine product regression, and it stands independently of the archive. Mechanically it may not even fit — `sdmx_request` composes SDMX-REST paths against `base_url`, and the hub uses a different path root. Note also that `scripts/constraints_archive.py:48` imports `_hub_get_json` directly, so any signature change touches the CI job.

The correct shape is to **share the transport hygiene without sharing the rate-limit policy**: give the hub tenacity retry, `_extra_headers` and consistent timeout handling. Pacing is worth adding for the loop case, but it is no longer urgent, and it should be calibrated from measurement rather than reasoning — the current evidence is only "nothing has gone wrong yet", which is absence of proof, not proof of safety.

**5. `run` reimplements `retrieval.run_query()`, and they have already diverged.** `cli.py:1244-1305` vs `retrieval.py:154-199`

`run_query` is exported in `__all__`. The CLI command does not call it. The two copies differ already:

| | CLI `run` | `retrieval.run_query` |
|---|---|---|
| `--provider` override | yes | absent |
| `OPENSDMX_PROVIDER` fallback | yes | **absent** — silently stays on eurostat |
| captures `set_filters` warnings | yes | no |

Two implementations of one behaviour, already out of sync, with the library version being the weaker one — that is the version a downstream importer gets.

**6. The same fetch block is written three times, and the third copy is degraded.** `cli.py:1156-1192`, `1282-1299`, `1416-1421`

`load_dataset → set_filters → get_data → enrich_with_labels` appears in `get`, `run` and `plot`. The `plot` copy does **not** capture `set_filters` warnings, so a suspicious filter value is reported by `get` and silently ignored by `plot`. The output-writing block is likewise duplicated between `get` and `run`, where the error strings differ by one word (`unsupported output format` vs `unsupported format`) — evidence of hand-copying.

**7. Packaging metadata is wrong in two directions.** `pyproject.toml`

- **`duckdb` is declared and never imported.** Zero occurrences across `src/`, `tests/`, `scripts/`. Flagged in three previous evaluations and still shipping.
- **`pandas` is imported directly and never declared.** `cli.py:1456` and `cli.py:1473` import it; only `pandas-stubs` (dev) appears in the manifest. It resolves today purely because `plotnine` depends on it.

These are the same problem seen from two sides, and they must be fixed together: moving `plotnine` to an optional extra without also declaring and moving `pandas` breaks `opensdmx plot` with an `ImportError`.

**8. Health check is inert, and points at the wrong provider.** `cli.py:157-171`, `191`

`_check_api_reachable` returns early if the rate-limit log file exists (`cli.py:159`, importing the private `base._rate_limit_file`). That file is written on every request and never deleted — so after the first successful call to any provider, the guard short-circuits forever. It protects a virgin install and nothing else.

Underneath that, a latent ordering bug: `_startup` calls the probe at line 191, but `_apply_provider` runs *inside* each command, afterwards. Since `base.py` never reads `OPENSDMX_PROVIDER`, `_active_provider` is still the `"eurostat"` default when the probe fires. On a cold cache, `opensdmx search X --provider istat` probes **Eurostat**. Finding 8a masks 8b on any machine that has run the tool once, which is why this has not surfaced.

### Tier 3 — correctness risks that have not fired yet

**9. Two savers can produce a permanent cache miss.** `db_cache.py:133`, `196`, gate at `174-184`

`save_dims` and `save_codelist_values` use bare `INSERT OR REPLACE` with no prior `DELETE`, unlike the correct `save_available_constraints` at `db_cache.py:236`. When an upstream codelist *shrinks*, orphan rows persist with their original `cached_at` — and the freshness gate tests an **arbitrary** row (`ORDER BY code_id`, then `rows[0]`). If a stale orphan sorts first, that codelist reads as expired forever, triggering a refetch and a 15 s ISTAT sleep on every single invocation, undiagnosable short of deleting `cache.db`. Two-line fix, or change the gate to `MIN(cached_at)`.

**10. `_struct_path` applied inconsistently.** `discovery.py:547` vs `363`

Codelist *descriptions* get the provider's `metadata_prefix`; codelist *values* hardcode the path without it. Bundesbank configures `metadata_prefix: "metadata"`, so `values` and `--labels` are expected to 404 there. The inconsistency is certain from the code; the resulting failure was not confirmed against the live endpoint.

**11. Rate-limit lock is held across the whole HTTP call.** `base.py:320`

Correct for the send-to-send semantics it implements, but it means a multi-minute download **blocks every other opensdmx process on that provider for its full duration**, with no feedback — the countdown at `base.py:246-259` only runs after the lock is acquired. On ISTAT there is no data/structure split, so a large `get` stalls any concurrent `search`. The timestamp is already written *before* the request, so narrowing the lock to the timestamp check/write would work.

**12. `get` pays an extra rate-limited round-trip it does not need.** `cli.py:1171`

The size probe is gated on `last_n`/`first_n`/`yes` but not on whether filters are set. A fully-specified single-cell ISTAT query still pays ~15 s for a probe whose answer is already known.

### Tier 4 — maintainability

**13. Dead code: two SQLite tables written and never read.** `db_cache.py:275-311`

`get_df_ids_with_content_constraint` and `is_bulk_constraint_fresh` form a closed loop — the second is called only by the first, and the first is called by nobody. The signal they would serve, `has_constraint`, already travels in the `dataflows.parquet` column, and that is what `discovery.py:862` actually reads. Two tables, three functions, and a `docs/cache.md` entry describing them as load-bearing.

**14. The two largest commands have no tests.** `cli.py:1123` `get` (104 lines), `cli.py:1324` `plot` (241 lines)

`test_cli.py` covers `search`, `constraints`, `tree`, `which` and the helpers, but never invokes `get` or `plot`. The retrieval layer beneath `get` is well covered, so the network path is safe; what is unprotected is the CLI wrapper — output format selection, `--labels`, `--out`, the large-dataset branch. `plot` is the largest untested function in the package and the sole consumer of the plotnine/pandas stack. `embed.py` is public API with no test file at all.

**15. Silent option-dropping in `search --semantic`.** `cli.py:232-265`

The semantic branch returns at line 265; the category filter and all pagination live after it. `--category`, `--page` and `--all` are accepted and ignored with no warning. Notably, `tree --show-dataflows` handles the analogous case correctly by warning explicitly at `cli.py:967-970` — the pattern to copy is already in the file.

**16. Contradictory exit codes for the same situation.** `cli.py:462` vs `299`

`values` with no results exits **1**; `search` with no results exits **0**. An agent using exit codes to decide whether to retry gets opposite signals for the same semantic outcome. (`which`'s exit 2 is documented and intentional — not an inconsistency.)

**17. Duplicated XML parse of the largest document fetched.** `discovery.py:154-155`

`_extract_bulk_long_ids` and `_parse_bulk_constraint_xml` each call `xml_parse()` on the same bulk contentconstraint bytes — two full tree builds plus two full-tree namespace scans. Trivially merged into one pass.

**18. Eager numpy costs 45 ms on every invocation.** `__init__.py:26` → `embed.py:8`

Measured: 282 ms import, 238 ms with numpy stubbed. Paid by `--help`, `get` and `search`, none of which touch numpy. The module already uses lazy imports for `ollama`; applying the same to numpy recovers 16% of import time. The remaining ~240 ms is polars, httpx, rich and typer — genuinely needed.

**19. `docs/architecture.md` is stale.** Module map omits `hub.py`, `categories.py`, `guide.py`, `which.py`, `cache_config.py` — 1.092 lines, roughly 20% of the package, including the distinctive ISTAT hub path. It also contradicts itself on the cache directory: `~/.cache/opensdmx/eurostat/` in one section, `{agency_id}` in another. The code (`base.py:156`) uses the **preset name** for preset providers and `agency_id` only for custom ones, so the second statement is wrong.

---

## Refactoring strategy

Sequenced so that each phase is independently shippable and leaves the suite green.

### Phase 1 — ship the bug fixes (small, high value)

1. `_emit` CSV: build a Polars frame from the list of dicts and call `write_csv()`, deleting the manual serializer (`cli.py:90-95`). Fixes finding 1 and finding 3-of-Tier-1's sibling — `-o csv` silently returning JSON — in the same edit.
2. Move `raise typer.Exit(1)` outside the `try`, or re-raise it in the handler (`cli.py:1182`).
3. Pass `f"{codelist_id}:{lang}"` at `utils.py:77` and `ai.py:79`, matching the writer.
4. Declare `pandas`; remove `duckdb`.

Each is a handful of lines. Together they close every Tier-1 finding.

Finding 4 (hub) is **not** in this phase: it touches a script the CI depends on, and its pacing half wants measurement rather than reasoning, so it gets its own change rather than riding along with one-liners. After the severity revision it is also no longer the most urgent item — see Phase 2.

### Phase 2 — delete duplication

6. `run` calls `retrieval.run_query()`; port the three CLI-only behaviours into the library function first, so the façade version becomes the strong one.
7. Extract the shared fetch pipeline and the output-writing block used by `get`/`run`/`plot` into two private helpers.
8. Delete `bulk_constraint_index` / `bulk_constraint_fetch` and their three accessors; drop the tables from `docs/cache.md`.
9. Merge the double XML parse into a single pass, extracting the 42-line block out of `all_available` — which drops that function below 80 lines as a side effect.

### Phase 3 — packaging and correctness hardening

10. Restructure extras: core keeps `httpx`, `lxml`, `polars`, `pyyaml`, `rich`, `tenacity`, `typer`, `platformdirs`, `portalocker`; `[plot]` takes `plotnine` + `pandas` + `pyarrow`; `[semantic]` takes `ollama` + `numpy`; `[guide]` unchanged. Each lazy import gets a friendly "install `opensdmx[plot]`" message — the pattern already exists at `cli.py:1640`.
11. Lazy `main` / `build_embeddings` / `semantic_search` via module-level `__getattr__` in `__init__.py`; the `[project.scripts]` entry point keeps working through it.
12. `DELETE` before `INSERT OR REPLACE` in `save_dims` and `save_codelist_values`; or `MIN(cached_at)` in the gate.
13. `_struct_path` at `discovery.py:547`.
14. Gate the size probe on "no filters set" (`cli.py:1171`).

### Phase 4 — tests and docs

15. Tests for CLI `get` and `plot`; tests for the non-Ollama parts of `embed.py`.
16. Align exit codes for "no results"; add a warning for the options `--semantic` drops.
17. Update `docs/architecture.md` (5 missing modules, cache-dir contradiction) and `docs/cache.md` (false FK, missing columns).

### Deliberately not doing

Narrowing the rate-limit lock (finding 11) is left out. It is a real limitation, but the current behaviour is conservative in exactly the direction that protects against IP bans, and the project's own guidance is that numeric choices here come from empirical measurement rather than reasoning. It deserves its own measured change, not a drive-by.

---

## Verified as correct — do not change

These were examined and found sound. Several look like problems at first glance.

- **`print()` and direct output.** Intentional and documented — the CLI speaks to an LLM orchestrating it.
- **The parquet/SQLite split.** Motivated, consistent, correct for the workload.
- **SQLite indexing.** Every hot query is already O(log n) on a PK-prefix autoindex. `journal_mode=DELETE` is right without in-process parallelism.
- **Brute-force cosine similarity.** Correct at 9k documents; an ANN index would be a regression in complexity for no measurable gain.
- **Connection-per-call in `_db_conn`.** 0,29 ms against second-scale network calls.
- **`base.py:268-283` `_is_retryable_exception`.** Never retries 4xx, with a 501 carve-out from 5xx. For IP-ban providers this is the difference between a transient error and a multi-day block.
- **`base.py:320`** holding the lock across the whole call *for correctness of the cross-process limit* — see finding 11 for the cost, but the reasoning in the comment is right.
- **`base.py:324-325`** timestamp written at request start, making the interval send-to-send.
- **`discovery.py:940-957`** `copy.deepcopy` in `set_filters`/`reset_filters` — genuinely immutable dataset dicts.
- **`discovery.py:243-271`** `search_dataset` AND→OR fallback with coverage-prioritized scoring.
- **`_parse_extra_filters`** is properly centralized and reused by both `get` and `plot` — a suspected duplication that is not one.
- **`tree`'s 48 lines of disambiguation messages.** For an LLM-facing CLI this is value, not bloat.
- **Lazy imports of `ollama`, `plotnine`, `matplotlib`, `pandas`.** Verified absent from the startup trace.
- **`scripts/constraints_archive.py`.** Genuinely reuses the library and reimplements nothing; its one private-API import is documented with its rationale.

---

## Findings by severity

| # | Location | Finding | Severity |
|---|---|---|---|
| 1 | `cli.py:90-95` | `-o csv` emits corrupt CSV (no quoting) | **High** |
| 2 | `cli.py:1182` | `typer.Exit` swallowed → spurious `Error: 1` | **High** |
| 3 | `utils.py:77`, `ai.py:79` | Codelist cache read with wrong key — always misses | Medium-high (unconditional, narrow surface) |
| 4 | `hub.py:92` | Bypasses transport: no retry, no `_extra_headers`, no pacing, same host as the rate-limited SDMX endpoint | Medium (was High — the burst-at-scale consumer is an experiment, not the product) |
| 5 | `cli.py:1244-1305` | `run` duplicates `run_query()`, already diverged | Medium-high |
| 6 | `cli.py:1416-1421` | Third fetch copy in `plot` drops filter warnings | Medium |
| 7 | `pyproject.toml` | `pandas` undeclared; `duckdb` orphan | Medium-high |
| 8 | `cli.py:157-191` | Health check inert, and probes the wrong provider | Medium |
| 9 | `db_cache.py:133,196` | Missing DELETE → possible permanent cache miss | Medium-low |
| 10 | `discovery.py:547` | `_struct_path` inconsistency breaks Bundesbank | Medium |
| 11 | `base.py:320` | Lock held across whole download, blocks other processes | Medium |
| 12 | `cli.py:1171` | Size probe not gated on filters (~15 s wasted on ISTAT) | Medium |
| 13 | `db_cache.py:275-311` | Two tables written, never read | Medium (dead weight) |
| 14 | `cli.py:1123,1324` | `get` and `plot` untested; `embed.py` untested | Medium |
| 15 | `cli.py:232-265` | `--semantic` silently drops three options | Medium |
| 16 | `cli.py:462` vs `299` | Exit 1 vs 0 for "no results" | Medium |
| 17 | `discovery.py:154-155` | Largest XML parsed twice | Medium |
| 18 | `__init__.py:26` | Eager numpy costs 45 ms per invocation | Low-medium |
| 19 | `docs/architecture.md` | 5 modules missing; cache-dir self-contradiction | Low |
