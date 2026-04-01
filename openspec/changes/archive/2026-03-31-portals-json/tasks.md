## 1. Create portals.json

- [x] 1.1 Create `src/opensdmx/portals.json` with `eurostat` and `istat` entries (all fields)
- [x] 1.2 Research and add additional portals: ECB, OECD, INSEE, Bundesbank, World Bank, ABS

## 2. Load portals in base.py

- [x] 2.1 Replace hardcoded `PROVIDERS` dict with JSON loading from `portals.json`
- [x] 2.2 Define `_DEFAULTS` dict and merge with each portal entry at load time
- [x] 2.3 Update `set_provider()` to merge custom providers with `_DEFAULTS`
- [x] 2.4 Verify `get_provider()` always returns a complete dict with all fields

## 3. Wire quirk fields into discovery.py

- [x] 3.1 `all_available()`: pass `provider["dataflow_params"]` to `sdmx_request_xml`
- [x] 3.2 `get_available_values()`: use `provider["constraint_endpoint"]` for path
- [x] 3.3 `_get_dimensions()`: use `provider["datastructure_agency"]` for path

## 4. Verify

- [x] 4.1 Test `opensdmx search unemployment` (Eurostat default)
- [x] 4.2 Test `opensdmx search disoccupazione -p istat`
- [x] 4.3 Test custom provider via Python API
