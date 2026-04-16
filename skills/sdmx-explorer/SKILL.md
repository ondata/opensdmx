---
name: sdmx-explorer
description: >
  Guided, interactive exploration of statistical data via SDMX providers
  (Eurostat, OECD, ECB, World Bank, ISTAT, and others) using the opensdmx CLI.
  Use this skill whenever the user asks ANY question about statistics or data
  that could be answered with SDMX data — even if they don't mention SDMX,
  Eurostat, or any provider by name. Topics include demographics, economy,
  employment, births, deaths, population, prices, trade, health, agriculture,
  GDP, inflation, unemployment, fertility rates, migration, energy, education,
  poverty, housing, and any other statistical topic. Also use it when the user
  mentions a dataflow ID. Trigger for implicit questions like
  "how many births were there in Italy last year?" or "I need EU unemployment
  data by age group". Guides the user step by step: discovers datasets, proposes
  the most meaningful candidates, explores the schema using real constraints
  (not codelists), explains the dataset structure, and invites the user to make
  informed filter choices before fetching any data.
license: MIT
compatibility: >
  Requires the opensdmx CLI (opensdmx search, info, constraints, values, get, plot).
metadata:
  author: ondata
  version: "1.2"
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
opensdmx run --help              # options and examples for run
# ... same for info, values, constraints, embed, blacklist, plot
```

All metadata commands (`search`, `info`, `values`, `constraints`, `providers`) support
a global `--output` flag for structured output. Use it when you need to parse results
programmatically instead of reading a Rich table:

```bash
opensdmx --output json search "unemployment" --n 10
opensdmx --output json info TIPSUN20
opensdmx --output json constraints TIPSUN20
opensdmx --output json values TIPSUN20 geo
opensdmx --output json providers
opensdmx --output csv values TIPSUN20 geo   # CSV for tabular use
```

In `--output json` mode: stdout is pure JSON, stderr carries errors/warnings, spinners
are suppressed. Pipe directly into `jq` or parse in Python.

This skill runs a four-phase interactive loop. Always follow the phases in order.
The goal is to help the user understand the data landscape and make informed choices,
not to fetch data immediately.

---

## Phase 1 — Discovery: find candidate dataflows

Identify which SDMX provider is relevant (ISTAT for Italian statistics, Eurostat for
European statistics, OECD for international comparisons, etc.). If unclear, ask.

### Step 1a — Extract keywords AND expected dimensions

Before searching, parse the user's question on two levels:

1. **Topic keywords** (2–4 terms) for the `opensdmx search` call.
   Example: "unemployment", "labour force"

2. **Expected dimensions** — the analytical angles the user wants to slice by.
   These are often NOT in the dataset title or description, but must appear as
   dimensions in the dataflow structure. Extract them explicitly:

   | User says | Expected dimension |
   |---|---|
   | "by age group" / "per fascia di età" | `age` |
   | "by sex" / "per sesso" | `sex` |
   | "by country" / "per paese" | `geo` |
   | "by region" | `geo` (NUTS level) |
   | "by education level" | `isced11` or similar |
   | "quarterly" / "monthly" | `freq` |

   Example: *"unemployment for EU countries, by age group and sex"* →
   topic keywords: `unemployment`; expected dimensions: `age`, `sex`, `geo`.

### Step 1b — Search and pre-filter candidates

Search for dataflows:

- **Eurostat** (default provider — no `--provider` flag needed):
  `opensdmx search "<keyword>"`
- **ISTAT**: `opensdmx search "<keyword>" --provider istat`
- **Other providers**: `opensdmx search "<keyword>" --provider <name>`
  (available: `oecd`, `ecb`, `worldbank`, `insee`, `bundesbank`, `abs`)

To see the full list of built-in providers — including which ones support
`constraints` and `last_n` — run:
```bash
opensdmx providers
```
The `constraints` column tells you whether `opensdmx constraints` works for that
provider (✓ = supported, ✗ = returns 400). The `last_n` column tells you whether
`--last-n N` is supported in `opensdmx get`. Use this to decide which exploration
flow to apply before you start (see Phase 2 and provider-specific quirks below).

From the search results, pick **5–8 plausible candidates** by title relevance.
Then run `opensdmx info <id>` on each one **in parallel** to check their dimension
list. Keep only the candidates that contain **all expected dimensions**.
Discard candidates missing a required dimension — even if the title looks right.

**If page 1 (50 results) yields no strong candidates**, paginate before giving up:

```bash
opensdmx search "unemployment" --page 2   # results 51-100
opensdmx search "unemployment" --page 3   # results 101-150
```

The title shows the total available (e.g. `51-100 of 114`), so you know how many
pages exist. Keep paginating until you find at least 3 plausible candidates or
exhaust the results. Only after exhausting pagination should you try a different
keyword or provider. Use `--all` only as a last resort (may produce very long output).

Results are ranked by relevance score (id match, start-of-description, occurrence count) —
the most relevant candidates appear first.

**If keyword search returns 0 or very few results (< 3), offer semantic search:**

> "I didn't find much with a keyword search. I can try a semantic search instead —
> it matches by meaning, not exact words, so it can find datasets even when the
> terminology differs. It requires Ollama to be running and is slower (10–30 s).
> Want me to try?"

If the user agrees:

```bash
opensdmx search --semantic "<query>"
```

Semantic search returns the top 20 results ranked by similarity score. Pick the
most relevant candidates (score > 0.5) and continue with Step 1c as normal.

```bash
# Example: verify age and sex are present
opensdmx info UNE_RT_A       # ✓ has age, sex, geo → keep
opensdmx info TIPSUN20       # ✗ no age, no sex → discard
```

### Step 1c — Present verified candidates

From the verified candidates, select **3–5** and present them. For each, confirm
which expected dimensions are present and note any extras or limitations.

Present them like this (use the conversation language; adapt as needed):

```
I found these datasets that could answer your question:

