## Why

Portal-specific quirks (Eurostat needs `detail=allstubs`, uses `contentconstraint` instead of `availableconstraint`, etc.) are currently scattered across Python code. A declarative `portals.json` bundled in the package makes it easy to add new SDMX portals and centralizes all portal differences in one file.

## What Changes

- New `src/opensdmx/portals.json` file with ~10 portal definitions (eurostat, istat, ecb, oecd, etc.)
- `base.py`: `PROVIDERS` dict loaded from `portals.json` instead of hardcoded; `get_provider()` merges portal config with defaults
- `discovery.py`: reads `dataflow_params`, `constraint_endpoint`, `datastructure_agency` from active provider config instead of hardcoded values
- Remove hardcoded `PROVIDERS` dict from `base.py`

## Capabilities

### New Capabilities

- `portal-config`: declarative portal configuration via bundled JSON file with per-portal endpoint quirks, defaults for missing fields, and custom provider support

### Modified Capabilities

- `provider-system`: `set_provider()` now looks up portals from JSON; `get_provider()` returns merged config with defaults; discovery code reads quirk fields from provider config

## Impact

- `base.py`: `PROVIDERS` replaced by JSON loading + default merging
- `discovery.py`: `all_available()` uses `dataflow_params`; `get_available_values()` uses `constraint_endpoint`; `_get_dimensions()` uses `datastructure_agency`
- `portals.json`: new file in `src/opensdmx/`
