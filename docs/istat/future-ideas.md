# Future ideas — faster ISTAT access via hub + SDMX REST

This file collects ideas for combining the ISTAT hub API (`/databrowserhub/api/`) with the
SDMX REST endpoint (`/SDMXWS/rest/`) to eliminate the performance problems described in
`tmp/problemi_istat.md` and documented in `hub-api.md`.

None of these are committed plans. They are design directions for discussion.

---

## The core opportunity

The hub API and the SDMX REST endpoint are complementary:

- **Hub**: fast catalog, fast dimension value discovery, no wildcards needed
- **SDMX REST**: standard, cacheable, works perfectly with fully-specified keys

The bottleneck today is value discovery. Replacing `availableconstraint` with
`column/{DIM}/partial/values` removes the bottleneck entirely and makes even the most
complex ISTAT datasets (11 dimensions, millions of observations) queryable in seconds.

---

## Idea 1 — hub as fallback for `get_available_values()`

**Current fallback chain** in `discovery.py:get_available_values()`:

```
1. SQLite cache (7 days)
2. availableconstraint  → 30s timeout on large datasets
3. serieskeysonly       → timeout on 9+ dimensions
4. codelist superset    → not implemented
5. return {}            → user gets nothing
```

**Proposed chain with hub**:

```
1. SQLite cache (7 days)
2. hub column/{DIM}/partial/values  → ~500ms, never times out
3. availableconstraint              → kept as cross-check for non-ISTAT providers
4. return {} with clear message
```

For ISTAT specifically, step 2 could be gated by a provider config flag
(`hub_values_url`) so other providers are unaffected. The hub URL and node ID would
be stored in the provider config.

The result of step 2 is ground truth (not a theoretical codelist superset), so steps
3–4 of the old chain become unnecessary for ISTAT.

---

## Idea 2 — hub-derived `source` field

The `source` field discussed in issue #26 becomes straightforward once the hub is
integrated. `get_available_values()` would return:

```python
{"dim_id": DataFrame, "source": "hub" | "constraint" | "serieskeysonly" | "cache"}
```

The CLI could surface this as:

```
RESULT   3 values  [source: hub]   M=morto  F=ferito  9=totale
```

This is low-effort once the hub call is in place.

---

## Idea 3 — hub catalog as primary catalog cache

Today `opensdmx tree --provider istat` triggers a SDMX `categoryscheme` fetch (~24 MB,
slow on first call). The hub `/catalog` endpoint returns the same hierarchy — 23 groups,
849 categories, 3743 datasets — in a single fast call, already structured with
`datasetIdentifiers` attached to each leaf.

Replacing the SDMX categoryscheme fetch with the hub catalog would:

- Eliminate the slow first-load for `tree`
- Return `datasetIdentifiers` already associated to categories (no separate
  `categorisation` parsing needed)
- Keep the SDMX-native path as fallback for providers without a hub

The hub catalog uses the same category IDs (`Z0810HEA`, `HEA_ROAD`) as the SDMX
categoryscheme, so the rest of the tree navigation code would require minimal changes.

---

## Idea 4 — `opensdmx constraints` backed by hub for ISTAT

`opensdmx constraints <df_id> --provider istat` currently fails silently on large
datasets. With the hub, it could iterate over all dimensions via `column/{DIM}/partial/values`
and return a complete constraints table — same output format, different data source.

Since each dimension call is independent, they can run in parallel (subject to the ISTAT
rate limit on the hub, which appears more permissive than the SDMX REST limit).

This would make `opensdmx constraints` reliable for all ISTAT datasets without changing
the user-facing interface.

---

## Idea 5 — hub POST `/data` as direct download path

For small, targeted queries (e.g. last observation for a specific territory and
indicator), the hub POST `/data` endpoint may be faster and simpler than constructing
a full SDMX REST URL:

```python
# Instead of:
curl ".../SDMXWS/rest/data/DF/A.015146.KILLINJ.M?lastNObservations=1"

# Use:
POST ".../databrowserhub/api/core/nodes/1/datasets/IT1,DF,1.0/data"
body: [{FREQ:A}, {REF_AREA:015146}, {DATA_TYPE:KILLINJ}, {RESULT:M}, {TIME_PERIOD:last1}]
```

The response is a JSON-stat-like object rather than CSV/SDMX-XML, so it would require
a dedicated parser. Worth evaluating for interactive use cases (skill queries, MCP tool
responses) where a single value or small table is needed and CSV overhead is unnecessary.

---

## Idea 6 — `DF_BULK_*` surface in `opensdmx search`

The hub catalog contains 80 `DF_BULK_*` datasets (identifiable by `obsCount: null`).
These are pre-aggregated bulk downloads, not explorable via constraints. Currently they
appear in search results but fail silently.

Two options:
- Filter them out of search results entirely
- Label them explicitly: `[bulk download]` — user downloads as-is, no constraint
  exploration

The hub catalog makes this detection trivial at catalog-load time, with no additional
API calls.

---

## Caveats and open questions

- The hub API is `.Stat Suite`'s internal frontend API. It has no stability contract.
  Any integration should degrade gracefully if the hub is unavailable (fall through to
  the existing SDMX REST chain).
- The `node/1` ID should be confirmed stable or made configurable in provider settings.
- The `partial` segment in `column/{DIM}/partial/values` suggests pagination may exist.
  Large dimensions (REF_AREA: 8716 codes) returned fully in one call, but this should
  be tested with a deliberate page-size parameter to confirm there is no silent
  truncation.
- Hub rate limits: not characterised. The 5-dataflow test ran ~7 calls per dataflow
  without throttling, but production use (iterating all dimensions, all datasets) should
  be monitored.
- If ISTAT upgrades to SDMX 3.0, the `schema` query with `referencepartial` would make
  the hub workaround unnecessary. The hub integration should be designed as a temporary
  bridge, not a permanent dependency.
