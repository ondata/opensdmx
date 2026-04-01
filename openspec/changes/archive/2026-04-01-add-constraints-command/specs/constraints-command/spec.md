## ADDED Requirements

### Requirement: List all constrained dimensions
The CLI SHALL provide a `constraints <dataflow_id>` command that queries the SDMX
`availableconstraint` endpoint and returns, for each dimension, the number of values
actually present in that dataflow and a short sample of those values.

#### Scenario: All dimensions summary
- **WHEN** user runs `opensdmx constraints APRO_CPNH1`
- **THEN** the system displays a table with columns `dimension_id`, `n_values`, `sample` (first 3 codes) for every dimension that has constrained values

#### Scenario: Provider respected
- **WHEN** user runs `opensdmx constraints <dataflow_id> --provider istat`
- **THEN** the system queries the ISTAT provider's constraint endpoint instead of Eurostat

#### Scenario: Endpoint not supported
- **WHEN** the active provider does not support the `availableconstraint` endpoint
- **THEN** the system exits with a clear error message explaining that constraints are not available for this provider

### Requirement: Show constrained values for a single dimension
The CLI SHALL accept an optional positional argument `[dimension]`. When provided,
the system SHALL return the full list of codes actually present in that dataflow for
that dimension, enriched with human-readable labels from the codelist.

#### Scenario: Dimension values with labels
- **WHEN** user runs `opensdmx constraints APRO_CPNH1 crops`
- **THEN** the system displays a two-column table (`id`, `name`) containing only the codes present in the dataflow for that dimension, with labels resolved from the codelist

#### Scenario: Codes without labels
- **WHEN** a code is present in the constraints but absent from the codelist
- **THEN** the system displays the code with an empty or `—` label (no error)

#### Scenario: Invalid dimension name
- **WHEN** user requests a dimension that does not exist in the dataflow structure
- **THEN** the system exits with an error listing the valid dimension names

### Requirement: Cache constraint results
The system SHALL cache the result of each `availableconstraint` query per dataflow
in SQLite with a 7-day TTL. Subsequent calls within the TTL period SHALL return
the cached result without making a network request.

#### Scenario: Cache hit
- **WHEN** `constraints` is called for a dataflow that was already queried within the last 7 days
- **THEN** the result is returned from cache and no HTTP request is made

#### Scenario: Cache miss
- **WHEN** `constraints` is called for a dataflow with no cached data or expired cache
- **THEN** the system queries the SDMX endpoint, displays the result, and saves it to cache
