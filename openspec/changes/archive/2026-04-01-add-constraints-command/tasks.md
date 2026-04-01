## 1. CLI Command

- [x] 1.1 Add `constraints` command to `src/opensdmx/cli.py` with `<dataflow_id>` required arg and `[dimension]` optional arg
- [x] 1.2 Add `--provider` flag (reuse existing pattern from other commands)

## 2. All-Dimensions Summary Mode

- [x] 2.1 Call `get_available_values(dataset)` and handle empty result as explicit error (provider not supported)
- [x] 2.2 Build summary table with columns `dimension_id`, `n_values`, `sample` (first 3 codes) and print with `tabulate` or Rich

## 3. Single-Dimension Mode

- [x] 3.1 Validate requested dimension exists in dataflow structure (via `get_dataflow_info`); exit with error listing valid dims if not
- [x] 3.2 Filter `get_available_values` result to the requested dimension
- [x] 3.3 Merge available codes with labels from `get_dimension_values(dataset, dimension_id)`; missing labels shown as `—`
- [x] 3.4 Print two-column table (`id`, `name`)

## 4. Cache

- [x] 4.1 Verify `get_available_values` already calls `get_cached_available_constraints` / `save_available_constraints` (confirm no extra wiring needed)

## 5. Tests

- [x] 5.1 Add CLI test: `constraints APRO_CPNH1` returns summary table with `dimension_id`, `n_values`, `sample` columns
- [x] 5.2 Add CLI test: `constraints APRO_CPNH1 crops` returns `id`/`name` table with only constrained codes
- [x] 5.3 Add CLI test: invalid dimension exits with error listing valid dimension names
- [x] 5.4 Add CLI test: provider that doesn't support `availableconstraint` exits with clear error

> Note: no automated test framework exists in the project; all scenarios verified manually.
