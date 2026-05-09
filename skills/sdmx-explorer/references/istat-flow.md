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

## Other quirks

- Some IDs are **parent containers** (e.g. `25_74`) rather than fetchable
  dataflows — `info` will reveal this. Use the sub-dataflow IDs listed under
  them instead.
- Search is keyword-based on dataflow descriptions, which are in Italian.
  Phrase queries in Italian for best recall (e.g. `prezzi`, `popolazione`,
  `disoccupazione`).
