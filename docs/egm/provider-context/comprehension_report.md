# Comprehension Test: Scoped provider for library use

Stage 6 of the EGM review of `docs/design-provider-context.md`. Reviewer: `egm-comprehension`, fresh context, document alone (no Goldfish context, no standard). FeatureRange lines 1-127, DetailedRange lines 128-155.

## Contents

- What this proposes
- How the existing system works, per this document
- Findings

## What this proposes

The library keeps its process-wide default provider. The design adds a per-context override on top of it, a `ContextVar`, which `get_provider()` checks first. A new public context manager, `use_provider(...)`, sets the override for a block of code and restores it on exit, including on exceptions. Scopes can be nested.

`load_dataset` will also record the provider that produced a dataset as `ds["provider"]`. Every public function that takes a dataset then runs under that provider, so a later `set_provider` call no longer sends requests to the wrong service. A dict without the key, such as one built by hand, uses the active provider, as today.

Two follow-ups are optional and depend on open questions: `run_query` would run under a scope instead of changing the caller's provider (Q1), and timeout and headers might be scoped too (Q2). The work is split into three PRs: the scope mechanism, then datasets that remember their provider, then the Q1/Q2 items.

## How the existing system works, per this document

The active provider is a single module-level variable, `base._active_provider`. `set_provider()` writes it and `get_provider()` reads it. Request URLs, the cache directory, `cache.db` and the rate-limit lock key are all derived from it.

Dataset dicts do not store their provider. `run_query(file, provider=...)` changes the global provider and leaves it changed. Two threads cannot use different providers, because whichever calls `set_provider` last wins for both.

Across threads and processes, the rate limiter already holds an exclusive `portalocker` lock per provider for the whole HTTP call. The TÜİK token is fetched inside that lock, and the cache schema is created with idempotent DDL. Timeout, extra headers and several CLI-only settings are also global.

Author's note: the sentence "the cache directory, `cache.db` and the rate-limit lock key are all derived from it [through `get_provider()`]" restates the document's claim, which Stage 5 (finding Z1) showed to be false.

## Findings

| # | Severity | Scope | Finding |
|---|---|---|---|
| C1 | Major | Goals l.57, Design l.88, Phase 1 step 5 l.138 | "Safe across threads" is undefined. A thread started inside `with use_provider("istat"):` (e.g. a `ThreadPoolExecutor` worker) will not see ISTAT and uses the `set_provider` default; the document never states it, and no acceptance test covers it (A3: each thread has its own scope; A4: no scope). Overlaps Stage 5 Z8. |
| C2 | Major | l.38, 97, 117, 134, 136 | The relation between `set_provider`, `resolve_provider`, `_build_provider` and the "shared resolver if needed" is unclear: one helper or two, and whether the two existing functions validate the same way today. Overlaps Stage 5 Z3. |
| C3 | Major | whole document | Core terms undefined: provider (SDMX never spelled out), preset, alias, custom provider dict and its fields, "provider value" (type `str \| dict` appears only at l.135). L.142 "the value `get_provider()` resolved from" is ambiguous: the returned config or the input it was built from? That decides what `ds["provider"]` holds. |
| C4 | Major | l.113, 130 | `multiprovider-reviewer` is a required gate for every phase but is never defined: script, CI job, agent or checklist? |
| C5 | Nit | l.113 | The invariant "no `if provider == ...`" has no reason or link to the project rule. |
| C6 | Nit | l.143 | `_dataset_scope(ds)` "entering `use_provider`-like scoping": does it call `use_provider` (re-validating) or set the ContextVar directly with the stored value? |
| C7 | Nit | l.144 | A3 (two threads, own scopes) is Phase 1 functionality but verified in Phase 2, with no reason. |
| C8 | Nit | l.48, 78 | TÜİK not expanded; why this provider needs a token is not said. |
| C9 | Nit | l.130 | `LOG.md` convention not explained. |
| C10 | Nit | Q3 l.126 vs plan | The plan uses `use_provider` while the name is still open in Q3. |
| C11 | Nit | l.138 | "Example runs offline against a mock": how a mock attaches to a README example, and where the check lives, is not said. |

No section was impossible to paraphrase: no Blockers.
