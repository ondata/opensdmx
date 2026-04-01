## Context

Portal-specific quirks are hardcoded in `discovery.py` and `base.py`. Adding a new portal requires editing Python code in multiple places. A `portals.json` centralizes all portal config.

## Goals / Non-Goals

**Goals:**
- Bundled `portals.json` with ~10 portals, loaded once at import
- Per-portal fields for endpoint quirks (dataflow params, constraint endpoint, datastructure agency)
- Sane defaults so a minimal entry needs only `base_url` + `agency_id`
- `set_provider("name")` does lookup in JSON; `set_provider(url, ...)` still works for custom

**Non-Goals:**
- User-level config file (`~/.config/opensdmx/portals.json`)
- CLI for managing portals (`opensdmx portal add`)
- Online portal registry
- SDMX 3.0 endpoint variants

## Decisions

### D1: JSON bundled in package at `src/opensdmx/portals.json`

Loaded via `importlib.resources` (or `Path(__file__).parent / "portals.json"`). Simpler than `__file__` for editable installs but both work. Using `Path(__file__).parent` for simplicity.

### D2: Default values applied at load time

```python
_DEFAULTS = {
    "rate_limit": 0.5,
    "language": "en",
    "dataflow_params": {},
    "constraint_endpoint": "availableconstraint",
    "datastructure_agency": "ALL",
}
```

Each portal entry is merged with `_DEFAULTS` so only `base_url`, `agency_id`, and `name` are required.

### D3: Discovery code reads config fields

- `all_available()`: `sdmx_request_xml(path, **provider["dataflow_params"])`
- `get_available_values()`: `path = f"{provider['constraint_endpoint']}/{df_id}"`
- `_get_dimensions()`: `path = f"datastructure/{provider['datastructure_agency']}/{structure_id}"`

### D4: Custom providers get defaults too

`set_provider(url, agency_id="X")` creates a dict merged with `_DEFAULTS`, same as JSON entries.

## Risks / Trade-offs

- **JSON schema drift**: no validation at load time → could silently ignore typos. Mitigation: keep it simple, only ~10 entries, easy to spot errors.
- **Eurostat `contentconstraint` path format**: may need `{agency},{df_id}` instead of just `{df_id}`. → Test during implementation, adjust path template if needed.