1. **UNE_RT_A** — Unemployment by sex and age – annual data (Eurostat)  ⭐ recommended
   Has all three dimensions you need: age (7 ranges), sex (F/M/total), geo (38 countries).
   Annual data from 2003 to 2025. Clean structure, no extra mandatory filters.

2. **LFSA_URGAED** — Unemployment rates by educational attainment level (Eurostat)
   Also has age (29 ranges!) and sex, but adds a mandatory education-level dimension
   (ISCED11). More granular age breakdown, but requires choosing an education filter.
   Best if you also want to break down by education.

3. **MET_LFU3RT** — Unemployment rates by sex, age and metropolitan region (Eurostat)
   Has age and sex, but geo is at metropolitan region level — not country level.
   Not suitable for country comparisons.

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

### ISTAT flow

Step 1 — get dimension order and structure:
```bash
opensdmx info <dataflow_id> --provider istat
```

Step 2 — explore codelist values for the dimensions you need to filter:
```bash
opensdmx values <dataflow_id> REF_AREA --provider istat
opensdmx values <dataflow_id> DATA_TYPE --provider istat
```

`values` returns the **full theoretical codelist** — codes that exist in the codelist
definition, not necessarily in this specific dataflow. Most ISTAT codes are reliable,
but some may be absent from a given dataflow (e.g. a versioned code like `LBIRTH_FROM2017`
may appear in the codelist but the dataflow only uses the base code `LBIRTH`).
Use `grep -i` to find candidate codes.

Step 3 — **CRITICAL: verify codes with `constraints` BEFORE testing with `get`**:
```bash
opensdmx constraints <dataflow_id> --provider istat
opensdmx constraints <dataflow_id> DATA_TYPE --provider istat
```

**Do NOT skip this step.** The `values` codelist is theoretical — many codes will not
exist in the actual dataflow. Testing invalid codes with `get` wastes enormous time
because of ISTAT's rate limit (~13 seconds between requests). Each failed `get` attempt
costs at least 13 seconds of waiting. Verifying codes with `constraints` first — even
if the endpoint is slow (30–60+ seconds) — is far cheaper than multiple failed `get`
attempts.

For very large datasets with thousands of territory codes (e.g. municipal-level data),
`constraints` on `REF_AREA` may time out. In that case only, use `values` + `grep` for
territory codes and verify with a single narrow `get`. But for all other dimensions
(DATA_TYPE, FREQ, etc.), always use `constraints`.

Step 4 — build the query using only codes confirmed by `constraints`:
```bash
opensdmx get <dataflow_id> --provider istat --REF_AREA <code> --last-n 1
```

If the query returns a 404 or empty result:
1. **Try the base form of the code** — remove any suffix that looks like a version or date
   (e.g. `LBIRTH_FROM2017` → try `LBIRTH`; `POP_1JAN2021` → try `POP_1JAN`).
