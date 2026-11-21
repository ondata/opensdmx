# Scoped provider for library use

Design for finding F2 of `docs/evaluation-v0.31.2.md`: the active provider is process-wide state, so a Python program cannot reliably use two providers. Decision by the maintainer (2026-11-21): support the importable-library use case. Revised after an EGM review (stages 5-9, reports in `docs/egm/provider-context/`).

## Contents

- Terms
- Context
- Problem
- Verified facts
- Goals and non-goals
- State inventory
- Design
- Alternatives considered
- Risks and accepted limits
- Acceptance tests
- Compatibility
- Decisions
- Detailed Implementation Plan

## Terms

- Provider: an SDMX (Statistical Data and Metadata eXchange) REST service opensdmx talks to, such as Eurostat or ISTAT.
- Preset: a provider defined in `portals.json`, addressed by its key (`istat`). An alias is another name for a preset (`estat` for `eurostat`).
- Custom provider: a provider given by base URL, stored as a dict with at least `base_url` and `agency_id`, plus any `portals.json` field passed to `set_provider`.
- Provider value: what selects a provider, type `str | dict[str, Any]`: a preset key or a custom provider dict. `base._active_provider` holds one.
- Provider config: the full dict `get_provider()` returns for a provider value (preset fields merged with defaults).
- Rate-limit key: the name of the lock and timestamp files that pace requests: the provider's `rate_limit_group`, else its cache key; split into data and structure streams when the provider sets `data_rate_limit`.

## Context

opensdmx is a CLI and an importable library (`README.md:11`, `docs/architecture.md:18`); trade-offs favour the CLI driven by an AI agent, which runs one provider per process. The library exposes `set_provider`, `load_dataset`, `get_data` and the other names in `opensdmx.__all__` (`src/opensdmx/__init__.py`).

A GitHub code search (`import opensdmx`, `from opensdmx`, 2026-11-21) found no public repository importing the library; the one related repository found, `aborruso/opensdmx-mcp`, is TypeScript. The search does not see private code or installs, so this is a lower bound: there is no known consumer. That argues for small, backward-compatible steps.

## Problem

1. A dataset dict does not record its provider. This sequence asks Eurostat for an ISTAT dataflow id, in a single-threaded script:

   ```python
   ds = opensdmx.load_dataset("X")   # ISTAT active
   opensdmx.set_provider("eurostat")
   opensdmx.get_data(ds)             # request goes to Eurostat
   ```

2. `run_query` changes the caller's provider and leaves it changed, on all four resolution branches (`retrieval.py:213-222`): the `provider` argument (`resolve_provider`), the file's `provider` alias and its `provider_url` (`set_provider`), and `OPENSDMX_PROVIDER` (`set_provider_from_env`).

3. Two threads cannot use two providers: whichever calls `set_provider` last wins for both.

## Verified facts

Measured on 2026-11-21, Python 3.12.7, offline:

- A `contextvars.ContextVar` set in the caller is not seen by a new `threading.Thread` nor by a `ThreadPoolExecutor` worker (both read the default). An `asyncio` task sees it.
- Threads of one process that share a rate-limit key are serialized: three threads calling `sdmx_request` on one mock provider with `rate_limit=1.0` sent at gaps of 1.01 s and 1.00 s. The exclusive `portalocker` lock is held for the whole HTTP call (`base.py:807`).
- An `auth` token is fetched inside that lock (`base.py:809-810`), so threads on the same rate-limit key never fetch it concurrently.
- `db_cache` creates its tables with `CREATE TABLE IF NOT EXISTS` (`db_cache.py:37-50`): schema initialization is idempotent.
- `get_provider()` is not the only reader of the provider value. `_provider_cache_key()` (`base.py:486-491`) and `utils.build_query_dict` (`utils.py:175-181`) read `_active_provider` directly. The cache directory (`get_cache_dir`, `base.py:495`), every per-provider cache file (`cache.db`, `dataflows.parquet`, `categories.parquet`, `embeddings.parquet`) and the rate-limit key fallback (`base.py:545`) derive from `_provider_cache_key()`. A grep of `src/` finds no other direct reader.
- Three tests read or patch `base._active_provider`: `tests/test_codelist_agency.py:99`, `tests/test_categories.py:520`, `tests/test_phase2_dedup.py:24`.

