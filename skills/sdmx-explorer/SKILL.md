---
name: sdmx-explorer
description: >
  Guided, interactive exploration of statistical data via SDMX providers
  (Eurostat, OECD, ECB, World Bank, ISTAT, and others) using the opensdmx CLI.
  Use this skill whenever the user asks a question about statistics that could
  be answered with SDMX data: demographics, economy, employment, births, deaths,
  population, prices, trade, health, agriculture, or any other topic.
  Also use it when the user mentions a specific dataflow ID they want to explore.
  The skill guides the user step by step: discovers relevant datasets, proposes
  the most meaningful candidates, explores the schema using real constraints
  (not codelists), explains the dataset structure, and invites the user to make
  informed filter choices before fetching any data.
license: MIT
compatibility: >
  Requires the opensdmx CLI (opensdmx search, info, constraints, values, get, plot).
metadata:
  author: ondata
  version: "1.1"
---

# SDMX Explorer — Guided Dataset Discovery

This skill uses the **opensdmx CLI** to explore any SDMX 2.1 REST endpoint:
Eurostat, OECD, ECB, World Bank, ISTAT, and others.
The primary reference provider is **Eurostat** (default in the opensdmx CLI).
All examples use Eurostat unless stated otherwise.

Every `opensdmx` command supports `--help` — run it first to discover options and
see usage examples:

```bash
opensdmx --help                  # list all commands
opensdmx search --help           # options and examples for search
opensdmx constraints --help      # options and examples for constraints
opensdmx get --help              # options and examples for get
# ... same for info, values, constraints, embed, blacklist, plot
```

This skill runs a four-phase interactive loop. Always follow the phases in order.
The goal is to help the user understand the data landscape and make informed choices,
not to fetch data immediately.

---

## Phase 1 — Discovery: find candidate dataflows

Identify which SDMX provider is relevant (ISTAT for Italian statistics, Eurostat for
European statistics, OECD for international comparisons, etc.). If unclear, ask.

Extract 2–4 meaningful keywords from the user's question.
Then search for dataflows:

- **Eurostat** (default provider — no `--provider` flag needed):
  `opensdmx search "<keyword>"`
- **ISTAT**: `opensdmx search "<keyword>" --provider istat`
- **Other providers**: `opensdmx search "<keyword>" --provider <name>`
  (available: `oecd`, `ecb`, `worldbank`, `insee`, `bundesbank`, `abs`)

From the results, select **3–5 candidates** that are genuinely relevant (not just
keyword matches). For each, write a short explanation of what it contains and why
it might answer the user's question.

Present them like this (use the conversation language; adapt as needed):

```
I found these datasets that could answer your question:

1. **demo_gind** — Demographic balance and crude rates (Eurostat)
   Contains births, deaths, migration balance and demographic rates for EU countries,
   with annual time series from 1960. Best for European comparisons.

2. **demo_nsinagec** — Live births by mother's age (Eurostat)
   Births broken down by mother's age group and country. Useful if you want
   age-specific fertility analysis rather than totals.

3. **APRO_CPNH1** — Crop production in national humidity (Eurostat)
   Agricultural production data by crop type, country and structure indicator
   (area, harvested production, yield). Covers 40+ European countries annually.

Which one would you like to explore? You can also say "the first one" or
describe more precisely what you need.
```

Wait for the user's choice before proceeding.

---

## Phase 2 — Schema: explore the chosen dataflow

Once the user has chosen, retrieve the structure and available codes for the dataflow.

### Default flow (Eurostat, OECD, ECB, etc.)

Step 1 — get the codes **actually present** in the dataflow (real constraints):
```bash
opensdmx constraints PRC_HICP_MANR
# shows all dimensions with count and sample of codes

opensdmx constraints PRC_HICP_MANR coicop
# shows full list of codes present in that dimension, with labels
```

`opensdmx constraints` is the ground truth — it queries the `availableconstraint`
SDMX endpoint and returns only codes that actually exist in this specific dataflow.

Step 2 — get dimension order and structure:
```bash
opensdmx info PRC_HICP_MANR
# (no --provider needed for Eurostat, it's the default)
```

`opensdmx values` returns the **full codelist** (all theoretically possible codes),
not the codes actually present. Use it only when you need labels for codes you already
know are valid and `opensdmx constraints` doesn't provide enough detail.

**Never use `opensdmx values` to validate filter codes.** A code present in the codelist
may return no data if it doesn't exist in this specific dataflow.

### ISTAT fast flow (recommended)

ISTAT's `availableconstraint` endpoint is extremely slow and often times out on large
datasets (e.g. municipal-level data with thousands of territory codes). Use this faster
flow instead:

Step 1 — get dimension order and structure:
```bash
opensdmx info <dataflow_id> --provider istat
```

Step 2 — explore codelist values for the dimensions you need to filter:
```bash
opensdmx values <dataflow_id> REF_AREA --provider istat
opensdmx values <dataflow_id> DATA_TYPE --provider istat
```

`values` returns the full codelist (all theoretically possible codes). For ISTAT this is
usually reliable enough because ISTAT codelists tend to be well-aligned with actual data.
Use `grep -i` to find specific codes (e.g. city names, indicators).