2. Re-check with `opensdmx constraints` to verify which codes are actually available.

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

### Step 4 — Offer to save the query as a reusable template

After a successful download, always ask the user if they want to save the query:

```
This query worked well. Would you like to save it as a YAML template so you can
re-run it later without remembering all the parameters?

  opensdmx get <id> [filters] --out data.csv --query-file my_query.yaml

The YAML captures provider, dataset, filters with human-readable descriptions,
and time range. To re-run it later:

  opensdmx run my_query.yaml
  opensdmx run my_query.yaml --out fresh_data.csv

The file is also useful for version control and sharing with colleagues.
```

Always suggest a meaningful filename (e.g. `unemployment_eu_2020_2024.yaml`,
`gdp_annual_eurostat.yaml`) based on the dataset and filters used.

### Step 5 — Offer metadata and README

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
- The goal is to make the output **verifiable** (check values against the source),
  **evaluable** (judge quality and scope), and **repeatable** (reproduce from scratch).
- Follow the full template in [references/readme-template.md](references/readme-template.md).
  In summary, include:
  - Files produced (table)
  - One section per source dataflow: ID, provider, filters with labels, unit,
    last update date, and the exact download URL
  - Derivations: join keys, filters applied after download, computed columns
    with explicit formulas (not prose)
  - Column schema: name, type, description, unit for every column in the output
  - Flag legend: only flags actually present in the data, with row counts
  - Coverage table when geographic or categorical gaps exist
  - Caveats: scope limitations, reporting lags, known biases

### Step 6 — Visualization

