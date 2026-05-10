# ISTAT Flow

ISTAT (Italian National Institute of Statistics) is the canonical SDMX source
for Italian statistics. Its API behaves differently from Eurostat in three ways
that shape the entire exploration flow:

1. **Strict rate limit (~13 s between requests)** on the SDMX REST endpoint —
   every wasted `get` costs real time, so verifying codes upfront is much
   cheaper than trial-and-error.
2. **Hub-backed `constraints` (sub-second per dimension)** — for ISTAT,
   `opensdmx constraints` uses the `.Stat Suite` databrowser hub by default and
   returns ground-truth values for **every** dimension, including `REF_AREA`
   (~8,000 comuni) and even on 11-dimension datasets that previously timed out
   on the SDMX REST endpoint. No wildcard cross-join, no 30 s waits.
3. **Versioned/dated codes** — some codes carry suffixes (`LBIRTH_FROM2017`,
   `POP_1JAN2021`) that may need to be stripped to match what the dataflow
   actually accepts.

> **Hub note.** The hub call is automatic and transparent. On any hub failure
> (network error, parse error, partial response) the CLI falls through to the
> classic SDMX REST chain (`contentconstraint` bulk → `availableconstraint` →
> `serieskeysonly`) without warning. Set `OPENSDMX_DISABLE_HUB=1` to force the
> SDMX REST path for debugging or comparison. See `docs/istat/hub-api.md` for
> the protocol details.

## Standard exploration flow

### Step 1 — get dimension order and structure

```bash
opensdmx info <dataflow_id> --provider istat
```

Note dimension flags: ISTAT uses **uppercase** (`--REF_AREA`, `--DATA_TYPE`,
`--FREQ`), unlike Eurostat (lowercase).

### Step 2 — call `constraints` (one stop)

```bash
opensdmx constraints <dataflow_id> --provider istat
```

For ISTAT, `constraints` resolves every dimension via the hub in roughly
500 ms per dimension. The output is ground truth — the codes actually present
in the dataflow, not the theoretical codelist superset.

```
Constraints: 41_270_DF_DCIS_MORTIFERITISTR1_1
  FREQ                1   A
  REF_AREA          179   IT111, IT, ITC
  DATA_TYPE           1   KILLINJ
  ACCIDENT_LOCALIZATON 4  1, 2, 3
  RESULT              3   M, F, 9
  AGE                14   Y_UN5, Y6-9, Y10-14
  SEX                 3   1, 2, 9
  MONTH              13   1, 2, 3
  …
```