## Goals and non-goals

Goals:

- G1. A dataset dict records its provider value; the functions listed under "Dataset binding" send their requests to that provider, whatever is active.
- G2. A scoped way to use a provider for a block of code, restored on exit, nestable. Each thread or task resolves its own innermost scope; a thread with no scope resolves the `set_provider` default.
- G3. `set_provider()` keeps its meaning: it sets the process default.
- G4. Inside a scope, everything derived from the provider follows the scope: request URLs, cache directory and files, rate-limit key.
- G5. The rate limit stays enforced per rate-limit key, as today.

Non-goals:

- Changing CLI behaviour or output.
- Scoping CLI-only state: `_explain`, `_wait_reporter`, `_rate_limit_context`, `cli._output_mode`.
- Scoping `set_timeout` and `set_extra_headers` (see Decisions).
- Promising that a thread started inside a scope inherits it (interpreter-dependent).
- Removing `set_provider` or the process default.

## State inventory

| State | Where | Treatment |
|---|---|---|
| `_active_provider` | `base.py:263` | process default; read only through one accessor |
| scoped provider | new | `ContextVar`, read first by the accessor |
| provider of a dataset | new | `ds["provider"]` |
| `_timeout`, `_timeout_explicit` | `base.py:264-266` | process-wide (Decision D2); `request_timeout` is already a per-provider field and follows the scope |
| `_extra_headers` | `base.py:267` | process-wide (Decision D2) |
| `_explain`, `_wait_reporter`, `_rate_limit_context`, `_output_mode` | `base.py:279-311, 658`, `cli.py:147` | stay global, CLI-only |
| `auth._tokens` | `auth.py:30` | unchanged: keyed by token URL and client id, fetched under the lock |
| `db_cache._INITIALIZED_DBS` | `db_cache.py:18` | unchanged: idempotent DDL |

## Design

### Resolution order

One private accessor returns the current provider value: the scoped value if set, else `_active_provider`. `get_provider()`, `_provider_cache_key()` and `utils.build_query_dict` read through it, and nothing else reads `_active_provider`. Because the cache key and the rate-limit key go through it, a scope moves the cache files and the lock with the requests (G4).

Precedence, one rule: a dataset's own provider, then the innermost scope, then the process default.

### Scope

`opensdmx.use_provider(name, agency_id=None)` is a context manager. `name` is a preset, an alias or a base URL. It resolves exactly as `resolve_provider` does today: alias expansion, `ValueError` for a name that is neither a preset nor a URL, `agency_id` falling back to `OPENSDMX_AGENCY`. Resolution happens before the scope is entered, so an invalid name leaves nothing set. On exit, including on an exception, the previous scope is restored.

`resolve_provider` and `use_provider` share one private resolver that returns a provider value; `resolve_provider` assigns it as the process default, `use_provider` scopes it. `set_provider` keeps its own wider signature (`rate_limit`, `language`, custom fields) and its permissive behaviour (an unknown name is taken as a URL); it shares the value builder with the resolver.

`set_provider` called inside a scope sets the process default; the enclosing scope still wins until it exits. This is documented in both docstrings and tested.

A thread does not inherit the caller's scope on CPython 3.12. To use a provider in workers, pass datasets (each carries its provider), or open a scope inside the worker.

### Dataset binding

`load_dataset` stores `ds["provider"]` = a deep copy of the current provider value. These public functions run under the dataset's provider when the key is present: `dimensions_info`, `get_dimension_values`, `get_codelist_hierarchy`, `get_available_values`, `get_data`, `enrich_with_labels`. Not bound, with the reason:

