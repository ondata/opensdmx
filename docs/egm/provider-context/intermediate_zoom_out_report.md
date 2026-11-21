# Intermediate Zoom Out: Scoped provider for library use

Stage 8 of the EGM review of `docs/design-provider-context.md` (full file, lines 1-155). Reviewer: `egm-zoom-out`, fresh context, standard `zoom-out-standard.md`, with the Stage 5, 6 and 7 reports. The document has not been edited since Stage 5. Question asked: do the additions the Comprehension and Critic stages request keep the design simple, or push it toward over-engineering?

## Contents

- Verdict
- Necessary design changes
- Necessary prose
- Optional
- Rejected as speculative
- Resulting plan

## Verdict

Keep the design: a private ContextVar, `ds["provider"]` and a public `use_provider`. A smaller design would not meet the goals: six public functions reach the network without taking a dataset (`all_available`, `search_dataset`, `fetch`, `semantic_search`, `build_embeddings`, `load_dataset`), so the alternative is `provider=` on all six. Most Stage 6-7 requests are prose. Building every listed mitigation would over-engineer it.

## Necessary design changes

| ID | Severity | Change | Earlier findings |
|---|---|---|---|
| N1 | Blocker | One private accessor for the raw provider value (scope, then `_active_provider`), read by `get_provider()`, `_provider_cache_key()` and `utils.py:175-181`, confirmed by grep as the only direct readers. Test A8: inside a scope, `get_cache_dir()` and the lock file belong to the scoped provider; two scopes, two lock files. | Z1, design-1-2 |
| N2 | Major | One private "arguments to provider value" function; drop `_build_provider` and "a shared resolver if needed". `use_provider(name, agency_id=None)` mirrors `resolve_provider` (aliases, unknown name raises `ValueError`, `OPENSDMX_AGENCY` fallback); no custom-field kwargs (only `set_provider` has them, no caller needs them in a scope). `_dataset_scope` sets the ContextVar from the stored value directly. | Z3, C2, design-1-8, structural-1-3 |
| N3 | Major | `run_query` resolves all four branches (`retrieval.py:213-222`) into a scope, in Phase 1. `set_provider` inside a scope: one documented sentence ("sets the process default; the enclosing scope still wins until it exits"), no warning, no raise. | Z2, design-1-4 |

## Necessary prose

| ID | Item |
|---|---|
| N4 | "Alternatives considered", about five lines: `provider=` everywhere (six signatures, internal callers such as `guide.py` read the global); client or session object (`docs/architecture.md:15`, "No rich object model"); `threading.local` (does not follow asyncio tasks, no cheaper); ContextVar replacing `_active_provider` (breaks the default for threads, A4); `ds["provider"]` only (leaves the non-dataset functions on the global). |
| N5 | "Risks and accepted limits". Pre-existing, unchanged by this design, one line: non-atomic parquet writes, SQLite "database is locked" (`db_cache.py:27`, `timeout=10`), same-provider calls serial under the lock (that is the rate limit). New, one line each with the accepted limit: a thread started inside a scope; the credential pairing shift through `ds["provider"]`; a preset name in a pickled dataset resolves against the reader's portals file. "Deep copy" goes into the Phase 2 step. |
| Z5 | Goal l.57 reworded: "each thread or task resolves its own innermost scope; a thread with no scope sees the `set_provider` default; whether a thread started inside a scope inherits it is interpreter-dependent and not promised". Document the robust pattern: pass datasets to workers (`pool.map(get_data, datasets)`), correct on any interpreter after Phase 2. Keep A4; drop A5 or fold it into A2. |
| Z4 | Q2 settled: headers and `set_timeout` stay process-wide. One sentence on `set_extra_headers`: "applies to every provider; for per-provider credentials use the provider's `auth` field". Credentials already have a provider-scoped path (`auth.py:59-60`; attached only to the provider's own URL, `base.py:789-791`); `request_timeout` is already per provider (`base.py:741-748`). The CLI runs one provider per process and is unaffected. |
| - | Precedence rule, one sentence: dataset, then scope, then default. |
| N7 | C3, C4, C5, C9, C11 and the style nits: definitions, link to `multiprovider-reviewer`, "no code branches on a provider name". |

## Optional

- Introspection test that every public function whose first parameter is `dataset` carries the decorator (the one-off grep in the PR gives the same assurance for six functions).
- Goal IDs and goal tags on tests (N6): narrowing the rate-limit goal to "per rate-limit key, unchanged" is enough.
- A test enforcing "no direct `_active_provider` reads" (A8 already catches the regression).

## Rejected as speculative

Scoped headers and timeout (Phase 3 step 2); a context-propagating helper; a CI matrix running A4/A5 on every Python version; warn or raise for `set_provider` inside a scope; a cross-process rate-limit test; custom-provider kwargs on `use_provider`; A5 as a separate test; `print_dataset` in the wrapped list.

Not verified by any reviewer, and not relied on by the wording above: the Python 3.14 `thread_inherit_context` flag, and how `asyncio.to_thread` and `run_in_executor` treat the context.

## Resulting plan

Phase 3 empties: Q1 moves into Phase 1 (N3) and Q2 becomes documentation (Z4). The plan becomes two PRs. Ship Phase 2 (dataset carries its provider) with or before the public `use_provider`.
