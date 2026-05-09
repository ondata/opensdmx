# Provider Proposals

Proposals for improvements that SDMX data providers could implement on their side to make
opensdmx (and any SDMX 2.1 client) more usable. Each section targets a specific provider,
documents the empirically observed problem, and describes the requested change.

---

## ISTAT

### P-ISTAT-01: Honor the key filter in `availableconstraint`

**Status:** Not implemented (verified 2026-05-09)

#### Problem

The SDMX 2.1 REST specification allows clients to pass a dimension key when querying the
`availableconstraint` endpoint:

```
GET /availableconstraint/{flowRef}/{key}/{providerRef}?mode=available
```

The `{key}` parameter lets the client pre-filter the constraint by fixing one or more
dimension values. For example, to retrieve only the codes that exist for the municipality
of Palermo (ISTAT code `082053`):

```
GET https://esploradati.istat.it/SDMXWS/rest/availableconstraint/
        22_289_DF_DCIS_POPRES1_24/.082053..../all?mode=available
```

**ISTAT accepts the URL (HTTP 200)** but ignores the key filter entirely. The response
contains all 8,128 Italian municipalities regardless of the `.082053....` key — identical
to calling the endpoint without any key:

```
# Response with key filter .082053....
REF_AREA: 8128 values — ['001001', '001002', '001003', ...]
```

As a result, the response takes **~77 seconds** to arrive even with the filter, because the
server performs a full-cube scan. For large datasets ("all municipalities × single ages",
~8k × 100+ dimensions), the unfiltered call consistently exceeds the 90-second client
timeout and is unusable.

#### Impact

- `opensdmx constraints` fails with a timeout for any "all municipalities" dataset
  (e.g., `22_289_DF_DCIS_POPRES1_24`, `22_289_DF_DCIS_POPRES1_22`, …)
- Users cannot discover which codes are valid for a specific territory without fetching
  the full data response
- Any SDMX 2.1 client that relies on `availableconstraint` for code validation is blocked
  on these datasets

#### Requested change

Implement server-side filtering in the `availableconstraint` response: when a key is
provided, restrict the enumerated code combinations to only those dimension slices that
match the key. A correct implementation of the example above would return:

```
REF_AREA: 1 value — ['082053']
DATA_TYPE: 1 value — ['JAN']
SEX: 3 values — ['1', '2', '9']
AGE: 102 values — ['TOTAL', 'Y_GE100', 'Y0', 'Y1', …]
…
```

This would reduce response time from ~77s to sub-second for a single-municipality query,
making the endpoint practical for interactive use.

#### Workaround (client-side)

Until the server is fixed, opensdmx bypasses the constraint step on timeout and falls
back to direct `data` requests using codes from the static codelist (`/codelist`). This
is less reliable because codelists contain all theoretically possible codes, not just
those present in the dataset.

---
