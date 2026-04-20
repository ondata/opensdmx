# ISTAT Flow

ISTAT (Italian National Institute of Statistics) is the canonical SDMX source
for Italian statistics. Its API behaves differently from Eurostat in three ways
that shape the entire exploration flow:

1. **Strict rate limit (~13 s between requests)** — every wasted call costs real
   time, so verifying codes upfront is much cheaper than trial-and-error `get`.
2. **Codelists vs constraints diverge often** — `values` returns the theoretical
   codelist, which can include codes absent from a specific dataflow.
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

### Step 2 — explore codelist values

```bash
opensdmx values <dataflow_id> REF_AREA --provider istat
opensdmx values <dataflow_id> DATA_TYPE --provider istat
```

`values` returns the full theoretical codelist. Use `grep -i` to find candidates.
Most ISTAT codes are reliable, but some (versioned variants) appear in the
codelist while the dataflow only accepts the base form.

### Step 3 — verify with `constraints` before any `get`

```bash
opensdmx constraints <dataflow_id> --provider istat
opensdmx constraints <dataflow_id> DATA_TYPE --provider istat
```

This is the most important step. The `values` codelist is theoretical — many
codes will not exist in the actual dataflow. Each failed `get` attempt costs
≥13 s due to rate limiting, so verifying with `constraints` first (even when
that endpoint takes 30–60 s on first call) is far cheaper than multiple failed
`get` attempts.

**Exception — municipal-level datasets.** When `REF_AREA` contains thousands
of territory codes, `constraints` on that dimension may time out. In that case
only, fall back to `values` + `grep` for territories and verify with one narrow
`get`. For all other dimensions, `constraints` remains the right call.

### Step 4 — build the query using verified codes

```bash
opensdmx get <dataflow_id> --provider istat --REF_AREA <code> --last-n 1
```

If the query returns a 404 ("NoRecordsFound" — not a server error) or empty
result:

1. Try the **base form** of the code — strip any suffix that looks like a
   version or date (e.g. `LBIRTH_FROM2017` → `LBIRTH`, `POP_1JAN2021` →
   `POP_1JAN`).
2. Re-check with `opensdmx constraints` to see which codes are actually
   available.

For previews use a narrow time range (1–2 years) — combined with `--last-n 1`,
this keeps the response small and avoids loading data you don't need yet.

## Territory codes

ISTAT uses numeric `REF_AREA` codes:

- 6-digit municipal codes
- Province codes (`IT*`)
- Region codes
- Aggregate codes (`ITG12` for groups of provinces, `SLL_*` for labour market
  areas, etc.)

Browse the codelist with `grep -i` to locate specific places:

```bash
opensdmx values <dataflow_id> REF_AREA --provider istat 2>&1 | grep -i "palermo\|matera"
```

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