Step 3 — go directly to `get` with filters and verify with a narrow query:
```bash
opensdmx get <dataflow_id> --provider istat --REF_AREA <code> --last-n 1
```

If the query returns a 404 or empty result, the code may not be present in this dataflow.
**Only then** fall back to `opensdmx constraints` to check which codes are actually
available — but be aware it may take 30–60+ seconds or time out on large datasets.

### Extract from both flows

Parse the output and extract:
- **Dimension list** in order (position matters for URL construction later)
- **Available codes** for each dimension, with descriptions
- **Time range** (StartPeriod / EndPeriod)
- **Dimensions with more than one available value** (these are the meaningful filters)

---

## Phase 3 — Presentation: explain the dataset to the user

Synthesize what you learned in Phase 2 into a clear, human-readable summary.
The goal is for the user to understand the dataset without knowing SDMX.

Structure your summary like this:

### What the dataset contains
Describe the subject matter in plain language.

### Granularity
- **Geographic**: national only? Regions? EU countries? Global?
- **Temporal**: what years are available? Annual, monthly, quarterly?

### Key dimensions to filter
List only the dimensions with more than one available value that are meaningful
for the user's question. For each, show the options in plain language:

```
- **Country** (GEO): IT (Italy), DE (Germany), FR (France)… 35 countries
- **Indicator** (INDIC_DE): live births (GBIRTHS), deaths (DEATH),
  crude birth rate (CNBIRTHS), total fertility rate (TOTFERRT)…
- **Period**: 1960 to 2024, annual frequency
```

For dimensions with only one available value, mention them briefly:
"Other dimensions have a single fixed value and are included automatically."

### Estimated size
Give a rough sense of scale: "Downloading everything (all countries + all indicators +
all years) would give you approximately X rows." This helps the user decide how to filter.

### Invitation to choose

End with a clear prompt:

```
How would you like to proceed?
- Do you want data for a specific country or a European comparison?
- Which time period are you interested in?
- Are there any dimensions you want to filter?

Tell me what you want and I'll build the query.
```

---

## Phase 4 — Data retrieval: after the user decides

Once the user has specified their choices, build the query and fetch the data.

### Building the query — critical rules

1. **Dimension order must match the `opensdmx info` output exactly.** Never guess the order.
2. **Use only codes confirmed by `opensdmx constraints`**, never codes from `opensdmx values`
   or other sources. Providers often return 404 or empty results for invalid codes.
3. **For dimensions with a single available value**, include that value — don't skip them.
4. **For unfiltered dimensions** (user wants all values), use `.` as wildcard.

Note: Eurostat dimension flags are lowercase (`--geo`, `--coicop`, `--freq`).
ISTAT dimension flags are uppercase (`--REF_AREA`, `--DATA_TYPE`, `--FREQ`).

### Step 1 — Verify with a preview (last observation)

Before fetching everything, do a quick sanity check with `--last-n 1` to confirm
the query is valid and the data looks correct:

```bash
opensdmx get PRC_HICP_MANR --coicop CP00 --geo IT+DE+FR --start-period 2020 --end-period 2023 --last-n 1
```

`--last-n 1` returns the most recent observation per series (one row per country/dimension
combination), which is enough to verify the query structure without flooding the output.
Prefer `--last-n 1` over `--first-n N` for previews: it shows the most recent data
and produces far fewer rows when there are many series.

For ISTAT: use a narrow time range (1–2 years) as preview.

Show the user those few rows and confirm the data makes sense (right columns, right units,
no unexpected flags). A one-line comment is enough: "Query works — here is the latest observation per series."

### Step 2 — Provide the download URL

Build and show the equivalent curl command so the user can download the full dataset
independently, without relying on the CLI:

**Eurostat URL pattern:**
```
https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/{dataflow_id}/{dim1.dim2...}/ALL/?startPeriod={start}&endPeriod={end}&format=SDMX-CSV
```

Dimension values in the path must follow the exact order from `opensdmx info`,
with `.` for unfiltered dimensions and `+` for multiple values.

**Example:**
```bash
curl "https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/APRO_CPNH1/A.I2200.AR./ALL/?startPeriod=2014&endPeriod=2023&format=SDMX-CSV"
```

**ISTAT URL pattern:**
```
https://esploradati.istat.it/SDMXWS/rest/data/{dataflow_id}/{dim1.dim2...}?startPeriod={start}&endPeriod={end}
```

### Step 3 — Ask the user what to do next

End with a short, clear question:

```
Would you like me to download and save the full dataset locally for analysis?
If yes, tell me where to save it (e.g. /tmp/data.csv) or I'll use a default path.
I can then run a quick analysis: row count, top values, time range, flagged records.
```

If the user says yes, download with `--out <path>` and run a quick analysis
(row count, top values, time range, any missing/flagged data worth noting).

### Step 4 — Offer metadata and README

After downloading, always ask the user two optional extras:

