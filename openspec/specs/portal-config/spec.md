## ADDED Requirements

### Requirement: Bundled portals.json
The package SHALL include a `portals.json` file at `src/opensdmx/portals.json` containing portal definitions for at least `eurostat` and `istat`.

#### Scenario: File exists in package
- **WHEN** the package is installed
- **THEN** `portals.json` is available alongside the Python modules

### Requirement: Portal entry schema
Each portal entry SHALL have required fields `base_url`, `agency_id`, `name` and optional fields `rate_limit`, `language`, `dataflow_params`, `constraint_endpoint`, `datastructure_agency`. Missing optional fields SHALL use defaults: `rate_limit=0.5`, `language="en"`, `dataflow_params={}`, `constraint_endpoint="availableconstraint"`, `datastructure_agency="ALL"`.

#### Scenario: Minimal portal entry
- **WHEN** a portal entry has only `base_url`, `agency_id`, and `name`
- **THEN** `get_provider()` returns a dict with all fields populated from defaults

#### Scenario: Full portal entry
- **WHEN** a portal entry specifies all fields including `dataflow_params`
- **THEN** `get_provider()` returns the exact values from JSON, no defaults applied for those fields

### Requirement: Dataflow params per portal
`all_available()` SHALL pass `dataflow_params` from the active provider as extra query parameters to the dataflow endpoint.

#### Scenario: Eurostat with allstubs
- **WHEN** active provider is `eurostat` with `dataflow_params: {"detail": "allstubs", "references": "none"}`
- **THEN** the dataflow request includes `?detail=allstubs&references=none`

#### Scenario: ISTAT with no extra params
- **WHEN** active provider is `istat` with `dataflow_params: {}`
- **THEN** the dataflow request has no extra query parameters

### Requirement: Constraint endpoint per portal
`get_available_values()` SHALL use `constraint_endpoint` from the active provider to build the API path.

#### Scenario: ISTAT uses availableconstraint
- **WHEN** active provider has `constraint_endpoint: "availableconstraint"`
- **THEN** the path is `availableconstraint/{df_id}`

#### Scenario: Eurostat uses contentconstraint
- **WHEN** active provider has `constraint_endpoint: "contentconstraint"`
- **THEN** the path uses the contentconstraint endpoint

### Requirement: Datastructure agency per portal
`_get_dimensions()` SHALL use `datastructure_agency` from the active provider instead of hardcoded `"ALL"`.

#### Scenario: ISTAT uses ALL
- **WHEN** active provider has `datastructure_agency: "ALL"`
- **THEN** the path is `datastructure/ALL/{structure_id}`

#### Scenario: Eurostat uses ESTAT
- **WHEN** active provider has `datastructure_agency: "ESTAT"`
- **THEN** the path is `datastructure/ESTAT/{structure_id}`

### Requirement: Custom providers get defaults
`set_provider(url, agency_id=...)` SHALL merge the custom dict with the same defaults used for JSON entries.

#### Scenario: Custom provider with minimal args
- **WHEN** `set_provider("https://x.org/rest", agency_id="X")` is called
- **THEN** `get_provider()` returns `constraint_endpoint="availableconstraint"`, `datastructure_agency="ALL"`, etc.
