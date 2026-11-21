# Implementation Readiness: Scoped provider for library use

Stage 9 of the EGM review of `docs/design-provider-context.md`. Round 2 (the one re-audit allowed), on the revised plan, DetailedRange lines 176-210. Reviewers in fresh contexts, all completed: `egm-implementation-readiness`, `egm-codebase-details` (standard `implementation-readiness-standard.md`), `egm-style`. Round 1 findings are summarised at the end.

## Contents

- Verdict
- Blocker
- Major findings
- Nits
- Verified as accurate
- Round 1, for reference

## Verdict

Not ready, but close. All round-1 blockers are closed: the single accessor, the settled decisions D1-D3, the file boundary and the closed function inventory are accepted by every reviewer, and every line reference checked matches the code. What remains is one behaviour defect and a set of choices the plan still leaves to the implementer (Zero-Decision Rule). Re-audit cap reached: no further Stage 9 round.

## Blocker

| ID | Reviewers | Lines | Finding | Fix |
|---|---|---|---|---|
| R2-B1 | all three | 193 | Phase 1 step 5 scopes only `load_dataset` and `get_data` inside `run_query`. With `labels: true` it also calls `enrich_with_labels` (`retrieval.py:241-242`), which requests codelists; dataset binding arrives only in Phase 2, so in Phase 1 labels come from the caller's provider. A7 does not test `labels`. | The whole body after resolution (`load_dataset`, `set_filters`, `get_data`, `enrich_with_labels`) runs in the scope; add a `labels: true` case to A7. |

## Major findings

| ID | Reviewers | Lines | Finding | Fix |
|---|---|---|---|---|
| R2-M1 | all three | 190, 191, 194 | "Assign as the process default" has no mechanism: `set_provider` takes a name or URL, not a provider value; `cli.py` cannot assign `base._active_provider` without breaking the "one reader" rule. The step 2 grep expectation goes stale after steps 3 and 6; `grep -n` on a directory needs `-r`. | Private setter `_set_default_provider(value: ProviderValue) -> None`, used by `set_provider`, `resolve_provider` and `cli.run`; check `grep -rn _active_provider src/` with the exact allowed hits. |
| R2-M2 | readiness, codebase | 194 | `query_provider_value` placement relative to the CLI `try` (`cli.py:1817-1836`) is unstated. Called outside it, a missing file or bad YAML prints a traceback, and `tests/test_run_and_which.py::test_run_missing_file_is_reported` fails (it mocks only `run_query`). Exceptions raised, module and import path, and public or private not stated. | Call it inside the existing `try`, before `console.status`; it raises `FileNotFoundError` (same message as `run_query`), `yaml.YAMLError`, `ValueError`; private, imported from `retrieval.py`. |
| R2-M3 | all three | 194, 184-185 | The new 413 test cannot be built: a query file selects a custom provider only through `provider_url` + `agency_id`, which never carries `too_large_hint` (`_DEFAULTS` has none, `base.py:27-38`). Its file is not named, and `tests/test_run_and_which.py` is not in the file list. | Use a preset alias with a hint (`bundesbank`) while the default is a provider without one; put it in `tests/test_run_and_which.py` and list that file as Modify. |
| R2-M4 | all three | 208 | `_bound_to_dataset` contract: keyword calls (`get_data(dataset=ds)`) skip binding if only `args[0]` is checked; mypy `strict = true` (`pyproject.toml:84-87`) needs a typed decorator (`ParamSpec`, `TypeVar`, `functools.wraps`); a dict value without `base_url`, a value of another type, and the error message are unspecified. | Bind the `dataset` argument positional or keyword; typed signature with `wraps`; dict used as stored; other types raise `TypeError`; preset error `unknown provider '<key>'` as today. |
| R2-M5 | readiness, codebase | 195 | A6 sets `rate_limit=0.2`, which `use_provider` cannot pass (custom URLs get 0.5 s). A3 and A8 threads pace at 0.5 s unless built with `_provider_scope(_build_provider(...))`. | A6 uses `set_provider(url, agency_id=..., rate_limit=0.2)` with unscoped threads; A3/A8 use `_provider_scope(_build_provider(url, agency_id=..., rate_limit=0.0))`. |
| R2-M6 | codebase | 195 | "Providers are custom URLs" conflicts with A7's alias branch, which needs a preset. Two custom providers with the same `agency_id` share cache dir and lock (`base.py:478-492`), so A8 would fail. | A7 alias case uses a preset (the mock covers every host); A and B get distinct `agency_id`s (`A`, `B`). |
| R2-M7 | all three | 195, 209 | Mock responses incomplete: A7 in Phase 1 already needs a dataflow list, a DSD and CSV; A1 for `get_dimension_values`, `get_codelist_hierarchy`, `enrich_with_labels` needs codelists, and `get_available_values` the constraint endpoint (or the `serieskeysonly` fallback). Whether A1 asserts only the host or a full parse is open. `_DSD` (`tests/test_structure_and_json.py:40`) and `_data_client` are private: import path not given. | One handler in `tests/test_provider_scope.py` answering dataflow, datastructure, codelist, availableconstraint and data URLs; A1 asserts the recorded host and a parsed result; `from tests.test_structure_and_json import _DSD`, `from tests.test_auth import _data_client`. |
| R2-M8 | readiness, codebase | 195 | Cache isolation: one `OPENSDMX_CACHE_DIR` per session (`tests/conftest.py:15`); a cached catalog or codelist from an earlier test suppresses the requests A1, A7, A8 assert on. `_isolated_db` covers only `cache.db`. | Autouse fixture setting `OPENSDMX_CACHE_DIR` to `tmp_path` (the cache base is resolved per env value, `base.py:437`). |
| R2-M9 | readiness, style | 192, 193 | `use_provider` shape: `@contextmanager` generator (error at `__enter__`) or a function returning `_provider_scope(value)` (error at the call); return annotation; what `with` yields. | A function that resolves first and returns `_provider_scope(value)`, so an invalid name raises at the call; annotation `AbstractContextManager[None]`; yields `None`. |
| R2-M10 | style | 192, 193, 195-196 | Verify clauses that cite tests written in a later step (steps 4-5 vs step 7); step 8 cites A2 for a thread rule covered by A3/A4; Phase 2 step 4 cites A1/A3 for `pool.map(get_data, datasets)`, which no test exercises; A6 tolerance (0.19 s) differs from the spec. | Write each test in the step it verifies; add a test for the dataset-pool pattern; state the tolerance in A6. |
| R2-M11 | style | 178 | "Each on its own branch from `main`": Phase 2 uses Phase 1 symbols. | Phase 2 branches from `main` after Phase 1 is merged. |