- `print_dataset`: reads only the dict, no provider state (`discovery.py:776-793`).
- `set_filters`, `reset_filters`: no request; both deep-copy the dict (`discovery.py:1525, 1578`), so the key survives.
- `fetch`, `run_query`: take an id or a file and build their own dataset under their own resolution.
- Internal: `utils.build_query_dict` and `guide.py:170, 285` read the current provider; they serve the CLI, which runs one provider per process.

A dict without the key (built by hand) uses the current provider, as today. A dict whose stored preset key is no longer defined (a different user `portals.json`) raises `ValueError` naming the key, rather than falling back to another provider.

### Saved queries

`run_query` resolves its four branches, with today's precedence, into one provider value and runs inside a scope on it; the caller's provider is unchanged after the call. If no branch applies, no scope is opened. The CLI `run` command needs the same value after `run_query` fails, to print the provider's HTTP 413 hint (`cli.py:1826-1829`): it resolves the value through the same private helper and sets it as the process default before calling `run_query`, which matches what the CLI does for `--provider`.

## Alternatives considered

- `provider=` argument on every public function: six network functions do not take a dataset (`all_available`, `search_dataset`, `fetch`, `semantic_search`, `build_embeddings`, `load_dataset`) and internal callers such as `guide.py` read the current provider; every signature changes, and the cache and lock paths still need the same accessor.
- A client or session object (`Client("istat").load_dataset(...)`): the usual fix for module state, but a second API next to the module functions, against `docs/architecture.md:15` ("No rich object model").
- `threading.local`: does not follow `asyncio` tasks; a `ContextVar` costs the same and covers both.
- A `ContextVar` replacing `_active_provider`: threads would read its default (`eurostat`) instead of the `set_provider` value, a regression for `set_provider` followed by a thread pool.
- `ds["provider"]` only, with no public scope: fixes Problem 1 but leaves the six non-dataset functions and `run_query` on the process default.

## Risks and accepted limits

New with this design:

- A thread started inside a scope does not see it on CPython 3.12. Accepted and documented; datasets carry their provider, and a scope can be opened in the worker. Inheritance may differ on other interpreter versions or builds; G2 does not promise it.
- Headers set with `set_extra_headers` go to whichever provider a call resolves to. After this change, `get_data(ds_A)` sends them to A even if B is the default; today the same call goes to B with them. Accepted (Decision D2) and documented on `set_extra_headers`: it applies to every provider; per-provider credentials belong in the provider's `auth` field, which reads secrets from the environment and sends them only to that provider's URL (`base.py:789-791`).
- A dataset dict pickled in one session and used in another resolves its preset key against that session's `portals.json`; a key that no longer exists raises.

Pre-existing, unchanged by this design (already true with two CLI processes, or with `set_provider` and a thread pool):

- Parquet cache writes are not atomic (`discovery.py:240, 342`).
- SQLite can raise "database is locked" after its 10 s timeout (`db_cache.py:27`).
- Calls on one rate-limit key are serial, since the lock is held for the whole request; that is the rate limit.

Found and fixed during Phase 1 (pre-existing): the cache base was resolved with a write probe of fixed name (`base.py`, `_resolve_cache_base_cached`). Two threads resolving it at once could unlink each other's probe; the loser fell back to another base, with another rate-limit lock, and its first request was not paced (reproduced in 130 of 300 cold starts). The probe now has a unique name per call.

## Acceptance tests

All offline, with a mock HTTP transport that records the requested URL. Each names the goal it covers.

