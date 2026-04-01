## Why

`opensdmx values` returns the full codelist for a dimension — all theoretically possible codes — not the codes actually present in a specific dataflow. To build a valid query, users need to know which values are available in that dataflow. Currently there is no CLI command for this; the only option is calling the SDMX `availableconstraint` endpoint manually.

## What Changes

- New CLI command `opensdmx constraints <dataflow_id> [dimension]` that queries the SDMX `availableconstraint` endpoint and returns the codes actually present in the dataflow
- Without `[dimension]`: shows all dimensions with their available codes and count
- With `[dimension]`: shows only the codes for that specific dimension, with human-readable labels (merged from the codelist)
- Respects the active `--provider` flag like all other commands
- Results cached in SQLite per (dataflow, dimension) with a 7-day TTL (already implemented in `db_cache.py` via `available_constraints` table)

## Capabilities

### New Capabilities
- `constraints-command`: CLI command that queries the SDMX `availableconstraint` endpoint and returns the real, constrained values for a dataflow's dimensions — optionally filtered to a single dimension, with labels

### Modified Capabilities

## Impact

- New command entry in `src/opensdmx/cli.py`
- New function in `src/opensdmx/discovery.py` (reuses existing `get_available_values` logic, already implemented but not exposed via CLI)
- SQLite cache reuse: `get_cached_available_constraints` / `save_available_constraints` already exist in `src/opensdmx/db_cache.py`
- No breaking changes