`REF_AREA` is now exposed alongside every other dimension. For the few
historical cases where it was returned with a `–` placeholder (hub disabled,
hub unreachable, very old cached entries), follow the legacy fallback in
[Step 2b](#step-2b--legacy-fallback-when-the-hub-is-unavailable) below.

### Step 2b — Legacy fallback when the hub is unavailable

If you see a `–` ("not in contentconstraint") in the output for a dimension,
or if you have set `OPENSDMX_DISABLE_HUB=1` and a dataset happens to time out
on `availableconstraint`, fall back to a probe GET with no area filter and a
narrow 1-year time range:

```bash
opensdmx get <dataflow_id> --provider istat \
  --start-period 2022 --end-period 2022 \
  --out /tmp/probe.csv

duckdb -c "SELECT DISTINCT REF_AREA, count(*) n FROM '/tmp/probe.csv' GROUP BY REF_AREA ORDER BY n DESC LIMIT 30"
```

This is slower (full-year scan) but gives ground truth on which `REF_AREA`
codes are actually populated in the dataflow. If even this returns no results,
the dataset may need a different aggregation: run `opensdmx siblings
<dataflow_id> --provider istat` and verify via I.Stat that the data exists at
the requested granularity.

### Step 3 — `values` for code labels (optional)

`opensdmx constraints` already returns the IDs you need. Use `opensdmx values`
only when you also want the human-readable label of a specific code:

```bash
opensdmx values <dataflow_id> REF_AREA --provider istat 2>&1 | grep -i "palermo"
```

Caveat: `values` is the **theoretical codelist** (universe of codes the
codelist defines), not necessarily the codes populated in this dataflow. Trust
`constraints` for what works, `values` for labels.

### Step 4 — build the query using verified codes

```bash
opensdmx get <dataflow_id> --provider istat --REF_AREA <code> --last-n 1
```

If the query returns 404 or empty:

1. Try the **base form** of the code — strip any suffix that looks like a
   version or date (`LBIRTH_FROM2017` → `LBIRTH`, `POP_1JAN2021` → `POP_1JAN`).
2. Re-check `opensdmx constraints` for the dimensions that are exposed; for
   those marked `–`, scan the codelist with `opensdmx values`.

For previews use a narrow time range (1–2 years) — combined with `--last-n 1`,
this keeps the response small and avoids loading data you don't need yet.

## Territory codes

ISTAT uses numeric `REF_AREA` codes:

- 6-digit municipal codes
- Province codes (`IT*`)
- Region codes
- Aggregate codes (`ITG12` for groups of provinces, `SLL_*` for labour market
  areas, etc.)

For ISTAT, `REF_AREA` is exposed by `opensdmx constraints` via the hub — start
there. Use `opensdmx values <df> REF_AREA --provider istat` only when you need
the full theoretical codelist (e.g. mapping a specific code to its readable
label) or when running with the hub disabled.

## Direct download URL pattern

```bash
curl -s \
  -H "Accept: application/vnd.sdmx.data+csv;version=1.0.0" \
  "https://esploradati.istat.it/SDMXWS/rest/data/{dataflow_id}/{dim1.dim2...}?startPeriod={start}&endPeriod={end}"
```

`Accept: text/csv` also works and returns the same CSV format.
Without an Accept header (or with `Accept: application/xml`) ISTAT returns XML.

Dimension values in the path follow the order from `opensdmx info`, with `.`
for unfiltered dimensions and `+` to combine multiple values.

**Tip — limit results without knowing exact codes:**
Use `lastNObservations=N` or `firstNObservations=N` to cap the number of
observations per series:

```bash
curl -s \
  -H "Accept: application/vnd.sdmx.data+csv;version=1.0.0" \
  "https://esploradati.istat.it/SDMXWS/rest/data/CPI/CPI.IT.PCPI_IX._Z.M?lastNObservations=3"
```

**Tip — probe without downloading data:**
Use `detail=serieskeysonly` to retrieve only series keys (no observations),
useful for checking how many series a key returns before a full download:

```bash
curl -s \
  "https://esploradati.istat.it/SDMXWS/rest/data/{dataflow_id}/{key}?detail=serieskeysonly"
```

## Aggregate codes in the data

Many ISTAT dataflows include **aggregate codes** alongside individual-level
codes. These are totals and sub-totals that summarise other rows — they must be
excluded before any sum, chart, or analysis, or they will double-count the data.

Common aggregate codes:

| Dimension | Code    | Meaning               |
|-----------|---------|-----------------------|
| AGE       | `TOTAL` | all ages combined     |
| SEX       | `9`     | both sexes combined   |
| DATA_TYPE | varies  | often a grand total   |

After downloading, always filter out aggregate codes before using the data.
Example with DuckDB:

```sql
SELECT * FROM 'data.csv'
WHERE AGE != 'TOTAL' AND SEX != 9
```

The `constraints` command shows aggregate codes alongside individual ones
without marking them as totals — you cannot distinguish them from the schema
alone. Check the codelist labels (via `opensdmx values <id> <dim> --provider
istat`) to identify which codes are aggregates (labels like "total", "all",
"tutti", "totale").

**`endPeriod` off-by-one bug**: ISTAT returns one extra period beyond the
requested `endPeriod` for any frequency (monthly, quarterly, annual). For
example, `endPeriod=2024-03` returns data through `2024-04`, and
`endPeriod=2024` returns data through `2025-01-01`. To get data through
period N, request `endPeriod=N-1`. Filter on `TIME_PERIOD` after download
to enforce the exact cutoff date.

## Other quirks

- Some IDs are **parent containers** (e.g. `25_74`) rather than fetchable
  dataflows — `info` will reveal this. Use the sub-dataflow IDs listed under
  them instead.
- Search is keyword-based on dataflow descriptions, which are in Italian.
  Phrase queries in Italian for best recall (e.g. `prezzi`, `popolazione`,
  `disoccupazione`).
