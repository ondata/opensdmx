# Provider-specific Notes

This reference covers per-provider quirks that affect how you explore and fetch
data. Always start by running `opensdmx providers` — the `constraints` and
`last_n` columns reflect verified test results and tell you which exploration
flow fits the target provider.

For flows that deviate substantially from the default pattern, see the dedicated
references:

- **ISTAT** (rate limit, suffix patterns, territory codes, mandatory `constraints`
  step): [istat-flow.md](istat-flow.md)
- **World Bank** (single-dataflow architecture, alpha-3 codes, known bug):
  [worldbank-flow.md](worldbank-flow.md)

## Capability matrix

| Provider | constraints | last_n | Notes |
|----------|:-----------:|:------:|-------|
| Eurostat | ✓ | ✓ | **Default provider** (no `--provider` flag needed); dimension flags are lowercase (`--geo`, `--coicop`); country codes: ISO 3166-1 alpha-2 + EU aggregates like `EU27_2020` |
| ISTAT | ✓ | ✓ | Use `--provider istat`; dedicated reference: [istat-flow.md](istat-flow.md) |
| ECB | ✗ | ✓ | Use `--provider ecb`; financial and monetary data; skip `opensdmx constraints`, use `opensdmx values` to explore codelists |
| OECD | ✗ | ✓ | Use `--provider oecd`; good for international comparisons; skip `opensdmx constraints`, use `opensdmx values` + probe `get` instead |
| INSEE | ✗ | ✓ | Use `--provider insee`; French macroeconomic time series (BDM database) |
| Bundesbank | ✗ | ✓ | Use `--provider bundesbank`; German monetary and financial statistics |
| World Bank | ✗ | ✗ | Use `--provider worldbank`; dedicated reference: [worldbank-flow.md](worldbank-flow.md) |
| ABS | ✓ | ✓ | Use `--provider abs`; official Australian statistics |
| BIS | ✓ | ✓ | Use `--provider bis`; global financial statistics from 63 central banks |
| IMF | ✓ | ✓ | Use `--provider imf`; WEO dataset: dataflow `WEO`, country codes ISO alpha-3; use `--last-n` with dimension filters (wildcard requests may return HTTP 500) |

## Dimension flag case

Dimension flags in `opensdmx get` follow the case used by the provider's own
SDMX metadata:

- **Eurostat** — lowercase (`--geo`, `--coicop`, `--freq`, `--sex`)
- **ISTAT** — uppercase (`--REF_AREA`, `--DATA_TYPE`, `--FREQ`)
- Other providers — check the output of `opensdmx info <dataflow>` and use the
  exact casing shown there.

## Territory codes — Eurostat

Country codes follow ISO 3166-1 alpha-2: `IT` (Italy), `DE` (Germany),
`FR` (France), `ES` (Spain). EU aggregates: `EU27_2020`, `EA20` (Euro area).
Verify against `opensdmx constraints` before using — not all codes are present
in every dataset.

## Territory codes — ISTAT

See [istat-flow.md](istat-flow.md) for numeric municipal/province/region codes
and aggregate codes (`ITG12`, `SLL_*`, etc.).

## When `constraints` is not supported

For providers marked ✗ in the `constraints` column (ECB, OECD, INSEE, Bundesbank,
World Bank), the standard Phase 2 flow does not apply. Use `opensdmx values
<dataflow_id> <DIM>` to explore codelists, and probe with a narrow `get`
(small time window, one or two values per dimension) to verify the query works
before downloading the full series.

## When `last_n` is not supported

World Bank does not accept `--last-n`. Use `--start-period` / `--end-period`
with an explicit date range for previews — passing `--last-n N` causes a parse
error.
