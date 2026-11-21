# Critic Review: Scoped provider for library use

Stage 7 of the EGM review of `docs/design-provider-context.md`, FeatureRange lines 1-127. Round 1. Reviewers, each in a fresh context, all completed: `egm-design` and `egm-structural` (standard `feature-spec-standard.md`), `egm-style` (persona only). Goldfish context: `src/opensdmx/base.py`, `discovery.py`, `retrieval.py`, `__init__.py`, `docs/architecture.md`.

## Contents

- Verdict
- Blockers
- Major findings
- Nits
- Cross-stage map
- Citations the reviewers could not verify

## Verdict

The spec fails the feature-spec standard as written: no alternatives section, no risks section, and a compatibility claim the code contradicts. Round 1 is not clean (3 Blockers, 13 Majors after deduplication).

## Blockers

| ID | Reviewers | Lines | Finding | Resolution |
|---|---|---|---|---|
| design-1-1, structural-1-1 | design, structural | 1-127 | No "Alternatives considered". Candidates a reader expects: explicit `provider=` on every function; a client or session object (`Client("istat").load_dataset(...)`); `threading.local`; a ContextVar replacing `_active_provider` (rejected by A4); only `ds["provider"]` without `use_provider`. | Add the section with a concrete rejection reason for each. |
| design-1-2 | design | 26, 83, 120 | Cache dir, `cache.db` and rate-limit key do not follow `get_provider()`: `_provider_cache_key()` and `utils.py:175-181` read `_active_provider` directly. Under a scope: cache written into the default provider's files, rate-limit lock shared across providers. Same as Stage 5 Z1. | Single accessor; inventory of every direct reader; tests on cache dir and lock path inside a scope and inside a ds-scoped call. |
| structural-1-2 (Major), design-1-7 (Major) | structural, design | 1-127 | No "Risks and mitigations". Promoted here because the standard requires it and two reviewers raise it. Missing risks: same-provider threads are strictly serial (lock held for the whole call, 300 s default timeout); concurrent non-atomic `write_parquet` of `dataflows.parquet` and possible SQLite "database is locked"; shallow vs deep copy of a custom dict in `ds["provider"]`; thread inside a scope falls back to the default. | Add the section, each risk with a mitigation or an accepted limit. |

## Major findings

| ID | Reviewers | Lines | Finding | Resolution |
|---|---|---|---|---|
| design-1-3 | design | 56, 99, 125 | New credential path, even single-threaded: `set_extra_headers(B's key)` then `get_data(ds_A)` sends B's key to A's host; today it goes to B. The leak comes from `ds["provider"]` itself, not only from threads. | Decide Q2 in the spec; at least state the default and add a test that headers do not cross providers. Ties to Stage 5 Z4. |
| design-1-4 | design | 57, 97, 124 | `set_provider`/`resolve_provider` inside a scope change only the hidden default: `with use_provider("istat"): run_query(f, provider="eurostat")` runs on ISTAT. The default path ships this bug while Q1 is optional. Same as Stage 5 Z2. | Define `set_provider` inside a scope (raise, warn, or update the scope); make the `run_query` fix mandatory or declare it unsupported in a scope; test. |
| design-1-5, style-1-M4 | design, style | 57, 46, 88 | "Safe across threads" is undefined and hides a footgun: `with use_provider("istat"): pool.map(load_dataset, ids)` runs on the default. Entry points differ (the reviewer recalls that `asyncio.to_thread` copies context and `run_in_executor` does not; to verify). Same as Stage 6 C1. | Restate the goal ("each thread or task resolves its innermost scope; no scope, the process default"); list executor patterns as a limit; consider a context-propagating helper; tests. |
| design-1-6 | design | 44-46 | Inheritance measured on 3.12.7 only; package supports `>=3.12` (3.13 classifier). Reviewer recalls, unverified, that 3.14 adds `sys.flags.thread_inherit_context` and `Thread(context=...)`. Same as Stage 5 Z8. | State the assumed versions and builds; run A4/A5 on every supported version in CI. |
| design-1-8, structural-1-3 | design, structural | 97, 117 | `use_provider` signature undefined: `resolve_provider` takes `(name, agency_id)` and reads `OPENSDMX_AGENCY`; custom fields belong to `set_provider`, which does no alias expansion or validation. Also `resolve_provider` is not in `opensdmx.__all__`, though l.117 lists it as public. Same as Stage 5 Z3 and Stage 6 C2. | Explicit signature, validation and env behaviour; state whether `set_provider` changes. |
| design-1-9 | design | 56, 99 | Wrapped-function list not justified: `print_dataset` makes no request; `dimensions_info` reads the cache only with `include_descriptions=True`; precedence when a ds names a provider different from an enclosing scope is not stated; internal callers such as `guide.py` are not covered. | One precedence rule (ds, then scope, then default); list only functions that resolve provider-dependent state. Ties to Stage 5 Z7. |
| structural-1-4 | structural | 59, 101-111 | Goal "rate limit enforced per provider across threads and processes": A6 covers threads only; no test for cross-process, or for two scopes on two providers taking different locks. Goal 1 tested only through `get_data`. | Goal IDs G1-G4; each A-test names its goal; or narrow the goal. |
| style-1-M1 | style | 47 | "The rate limiter already serializes threads of one process": true only per rate-limit key (provider or group, and stream when `data_rate_limit` splits it); evidence is one mock provider, one stream. | Scope the sentence; keep the measurement. |
| style-1-M2 | style | 48 | "Two threads never fetch [the token] concurrently": false for a provider with split data/structure locks. | Scope to "the same rate-limit key", or verify TÜİK has no split limit. |
| style-1-M3, design-1-10 | style, design | 22 | "No external Python project" rests on public, indexed GitHub code search only. | State it as a lower bound: "no public GitHub repository found". |
| style-1-M5 | style | 113 | `multiprovider-reviewer` undefined; "no `if provider == ...`" informal; "CLI output identical" packed into a parenthesis. Same as Stage 6 C4, C5. | Define or link it; "no code branches on a specific provider name"; separate invariant. |