```
Two optional extras:
1. **Full metadata**: do you want the complete list of codes and labels for each
   dimension (e.g. all country names, all flag meanings)? I can extract them from
   the opensdmx cache and save them as a companion file (e.g. `metadata.csv`).
2. **README**: do you want a `README.md` that documents the dataset schema —
   columns, dimension codes with labels, flag meanings, units, and source URL?
   Useful if you plan to share the data or revisit it later.
```

If the user says yes to **metadata**:
- Run `opensdmx constraints <dataflow_id> <dim>` for each dimension with more than
  one value to get the full code → label mapping.
- Combine all dimensions into a single metadata file with columns:
  `dimension`, `code`, `label`.
- Save it alongside the data file (e.g. `tomato_production_metadata.csv`).

If the user says yes to **README**:
- Generate a `README.md` in the same folder as the data file.
- Include:
  - Dataset name and ID
  - Provider and source URL (the curl URL from Step 2)
  - Last update timestamp (from the `LAST UPDATE` column in the data)
  - Column descriptions: for each column in the CSV, explain what it contains
  - Dimension tables: for each dimension, list codes and labels (from constraints
    or the metadata file if already generated)
  - Flag legend: list all `OBS_FLAG` values found in the data with their meaning
  - Units: clearly state the unit of measurement for `OBS_VALUE`
  - Any caveats noted during analysis (gaps, estimated values, provisional data)

---

## Key principles

**Constraints vs codelists — always use constraints**
Use `opensdmx constraints` to get codes actually present in the data.
`opensdmx values` returns the full codelist (all possible codes), which may include
codes absent from a specific dataflow. A code valid in the codelist may return no data
if it doesn't exist in that dataflow.

**Proposals, not lists**
When presenting dataflow candidates, reason about each one: explain why it might or
might not answer the question, what its limitations are, and which one you'd recommend.
The user should feel guided, not overwhelmed.

**Explain dimensions in plain language**
Translate SDMX dimension IDs into human concepts:
- `CITIZENSHIP_MOTHER` → "mother's citizenship"
- `DATA_TYPE: LBIRTH` → "live births (absolute count)"
- `GEO: IT` → "Italy"
- `INDIC_DE: GBIRTHS` → "live births"
- `INDIC_DE: CNBIRTHS` → "crude birth rate (per 1,000 inhabitants)"
Never show raw codes without an explanation.

**Explore all columns, not just the value column**
When the preview arrives (Step 1 of Phase 4), look at all columns in the response,
not just the observation value. SDMX datasets often include extra columns that affect
interpretation: quality flags, confidentiality markers, unit multipliers, notes.
For each non-obvious column, check what values are present and explain their meaning
to the user. For example:
- `OBS_FLAG` or `OBS_STATUS`: quality/availability flags — look up what each code means
  in the context of that provider (`b` = break in series, `e` = estimated, `n` = not
  significant, `u` = unreliable, `p` = provisional, etc.)
- `UNIT_MULT`: multiplier applied to the value (e.g. `3` means values are in thousands)
- `CONF_STATUS`: confidentiality status
- `NOTE_*`: free-text annotations attached to specific dimensions

Don't hardcode these — inspect what columns are actually present in the data and
explain the ones that are populated. Skip columns that are entirely empty.

**Provider-specific quirks**

| Provider | Notes |
|----------|-------|
| ISTAT | Use `--provider istat`; 404 = "NoRecordsFound" (not a server error); rate limit ~13s; some IDs are parent containers (e.g. `25_74`) — use sub-dataflow IDs (e.g. `25_74_DF_DCIS_NATI2_1`); **use the ISTAT fast flow** (info → values → get) instead of constraints — the `availableconstraint` endpoint is very slow and often times out on large datasets |
| Eurostat | **Default provider** (no `--provider` flag needed); dimension flags are lowercase (`--geo`, `--coicop`); country codes: ISO 3166-1 alpha-2 + EU aggregates like `EU27_2020` |
| OECD | Use `--provider oecd`; good for international comparisons |
| ECB | Use `--provider ecb`; financial and monetary data |
| World Bank | Use `--provider worldbank`; development indicators |

**Territory resolution (Eurostat)**
Country codes follow ISO 3166-1 alpha-2: `IT` (Italy), `DE` (Germany), `FR` (France),
`ES` (Spain). EU aggregates: `EU27_2020`, `EA20` (Euro area). Always verify against
`opensdmx constraints` before using — not all codes are present in every dataset.

**Territory resolution (ISTAT)**
ISTAT uses numeric REF_AREA codes (6-digit municipal codes, province codes, region codes,
and aggregate codes like `ITG12` for provinces or `SLL_*` for labour market areas).
Use `opensdmx values <dataflow_id> REF_AREA --provider istat` to browse the full
codelist — pipe through `grep -i` to find specific cities or territories:

```bash
opensdmx values <dataflow_id> REF_AREA --provider istat 2>&1 | grep -i "palermo\|matera"
```

Avoid `opensdmx constraints <dataflow_id> REF_AREA --provider istat` on municipal-level
datasets — the `availableconstraint` endpoint is very slow with thousands of codes.
Use `values` + `grep` to find codes, then verify with a narrow `get` query.
