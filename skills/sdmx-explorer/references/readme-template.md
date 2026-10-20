# README template for SDMX explorations

The goal of a README is to make the output **verifiable, evaluable, and repeatable**:

- **Verifiable** — anyone can check a value against the original source
- **Evaluable** — enough context to judge quality, scope, and limitations
- **Repeatable** — enough detail to reproduce the exact same dataset from scratch

Generate a `README.md` in the same folder as the output file(s).
Follow this structure, in order.

---

## Structure

### Title and one-line description

State the topic and unit of measurement in plain language.

```markdown
# Drinking water consumption per capita in Europe (2019–2023)

Water supplied by the public network to households, expressed in litres
per inhabitant per day.
```

---

### Files

List every file produced with a short description.

```markdown
| File | Description |
|---|---|
| `water_per_capita_eu.csv` | Final dataset — per-capita consumption by country and year |
| `water_eu.csv`            | Source: absolute volumes in million m³ (ENV_WAT_CAT) |
| `pop_eu.csv`              | Source: population on 1 January (DEMO_PJAN) |
```

---

### Source dataflows

**One subsection per dataflow used.** This section is the backbone of
verifiability: it must contain enough information for anyone to re-download
the exact same data independently.

For each dataflow, document:

1. Dataset ID and full title
2. Provider (Eurostat, ISTAT, OECD, …)
3. Filters applied — dimension code, value code, human-readable label
4. Unit of measurement
5. The exact download URL (curl-compatible, from Phase 4 Step 2)
6. The methodology page, when `opensdmx info` shows a `Metadata:` line

Example:

```markdown
#### Water consumption

- **Dataset**: `ENV_WAT_CAT` — Water use by supply category and economical sector
- **Provider**: Eurostat
- **Filters**:
  - `wat_proc = PWS` → Public Water Supply
  - `nace_r2 = EP_HH` → Households
  - Period: 2019–2023
- **Unit**: million m³ (MIO_M3)
- **Last updated**: 31/07/2025
- **Metadata**: https://ec.europa.eu/eurostat/cache/metadata/en/env_nwat_esms.htm
- **Download URL**:

      https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/ENV_WAT_CAT/A.PWS.EP_HH.MIO_M3./ALL/?startPeriod=2019&endPeriod=2023&format=SDMX-CSV
```

If the only source is a single dataflow with no joins, this section alone
is enough to make the output fully verifiable.

---

### Derivations

Document every transformation between the raw downloads and the final file.
This section makes the output **repeatable**: given the source files,
anyone must be able to re-run the same steps and get the same result.

Include:

- **Join keys** when two or more dataflows were merged
- **Filters** applied after download (e.g. keeping only certain codes)
- **Computed columns** with the exact formula

Write formulas in plain math or SQL — not prose.

Example:

```markdown
The final dataset joins `water_eu.csv` and `pop_eu.csv` on `(geo, anno)`.

**Computed columns:**

    m3_per_capita           = water_mio_m3 × 1_000_000 / population
    litri_giorno_per_capita = water_mio_m3 × 1_000_000_000 / population / 365

Population denominator: residents on 1 January of the reference year.
```

If no derivation was applied (data used as-is), write: "No transformations applied."

---

### Column schema

For every column in the final CSV: name, type, description, unit.

```markdown
| Column | Type | Description |
|---|---|---|
| `geo`                     | string  | ISO 3166-1 alpha-2 country code |
| `anno`                    | integer | Reference year |
| `water_mio_m3`            | float   | Volume supplied to households — million m³ |
| `population`              | integer | Population on 1 January |
| `m3_per_capita`           | float   | m³ per inhabitant per year |
| `litri_giorno_per_capita` | float   | Litres per inhabitant per day |
| `OBS_FLAG`                | string  | Quality flag (see Flag legend) |
```

---

### Flag legend

List only the `OBS_FLAG` values **actually present** in the final data,
with their meaning and row count. This lets readers evaluate data quality at a glance.

```markdown
| Code       | Meaning     | Rows |
|---|---|---|
| *(absent)* | Confirmed   | 91   |
| `e`        | Estimated   | 18   |
| `i`        | Imputed     | 3    |
| `p`        | Provisional | 2    |
```

Common Eurostat flag codes for reference:

| Code | Meaning |
|---|---|
| `b` | Break in time series |
| `c` | Confidential |
| `d` | Definition differs |
| `e` | Estimated |
| `i` | Imputed |
| `n` | Not significant |
| `p` | Provisional |
| `r` | Revised |
| `s` | Eurostat estimate |
| `u` | Unreliable |
| `z` | Not applicable |

---

### Coverage

When the dataset includes a geographic or categorical dimension, show
availability per entity. Gaps here are part of evaluability.

```markdown
| Country | Code | Years available | Range     |
|---|---|---|---|
| Austria | AT   | 5               | 2019–2023 |
| Belgium | BE   | 3               | 2019–2021 |
| Spain   | ES   | 2               | 2019–2020 |
```

---

### Caveats

Document limitations that affect how the data should be interpreted or compared.
This section is essential for evaluability.

Always check and mention:
- Years or countries with incomplete coverage
- Flags covering a large share of rows (>10%)
- Conceptual scope: what the indicator includes and excludes
- Known biases (e.g. tourist pressure, reporting lags, definition changes)

Example:

```markdown
- 2023 data available for only 17 of 27 countries (late reporting)
- Measures water **distributed** through the public network — excludes
  private wells and self-supply
- Countries with high tourism density may show inflated per-capita values
```

---

## Checklist before saving

- [ ] Every source dataflow has its section with filters and a download URL
- [ ] Derivations section documents every join, filter, and formula
- [ ] Column schema covers every column in the output file
- [ ] Flag legend shows only flags present in the data, with row counts
- [ ] Coverage table present when geographic or categorical gaps exist
- [ ] Caveats mention any flags covering >10% of rows, and scope limitations
