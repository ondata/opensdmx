# INPS DataBrowser middleware API

Reference for the `.Stat Suite` DataBrowser middleware that backs the `inps`
provider. INPS publishes its statistical observatories through this middleware
only: the classic SDMX-REST NSI Web Service is blocked by a WAF for external
access, so opensdmx talks exclusively to `api/core`.

All INPS logic lives in `src/opensdmx/inps.py`, gated by `hub_only: true` in
`portals.json`. Calls go through `base.sdmx_request(..., _base_url=hub, _method=...)`,
inheriting rate-limit, retry, file-lock and User-Agent handling.

## Base URL

```
https://opendata.inps.it/databrowser/api/core
```

## Nodes (observatories)

The middleware is split into four nodes. In the SPA URL the node appears as a
*code*; the middleware requires the numeric *nodeId*. Passing the code instead of
the id silently falls back to another node, so always use the id. The map lives
in `portals.json` under `hub_nodes`:

| Observatory | code (SPA URL) | nodeId |
|---|---|---|
| Pensioni | `pensioni` | 2 |
| Lavoratori dipendenti | `dipendenti` | 3 |
| Imprese | `imprese` | 4 |
| Politiche Occupazionali (NASPI/DIS-COLL) | `politiche_occupazionali` | 1 |

Static source: `GET /hub/minimalInfo` → `.nodes[] | {nodeId, code, name}`.

## Endpoints used by opensdmx

| Purpose | Method + path | opensdmx use |
|---|---|---|
| Catalog (dataflows + category tree) | `GET /nodes/{n}/catalog` | `tree`, `search`, `all_available`, `df→node` index |
| Structure (dimensions/DSD) | `GET /nodes/{n}/datasets/{agency},{flow},{ver}/structure` | `info` |
| Available values per dimension | `POST /nodes/{n}/datasets/{ds}/PartialCodelists/{DIM}` (body `[]`) | `constraints`, `values` |
| Data download (full) | `POST /nodes/{n}/datasets/{ds}/download/csv` (body `[]`) | `get` (full download + client-side filter) |

Dataset identifier: `{agency},{flow},{version}` → e.g. `INPS,DFB_ST_DIP_ATECO_REG_01,1.0`.

### Catalog shape

```json
{"categoryGroups": [{"categories": [
  {"id": "OS15", "label": "...", "childrenCategories": [ ... ],
   "datasetIdentifiers": ["INPS,DFB_...,1.0", ...]}
]}],
 "datasetMap": {"INPS,DFB_...,1.0": {"title": "..."}}}
```

- Dataflow titles come from `datasetMap[full_id].title`; the leaf-category label
  is a fallback.
- Each observatory's top category (OS06/OS10/OS11/OS15) is exposed as a *scheme*.
  Some (e.g. Imprese/OS11) hang datasets directly off the top category with no
  children — that top category is then also emitted as a depth-1 category.

### Structure shape

```json
{"criteria": [{"id": "TERRITORIO", "label": "Territory of work",
               "extra": {"DataStructureRef": "INPS+CL_HIER_TERRITORIO_REG+1.0"}}, ...],
 "timeDimension": "TIME_PERIOD", "territorialDimension": "TERRITORIO"}
```

- Dimension order = array order (position 1..N). `TIME_PERIOD` (the
  `timeDimension`) is excluded from the ordinary dimension list.
- `codelist_id` is parsed from `extra.DataStructureRef` (`INPS+CL_X+1.0` → `CL_X`).
- `label` is used as the dimension description in `info`.

### PartialCodelists shape and territory hierarchy

```json
{"criteria": [{"id": "TERRITORIO",
  "values": [{"id": "ITC4", "name": "Lombardia", "isSelectable": true}, ...]}]}
```

- Body `[]` returns the root level. For a hierarchical dimension a value flagged
  `isSelectable: false` is a parent; its children are fetched with body
  `[{"id": DIM, "values": [{"id": PARENT}]}]`. The adapter recurses only into
  non-selectable parents, so flat codelists stay a single request.
- Territory codes are NUTS 2021 (Lombardia = `ITC4`).

## No server-side data filter

The middleware does not filter data server-side: `POST .../download/csv` with a
criteria body still returns the whole dataflow (verified by tracing the
DataBrowser SPA — it downloads everything and filters client-side in web
workers). `opensdmx get` therefore downloads the full SDMX-CSV and filters
client-side (dimension filters, plus a by-year period window since the
middleware ignores `startPeriod`/`endPeriod`), mirroring the
`data_key_format: "empty"` pattern used by Derzhstat. Privacy-suppressed cells
carry `_` in OBS_VALUE and are read as null.

## Formats on `download/{format}`

| `{format}` | Content-Type | Note |
|---|---|---|
| `csv` | `application/vnd.sdmx.data+csv` | SDMX-CSV (the one to use) |
| `genericdata` | `…genericdata+xml` | SDMX 2.1 GenericData |
| `structurespecificdata` | `…structurespecificdata+xml` | SDMX 2.1 SS |
| `sdmx-csv` | `…data+json` | misleading name — returns SDMX-JSON |
