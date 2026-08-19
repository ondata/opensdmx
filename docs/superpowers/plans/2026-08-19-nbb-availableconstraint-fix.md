# NBB `availableconstraint` Retry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recover generically when an `availableconstraint` response cannot be parsed because `references` is rejected, without changing successful standard-provider requests.

**Architecture:** Keep the existing request as the first attempt inside `get_available_values()`. On `lxml.etree.XMLSyntaxError` only, retry the same `availableconstraint` path once with only `references` removed; every success path, explicit empty parameter set, `contentconstraint` path, timeout, HTTP status, cache, and fallback remains unchanged. Replace the CLI's unsupported-endpoint guess with a neutral empty-result error.

**Tech Stack:** Python 3.12+, httpx, lxml, Polars, Typer, pytest/unittest.mock, ruff, mypy, uv.

**Spec:** `docs/superpowers/specs/2026-08-19-nbb-availableconstraint-design.md`

## Global Constraints

- No NBB-specific URL or provider-name checks.
- No public API or configuration-schema additions.
- The first request for every provider must remain byte-for-byte equivalent in path and parameters.
- Retry at most once, only after XML parsing fails on `availableconstraint` and effective params contain `references`.
- Remove only `references`; preserve timeout, HTTP retry count, path, and every other query parameter.
- Do not change hub, `contentconstraint`, 404 fallback, timeout, `serieskeysonly`, or cache semantics.
- Do not include unrelated working-tree changes in commits.

---

## File map

- `src/opensdmx/discovery.py`: narrow XML parsing retry in `get_available_values()`.
- `src/opensdmx/cli.py`: neutral error when a constraint request returns no values.
- `tests/test_discovery.py`: request/retry behavior and standard-path regression guards.
- `tests/test_cli.py`: user-facing diagnosis regression test.
- `LOG.md`: implemented behavior and verified compatibility evidence.
- `tasks/todo.md`: execution checklist and final review; ignored project working document.

### Task 1: Capture the pre-fix compatibility baseline

**Files:**
- Modify: `tasks/todo.md`
- Use for isolated cache only: `tmp/nbb-constraints/baseline/`

**Interfaces:**
- Consumes: installed `opensdmx` 0.22.1 CLI and public SDMX endpoints.
- Produces: baseline provider, dataflow, exit code, dimensions/counts, and observed failure notes in `tasks/todo.md`.

- [x] **Step 1: Confirm the branch and preserve the dirty log**

Run:

```bash
git branch --show-current
git status --short
```

Expected: branch `fix/nbb-availableconstraint-retry`; `LOG.md` modified; no application files modified.

- [x] **Step 2: Run standard-provider probes with isolated caches**

Run each command independently and record exit code plus dimension/count summary:

```bash
OPENSDMX_CACHE_DIR=$PWD/tmp/nbb-constraints/baseline/eurostat opensdmx -o json constraints PRC_HICP_MANR --provider eurostat
OPENSDMX_CACHE_DIR=$PWD/tmp/nbb-constraints/baseline/abs opensdmx -o json constraints CPI --provider abs
OPENSDMX_CACHE_DIR=$PWD/tmp/nbb-constraints/baseline/bis opensdmx -o json constraints WS_LONG_CPI --provider bis
OPENSDMX_CACHE_DIR=$PWD/tmp/nbb-constraints/baseline/imf opensdmx -o json constraints WEO --provider imf
```

Expected: successful providers exit 0 with parseable JSON. If a public endpoint or chosen dataflow is unavailable, run `opensdmx search "" --all --provider PROVIDER` to distinguish external/catalog failure, record the exact exit/error, and do not treat it as a code regression.

- [x] **Step 3: Confirm the NBB failure before changing code**

Run:

```bash
OPENSDMX_CACHE_DIR=$PWD/tmp/nbb-constraints/baseline/nbb opensdmx constraints EXR --provider https://nsidisseminate-stat.nbb.be/rest
```

Expected: exit 1; `EntityRef: expecting ';'`; unsupported-endpoint guess present.

