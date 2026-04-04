# Project Evaluation — opensdmx v0.2.6

Version: `0.2.6` — commit `2ce8921`

---

## Executive Summary

opensdmx is a Python CLI and library for SDMX 2.1 REST APIs with a clean modular architecture, solid multi-provider support (8 providers), and a well-designed two-layer cache. Since the previous evaluation (v0.2.2), the project has made substantial progress: CI is now active, test count grew from 4 to 64 (covering XML parsing, URL key building, filter logic, SQLite cache, provider management, and time-period parsing), and all Italian UI strings and the production debug log have been removed. The main remaining gaps are: heavy non-optional AI/plot dependencies for users who need only the core library, `cli.py` at 1,086 lines with `guide()` embedded, `duckdb` declared as a dependency but never imported, and `print_dataset()` using bare `print()` inconsistently with the rest of the CLI.

---

## Scores by dimension

| Dimension | Score | Brief note |
|---|---|---|
| Code quality and architecture | 4/5 | Clean layering, consistent conventions; `cli.py` very long |
| Test coverage and reliability | 3.5/5 | 64 tests, all pure-logic; zero HTTP/XML integration tests |
| Error handling and resilience | 3.5/5 | Retry + rate-limit solid; 27 broad `except Exception` catches |
| Documentation | 4/5 | README thorough, architecture documented; docstrings partial |
| Packaging and distribution | 3/5 | PyPI present; AI/plot deps not optional; `duckdb` orphaned |
| CI/CD | 3.5/5 | GitHub Actions on push/PR (pytest + ruff); no publish pipeline |
| Security | 4/5 | No hardcoded secrets; Gemini key documented in `.env.example` |
| Dependency management | 2.5/5 | Heavy mandatory deps; `duckdb` declared but unused |
| CLI UX and usability | 4.5/5 | Rich tables, stderr/stdout split, contextual hints, spinner |
| LOG.md and traceability | 5/5 | Detailed per-session entries, high-signal, consistent |

**Overall score: 3.7/5 — Solid foundation, not yet production-ready for broad PyPI distribution**

---

## Strengths

**Clear modular layering.** Nine modules with distinct responsibilities. Data flow is documented in `docs/architecture.md` and matches the actual code.

```
cli.py → discovery.py / retrieval.py → base.py (HTTP)
                  ↓                         ↓
            db_cache.py               utils.py / utils
embed.py / ai.py (optional features)
```

**Two-layer cache with TTL.** Parquet for the dataflow catalog (7-day TTL), SQLite for structure/codelist/constraints (30-day and 7-day). TTL is overridable via `OPENSDMX_*_CACHE_TTL` env vars. Cache is namespaced per provider under `~/.cache/opensdmx/{AGENCY_ID}/`.

**Retry and rate-limiting.** `sdmx_request` uses `tenacity` (3 attempts, exponential backoff, `reraise=True` to avoid wrapping in `RetryError`). The rate limiter uses a temp file, works cross-process, shows a countdown on stderr without polluting stdout.

**Multi-provider design.** `portals.json` with 8 providers; custom providers via URL; per-provider overrides for endpoint paths, data format, rate limit, and language. `--provider` / `-p` works on every subcommand. `OPENSDMX_PROVIDER` and `OPENSDMX_AGENCY` env vars for session-wide config.

**Test suite — major improvement.** 64 tests across 6 files, all pass in 0.46s. Coverage includes: `xml_parse()` namespace normalization (canonical and non-canonical prefixes), `xml_attr_safe()`, `xml_text_safe()`, `get_name_by_lang()` with fallback, `make_url_key()` with 7 parametrized cases, `set_filters()` / `reset_filters()` (copy semantics, case-insensitivity, unknown-dim warning), `get_dimension_values()` case-insensitivity, `parse_time_period()` for all 7 SDMX frequency types plus None/invalid, all SQLite cache operations with TTL expiry, and provider preset/custom-URL management.

**CI active.** GitHub Actions workflow runs `pytest` and `ruff` on every push and PR to `main`.

**CLI UX.** Rich tables with color, stderr/stdout separation (pipe-friendly), contextual hints on HTTP 400/404, spinners during slow operations, `--help` on all commands with concrete examples, large-dataset warning with `--yes` bypass.