- A1 (G1). Load a dataset under custom provider A, `set_provider(B)`, then each bound function that makes a request sends it to A's host.
- A2 (G2). `use_provider`: active inside, restored after; nested scopes restore in order; an exception inside restores; an invalid name raises and leaves no scope; an `asyncio` task started inside sees it.
- A3 (G2). Two threads, each in its own scope, request their own host.
- A4 (G2, G3). `set_provider(A)`, then a thread with no scope resolves A, not `eurostat`.
- A5 (G3). `set_provider(B)` inside `use_provider(A)`: the block still resolves A; after the block, B.
- A6 (G5). Two threads on one provider are paced: gaps between sends are at least its `rate_limit` minus 0.01 s (timer granularity).
- A7. `run_query` on a file naming B, inside `use_provider(A)` and with A as default: requests go to B; afterwards the caller resolves A. Same for the `provider` argument, `provider_url` and `OPENSDMX_PROVIDER` branches, and for a file with `labels: true` (label requests go to B too).
- A8 (G4). Inside `use_provider(A)` with default B, and inside a call bound to a dataset of A: `get_cache_dir()` and the rate-limit lock file are A's; two threads scoped to two providers use two different lock files.
- A9 (G1). A dict without `provider` uses the current provider; a stored preset key that is not defined raises `ValueError`; `set_filters` and `reset_filters` keep the key; binding applies whether the dataset is passed by position or as `dataset=`.
- A10 (G1, G2). Datasets of A and B mapped over a `ThreadPoolExecutor` with no scope: each request goes to its own dataset's host.

Invariants for every phase: the full test suite passes (outside a scope behaviour is unchanged, so CLI output is identical); no code branches on a specific provider name (provider quirks are declared in `portals.json`, see `.claude/agents/multiprovider-reviewer.md`); the diff passes the `multiprovider-reviewer` agent (`.claude/agents/multiprovider-reviewer.md`), which checks impact on every provider in `portals.json`.

## Compatibility

- `set_provider`, `get_provider` and `resolve_provider` keep their signatures and meaning outside a scope. `resolve_provider` is internal (not in `__all__`).
- `ds["provider"]` is a new key; the `load_dataset` docstring lists it. A search of `src/` and `tests/` for exact-key comparisons on a dataset dict (`.keys() ==`, `set(ds)`) finds none.
- `run_query` no longer changes the caller's provider. The CLI `run` command keeps its behaviour (it sets the file's provider itself).
- `base._active_provider` keeps its name; the three tests that patch it still control the provider, since no scope is open in them.

## Decisions

- D1. `run_query` runs under a scope (Problem 2), in Phase 1.
- D2. `set_timeout` and `set_extra_headers` stay process-wide, documented. Scoping them is deferred until a consumer needs it; the shape to use then is headers as a provider field naming an environment variable, as `auth` does.
- D3. The public name is `use_provider`.

## Detailed Implementation Plan