- [x] **Step 4: Record baseline in the task review**

Add a `Baseline` subsection to `tasks/todo.md` with the commands, current date, exit codes, stable result summaries, and explicitly labelled external failures.

### Task 2: Add failing request/retry tests

**Files:**
- Modify: `tests/test_discovery.py` near the existing contentconstraint fallback tests.

**Interfaces:**
- Consumes: `get_available_values(dataset: dict[str, Any]) -> dict[str, pl.DataFrame]`.
- Produces: regression contract for the private retry implemented in Task 3.

- [x] **Step 1: Add a minimal valid constraint fixture**

Add `get_available_values` to the discovery import used by this test section:

```python
from opensdmx.discovery import get_available_values
```

Then add:

```python
_AVAILABLE_CONSTRAINT_XML = b"""<?xml version="1.0"?>
<message:Structure
  xmlns:message="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message"
  xmlns:common="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common">
  <message:Structures>
    <common:KeyValue id="FREQ"><common:Value>A</common:Value></common:KeyValue>
  </message:Structures>
</message:Structure>"""
```

- [x] **Step 2: Add the NBB-shaped recovery test**

Add:

```python
def test_availableconstraint_parse_error_retries_without_references():
    provider = {
        **_ISTAT_PROVIDER,
        "constraint_endpoint": "availableconstraint",
        "constraint_params": {"references": "none", "mode": "available"},
    }

    with patch("opensdmx.discovery.get_provider", return_value=provider), \
         patch("opensdmx.db_cache.get_cached_available_constraints", return_value=None), \
         patch("opensdmx.db_cache.save_available_constraints"), \
         patch(
             "opensdmx.discovery.sdmx_request_xml",
             side_effect=[b"<not-xml", _AVAILABLE_CONSTRAINT_XML],
         ) as mock_req:
        result = get_available_values(_istat_dataset())

    assert result["FREQ"].to_series().to_list() == ["A"]
    assert mock_req.call_count == 2
    assert mock_req.call_args_list[0].kwargs["references"] == "none"
    assert mock_req.call_args_list[0].kwargs["mode"] == "available"
    assert "references" not in mock_req.call_args_list[1].kwargs
    assert mock_req.call_args_list[1].kwargs["mode"] == "available"
```

- [x] **Step 3: Add standard-path guards**

Add:

```python
def test_availableconstraint_valid_xml_does_not_retry():
    provider = {
        **_ISTAT_PROVIDER,
        "constraint_endpoint": "availableconstraint",
        "constraint_params": {"references": "none"},
    }

    with patch("opensdmx.discovery.get_provider", return_value=provider), \
         patch("opensdmx.db_cache.get_cached_available_constraints", return_value=None), \
         patch("opensdmx.db_cache.save_available_constraints"), \
         patch(
             "opensdmx.discovery.sdmx_request_xml",
             return_value=_AVAILABLE_CONSTRAINT_XML,
         ) as mock_req:
        result = get_available_values(_istat_dataset())

    assert result["FREQ"].to_series().to_list() == ["A"]
    assert mock_req.call_count == 1
    assert mock_req.call_args.kwargs["references"] == "none"


def test_contentconstraint_parse_error_does_not_retry():
    with patch("opensdmx.discovery.get_provider", return_value=_ISTAT_PROVIDER), \
         patch("opensdmx.db_cache.get_cached_available_constraints", return_value=None), \
         patch("opensdmx.db_cache.save_available_constraints"), \
         patch("opensdmx.discovery.sdmx_request_xml", return_value=b"<not-xml") as mock_req:
        result = get_available_values(_istat_dataset())

    assert result == {}
    assert mock_req.call_count == 1


def test_availableconstraint_without_references_parse_error_does_not_retry():
    provider = {
        **_ISTAT_PROVIDER,
        "constraint_endpoint": "availableconstraint",
        "constraint_params": {},
    }

    with patch("opensdmx.discovery.get_provider", return_value=provider), \
         patch("opensdmx.db_cache.get_cached_available_constraints", return_value=None), \
         patch("opensdmx.db_cache.save_available_constraints"), \
         patch("opensdmx.discovery.sdmx_request_xml", return_value=b"<not-xml") as mock_req:
        result = get_available_values(_istat_dataset())

    assert result == {}
    assert mock_req.call_count == 1


def test_availableconstraint_retry_parse_error_stops_after_second_attempt(caplog):
    provider = {
        **_ISTAT_PROVIDER,
        "constraint_endpoint": "availableconstraint",
        "constraint_params": {"references": "none"},
    }

    with patch("opensdmx.discovery.get_provider", return_value=provider), \
         patch("opensdmx.db_cache.get_cached_available_constraints", return_value=None), \
         patch("opensdmx.db_cache.save_available_constraints"), \
         patch(
             "opensdmx.discovery.sdmx_request_xml",
             side_effect=[b"<first-bad", b"<second-bad"],
         ) as mock_req:
        result = get_available_values(_istat_dataset())

    assert result == {}
    assert mock_req.call_count == 2
    assert "Could not retrieve available values" in caplog.text
```