## Nits

- Alias branch arguments spelled out (`_build_provider(name)` with defaults, as today's `set_provider(name)`); env branch arguments; whether `set_provider_from_env` stays as is (it keeps its tests, `tests/test_phase2_dedup.py:39-49, 133-137`).
- `run_query` docstring (`retrieval.py:190-192`) updated: the caller's provider is never changed.
- Refactor guards: also `tests/test_phase2_dedup.py:39-137`, `tests/test_user_portals.py:250`.
- One-off mutation check: scoped-only breaks every unscoped call, active-only breaks A8; say how A8 observes the lock (`_rate_limit_lock_file()` inside the scope).
- Imports to add (`contextvars`, `contextlib`, `copy` and `_current_provider_value` in `discovery.py`); `ProviderValue` on `_active_provider`'s annotation.
- `docs/architecture.md`: Phase 1 text describes the dataset rule that arrives in Phase 2; add the file to Phase 2; fix the stale `{agency_id}` cache path (l.125) and "`--provider` calls `set_provider()`" (l.127) while there.
- Wording: "today's body" → cite `base.py:336-362`; "on it"; "the default" → "process default"; "short example"; "hub" undefined; `ds["provider"]` unit test assertion and file not named; `LOG.md` entry content.

## Verified as accurate

All cited references: `base.py:263, 486-491`, `utils.py:175-181`, `retrieval.py:213-222`, `cli.py:1792-1838, 1826-1829`, `discovery.py:706-731`, `__init__.py:10, 29-57`, `README.md:276`, `docs/architecture.md:114-127`, `tests/test_auth.py:56-63`. The `_data_client` patch is visible across threads. Existing `run_query` tests (`test_phase2_dedup.py`, `test_user_portals.py:415-445`) still hold under a scope. No CLI path serialises a whole dataset dict.

## Round 1, for reference

Round 1 failed on: cache and lock readers bypassing the scope (B1), open questions inside the plan (B2), no file boundary, undefined resolver and signature, no raw-value accessor, vague `_dataset_scope`, delegated inventory, `run_query` branches and the CLI 413 hint, scoped headers and timeout, test-plan gaps, test infrastructure reuse. All are addressed by the revision except the points listed above.
