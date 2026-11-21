# Zoom Out Review: Scoped provider for library use

Stage 5 (Initial Zoom Out) of the EGM review of `docs/design-provider-context.md` (lines 1-155, split at line 128). Reviewers: `egm-zoom-out` and `egm-inventive-catalyst`, each in a fresh context, standard `zoom-out-standard.md`. Goldfish context: `src/opensdmx/base.py`, `discovery.py`, `retrieval.py`, `__init__.py`, `docs/architecture.md`.

## Contents

- Verdict
- Findings
- Points checked by the author
- What the reviewers found sound

## Verdict

Both reviewers accept the direction: a ContextVar layered over the process default, read at the one point `get_provider()` shares with about 70 call sites, and a dataset that carries its provider. Both find the same blocking defect: the claim that cache directory, `cache.db` and rate-limit key "follow `get_provider()`" is false. The plan needs revision before Stage 6.

## Findings

| # | Severity | Source | Finding | Proposed resolution |
|---|---|---|---|---|
| Z1 | Blocker | both | `_provider_cache_key()` (`base.py:486-491`) and `utils.py:175-181` read `_active_provider` directly. Under a scope, requests would go to the scoped provider while cache dir, `cache.db` and the rate-limit lock key stay on the default. Effects: cached codelists, dimensions and constraints served across providers (keys such as `CL_FREQ:en` exist in several); the rate-limit lock shared or swapped between providers (ISTAT per-IP limit not enforced; IP ban risk); a saved query records the wrong provider. A1-A7 check only the host and would not catch it. | One private accessor for the raw provider value (scope, then `_active_provider`), used by `get_provider()`, `_provider_cache_key()`, `utils.py` and `load_dataset`; invariant "nothing else reads `_active_provider`", checked by a test; new test A8: inside a scope, `get_cache_dir()` and the lock file belong to the scoped provider, and two scoped providers in two threads use different lock files. |
| Z2 | Major | both | `run_query` changes the process provider in all four resolution branches (argument, file alias, `provider_url`, `OPENSDMX_PROVIDER`), not only with `provider=`. Once the scope is read first, a `run_query` (or a user `set_provider`) inside `use_provider(A)` changes the default for other threads and has no effect in the current context: `with use_provider("istat"): run_query(eurostat.yaml)` asks ISTAT for a Eurostat dataflow. Q1 is a correctness requirement of Phase 1, not an option for Phase 3. | Phase 1: `run_query` resolves all four branches into a scope; move A7 to Phase 1 with a test "inside `use_provider(A)`, a file naming B requests B". Decide and document what `set_provider` inside a scope does (warning, or documented silence). |
| Z3 | Major | zoom-out | The validation contract of `use_provider` is undefined. `resolve_provider` expands aliases, rejects unknown names, falls back to `OPENSDMX_AGENCY`, takes no kwargs; `set_provider` does none of that and takes `rate_limit`, `language`, `**kwargs`. The plan adds two helpers (`_build_provider`, "a shared resolver if needed") next to two functions that already exist. | One private "argument to provider value" function (aliases, validation, agency fallback, custom dict). `set_provider`, `resolve_provider` and `use_provider` become thin wrappers. State that `use_provider("typo")` raises. |
| Z4 | Major | both, opposite remedies | Q2 (timeout and extra headers). Zoom-out: YAGNI, no known consumer, and the header leak already exists sequentially (`_extra_headers` survive `set_provider`, `base.py:823`); settle Q2 as "process-wide, documented" and drop Phase 3 step 2. Catalyst: a third layer is the wrong shape; headers and timeout belong to the provider value (`request_timeout` already is a provider field, `auth` already scopes credentials to the provider's own URL), so they would follow the scope and `ds["provider"]` with no new layer; a header field should name an environment variable, as `auth` does, so a dataset dict never carries a secret. | Author's decision (see open choice below). |
| Z5 | Nit | zoom-out | The only bug shown today is the single-threaded one (Problem 1). Thread and asyncio guarantees serve consumers that do not exist yet. A5 pins a property of the runtime, not of opensdmx. | Ship Phase 2 (dataset carries its provider) before or together with a public `use_provider`; reconsider A5. |
| Z6 | Nit | zoom-out | Three tests touch `base._active_provider`, not two: `tests/test_categories.py:520` is missing. | Correct the count; note the monkeypatches keep working because the accessor still reads the variable. |
| Z7 | Nit | both | `set_filters`/`reset_filters` already `copy.deepcopy` the input (`discovery.py:1525,1578`): the key survives with no work. Wrapping seven bodies by hand invites drift; `print_dataset` makes no request (`discovery.py:776-793`). | One `_bound_to_dataset` decorator at the definitions, plus a test that every public function whose first parameter is `dataset` is decorated; turn the filters point into a test; drop or justify `print_dataset`. Note: `fetch` and `run_query` build their own dataset. |
| Z8 | Nit | catalyst | Thread inheritance was measured on 3.12.7 only, while `requires-python = ">=3.12"`. The reviewer states, without checking, that Python 3.14 adds `sys.flags.thread_inherit_context`, on by default in free-threaded builds. Then `with use_provider(X): ThreadPoolExecutor().map(load_dataset, ids)` would use X on one build and the default on another. | README: a thread sees a scope only if the context is passed (`contextvars.copy_context().run`), or pass the dataset dict. Add a test that pins the pool-inside-scope behaviour on the running interpreter. |

## Points checked by the author

- Z1: confirmed by grep. Direct reads of `_active_provider` outside `get_provider()`: `base.py:486-491` (`_provider_cache_key`) and `utils.py:175-181`.
- Z6: confirmed, `tests/test_categories.py:520`.
- Z8: the Python 3.14 claim is the reviewer's and is not verified here.

## What the reviewers found sound

- The ContextVar is not over-engineering: one read point for about 70 call sites is the least invasive fix even for the single-threaded bug.
- The portalocker lock held for the whole HTTP call is a sound cross-thread and cross-process mechanism; the risk is only which key it uses (Z1).
- Idempotent DDL in `db_cache`, tokens fetched under the provider lock, and CLI-only state left global are handled correctly.

## Open choice for the author

Z4 has two incompatible remedies: settle Q2 as process-wide and drop Phase 3 step 2 (zoom-out), or move headers and timeout into the provider value (catalyst).