**LOG.md.** High-signal chronological log of every development session. Serves as a reliable audit trail and decision history.

**Documentation.** README covers installation, CLI quick-start, Python API, all 8 providers, env vars, output formats, caching, and the sdmx-explorer agent skill. Supplementary docs: `architecture.md`, `cache.md`, `PRD.md`, `release.md`, `cli-test-examples.md`.

**Large-dataset guard.** `get` issues a probe request (`lastNObservations=1`) when no filters or limits are set and warns the user if series count exceeds 5,000. Bypassed with `--yes`.

---

## Weaknesses

### High — Non-optional heavy dependencies

`chatlas[google]`, `ollama`, `numpy`, `plotnine`, `inquirerpy`, `questionary` are in `dependencies` (not optional). A user who only needs `fetch()` or `get_data()` installs the full Gemini SDK, Ollama client, matplotlib backend, and interactive UI libraries. The core functionality (`search`, `info`, `constraints`, `get`) requires none of these.

Relevant section in `pyproject.toml` (all mandatory):

```toml
"numpy>=2.4.2",
"ollama>=0.6.1",
"plotnine>=0.15.3",
"inquirerpy>=0.3.4",
"questionary>=2.1.1",
"chatlas[google]>=0.7",
```

### High — `duckdb` declared but never imported

`duckdb>=1.4.4` is in `dependencies`. Zero occurrences of `import duckdb` or `from duckdb` in any source file. It is an orphaned dependency adding install weight with no benefit.

### Medium — `cli.py` monolithic (1,086 lines)

The `guide()` command alone is ~450 lines of interactive logic embedded in the main CLI file. It is hidden (`hidden=True`) but still adds to the module's cognitive load. It is a natural candidate for extraction to `cli_guide.py`.

### Medium — Zero HTTP/XML integration tests

All 64 tests cover pure logic. No test exercises the HTTP layer (even mocked with `httpx_mock` or `respx`). Regressions in `sdmx_request`, `sdmx_request_csv`, `all_available()`, or `get_data()` are not caught automatically before release.

### Medium — 27 broad `except Exception` clauses

22 in `cli.py`, 5 across other modules. Many are appropriate top-level guards, but some mask specific errors (e.g. distinguishing `httpx.ConnectError` from `httpx.HTTPStatusError`). The `_check_api_reachable()` function catches all exceptions and shows a generic "unreachable" message regardless of the actual cause.

### Low — `print_dataset()` uses bare `print()`

`discovery.py:229-244` uses `print()` rather than `rich.Console`. This is a public API function inconsistent with the rest of the output layer.

### Low — Global mutable state in `base.py`

`_active_provider`, `_timeout`, `_rate_limit_context` are module-level globals. Acceptable for the single-threaded CLI, but makes library mode non-thread-safe and requires manual cleanup in tests (`test_base.py` does not restore the original provider after each test).

### Low — No publish pipeline

Release is manual (`docs/release.md`). CI runs tests and linting but does not publish to PyPI on version tags.

---

## Architecture assessment

The layering is correct and consistent. `base.py` is the only module that does I/O (HTTP + file); everything above it is pure logic. `db_cache.py` is correctly isolated from HTTP — it only reads/writes SQLite. `utils.py` is stateless. `retrieval.py` depends only on `base` and `discovery`.

The provider abstraction via `portals.json` + `_DEFAULTS` merge is clean. Adding a new provider requires only a JSON entry with no code changes.

The dataset as a plain `dict` is simple but lacks type safety. A `TypedDict` or `@dataclass` would improve IDE autocompletion and catch typos in key names at development time.

The global `_active_provider` singleton works for CLI use but prevents concurrent multi-provider use in library mode. An explicit `SDMXClient` object would resolve this, but is a significant refactor not needed for the current use case.

---

## Code quality metrics

| Metric | Value |
|---|---|
| Total source lines | 2,628 |
| Modules | 9 (excluding `guide`) |
| Tests | 64 (6 files) |
| Test run time | 0.46s |
| Broad `except Exception` | 27 |
| `# type: ignore` | 11 |
| Italian strings in UI | 0 (all translated) |
| Production debug logs | 0 (removed) |
| Total commits | 51 |
| Providers supported | 8 |
| CI | pytest + ruff on push/PR |

---

## Dependency analysis

