## Context

The `opensdmx values` command shows the full codelist for a dimension (all theoretically possible codes). Users building queries need to know which codes are actually present in a specific dataflow — different dataflows use different subsets of any given codelist.

The backend logic already exists:
- `get_available_values(dataset)` in `discovery.py` calls the `availableconstraint` SDMX endpoint and returns a dict of `{dim_id: DataFrame({"id": codes})}`
- `get_cached_available_constraints(df_id)` / `save_available_constraints(df_id, data)` in `db_cache.py` handle SQLite caching with a 7-day TTL (`_TTL = 7 * 86400`)
- The cache table `available_constraints` already exists in the schema

The only missing piece is a CLI command that loads the dataset, calls `get_available_values`, and renders the result — optionally filtered to a single dimension and enriched with human-readable labels.

## Goals / Non-Goals

**Goals:**
- Expose `opensdmx constraints <dataflow_id> [dimension]` as a new CLI command
- Without `[dimension]`: show all dimensions with count of available codes
- With `[dimension]`: show the available codes for that dimension with labels (merged from codelist via `get_dimension_values`)
- Respect `--provider` like all other commands
- Use the existing 7-day SQLite cache transparently

**Non-Goals:**
- No new cache infrastructure — reuse what exists
- No changes to the `availableconstraint` endpoint handling
- No output format options (no `--out`, no `--format`) in this iteration

## Decisions

**Reuse `get_available_values` directly**
The function already handles provider-specific endpoint variants (`availableconstraint` vs `contentconstraint`), XML parsing, and caching. The CLI command wraps it rather than reimplementing it.

**Labels via `get_dimension_values`**
When a specific dimension is requested, merge available codes with the full codelist labels using the existing `get_dimension_values(dataset, dimension_id)`. This gives the user the code + name, same style as `opensdmx values`. Codes present in the constraints but missing from the codelist are shown without a label (rare edge case).

**Single dimension as optional argument (not `--flag`)**
Consistent with `opensdmx values <dataflow_id> <dimension>` — positional argument, not a flag.

**Summary table for all-dimensions view**
When no dimension is specified, show a table with columns `dimension_id`, `n_values`, `sample` (first 3 codes). This gives a quick overview without flooding the terminal.

## Risks / Trade-offs

`get_available_values` falls back silently with a warning if the endpoint fails (returns `{}`). The CLI command should surface this as a clear error to the user rather than showing an empty table.

[Provider doesn't support `availableconstraint`] → The command warns the user and exits early. No crash.

[Cache stale for 7 days] → Acceptable: constraint data changes rarely. Users can force a refresh by clearing the cache with `opensdmx blacklist` (or a future `--no-cache` flag).

## Open Questions

- Should `opensdmx constraints` without a dimension show a compact summary (recommended) or the full list of all codes for all dimensions? Full list can be very large.
