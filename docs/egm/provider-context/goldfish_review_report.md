# Goldfish Annotated Review Report

Status: resolved (auto accept, 2026-11-21): 13 PROPOSE FIX applied to `docs/design-provider-context.md`, 1 DECLINE recorded, 0 CONTEST, 0 ESCALATE. Plan section now at lines 177-216.

**Target:** `docs/design-provider-context.md` (lines 176-210, Detailed Implementation Plan; Stage 9 round 2)

Summary: 12 PROPOSE FIX (1 Blocker, 11 Major), 3 Nits fixed with them, the other Nits DECLINE. No CONTEST, no ESCALATE: every finding was checked against the code the reviewers cite and holds.

## Prioritized Findings & AI Suggestions

### [Issue 1] [`implementation-readiness`, `codebase-details`, `style`] - Severity: Blocker
*   **Affected Scope:** [Lines 193](docs/design-provider-context.md#L193) (Phase 1 step 5)
*   **Discrepancy Description:** only `load_dataset` and `get_data` run in the scope; `run_query` also calls `enrich_with_labels` with `labels: true` (`retrieval.py:241-242`).
*   **Rationale:** in Phase 1 labels would come from the caller's provider.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:*** confirmed in `retrieval.py:241-242`; binding arrives only in Phase 2.
*   ***Proposed Edit:***
    *   Location: Phase 1 step 5; A7.
    *   Change: "runs everything after resolution (`load_dataset`, `set_filters`, `get_data`, `enrich_with_labels`) inside `_provider_scope(value)`"; A7 gains a `labels: true` case.

### [Issue 2] [all three] - Severity: Major
*   **Affected Scope:** [Lines 190-194](docs/design-provider-context.md#L190-L194) (steps 2, 3, 6)
*   **Discrepancy Description:** no mechanism to set a provider value as process default; grep expectation goes stale; `grep -n` on a directory.
*   **Rationale:** two implementers would choose differently.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Proposed Edit:*** add `_set_default_provider(value: ProviderValue) -> None` in step 1; `set_provider`, `resolve_provider` and `cli.run` use it; step 2 check becomes `grep -rn _active_provider src/` with hits only in its definition, `_set_default_provider` and `_current_provider_value`.

### [Issue 3] [`implementation-readiness`, `codebase-details`] - Severity: Major
*   **Affected Scope:** [Line 194](docs/design-provider-context.md#L194) (step 6)
*   **Discrepancy Description:** placement of `query_provider_value` relative to the CLI `try` (`cli.py:1817-1836`); exceptions, module, visibility.
*   **Rationale:** outside the `try`, missing file and bad YAML become tracebacks; `test_run_missing_file_is_reported` fails.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Proposed Edit:*** name it `_query_provider_value_from_file(query_file, provider)` (private, in `retrieval.py`); called inside the existing `try`, before `console.status`; raises `FileNotFoundError` ("Query file not found: ..."), `yaml.YAMLError`, `ValueError`.

### [Issue 4] [all three] - Severity: Major
*   **Affected Scope:** [Line 194](docs/design-provider-context.md#L194), [lines 184-185](docs/design-provider-context.md#L184-L185)
*   **Discrepancy Description:** the 413 test as written cannot be built (a `provider_url` provider never carries `too_large_hint`); test file not named or listed.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Proposed Edit:*** query file with `provider: bundesbank` (preset with a `too_large_hint`), default set to a custom provider without one, mocked HTTP 413; assert bundesbank's hint is printed. In `tests/test_run_and_which.py`, listed as Modify.

### [Issue 5] [all three] - Severity: Major
*   **Affected Scope:** [Line 208](docs/design-provider-context.md#L208) (Phase 2 step 2)
*   **Discrepancy Description:** decorator: keyword `dataset=`, typing under mypy strict, dict and other values, error text.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Proposed Edit:*** binds the `dataset` argument positional or keyword (via `inspect.signature(func).bind_partial`); typed `Callable[P, R] -> Callable[P, R]` with `ParamSpec`/`TypeVar` and `functools.wraps`; a dict value is used as stored; a string not in `PROVIDERS` raises `ValueError("unknown provider '<key>' stored in dataset")`; any other type raises `TypeError`.

### [Issue 6] [`implementation-readiness`, `codebase-details`] - Severity: Major
*   **Affected Scope:** [Line 195](docs/design-provider-context.md#L195) (step 7)
*   **Discrepancy Description:** `rate_limit=0.2` cannot reach a `use_provider` scope; scoped threads pace at 0.5 s.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Proposed Edit:*** A6 uses `set_provider(url, agency_id="A", rate_limit=0.2)` with unscoped threads; A3 and A8 use `_provider_scope(_build_provider(url, agency_id=..., rate_limit=0.0))`.

### [Issue 7] [`codebase-details`] - Severity: Major
*   **Affected Scope:** [Line 195](docs/design-provider-context.md#L195)
*   **Discrepancy Description:** A7's alias branch needs a preset; two custom providers with the same `agency_id` share cache and lock (`base.py:478-492`).
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Proposed Edit:*** custom providers `https://a.example/rest` (agency `A`) and `https://b.example/rest` (agency `B`); A7's alias case uses `bundesbank` (the mock answers every host).

### [Issue 8] [all three] - Severity: Major
*   **Affected Scope:** [Lines 195, 209](docs/design-provider-context.md#L195)
*   **Discrepancy Description:** mock responses incomplete (codelist, constraint endpoints); A1 assertion undefined; private fixtures' import paths.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Proposed Edit:*** one handler in `tests/test_provider_scope.py`, written in Phase 1, answering by path: `dataflow/`, `datastructure/` (`_DSD`), `codelist/`, `availableconstraint/`, `data/` (CSV); A1 asserts the recorded host and a non-empty parsed result; `from tests.test_structure_and_json import _DSD`, `from tests.test_auth import _data_client`.

### [Issue 9] [`implementation-readiness`, `codebase-details`] - Severity: Major
*   **Affected Scope:** [Line 195](docs/design-provider-context.md#L195)
*   **Discrepancy Description:** one cache dir for the session (`tests/conftest.py:15`); cached data suppresses asserted requests.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Proposed Edit:*** autouse fixture in `tests/test_provider_scope.py` setting `OPENSDMX_CACHE_DIR` to `tmp_path` (cache base resolved per env value, `base.py:437`).

### [Issue 10] [`implementation-readiness`, `style`] - Severity: Major
*   **Affected Scope:** [Line 192](docs/design-provider-context.md#L192) (step 4)
*   **Discrepancy Description:** `use_provider` shape, annotation, yield.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Proposed Edit:*** a plain function: resolves first (an invalid name raises at the call), returns `_provider_scope(value)`; signature `use_provider(name: str, agency_id: str | None = None) -> AbstractContextManager[None]`; the `with` yields `None`.

### [Issue 11] [`style`] - Severity: Major
*   **Affected Scope:** [Lines 192-196, 210](docs/design-provider-context.md#L192-L196)
*   **Discrepancy Description:** Verify clauses citing tests written later; A2 cited for the thread rule; no test for `pool.map(get_data, datasets)`; A6 tolerance differs from the spec.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Proposed Edit:*** each step writes the tests it verifies; step 8 cites A3/A4; new A10 (datasets of A and B mapped over a `ThreadPoolExecutor` with no scope, each request to its own host) in Phase 2; A6 states "at least `rate_limit` minus 0.01 s (timer granularity)".

### [Issue 12] [`style`] - Severity: Major
*   **Affected Scope:** [Line 178](docs/design-provider-context.md#L178)
*   **Discrepancy Description:** Phase 2 cannot branch from `main` before Phase 1 is merged.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Proposed Edit:*** "Phase 2 branches from `main` after Phase 1 is merged."

### [Issue 13] [several] - Severity: Nit
*   **Affected Scope:** steps 3, 5, Phase 2 step 1
*   **Discrepancy Description:** alias and env branch arguments; `run_query` docstring; imports in `discovery.py`.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Proposed Edit:*** spell out `_build_provider(_resolve_provider_name(alias))` and `_resolve_provider_value(os.environ["OPENSDMX_PROVIDER"], None)`; `set_provider_from_env` kept, rebuilt on `_resolve_provider_value`; docstring line; `import copy` and `_current_provider_value` added to `discovery.py`.

### [Issue 14] [several] - Severity: Nit
*   **Affected Scope:** various
*   **Discrepancy Description:** refactor guard tests to name, mutation-check pairing, `docs/architecture.md` timing and stale lines, wording ("today's body", "on it", "short", "hub"), `ds["provider"]` unit test assertion, `LOG.md` content.
*   ***AI Suggestion:*** DECLINE
*   ***Justification:*** recorded; they change no behaviour and the implementer resolves them by reading the cited lines. `docs/architecture.md` moves to Phase 2 with the precedence rule (folded into Issue 11's edit of step 8).