```
httpx, tenacity, lxml, polars, pyarrow, rich, typer    ← core (justified)
duckdb                                                   ← declared, NEVER imported — remove
numpy, plotnine                                          ← plot only (not optional)
ollama, chatlas[google]                                  ← semantic search + guide (not optional)
inquirerpy, questionary                                  ← interactive guide (not optional)
```

Minimum Python version is 3.12. Version pins are recent but justified (Polars API stability). The `pyarrow` dependency is justified for Polars Parquet I/O.

---

## Security

No hardcoded secrets in source. `.env.example` documents `GOOGLE_API_KEY` with a link to obtain one. All HTTP traffic goes to public SDMX APIs over HTTPS. The rate-limit file in `/tmp` is a minor race-condition surface in shared multi-user environments but is not a meaningful threat in practice.

---

## Progress since v0.2.2

| Issue from v0.2.2 | Status |
|---|---|
| Debug log `/tmp/guide_debug.log` in `ai.py` | Fixed |
| No CI/CD | Fixed — GitHub Actions added |
| 4 tests (1 file) | Fixed — 64 tests (6 files) |
| Italian strings in UI | Fixed — all translated |
| Gemini API key undocumented | Fixed — documented in `.env.example` |
| Non-optional AI deps | Still open |
| `duckdb` orphaned | Still open |
| `cli.py` monolithic | Worsened — grew from 971 to 1,086 lines |
| `print_dataset()` uses bare print | Still open |

---

## Prioritised recommendations

### P0 — Blocking for broad PyPI distribution

**Remove `duckdb` from dependencies.**
It is declared but never imported. One line removed from `pyproject.toml`, no code changes needed.

### P1 — High priority

**Make AI/plot dependencies optional.**
Split into extras so users who only need the data layer can install a lean package:

```toml
[project.optional-dependencies]
ai = ["ollama>=0.6.1", "chatlas[google]>=0.7", "inquirerpy>=0.3.4", "questionary>=2.1.1"]
plot = ["plotnine>=0.15.3", "numpy>=2.4.2"]
```

**Add HTTP mocked tests.**
Use `respx` or `pytest-httpx` to test at least `sdmx_request` retry logic, `sdmx_request_csv` format selection, and `all_available()` XML parsing against a fixture.

### P2 — Medium priority

**Extract `guide()` from `cli.py`.**
Move the 450-line interactive flow to `cli_guide.py`. Import and register in `cli.py`. No behavioural change.

**Add a publish step to CI.**
On a version tag, run `uv build` and `uv publish` (or `twine`). Eliminates manual PyPI release steps.

**Narrow some `except Exception` catches.**
Especially in `_check_api_reachable()` — distinguish `httpx.ConnectError` (network issue) from `httpx.HTTPStatusError` (server reachable but erroring) for better error messages.

**Restore provider after `test_base.py` tests.**
Add `set_provider("eurostat")` in a teardown or use `monkeypatch` to avoid state leakage between tests.

### P3 — Low priority

**Replace `print_dataset()` with Rich output.**
Replaces bare `print()` with `rich.Console` for consistency with the rest of the CLI.

**Type the dataset dict as `TypedDict`.**
Documents the shape, improves IDE autocomplete, reduces `# type: ignore` count.

---

## Hypothesis analysis

| Hypothesis | Result |
|---|---|
| Modular architecture, consistent layering | Confirmed — 9 modules, clean data flow, documented |
| Test coverage improved since v0.2.2 | Confirmed — 4 → 64 tests; still no HTTP integration tests |
| Dependencies well-managed | Partially confirmed — versions recent; `duckdb` orphaned; AI deps mandatory |
| CI now active | Confirmed — pytest + ruff on push/PR |
| CLI UX high quality | Confirmed — Rich output, pipe-friendly, contextual hints |

---

## Open questions

- Is `duckdb` planned for future use (e.g. in-process SQL on downloaded data)? If so, document the intent; if not, remove it now.
- Are `insee`, `abs` providers tested beyond the portals.json entry? Not referenced in `cli-test-examples.md`.
- Is the `gemini-2.5-flash` model hardcoded in `ai.py:161` intentional? A configurable model name (env var or CLI option) would increase portability.
- Is `guide` intended to remain hidden from the public CLI long-term? If yes, AI dependencies could be guarded with a runtime import error instead of being always installed.
