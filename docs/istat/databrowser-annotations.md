# ISTAT dataflow annotations — what the SDMX Istat Toolkit reveals

Findings from exploring [sdmxistattoolkit.github.io](https://sdmxistattoolkit.github.io/), the site of the **SDMX Istat Toolkit** (StatKit) — the open-source software suite ISTAT builds and publishes.

The question behind this pass: *is there anything in ISTAT's own tooling that we could query and currently do not?* The answer is yes, and the entry point is the **annotation mechanism**.

Evidence date: 2026-07-25. The annotation census was run against the live ISTAT catalog on that day.

---

## Platform identification — a correction

`docs/istat/hub-api.md` states that esploradati.istat.it is built on the [.Stat Suite](https://sis-cc.gitlab.io/dotstatsuite-documentation/) platform. **That is wrong.**

esploradati runs the **StatKit Data Browser**, ISTAT's own product. The Data Browser user manual (Release 4.0, Feb 2025, §3.7 *Application deployment*, p. 36) states verbatim:

> The "app/databrowserhub/api/core" folder contains the main web service.

`databrowserhub/api/core` is exactly the path opensdmx targets in `portals.json:47` (`hub_base_url`). The same manual shows `http://localhost/databrowser/api/core` as the external REST URL — the path INPS uses.

Consequences:

- The hub API we treat as undocumented belongs to an application with a public **146-page manual** and downloadable source. The manual is not an API reference (it is install/admin/user documentation), but the software itself is published.
- ISTAT and INPS very likely run the **same software**, not two bespoke middlewares. `docs/inps/middleware-api.md` carries the same `.Stat Suite` misattribution. *(Inferred from path shape plus the manual; not confirmed by comparing live response envelopes.)*

Sources: `Manuals/DataBrowser_Install+User manual_4.0.0.pdf` and `Software/databrowser_v4.1.11_2025-03-03/` in the site repo (branch `master`, not `main`).

---

## The annotation mechanism

The Data Browser drives nearly all of its per-dataflow behaviour from **SDMX annotations** set in the Meta&Data Manager: table layout, default filters, keywords, territorial dimension, update date, notes, attached files, visibility. Manual §5.3.6 lists roughly 25 of them.

These annotations travel in the ordinary `/dataflow` SDMX response. **Any SDMX client can read them — including ours.**

### What ISTAT actually populates

One call (`dataflow/IT1/all?references=none`, 13.6 MB, 4,899 dataflows) gives the full census. **29 distinct annotation types** are in use (31 raw keys, minus 2 parse artefacts):

| Annotation | Dataflows | % | Used by opensdmx |
|---|---:|---:|---|
| `DDBDataflow` | 4,511 | 92.1% | — (internal hash) |
| **`LAST_UPDATE`** | 4,511 | 92.1% | **no** |
| `METADATA_URL` | 3,974 | 81.1% | **yes** (`annotations.metadata_url`) |
| **`LAYOUT_ROW`** | 3,945 | 80.5% | **no** |
| **`LAYOUT_COLUMN`** | 3,945 | 80.5% | **no** |
| **`LAYOUT_FILTER`** | 3,941 | 80.4% | **no** |
| **`NOT_DISPLAYED`** | 3,118 | 63.6% | **no** |
| **`DATAFLOW_CATALOG_TYPE`** | 664 | 13.6% | **no** |
| **`NonProductionDataflow`** | 620 | 12.7% | **no** |
| **`DEFAULT`** | 594 | 12.1% | **no** |
| **`ATTACHED_DATA_FILES`** | 366 | 7.5% | **no** |
| **`DATAFLOW_HIDDEN`** | 217 | 4.4% | **no** |
| **`DATAFLOW_NOTES`** | 145 | 3.0% | **no** |
| `LAYOUT_DATAFLOW_KEYWORDS` | 144 | 2.9% | **yes** (`annotations.keywords`) |
| `LAYOUT_ROW_SECTION` | 137 | 2.8% | no |
| `CRITERIA_SELECTION` | 124 | 2.5% | no |
| `LAYOUT_REFERENCE_METADATA` | 119 | 2.4% | no — but 107/119 duplicate `METADATA_URL` |
| `LAYOUT_CRITERIA_SELECTION` | 69 | 1.4% | no |
| `LAYOUT_NUMBER_OF_DECIMALS` | 39 | 0.8% | no |
| `LAYOUT_EMPTY_CELL_PLACEHOLDER` | 38 | 0.8% | no |
| `LAYOUT_DATAFLOW_NOTES` | 21 | 0.4% | no |
| `READY_FOR_PRODUCTION` | 17 | 0.3% | no |
| `LAYOUT_TERRITORIAL_DIMENSION_IDS` | 16 | 0.3% | no |
| `GEO_ID` | 11 | 0.2% | no |
| `LAYOUT_DATAFLOW_SOURCE` | 3 | 0.1% | no |
| `LAYOUT_ATTACHED_DATA_FILES` | 3 | 0.1% | no |
| `LINkEDDATAFLOWNODE` | 2 | 0.0% | no |
| `AnnotationServiceURL` | 2 | 0.0% | no |
| `AnnotationStructureURL` | 2 | 0.0% | no |

**We read 2 of 29.**

Note the literal spelling `LINkEDDATAFLOWNODE` — lowercase `k`. A parser must match ISTAT's strings exactly as published, typos included.

---

## Findings, ranked by value

### 1. 643 dataflows are hidden in ISTAT's own portal — 14% of our search results. Label them, do not filter them.

620 dataflows carry `NonProductionDataflow=true` and 217 carry `DATAFLOW_HIDDEN`; the union is **643 (13.1% of the catalog)**. Our `dataflows.parquet` holds all 4,899 — the flags are dropped at parse time, so every one of them is searchable and embeddable.

Measured on real searches against the local cache:

| Query | Results | Hidden by ISTAT | of which `ONLY_FILE` |
|---|---:|---:|---:|
| popolazione | 50 | 13 (26%) | 10 |
| prezzi | 50 | 6 | 3 |
| turismo | 13 | 4 | 3 |
| imprese | 50 | 4 | 3 |
| occupazione | 50 | 3 | 1 |
| **total** | **213** | **30 (14.1%)** | — |

**The obvious remedy — filter them out — is wrong**, and this was verified rather than assumed. The flagged set splits in two:

- **364 are `ONLY_FILE`** (see finding 2): bulk zips, not queryable cubes.
- **277 are ordinary dataflows** with no attached file. These include `CPI` (Consumer prices), `POP` (Population), `EMP` (Employment), `UEM` (Unemployment), `IND` (Industrial production) — the short-ID `ECOFIN_DSD` series.

A live probe settles it. `CPI`, flagged `NonProductionDataflow=true`, returns valid and current data:

```
$ opensdmx -o csv get CPI --REF_AREA IT --FREQ M --last-n 3 -y
DATAFLOW,DATA_DOMAIN,REF_AREA,INDICATOR,COUNTERPART_AREA,FREQ,TIME_PERIOD,OBS_VALUE,...
IT1:CPI(1.0),CPI,IT,PCPI_IX,_Z,M,2025-12-01,122.6,,,0,,
```

So `NonProductionDataflow` is a **catalog-visibility decision, not a data-availability one**. Filtering on it would delete working datasets from search. The right treatment is to expose the flag as a column and let ranking (or the user) decide — deprioritize, label, never silently drop.

### 2. `DATAFLOW_CATALOG_TYPE=ONLY_FILE` marks 364 dataflows that are not queryable

All 364 have an `ATTACHED_DATA_FILES` annotation, and **all 364 are already flagged non-production or hidden** — the overlap is total. They are bulk-download entries (`DCSS_BULK_ABITAZIONI`, `DF_BULK_COECPA`, …) whose payload is a zip, not an SDMX cube.

They are the worst kind of search result for an agent: they look like dataflows and are expected to fail on `get`. They are not junk — they are *bulk downloads*, and should be presented as such.

### 3. `ATTACHED_DATA_FILES` — 366 direct bulk downloads

Format is `URL|LABEL`, 319 pointing at zips:

```
https://esploradati.istat.it/databrowser/DWL/PERMPOP/MUN/DCSS_ABITAZIONI - Conventional dwellings - full dataset.csv.zip|DOWNLOAD_ZIP
```

Full-dataset CSVs, published by ISTAT, bypassing SDMX entirely. For a whole-dataset pull this is faster than any paginated SDMX query — and it is exactly the scenario where the ISTAT rate limit hurts most.

### 4. `LAST_UPDATE` on 92.1% of dataflows — freshness we do not expose

An update timestamp per dataflow, on 4,511 of 4,899. We have nothing equivalent today: we cannot answer "was this refreshed recently?" or sort by recency, and cache invalidation stays time-based rather than change-based.

**Caveat: the format is inconsistent.** 3,491 are ISO 8601 (`2026-07-22T08:34:26.801Z`), 1,020 are `dd/mm/yyyy HH:MM:SS` (`01/03/2022 10:03:43`). A parser needs both branches. Distribution by year is plausible (1,851 in 2026, 587 in 2025), so the field is maintained, not vestigial.

### 5. `LAYOUT_ROW` / `LAYOUT_COLUMN` / `LAYOUT_FILTER` — ISTAT's own view of which dimensions matter

On ~80% of dataflows, ISTAT declares how the dataset should be pivoted:

```
LAYOUT_ROW    = TYPE_OF_CROP
LAYOUT_COLUMN = TIME_PERIOD
LAYOUT_FILTER = FREQ,REF_AREA,DATA_TYPE
```

This is a curated answer to the question the `sdmx-explorer` skill asks at every exploration: *which dimensions are the interesting ones, and which are just filters?* Today we infer it from cardinality. Here the data owner states it outright — and `LAYOUT_FILTER` naming `REF_AREA` also flags the territorial dimension.

### 6. `DATAFLOW_NOTES` — 145 methodological caveats we do not surface

Free prose, e.g.:

> PROVINCIAL data are not perfectly comparable with those in similar tables published: prior to 2017, following the abolition of the provinces of Olbia-Tempio, Ogliastra…

Exactly the kind of warning that should reach anyone comparing a time series across a boundary change. Per `docs/descriptions.md`, embeddings currently use `df_id`, title, category context, the harvested METADATA_API description (~81%) and keywords (~3%) — **notes are not among them**, neither for search nor for display.

### 7. `NOT_DISPLAYED` on 63.6%, `DEFAULT` on 594

`NOT_DISPLAYED` lists dimensions/items ISTAT suppresses in its UI (mean 9.5 entries per dataflow — mostly note attributes). `DEFAULT` gives starting filter values (`FREQ=M`, `FREQ=A`) — a sane default query for a dataflow, straight from the publisher.

### 8. `CRITERIA_SELECTION` — a possible lead on the `availableconstraint` problem

Values: `PartialAllOptimized` (85), `PartialAll` (65), `PartialStep` (36), `FullAll` (2), `Dynamic` (1). These configure how the Data Browser resolves valid filter combinations — the same job as the `availableconstraint` endpoint that times out for us (see `docs/provider-proposals.md`, P-ISTAT-01). `PartialAllOptimized` suggests ISTAT flags dataflows with an optimized resolution path; the manual also documents a "Dataflow has optimized version" annotation.

Lead, not a conclusion — worth a targeted probe.

### 9. `GEO_ID` — low coverage by design, and it lands exactly where our heuristic fails

`GEO_ID` (11) and `LAYOUT_TERRITORIAL_DIMENSION_IDS` (16) name the territorial dimension of a dataflow. 27 of 4,899 looks negligible — it is not. **Not one of them points at `ITTER107` or `REF_AREA`:**

| Dimension named by the annotation | Dataflows |
|---|---:|
| `RESIDENCE_TERR` | 20 |
| `REGION_OF_STUDY` | 3 |
| `PLACE_COMM_CRIME` | 2 |
| `TERR_REGISTRATION` | 2 |

The reason is structural: the Data Browser takes the territorial dimension ids from **node configuration** (manual §4.2.2 — "Territorial dimensions Ids … for example: ITTER107, REF_AREA, COM"), and the per-dataflow annotation exists only to override that default. ISTAT sets it precisely when the dimension is *not* called the usual thing.

That is the same assumption `docs/territorial-classification.md` makes (§2: keep dimensions starting with `ITTER` or equal to `REF_AREA`), so the annotation covers our exact blind spot. Measured against `data/constraints/istat.parquet`: **31 dimensions across 272 dataflows** carry ISTAT-shaped territorial codes without matching our rule — `RESIDENCE_TERR` alone appears in 79. Caveat in the other direction: the 6-digit municipality pattern also matches non-geographic classifications (`ECOICOP_2`, `COICOP_REV_ISTAT`), so the dimension id must gate the code shape, never the reverse.

`LAYOUT_REFERENCE_METADATA` (119) is **mostly redundant**: 107 of 119 hold a URL identical to that dataflow's `METADATA_URL`, which we already harvest. Only 9 carry it without a `METADATA_URL`. Not worth a pass of its own.

---

## If any of this gets implemented

New annotation reads must be declared in the provider's `annotations` block in `portals.json` (`{stable_key: {type, value: text|title|presence}}`) and read through the shared single-pass reader — never behind a per-provider `if`. Since ISTAT and INPS appear to run the same software, an annotation declared this way may serve both.

---

## Confirmed vs inferred

**Confirmed** — measured against the live catalog on 2026-07-25, or quoted from the manual:

- the platform is the StatKit Data Browser (manual §3.7, p. 36)
- every count and percentage in this document
- the two annotations we already consume
- the search-noise measurement
- `NonProductionDataflow` does not imply missing data (`CPI` probe)
- `LAYOUT_REFERENCE_METADATA` duplicates `METADATA_URL` in 107 of 119 cases

**Inferred** — plausible, not verified:

- INPS runs the same software as ISTAT (path shape + manual; not confirmed against live response envelopes)
- `ONLY_FILE` dataflows fail on `get` (the annotation plus the total overlap with hidden/non-production imply it; not probed)
- `CRITERIA_SELECTION` relates to the `availableconstraint` timeout

**Version caveat**: the manual is Release 4.0 (Feb 2025); the version deployed on esploradati is unknown. Documented-in-4.0 does not mean live. The annotation census, however, is live data fetched today — those numbers stand regardless of the manual.

---

## Not worth pursuing

- The MDM online user manual (716 files in the site repo): it documents the *authoring* tool — how ISTAT staff build DSDs and load data — not how to query.
- `pages/mydoc/*` in the site repo: Jekyll theme boilerplate.
- The Excel2csv / CsvHandler manuals: production-side, not query-side.

## Reproducing

Scripts used, kept out of the package (one network call for the census, one for the `CPI` probe):

- `tmp/statkit/probe_annotations.py` — fetches the catalog once and censuses annotation types
- `tmp/statkit/extract_annotations.py` — flattens per-dataflow annotations to CSV for cross-checking
