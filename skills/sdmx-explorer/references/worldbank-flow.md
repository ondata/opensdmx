# World Bank Flow

World Bank's SDMX endpoint differs from every other supported provider in two
fundamental ways:

1. **Single-dataflow architecture** — all 1400+ World Development Indicators
   live inside a single dataflow called `WDI`. The "search for a dataflow"
   step from the standard Phase 1 does not apply.
2. **No `constraints` and no `last_n`** — both endpoints are unsupported. Code
   discovery happens through `values`, and time filtering must use explicit
   start/end periods.

## Known issue — data requests fail with HTTP 401/307

As of the latest tests, World Bank data retrieval fails intermittently with
HTTP 401 or 307 errors (see [GitHub issue #5](https://github.com/ondata/opensdmx/issues/5)).
When this happens, suggest the equivalent **OECD** dataset as a workaround —
OECD publishes most macro indicators (GDP, employment, prices) with comparable
country and time coverage.

## Exploration flow

### Step 1 — find the indicator code (replaces `opensdmx search`)

```bash
opensdmx values WDI SERIES --provider worldbank 2>&1 | grep -i "gdp per capita"
# → NY_GDP_PCAP_KD  (constant USD)
# → NY_GDP_PCAP_PP_KD  (PPP)
```

The `SERIES` dimension carries the indicator concept. Pipe through `grep -i`
to narrow down by topic.

### Step 2 — check structure

```bash
opensdmx info WDI --provider worldbank
# → 3 dimensions: FREQ · SERIES · REF_AREA
```

### Step 3 — find country codes (alpha-3, not alpha-2)

```bash
opensdmx values WDI REF_AREA --provider worldbank 2>&1 | grep -i "italy\|germany"
# → ITA, DEU  (not IT, DE)
```

World Bank uses ISO 3166-1 **alpha-3** codes — do not use the alpha-2 codes
that work for Eurostat (`IT`, `DE`).

### Step 4 — build the query

```bash
opensdmx get WDI --provider worldbank \
  --SERIES NY_GDP_PCAP_KD \
  --REF_AREA ITA+DEU+FRA \
  --start-period 2000 --end-period 2023
```

Two things to remember:

- `constraints` is unsupported — go straight from `values` to `get` (skip the
  verification step that's standard for ISTAT/Eurostat).
- `--last-n` is unsupported and triggers a parse error — always use
  `--start-period` / `--end-period` for time filtering, even for previews.
