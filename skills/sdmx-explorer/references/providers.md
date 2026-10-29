# Provider-specific Notes

This reference covers per-provider quirks that affect how you explore and fetch
data. Always start by running `opensdmx providers` — the `constraints` and
`last_n` columns reflect verified test results and tell you which exploration
flow fits the target provider.

For flows that deviate substantially from the default pattern, see the dedicated
references:

- **ISTAT** (rate limit, suffix patterns, territory codes, hub-backed
  `constraints` for ground-truth dimension values incl. `REF_AREA`):
  [istat-flow.md](istat-flow.md)
- **World Bank** (single-dataflow architecture, alpha-3 codes, known bug):
  [worldbank-flow.md](worldbank-flow.md)

## Capability matrix

| Provider | constraints | last_n | Notes |
|----------|:-----------:|:------:|-------|
| Eurostat | ✓ | ✓ | **Default provider** (no `--provider` flag needed); dimension flags are lowercase (`--geo`, `--coicop`); country codes: ISO 3166-1 alpha-2 + EU aggregates like `EU27_2020` |
| ISTAT | ✓ | ✓ | Use `--provider istat`; `constraints` uses the StatKit Data Browser hub by default — sub-second per dimension, exposes every dim including `REF_AREA`. Dedicated reference: [istat-flow.md](istat-flow.md) |
| ISTAT HVD | ✗ | ✓ | Use `--provider istat_hvd`; ISTAT High Value Datasets endpoint (`esploradati.istat.it/HVD`), 17 series: HICP, industrial producer prices, employment, unemployment, poverty, inequality, fertility, mortality, population (`DF_POP`), NAMEA air emissions, retail and wholesale sales volume (`BCS_TOR_M`, `BCS_TOW_M`). **Dataflow IDs differ from `istat`**: `DF_DCCV_TAXOCCU1` here merges the 16 `150_*_DF_DCCV_TAXOCCU1_*` of the main catalogue, so do not reuse IDs across the two. No `constraints` (`contentconstraint` 404, `availableconstraint` 500): use `values` and a probe `get` with `--last-n 1`. `tree` works: 15 dataflows under `CS_HVD`, the 2 sales-volume ones under `CS_VND`, the other schemes are empty. Shares ISTAT's per-IP limit: opensdmx paces both providers on one timer |
| INPS | ✓ | ✗ | Use `--provider inps`; **hub-only** provider (classic SDMX-REST is WAF-blocked, so everything goes through the DataBrowser middleware). Four observatories appear as schemes in `opensdmx tree` (pensioni, dipendenti, imprese, politiche occupazionali). `constraints` returns ground-truth values incl. NUTS-2021 territory codes (Lombardia=`ITC4`); dimension IDs are uppercase (`TERRITORIO`, `INDICATORI`, ...). `opensdmx get` **works**: it downloads the full dataflow (the middleware has no server-side filter) and applies dimension filters client-side; the period window (`--start-period`/`--end-period`) is applied client-side by year, and `--last-n`/`--first-n` are unavailable (`last_n ✗`). |
| ECB | ✗ | ✓ | Use `--provider ecb`; financial and monetary data; skip `opensdmx constraints`, use `opensdmx values` to explore codelists |
| OECD | ✗ | ✓ | Use `--provider oecd`; good for international comparisons; skip `opensdmx constraints`, use `opensdmx values` + probe `get` instead |
| INSEE | ✗ | ✓ | Use `--provider insee`; French macroeconomic time series (BDM database) |
| Bundesbank | ✗ | ✓ | Use `--provider bundesbank`; German monetary and financial statistics |
| World Bank | ✗ | ✗ | Use `--provider worldbank`; dedicated reference: [worldbank-flow.md](worldbank-flow.md) |
| ABS | ✓ | ✓ | Use `--provider abs`; official Australian statistics |
| BIS | ✓ | ✓ | Use `--provider bis`; global financial statistics from 63 central banks |
| IMF | ✓ | ✓ | Use `--provider imf`; WEO dataset: dataflow `WEO`, country codes ISO alpha-3; use `--last-n` with dimension filters (wildcard requests may return HTTP 500) |
| ILO | ✗ | ✓ | Use `--provider ilo`; ILOSTAT labour statistics, 1,200+ dataflows reachable through `tree`. Country codes ISO alpha-3 (`ITA`); codes carry their dimension as prefix (`SEX_T`, `AGE_10YRBANDS_Y55-64`), so read them with `opensdmx values`. Many series are quarterly. Skip `opensdmx constraints` |
| UNICEF | ✓ | ✓ | Use `--provider unicef`; child and SDG indicators, country codes ISO alpha-3. One dataflow holds many indicators (`CME` = child mortality, 34 codes in `INDICATOR`): filter `--INDICATOR` after `constraints`. No `tree` (`categorisation` answers 404): use `search` |
| Derzhstat | ✓ | ✓ | Use `--provider derzhstat`; State Statistics Service of Ukraine. No `tree`: use `search`. Territory codes are KATOTTG (`UA74000000000025378`); dimension filters are applied client-side after the download, so a filtered `get` still downloads every series; narrow it with `--start-period` or `--last-n`, which do reach the server |
| BFS | ✓ | ✓ | Use `--provider bfs` (alias `fso`); Swiss Federal Statistical Office. Partial SDMX catalogue: population, mobility and transport, crime and criminal justice, then employment, housing, tourism, health, education. **No dataflows for prices or national accounts (GDP)**: look elsewhere for Swiss CPI or GDP. The `tree` misses some dataflows (`DF_VOTATION` exists, the Politics branch is empty), so run `search` too. Totals are `_T` |

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

For providers marked ✗ in the `constraints` column (ECB, OECD, INSEE, Bundesbank, ILO,
World Bank, ISTAT HVD), the standard Phase 2 flow does not apply. Use `opensdmx values
<dataflow_id> <DIM>` to explore codelists, and probe with a narrow `get`
(small time window, one or two values per dimension) to verify the query works
before downloading the full series.

## When `last_n` is not supported

World Bank does not accept `--last-n`. Use `--start-period` / `--end-period`
with an explicit date range for previews — passing `--last-n N` causes a parse
error.

## User-declared providers

The user can add providers, or override fields of a built-in one (for example a slower `rate_limit` for `istat`), in a JSON file merged over the bundled `portals.json`: `$OPENSDMX_PORTALS`, otherwise `$XDG_CONFIG_HOME/opensdmx/portals.json`, otherwise `~/.config/opensdmx/portals.json`. Format and merge rules: [docs/providers.md](https://github.com/ondata/opensdmx/blob/main/docs/providers.md#user-level-provider-overrides).

- A provider declared there is used by name or alias (`--provider mysdmx`) and listed by `opensdmx providers`. One that is not in the bundled `portals.json` is not in the capability matrix above: its columns show `?` unless the file declares `constraints_supported`, `last_n_supported` or `categories_supported`, so probe instead of assuming. `tree` tries `/categoryscheme` live, `--last-n` is attempted.
- An override of a bundled provider is merged key by key, so it keeps the bundled columns for every field it does not set: `{"istat": {"rate_limit": 30}}` still reads `✓` for the capabilities `istat` declares.
- Lines on stderr starting with `portals:` come from that file: `aliases` that is not a list of non-empty strings, a non-numeric `rate_limit`/`data_rate_limit`, an entry without `base_url`, an alias clash, or a file that cannot be parsed (then the built-in providers are used unchanged). If a user provider is missing or behaves like the built-in one, read those lines first.
- If the user keeps passing the same `--provider https://...` URL, suggest declaring it once in that file.