After downloading data, offer to create charts using `opensdmx plot`.
The plot command uses plotnine (Python's ggplot2) and accepts both dataflow IDs
and local files (.csv, .tsv, .parquet).

For the complete visualization reference — Grammar of Graphics concepts, data
preparation rules, DuckDB examples, iterative chart quality loop, and common
fixes — see [references/visualization.md](references/visualization.md).

**Supported chart types** (via `--geom`):
- `line` (default): line chart with points — best for time series
- `bar`: vertical bar chart — best for comparing values across categories over time;
  with `--color` produces stacked bars
- `barh`: horizontal bar chart — best for rankings; bars are automatically sorted
  by value (lowest at bottom, highest at top)
- `point`: scatter plot — best for correlations between two numeric variables

For other chart types not supported by `opensdmx plot` (heatmaps, grouped/dodge bars),
write a short Python script using plotnine directly.

For DuckDB installation and common data-prep patterns, see
[references/duckdb-setup.md](references/duckdb-setup.md).

Key points:
- Always prepare data with DuckDB before plotting (separate units, limit series,
  remove aggregates, use year strings for annual data)
- After generating a chart, read the image and evaluate it — if it's not good,
  fix it yourself before showing the user
- Multiple focused charts are better than one overloaded chart

---

## Key principles

**Always explain the indicator — never assume prior knowledge**
After presenting any results, always include a plain-language explanation of the
key indicator(s) used. Do not assume the user knows what GNI, PPP, HICP, or any
other acronym means. For every indicator shown:
- State in one sentence what it measures
- Explain how it differs from similar concepts the user might know (e.g. GNI vs GDP)
- Clarify the unit and any methodological choice that affects interpretation
  (e.g. "Atlas method" vs PPP, constant vs current USD)

This applies even when the indicator name seems obvious. A user who asks
"which are the poorest countries?" may not know what GNI is, even if they
implicitly agree with using it as a proxy for poverty.

Place this explanation immediately after the data summary, before any offer
to download or visualize.

**Constraints vs codelists — always use constraints**
Use `opensdmx constraints` to get codes actually present in the data.
`opensdmx values` returns the full codelist (all possible codes), which may include
codes absent from a specific dataflow. A code valid in the codelist may return no data
if it doesn't exist in that dataflow.

**Proposals, not lists**
When presenting dataflow candidates, reason about each one: explain why it might or
might not answer the question, what its limitations are, and which one you'd recommend.
The user should feel guided, not overwhelmed.

**Make filter choices coherent with the user's intent**
Match the granularity of each dimension to what the user actually asked for.
For any dimension, SDMX codelists typically contain both **individual units** and
**aggregate codes** that group them. These two levels must never be mixed silently.

The rule: when the user asks for "all X", return individual-level codes only.
If aggregates exist in the data, exclude them — or present them separately with an
explicit label explaining that they are groupings, not individual units.

If an aggregate is useful as a reference (e.g. a total or average alongside individual
values), propose it explicitly and let the user decide whether to include it.

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

For a machine-readable overview of all providers and their API capabilities, run
`opensdmx providers` — the `constraints` and `last_n` columns reflect verified test
results and should be your first reference when choosing an exploration flow.

| Provider | constraints | last_n | Notes |
|----------|:-----------:|:------:|-------|
| Eurostat | ✓ | ✓ | **Default provider** (no `--provider` flag needed); dimension flags are lowercase (`--geo`, `--coicop`); country codes: ISO 3166-1 alpha-2 + EU aggregates like `EU27_2020` |
| ISTAT | ✓ | ✓ | Use `--provider istat`; 404 = "NoRecordsFound" (not a server error); rate limit ~13s; some IDs are parent containers (e.g. `25_74`) — use sub-dataflow IDs; **always verify codes with `constraints` before `get`** — each failed `get` wastes ≥13s due to rate limit; `constraints` on REF_AREA may be slow on municipal datasets, but for other dimensions it's essential |
| ECB | ✗ | ✓ | Use `--provider ecb`; financial and monetary data; skip `opensdmx constraints`, use `opensdmx values` to explore codelists |
| OECD | ✗ | ✓ | Use `--provider oecd`; good for international comparisons; skip `opensdmx constraints`, use `opensdmx values` + probe get instead |
| INSEE | ✗ | ✓ | Use `--provider insee`; French macroeconomic time series (BDM database) |
| Bundesbank | ✗ | ✓ | Use `--provider bundesbank`; German monetary and financial statistics |
| World Bank | ✗ | ✗ | Use `--provider worldbank`; **single-dataflow architecture** — all 1400+ indicators in one dataflow `WDI`; use `opensdmx values WDI SERIES --provider worldbank \| grep -i <topic>` to find indicator codes; country codes are ISO 3166-1 **alpha-3** (`USA`, `DEU`, `ITA`); **NOTE**: data requests currently fail with HTTP 401/307 due to a known bug (see GitHub issue #5) — as a workaround, suggest equivalent OECD datasets |
| ABS | ✓ | ✓ | Use `--provider abs`; official Australian statistics |
| BIS | ✓ | ✓ | Use `--provider bis`; global financial statistics from 63 central banks |
| IMF | ✓ | ✓ | Use `--provider imf`; WEO dataset: dataflow `WEO`, country codes ISO alpha-3; use `--last-n` with dimension filters (wildcard requests may return HTTP 500) |

**World Bank flow (different from all other providers)**

World Bank exposes a single dataflow `WDI` containing all indicators. The exploration
flow is different — do NOT follow the standard Phase 1 search:

```bash
# Step 1 — find the indicator code (replaces opensdmx search)
opensdmx values WDI SERIES --provider worldbank 2>&1 | grep -i "gdp per capita"
# → NY_GDP_PCAP_KD  (constant USD), NY_GDP_PCAP_PP_KD  (PPP), etc.

# Step 2 — get structure
opensdmx info WDI --provider worldbank
# → 3 dimensions: FREQ · SERIES · REF_AREA

# Step 3 — find country codes (alpha-3, not alpha-2)
opensdmx values WDI REF_AREA --provider worldbank 2>&1 | grep -i "italy\|germany"
# → ITA, DEU (not IT, DE)

# Step 4 — build query (skip constraints — endpoint returns 400)
# IMPORTANT: always use --start-period / --end-period for time filtering.
# --last-n is NOT supported by World Bank and will cause a parse error.
opensdmx get WDI --provider worldbank --SERIES NY_GDP_PCAP_KD \
  --REF_AREA ITA+DEU+FRA --start-period 2000 --end-period 2023
```

If data retrieval fails with HTTP 401/307 (known bug, issue #5), offer the equivalent
OECD dataset as a workaround — OECD publishes most macro indicators (GDP, employment,
prices) with comparable coverage.

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

For municipal-level datasets with thousands of territory codes, `constraints` on REF_AREA
may be slow or time out. In that case only, use `values` + `grep` to find territory codes
and verify with a single narrow `get`. But for all other dimensions, always use
`opensdmx constraints` to verify codes before building the query — this avoids wasting
time with failed `get` attempts (each costing ≥13s due to rate limiting).