## Nits

| ID | Lines | Finding |
|---|---|---|
| structural-1-5 | 113, 126 | Q3 open while `use_provider` is used as settled; invariants "for every phase" sit in Acceptance tests. Same as Stage 6 C10. |
| structural-1-6 | 81-99 | Design mixes three components in one section; H3 subsections and a bulleted function list would expose that `fetch` and `run_query` are not covered. |
| structural-1-7 | 3, 20-22, 113 | Cross-references are code spans, not links; decision and code search have no source link. (Project rule: no anchor links in the Contents.) |
| structural-1-8 | 38 | `run_query` citation should be 203-222 and name `set_provider_from_env()` too. |
| design-1-11 | 113, 50 | "Full suite passes unchanged" holds only outside scopes: tests that patch `base._active_provider` no longer control the provider inside one. |
| design-1-12 | 118 | `ds["provider"]` changes the `load_dataset` docstring contract; a preset name in a pickled ds resolves against the reader's own portals file. |
| style-1-N1..N11 | 3, 28, 36, 46, 49, 56, 59, 85-99, 7-16 | Wording: passive decision line; "forgets"; "wrong"; capitalised "NOT"; "harmless" → "idempotent"; "every function"; "per provider" → "per rate-limit key"; "works"; "provider value" used before it is defined; "run their body under"; Contents optional. |

## Cross-stage map

| This stage | Earlier finding |
|---|---|
| design-1-2 | Stage 5 Z1 |
| design-1-4 | Stage 5 Z2 |
| design-1-8, structural-1-3 | Stage 5 Z3, Stage 6 C2 |
| design-1-3 | Stage 5 Z4 (Q2) |
| design-1-9 | Stage 5 Z7 |
| design-1-5, style-1-M4 | Stage 6 C1 |
| design-1-6 | Stage 5 Z8 |
| style-1-M5 | Stage 6 C4, C5 |
| structural-1-5 | Stage 6 C10 |

## Citations the reviewers could not verify

`egm-design` did not read: `docs/evaluation-v0.31.2.md`, `README.md:11`, `db_cache.py:37-50`, `cli.py:147`, the two test files at l.50, and the runtime measurements at l.44-48. The author verified `db_cache.py:37-50`, the test references (three files, Stage 5 Z6) and the measurements in this session; `cli.py:147` (`_output_mode: str = "table"`) was seen in the state grep.