- [x] **Step 4: Run the new tests and confirm the recovery test fails**

Run:

```bash
uv run pytest tests/test_discovery.py -k "parse_error or valid_xml_does_not_retry" -v
```

Expected before implementation: the NBB-shaped test fails because only one request occurs and the result is empty; standard guards pass under current behavior.

- [x] **Step 5: Commit only the failing tests**

Run:

```bash
git add tests/test_discovery.py
git commit -m "test: cover constraint parsing retry"
```

### Task 3: Implement the narrow parsing retry

**Files:**
- Modify: `src/opensdmx/discovery.py:14-35`
- Modify: `src/opensdmx/discovery.py:1150-1158`

**Interfaces:**
- Consumes: `sdmx_request_xml(...) -> bytes`, `_parse_constraint_xml(bytes) -> dict[str, list[str]]`, effective `constraint_params`.
- Produces: unchanged `get_available_values()` return type; one private compatibility retry with no new public symbol.

- [x] **Step 1: Import the concrete XML exception namespace**

Add with third-party imports:

```python
from lxml import etree
```

- [x] **Step 2: Wrap only parsing with the compatibility retry**

Replace the direct parse with the following minimal structure inside the existing outer `try`:

```python
content = sdmx_request_xml(
    path,
    _timeout=constraint_timeout,
    _max_retries=constraint_max_retries,
    **constraint_params,
)
try:
    result = _parse_constraint_xml(content)
except etree.XMLSyntaxError:
    if constraint_endpoint != "availableconstraint" or "references" not in constraint_params:
        raise
    retry_params = {
        name: value
        for name, value in constraint_params.items()
        if name != "references"
    }
    logger.warning(
        "availableconstraint response could not be parsed for %s; retrying without references",
        df_id,
    )
    content = sdmx_request_xml(
        path,
        _timeout=constraint_timeout,
        _max_retries=constraint_max_retries,
        **retry_params,
    )
    result = _parse_constraint_xml(content)
```

Do not catch HTTP failures in the inner block and do not mutate `constraint_params`.

- [x] **Step 3: Run the new request/retry tests**

Run:

```bash
uv run pytest tests/test_discovery.py -k "parse_error or valid_xml_does_not_retry" -v
```

Expected: all selected tests pass; recovery uses two calls and every guard uses one.

- [x] **Step 4: Run discovery and HTTP regression suites**

Run:

```bash
uv run pytest tests/test_discovery.py tests/test_http.py -q
```

Expected: all tests pass.

- [x] **Step 5: Commit implementation only**

Run:

```bash
git add src/opensdmx/discovery.py
git commit -m "fix: retry unparseable constraints"
```

### Task 4: Correct the CLI diagnosis

**Files:**
- Modify: `tests/test_cli.py` after the existing constraints command tests.
- Modify: `src/opensdmx/cli.py:765-770`.

