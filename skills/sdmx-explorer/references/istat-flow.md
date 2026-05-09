# ISTAT Flow

ISTAT (Italian National Institute of Statistics) is the canonical SDMX source
for Italian statistics. Its API behaves differently from Eurostat in three ways
that shape the entire exploration flow:

1. **Strict rate limit (~13 s between requests)** — every wasted call costs real
   time, so verifying codes upfront is much cheaper than trial-and-error `get`.
2. **`constraints` uses `contentconstraint` (sub-second)** — fast, reliable, but
   does **not** expose `REF_AREA` (geographic dimension). For municipal datasets
   that's by design: 8,000+ comuni would inflate the payload. The CLI surfaces
   the missing dimension with an inline hint to `opensdmx values`.
3. **Versioned/dated codes** — some codes carry suffixes (`LBIRTH_FROM2017`,
   `POP_1JAN2021`) that may need to be stripped to match what the dataflow
   actually accepts.

## Standard exploration flow

### Step 1 — get dimension order and structure

```bash
opensdmx info <dataflow_id> --provider istat
```

Note dimension flags: ISTAT uses **uppercase** (`--REF_AREA`, `--DATA_TYPE`,
`--FREQ`), unlike Eurostat (lowercase).

### Step 2 — call `constraints` first

```bash
opensdmx constraints <dataflow_id> --provider istat
```

`contentconstraint` returns sub-second, so this is the cheapest first call
to make. The output looks like:

```
Constraints: 22_289_DF_DCIS_POPRES1_24
  FREQ            1   A
  REF_AREA        –   not in contentconstraint — use: opensdmx values 22_289_DF_DCIS_POPRES1_24 REF_AREA
  DATA_TYPE       1   JAN
  SEX             3   1, 2, 9
  AGE           102   TOTAL, Y_GE100, Y0
  MARITAL_STATUS  1   99
```

For the dimensions present (`FREQ`, `DATA_TYPE`, `SEX`, `AGE`,
`MARITAL_STATUS`) you have ground truth: the codes really present in the
dataflow. For any dimension marked `–` ("not in contentconstraint"), the CLI
tells you exactly which command to run next.

### Step 2b — When `contentconstraint` returns 404

Some ISTAT datasets do not publish a `contentconstraint`. When
`opensdmx constraints` returns 404, try these fallbacks in order:

**Fallback A — `availableconstraint` via curl**

`availableconstraint` is a different SDMX endpoint that returns the values
actually present in the data. It requires the full key (all dimensions as
wildcards). Get the dimension count from `opensdmx info`, then build the key:

```bash
# Get dimension count
NDIM=$(opensdmx --output json info <dataflow_id> --provider istat | jq '[.[] | select(.type=="dimension")] | length')

# Build the all-wildcard key (N-1 dots for N dimensions) and query REF_AREA
curl -s "https://esploradati.istat.it/SDMXWS/rest/availableconstraint/IT1,<dataflow_id>,1.0/$(python3 -c "print('.'*($NDIM-1))")/REF_AREA/?mode=Available&references=none"
```

The response is XML — grep for `<a:Value>` to extract valid codes. Repeat with
other dimension names to discover which codes are actually in the data.

**Fallback B — probe GET to discover valid territory codes**

If `availableconstraint` also times out or fails, do a probe GET with no area
filter and a narrow 1-year time range. Save to CSV and inspect distinct values:

```bash
opensdmx get <dataflow_id> --provider istat \
  --start-period 2022 --end-period 2022 \
  --out /tmp/probe.csv

duckdb -c "SELECT DISTINCT REF_AREA, count(*) n FROM '/tmp/probe.csv' GROUP BY REF_AREA ORDER BY n DESC LIMIT 30"
```

This is slower (full-year scan) but gives ground truth on which `REF_AREA`
codes are actually populated in the dataflow.

**If both fallbacks fail or time out**

The dataset may have issues specific to the SDMX REST endpoint:

1. Check if the search results included region-specific variants (e.g.
   `41_269_1` for Lazio) — the data may be published per-region.
2. Run `opensdmx siblings <dataflow_id> --provider istat` to find related
   dataflows that may cover the same subject at a different aggregation level.
3. Verify via the ISTAT web explorer (I.Stat) that the data exists at the
   requested granularity.

Note: the correct long-term fix is for `opensdmx constraints` to automatically
fall back to `availableconstraint` when `contentconstraint` returns 404. Until
that is implemented in the CLI, use the manual curl approach above.

### Step 3 — for missing dimensions, fall back to `values`

```bash
opensdmx values <dataflow_id> REF_AREA --provider istat
```

`values` returns the **theoretical codelist**. For `REF_AREA` (`CL_ITTER107`)
that's all 8,000+ Italian territory codes — comuni, province, regioni,
aggregati statistici (`ITG12`, `SLL_*`, etc.). Filter with `grep -i` to find
candidates:

```bash
opensdmx values <dataflow_id> REF_AREA --provider istat 2>&1 | grep -i "palermo"
```

Caveat: `values` is the universe of codes the codelist defines, **not** the
codes actually populated in the dataflow. Most municipal codes work, but some
versioned variants (`POP_1JAN2021`) appear in the codelist while the dataflow
only accepts the base form. If a `get` returns 404 / `NoRecordsFound`, try
the base code or check whether the suffix matches the year you're querying.

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

`REF_AREA` is the dimension `contentconstraint` does not expose — always go
through `opensdmx values <df> REF_AREA --provider istat` to discover codes.

## Direct download URL pattern

```
https://esploradati.istat.it/SDMXWS/rest/data/{dataflow_id}/{dim1.dim2...}?startPeriod={start}&endPeriod={end}
```

Dimension values in the path follow the order from `opensdmx info`, with `.`
for unfiltered dimensions and `+` to combine multiple values.

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

Also note: when filtering by time period with `--start-period` / `--end-period`
using year-only values (e.g. `2025`), ISTAT may return observations dated
`YYYY+1-01-01` because it stores annual data as `YYYY-01-01`. Filter on the
`TIME_PERIOD` column after download to select the exact reference date.

## Other quirks

- Some IDs are **parent containers** (e.g. `25_74`) rather than fetchable
  dataflows — `info` will reveal this. Use the sub-dataflow IDs listed under
  them instead.
- Search is keyword-based on dataflow descriptions, which are in Italian.
  Phrase queries in Italian for best recall (e.g. `prezzi`, `popolazione`,
  `disoccupazione`).