One PR, one commit per phase (maintainer's decision, 2026-11-21; first planned as two PRs). Phase 2 builds on Phase 1 symbols. Each passes `uv run ruff check`, `uv run mypy` (strict) and `uv run pytest`, is reviewed with the `multiprovider-reviewer` agent, and adds an entry at the top of `LOG.md` (date heading, English bullets).

### Phase 1: one accessor, a scope, saved queries

Files:

- Modify `src/opensdmx/base.py`, `src/opensdmx/utils.py`, `src/opensdmx/retrieval.py`, `src/opensdmx/cli.py`, `src/opensdmx/__init__.py`, `README.md`, `LOG.md`, `tests/test_run_and_which.py`.
- Create `tests/test_provider_scope.py`.

Test infrastructure, written in step 1 and extended by each step that verifies something:

- HTTP mock: `from tests.test_auth import _data_client` (`tests/test_auth.py:56-63`); it patches every `httpx.Client` that `sdmx_request` opens, whatever the host. One handler records each requested URL and answers by path: `dataflow/` (a two-flow catalog), `datastructure/` (`from tests.test_structure_and_json import _DSD`), `codelist/` (a small codelist), `availableconstraint/` (a constraint with one value per dimension), `data/` (a CSV body).
- Providers: custom `https://a.example/rest` with `agency_id="A"` and `https://b.example/rest` with `agency_id="B"`, so their cache keys and lock files differ; the preset `bundesbank` where a test needs a preset.
- Cache isolation: an autouse fixture sets `OPENSDMX_CACHE_DIR` to `tmp_path` (the cache base is resolved per environment value, `base.py:437`), so no test is served from another test's cache.

Steps:

1. `base.py`: imports `from contextvars import ContextVar` and `from contextlib import AbstractContextManager, contextmanager`. Add `ProviderValue = str | dict[str, Any]` (also as the annotation of `_active_provider`, `base.py:263`), `_scoped_provider: ContextVar[ProviderValue | None] = ContextVar("opensdmx_provider", default=None)`, `_current_provider_value() -> ProviderValue` (scoped value if not `None`, else `_active_provider`) and `_set_default_provider(value: ProviderValue) -> None` (the only writer of `_active_provider`). `get_provider()` and `_provider_cache_key()` read through `_current_provider_value()`. Verify: full suite green.
2. `utils.py:175-181`: `build_query_dict` reads `_current_provider_value()` instead of importing `_active_provider`. Verify: `grep -rn _active_provider src/` finds only its definition, `_set_default_provider` and `_current_provider_value`.
3. `base.py`: the body of `set_provider` (`base.py:336-362`) becomes `_build_provider(name_or_url: str, agency_id: str | None = None, rate_limit: float = 0.5, language: str = "en", **kwargs: Any) -> ProviderValue`, warnings and their `set_provider:` prefix unchanged; `set_provider` calls it and `_set_default_provider`. Add `_resolve_provider_value(name: str, agency_id: str | None) -> ProviderValue`: `_resolve_provider_name`, the preset-or-`http` check raising the `ValueError` now at `base.py:392-394`, the `OPENSDMX_AGENCY` fallback, then `_build_provider(resolved, agency_id=...)`. `resolve_provider` becomes `_set_default_provider(_resolve_provider_value(name, agency_id))`; `set_provider_from_env` keeps its signature and goes through `resolve_provider`. Verify: `tests/test_base.py`, `tests/test_phase2_dedup.py:39-137` and `tests/test_user_portals.py` unchanged and green.
4. `base.py`: `_provider_scope(value: ProviderValue)`, a `@contextmanager` (`token = _scoped_provider.set(value)`, `yield`, `_scoped_provider.reset(token)` in `finally`). Public `use_provider(name: str, agency_id: str | None = None) -> AbstractContextManager[None]`, a plain function: it calls `_resolve_provider_value` first, so an invalid name raises at the call and nothing is set, then returns `_provider_scope(value)`; the `with` yields `None`. Docstrings of `use_provider` and `set_provider` state the rule for `set_provider` inside a scope; the `set_extra_headers` docstring states D2. Export in `src/opensdmx/__init__.py`: add `use_provider` to the `from .base import` line (line 10) and to `__all__` (lines 29-57). Verify: write A2 and A5 now, green.
5. `retrieval.py`: extract `_query_provider_value(q: dict[str, Any], provider: str | None) -> ProviderValue | None` from `retrieval.py:213-222`, same precedence: the `provider` argument through `_resolve_provider_value(provider, q.get("agency_id") or None)`; a `provider` alias that resolves to a preset through `_build_provider(_resolve_provider_name(alias))`; `provider_url` through `_build_provider(q["provider_url"], agency_id=q.get("agency_id") or None)`; else, if `OPENSDMX_PROVIDER` is set, `_resolve_provider_value(os.environ["OPENSDMX_PROVIDER"], None)`; else `None`. Add `_query_provider_value_from_file(query_file: str, provider: str | None) -> ProviderValue | None`, which reads the file (raising `FileNotFoundError("Query file not found: ...")` as `run_query` does, `yaml.YAMLError`, `ValueError`) and returns `_query_provider_value(q, provider)`. `run_query` calls `_query_provider_value` on its own parsed dict and runs everything after resolution (`load_dataset`, `set_filters`, `get_data`, `enrich_with_labels`) inside `_provider_scope(value)` when the value is not `None`. Its docstring (`retrieval.py:190-192`) says the caller's provider is never changed. Verify: write A7, including the `labels: true` case, green.
6. `cli.py` `run` (`cli.py:1792-1838`): inside the existing `try` (`cli.py:1817`), before `console.status`, call `_query_provider_value_from_file(str(query_file), provider)` (imported from `.retrieval`) and, when not `None`, `_set_default_provider(value)`, so the 413 handler at `cli.py:1826-1829` reads the file's provider; missing file and bad YAML keep their current messages. Verify: existing `run` tests in `tests/test_run_and_which.py` green; new test there: a query file with `provider: bundesbank`, process default `https://a.example/rest` (no `too_large_hint`), the mocked data request answers 413, and the hint printed is bundesbank's.
7. `tests/test_provider_scope.py`: A3, A4, A6 and the scope part of A8. A6 uses `set_provider("https://a.example/rest", agency_id="A", rate_limit=0.2)` and two unscoped threads. A3 and A8 enter `_provider_scope(_build_provider(url, agency_id=..., rate_limit=0.0))`, so they do not pace. A8 calls `get_cache_dir()` and `_rate_limit_lock_file()` inside the scope. Verify: green; one-off check before merge, not a test: making `_current_provider_value` return only `_active_provider` fails A8.
8. `README.md` "## Python API" (`README.md:276`): a `use_provider` row in the table and an example that enters a scope, calls `load_dataset` and `dimensions_info` (no data download, ISTAT is rate-limited), and exits, with one sentence on threads (a thread sees the `set_provider` default, not the caller's scope). Verify: the example uses only calls covered by A2, A3 and A4.

### Phase 2: a dataset carries its provider

Files:

- Modify `src/opensdmx/base.py`, `src/opensdmx/discovery.py`, `src/opensdmx/retrieval.py`, `README.md`, `docs/architecture.md`, `LOG.md`, `tests/test_provider_scope.py`.

Steps:

1. `discovery.py`: `import copy` at module level and `_current_provider_value` in the `from .base import (...)` block (`discovery.py:51-57`). `load_dataset` (`discovery.py:706-731`) adds `"provider": copy.deepcopy(_current_provider_value())` to the returned dict and to its docstring. Verify: test in `tests/test_provider_scope.py` that `ds["provider"]` equals `"bundesbank"` for a preset, and for a custom URL equals the custom dict without being the same object.
2. `base.py`: decorator `_bound_to_dataset(func: Callable[P, R]) -> Callable[P, R]` (`ParamSpec P`, `TypeVar R`, `functools.wraps`). It takes the `dataset` argument, positional (`args[0]`) or keyword (`kwargs["dataset"]`). When it is a dict with a `"provider"` key: a string not in `PROVIDERS` raises `ValueError(f"unknown provider '{key}' stored in dataset")`; a dict is used as stored; any other type raises `TypeError`; then it runs `func` inside `_provider_scope(value)`. Otherwise it calls `func` unchanged. Verify: A9.
3. Apply it at the definitions of `dimensions_info`, `get_dimension_values`, `get_codelist_hierarchy`, `get_available_values` (`discovery.py`), `get_data`, `enrich_with_labels` (`retrieval.py`). Verify: A1 for each of the six (the recorded host is A's and the result is non-empty), A8 dataset part, A10.
4. `README.md`: one sentence that datasets carry their provider, and the worker pattern `pool.map(get_data, datasets)`. `docs/architecture.md:114-127` "Provider abstraction": the accessor, the scope and the precedence rule; correct line 125 (the cache directory is the provider cache key, not `{agency_id}`) and line 127 (`--provider` goes through `resolve_provider`). Verify: the README pattern is the one A10 exercises.