**Interfaces:**
- Consumes: empty mapping from `get_available_values()`.
- Produces: exit 1 with a factual message and no unsupported-endpoint speculation.

- [x] **Step 1: Add a failing CLI regression test**

Add:

```python
def test_constraints_empty_result_does_not_guess_endpoint_unsupported():
    with patch("opensdmx.cli._check_api_reachable"), \
         patch("opensdmx.load_dataset", return_value=_fake_constraints_dataset()), \
         patch("opensdmx.discovery.get_available_values", return_value={}):
        result = runner.invoke(app, ["constraints", "TEST_DF", "--provider", "istat"])

    assert result.exit_code == 1
    assert "No constrained values returned" in result.output
    assert "may not support" not in result.output
```

- [x] **Step 2: Run the test and verify it fails**

Run:

```bash
uv run pytest tests/test_cli.py::test_constraints_empty_result_does_not_guess_endpoint_unsupported -v
```

Expected before the CLI change: FAIL because output contains `may not support`.

- [x] **Step 3: Make the message factual**

Replace the two-string message with:

```python
err_console.print(
    "[red]Error:[/red] No constrained values returned by the constraint endpoint."
)
```

- [x] **Step 4: Run CLI tests**

Run:

```bash
uv run pytest tests/test_cli.py -q
```

Expected: all CLI tests pass.

- [x] **Step 5: Commit test and message together**

Run:

```bash
git add tests/test_cli.py src/opensdmx/cli.py
git commit -m "fix: report empty constraints factually"
```

### Task 5: Run full gates and compare live providers

**Files:**
- Modify: `LOG.md`
- Modify: `tasks/todo.md`

**Interfaces:**
- Consumes: completed implementation and Task 1 baseline.
- Produces: verified branch with recorded evidence and no unrelated diff.

- [x] **Step 1: Run static and full test gates**

Run:

```bash
uv run ruff check src/ tests/
uv run mypy src/opensdmx
uv run pytest tests/ -q
```

Expected: all commands exit 0. If ruff reports a pre-existing script-only issue, it is irrelevant because the command is scoped to `src/ tests/`; no unrelated cleanup is allowed.

- [x] **Step 2: Repeat the standard-provider probes**

Repeat Task 1 with new isolated directories under `tmp/nbb-constraints/after/`. Compare exit codes and dimension/count summaries with the baseline. Successful baseline providers must remain successful with the same dimension/count summaries; externally unavailable providers must show no new local traceback or request-shape change.

- [x] **Step 3: Verify NBB from a clean cache**

Run:

```bash
OPENSDMX_CACHE_DIR=$PWD/tmp/nbb-constraints/after/nbb opensdmx -o json constraints EXR --provider https://nsidisseminate-stat.nbb.be/rest
```

Expected: exit 0 with `DATA_DOMAIN=27`, `REF_AREA=1`, `INDICATOR=945`, `COUNTERPART_AREA=3`, and `FREQ=4`.

- [x] **Step 4: Update delivery records**

Revise the top `LOG.md` entry so it states the implemented retry, neutral CLI message, focused/full gate counts, and live standard/NBB comparisons. Mark `tasks/todo.md` items complete and add a `Review` section with exact results and any external limitations.

- [x] **Step 5: Inspect the complete branch diff**

Run:

```bash
git diff --check main...HEAD
git diff --stat main...HEAD
git status --short
```

Expected tracked scope: design, plan, `discovery.py`, `cli.py`, their tests, and `LOG.md`. `tasks/todo.md` may remain ignored. No cache or `tmp/` material is tracked.

- [x] **Step 6: Commit documentation and plan**

Run:

```bash
git add LOG.md docs/superpowers/plans/2026-08-19-nbb-availableconstraint-fix.md
git commit -m "docs: record constraint retry fix"
```

- [x] **Step 7: Final branch verification**

Run:

```bash
git status --short
git log --oneline main..HEAD
```

Expected: clean tracked worktree and concise commits for spec, tests, implementation, CLI diagnosis, and delivery record.
