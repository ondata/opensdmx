# ISTAT Data Browser Hub API

ISTAT's public web interface ([esploradati.istat.it](https://esploradati.istat.it)) is built
on the [.Stat Suite](https://sis-cc.gitlab.io/dotstatsuite-documentation/) platform. The
frontend communicates with a backend hub layer — `/databrowserhub/api/` — that is separate
from the official SDMX 2.1 REST endpoint (`/SDMXWS/rest/`).

> **Status**: this is the data browser's internal API. It is not an officially documented
> public endpoint and carries no stability guarantee. Tested on 2026-05-10 against
> `esploradati.istat.it`.

The hub API is relevant because the SDMX REST `availableconstraint` endpoint times out on
large Italian datasets (e.g. road accident statistics at province/municipality level), while
the hub returns the same information in sub-second time.

---

## Base URL

```
https://esploradati.istat.it/databrowserhub/api/core/nodes/1
```

The `1` is the node ID observed in practice. It may vary across deployments.

## Required headers

```
Accept: application/json
userlang: it
```

No authentication is required.

---

## Endpoints

### Catalog

```
GET /catalog
```

Returns the full thematic tree: category groups, nested categories, and dataset identifiers
attached to each leaf.

**Response structure**:

```json
{
  "categoryGroups": [
    {
      "id": "IT1,Z0810HEA,1.0",
      "label": "Salute e sanità",
      "categories": [
        {
          "id": "HEA_ROAD",
          "label": "Incidenti stradali",
          "childrenCategories": [],
          "datasetIdentifiers": [
            "IT1,41_270_DF_DCIS_MORTIFERITISTR1_1,1.0",
            "IT1,41_983_DF_DCIS_INCIDMORFER_COM_1,1.0"
          ]
        }
      ]
    }
  ]
}
```

Tested result: 23 top-level groups, 849 categories, 3743 dataset identifiers in a single call.

---

### Dataset structure

```
GET /datasets/{dataset_id}/structure
```

Where `{dataset_id}` is the full ISTAT identifier, e.g.
`IT1,41_270_DF_DCIS_MORTIFERITISTR1_1,1.0`.

Returns dimension IDs and labels. The dimension list matches the SDMX DSD, with `TIME_PERIOD`
made explicit as an additional entry.

**Response excerpt**:

```json
{
  "criteria": [
    {"id": "FREQ",     "label": "Frequenza"},
    {"id": "REF_AREA", "label": "Territorio"},
    {"id": "RESULT",   "label": "Esito"},
    {"id": "TIME_PERIOD", "label": "Tempo"}
  ],
  "optimizedData": false
}
```

---

### All dimension values (bulk — preferred)

```
GET /datasets/{dataset_id}/columns/partial/values
```

Returns the values **actually present** for **all dimensions at once** in a single request.
Response time is ~2 s for datasets with 10+ dimensions — the same cost as a single
per-dimension call. This is the endpoint used by the Data Browser UI and is the preferred
discovery path.

`TIME_PERIOD` is included in the response but should be handled separately (it is a
`TimeDimension`, not a codelist dimension).

**Response structure**:

```json
{
  "criteria": [
    {
      "id": "FREQ",
      "values": [{"id": "A", "name": "annuale", "isDefault": false, "isSelectable": true}]
    },
    {
      "id": "REF_AREA",
      "values": [
        {"id": "IT",     "name": "Italia",   "isDefault": false, "isSelectable": true},
        {"id": "ITG12",  "name": "Palermo",  "isDefault": false, "isSelectable": true},
        {"id": "015146", "name": "Milano",   "isDefault": false, "isSelectable": true}
      ]
    },
    {"id": "TIME_PERIOD", "values": [{"id": "2023", "name": "2023"}]}
  ]
}
```

`obsCount` may appear at top level; `null` indicates a bulk/glossary container with no
queryable data (~80 of the 3743 catalog entries, identifiable by the `DF_BULK_` prefix).

---

### Single dimension values (fallback)

```
GET /datasets/{dataset_id}/column/{dim_id}/partial/values
```

Returns the values **actually present** in the dataset for a single dimension, with Italian
labels and total observation count. Responds in ~500 ms even for `REF_AREA` with 8716 codes.

Use this endpoint only as a fallback when the bulk endpoint is unavailable. The response
structure is identical to a single entry in the `criteria` array of the bulk response.

The `partial` segment in the path suggests the endpoint may support pagination or filtering;
this was not investigated.

---

### Data (filtered)

```
POST /datasets/{dataset_id}/data
Content-Type: application/json
```

Request body: a JSON array of filter objects.

```json
[
  {"id": "FREQ",        "filterValues": ["A"],      "type": "CodeValues", "period": 0},
  {"id": "REF_AREA",    "filterValues": ["015146"], "type": "CodeValues", "period": 0},
  {"id": "RESULT",      "filterValues": ["M"],      "type": "CodeValues", "period": 0},
  {"id": "TIME_PERIOD", "type": "TimePeriod",        "period": 1, "filterValues": []}
]
```

`"period": 1` on `TIME_PERIOD` requests the most recent period.

**Response structure** (JSON-stat-like):

```json
{
  "id":    ["FREQ", "REF_AREA", "DATA_TYPE", "RESULT", "TIME_PERIOD"],
  "size":  [1, 1, 1, 1, 1],
  "value": {"0": 22}
}
```

Typical response time: ~466 ms (backend timer: ~186 ms).

---

## Worked examples

### Fatal road accidents in Milan (municipality), 2024

Dataset: `41_983_DF_DCIS_INCIDMORFER_COM_1` (Incidenti, morti e feriti — comuni)

```bash
# Step 1 — discover the Milano municipality code
curl -s \
  "https://esploradati.istat.it/databrowserhub/api/core/nodes/1/datasets/IT1,41_983_DF_DCIS_INCIDMORFER_COM_1,1.0/column/REF_AREA/partial/values" \
  -H "userlang: it" -H "Accept: application/json" \
  | jq -r '.criteria[0].values[] | select(.name | ascii_downcase | contains("milano")) | "\(.id)=\(.name)"'
# → 015146=Milano  (municipality)
# → ITC45=Milano   (province)

# Step 2 — query the SDMX REST endpoint with a precise key
# Dimension order from opensdmx info: FREQ · REF_AREA · DATA_TYPE · RESULT
curl -s -H "Accept: text/csv" \
  "https://esploradati.istat.it/SDMXWS/rest/data/41_983_DF_DCIS_INCIDMORFER_COM_1/A.015146.KILLINJ.M?lastNObservations=1"
# → OBS_VALUE=38  (38 fatalities, Milan municipality, 2024)
```

---

### Fatal road accidents in Palermo (province), 2024

Dataset: `41_270_DF_DCIS_MORTIFERITISTR1_1` (Morti e feriti — 11 SDMX dimensions)

This dataset causes timeouts on both `availableconstraint` and `serieskeysonly`. The hub
returns all dimension values in sub-second time, enabling a precise SDMX REST query.

```bash
# Step 1 — get all dimension values via hub (run once per dimension)
for DIM in FREQ REF_AREA DATA_TYPE ACCIDENT_LOCALIZATON INTERSECTION \
           TY_ROAD_ACCIDENT RESULT PERSON_CLASS AGE SEX MONTH; do
  echo "--- $DIM ---"
  curl -s \
    "https://esploradati.istat.it/databrowserhub/api/core/nodes/1/datasets/IT1,41_270_DF_DCIS_MORTIFERITISTR1_1,1.0/column/$DIM/partial/values" \
    -H "userlang: it" -H "Accept: application/json" \
    | jq -r '.criteria[0].values[] | "\(.id)=\(.name)"'
done

# Aggregate codes found:
#   ACCIDENT_LOCALIZATON=9 (totale), INTERSECTION=9, TY_ROAD_ACCIDENT=9
#   RESULT=M (morto), PERSON_CLASS=9, AGE=TOTAL, SEX=9, MONTH=99

# Step 2 — SDMX REST with fully specified 11-dimension key
# Dimension order: FREQ · REF_AREA · DATA_TYPE · ACCIDENT_LOCALIZATON · INTERSECTION
#                  · TY_ROAD_ACCIDENT · RESULT · PERSON_CLASS · AGE · SEX · MONTH
curl -s -H "Accept: text/csv" \
  "https://esploradati.istat.it/SDMXWS/rest/data/41_270_DF_DCIS_MORTIFERITISTR1_1/A.ITG12.KILLINJ.9.9.9.M.9.TOTAL.9.99?lastNObservations=1"
# → OBS_VALUE=55  (55 fatalities, Palermo province, 2024)
```

The same query via `opensdmx get` without explicit codes timed out after 15+ minutes.
The precise-key SDMX REST call returned in under 5 seconds.

---

## Relationship with the SDMX REST endpoint

The hub API and the SDMX REST endpoint (`/SDMXWS/rest/`) serve different roles:

| Operation | SDMX REST | Hub API |
|---|---|---|
| Dataset catalog | `categoryscheme` (~24 MB, slow) | `GET /catalog` (single call, fast) |
| Dimension values | `availableconstraint` (timeouts on large datasets) | `GET /column/{DIM}/partial/values` (sub-second) |
| Data download | `GET /data/{key}` (works well with precise keys) | `POST /data` (JSON body, ~466ms) |

For value discovery on ISTAT, `column/{DIM}/partial/values` is a practical alternative to
`availableconstraint` when the latter times out.

---

## Why the hub solves the `41_270` timeout problem

`41_270_DF_DCIS_MORTIFERITISTR1_1` (morti e feriti in incidenti stradali) has 11 SDMX
dimensions. Any SDMX REST query that leaves even one dimension as a wildcard triggers a
server-side cartesian product that the backend cannot complete within any practical timeout.

### What fails and why

The standard discovery flow on ISTAT uses `availableconstraint` to retrieve the codes
actually present in the dataset before building a query. For `41_270`, this endpoint never
responds — it times out after 30+ seconds with zero bytes received. The automatic fallback
to `data?detail=serieskeysonly` also times out, because the server has to enumerate all
valid series keys across 11 dimensions. A probe `GET` with partial wildcards (tested with
`--REF_AREA 082053 --RESULT M`, nine other dimensions left as `.`) also timed out after
over 15 minutes in two independent tests.

The root cause is server-side: ISTAT's SDMX endpoint executes a full cross-join across
all unspecified dimensions before filtering. With 11 dimensions the search space is too
large regardless of how tight the specified filters are.

### Why the hub does not have this problem

The hub `column/{DIM}/partial/values` endpoint returns the valid values for **one
dimension at a time**, independently of the others. There is no cross-join. Each call
costs ~500–650 ms regardless of dataset size or dimension count. For `41_270`:

```
11 dimensions × ~600 ms each ≈ 6.6 s total discovery time
```

versus the SDMX REST `availableconstraint` approach: **no response at all**.

### The resulting workflow

Once all dimension values are known, the SDMX REST data endpoint works fine — it is only
slow when wildcards force a server-side enumeration. A fully specified 11-dimension key
returns in under 5 seconds:

```
A.ITG12.KILLINJ.9.9.9.M.9.TOTAL.9.99
└─┬──┘ └─┬───┘ └──┬──┘ └┬┘ └┬┘ └┬┘ └┬┘ └─┬─┘└──┬──┘ └┬┘ └┬─┘
  A    Palermo  KILLINJ  9   9   9  M   9  TOTAL  9   99
FREQ  REF_AREA  DATA_TY  LOC INT TYP RES PERSON AGE  SEX MON
```

Result: `OBS_VALUE=55` (55 fatalities, Palermo province, 2024) — from a query that
previously produced only timeouts.

The key insight is that the SDMX REST data endpoint is not slow; the bottleneck is
**value discovery**. The hub eliminates that bottleneck entirely.

---

## References

- [.Stat Suite documentation](https://sis-cc.gitlab.io/dotstatsuite-documentation/using-api/data/)
- ISTAT SDMX API guide: [ondata.github.io/guida-api-istat](https://ondata.github.io/guida-api-istat)
- `tmp/problemi_istat.md` — diagnosis and timeline of SDMX REST timeout issues
