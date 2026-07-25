# Territorial classification

How opensdmx determines the territorial granularity of a dataflow — national, region, province, municipality, … — from the geographic codes it actually exposes.

## Overview (provider-agnostic)

opensdmx is multi-provider, and every provider encodes geography differently: a dedicated dimension (`ITTER107`, `REF_AREA`, `geo`, `REGION`, …) whose codelist follows that provider's own hierarchy (Italian ISTAT codes, Eurostat NUTS, Ukrainian KATOTTG, …).

Two ideas are shared across providers:

- **We read the codes actually present, per dataflow.** The constraints archive (`scripts/constraints_archive.py`) queries the best discovery endpoint per provider and records, for each dataflow, the codes that really exist for each dimension — stored in `data/constraints/<provider>.parquet` as `(df_id, dimension_id, code_id)`. This is a per-**dataflow** fact: the same survey can publish some cuts at municipality level and others only at region level.

- **Classifying a code into a level is provider-specific.** Because each provider's code scheme is different, the rule that maps a code to a level (national → … → municipality) is written once per provider. Today **ISTAT** is implemented; other providers are documented as future sections below.

> The level is a property of the published **dataflow** (the specific table/cut), not of the underlying survey. A survey that *collects* municipal data may publish a given table only at province or region level. For the survey-level view (what a survey *can* reach), see the SIQual notes — the two are complementary.

## ISTAT — `CL_ITTER107` / `REF_AREA`

Implemented in `scripts/constraints_archive.py` (`classify_territorial_code`, `rebuild_istat_territorial`); output in `data/constraints/istat_territorial.csv`.

### 1. Reading the codes

For each dataflow we query the ISTAT databrowser **hub** (`databrowserhub/api/core`, sub-second, no DSD call) and store the codes present per dimension in `data/constraints/istat.parquet`.

### 2. Identifying the territorial dimension

We keep the dimension whose id **starts with `ITTER`** (older dataflows) **or equals `REF_AREA`** (newer ones) — same `CL_ITTER107` code hierarchy — **plus any dimension ISTAT names as territorial via the `GEO_ID` annotation**.

Some dataflows carry their territory on a differently-named dimension (`RESIDENCE_TERR`, `REGION_OF_STUDY`, …). ISTAT declares the exception on the dataflow with a `GEO_ID` annotation, captured as the `df_geo_dim` catalog column. `GEO_ID` is set on only ~27 dataflows, but it reveals the *names*, which appear on many more (`RESIDENCE_TERR` alone on ~79). We collect the distinct `df_geo_dim` values across the catalog and add them to the territorial-dimension set, so each discovered name is classified **wherever it occurs** — e.g. this is what puts the births survey (`RESIDENCE_TERR`) into the view.

**Gate on the name, never on code shape.** A dimension is territorial only if its id is in the set; only then are its codes classified by format. The 6-digit municipality pattern also matches non-geographic classifications (`ECOICOP_2`, `COICOP_REV_ISTAT`), so widening by code shape would misclassify them — the `GEO_ID` name-gating is the safeguard.

### 3. Classifying a single code

An ISTAT territorial code *encodes* its level in its shape, so five regex rules suffice — no lookup table:

| Level | Code pattern | Example |
|---|---|---|
| national (`nazionale`) | `IT` | `IT` (Italy) |
| macro-area (`ripartizione`) | `IT` + 1 char | `ITC` (North-west) |
| region (`regione`) | `IT` + 2 chars | `ITC4` (Lombardy) |
| province (`provincia`) | `IT` + 3 chars | `IT108` (Monza e Brianza) |
| municipality (`comune`) | 6 digits | `015146` (Milan) |

Anything else — aggregates (`IT108_NC`, `FILTER__*`), foreign areas — matches no pattern and is **ignored**.

### 4. Deriving the dataflow level

Per `(df_id, territorial dimension)`:

- collect the **set of levels** seen across its codes;
- `max_level` = the **deepest** level present (order: national → ripartizione → region → province → municipality);
- `levels` = the full chain, e.g. `nazionale|regione|provincia`;
- `n_territories` = total count of territorial codes.

Written one row per `(df_id, dimension_id)` to `data/constraints/istat_territorial.csv` — usually one row per dataflow, but a dataflow with more than one territorial dimension (e.g. `REF_AREA` + `RESIDENCE_TERR`) gets a row each, so their code counts and levels never conflate.

**Worked example** — same survey, two cuts, classified correctly:

| df_id | title | max_level | n_territories |
|---|---|---|---|
| `122_54_DF_DCSC_TUR_1` | Accommodation capacity … - com. | **comune** | 12,471 |
| `122_54_DF_DCSC_TUR_2` | Hotel size - prov. | **provincia** | 139 |

### 5. Caveats

- **Per dataflow, not per survey.** `max_level` is the granularity of the specific published cut, not of the survey.
- **`max_level` reflects the codes present, not that every cell is populated.** For municipal cuts `n_territories` is typically the full codelist (~12,471); whether every municipality actually carries data is a further check. For the question "does this dataflow reach municipality level?", `max_level` is reliable.
- **Incremental coverage.** The archive grows a few dataflows per scheduled run, so not every dataflow is classified yet.

## Other providers (future)

The same shape applies; only the dimension name and the code→level rule change. Sketches for when they are implemented:

- **Eurostat** — dimension `geo`, NUTS codes: country (`IT`), NUTS 1/2/3 by code length (`ITC`, `ITC4`, `ITC4C`). Note the overlap with ISTAT is coincidental — the classifier must be selected by provider, never shared blindly.
- **Derzhstat (Ukraine)** — dimension `REGION`, KATOTTG codes; region names resolved via `constraints`.
- **Others** — add a per-provider classifier and a `rebuild_<provider>_territorial` step mirroring the ISTAT one; declare any dimension-name quirk in `portals.json` rather than hardcoding it.
