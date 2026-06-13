# DuckDB — Setup and Use with sdmx-explorer

DuckDB is used throughout this skill to transform, filter, and reshape raw SDMX data
before plotting or analysis. It is not required to *fetch* data (the `opensdmx` CLI
handles that), but it becomes essential the moment you need to:

- select the most recent year per country
- exclude aggregate codes (e.g. `EU27_2020`) from country rankings
- pivot from long to wide format
- join two dataflows on a shared dimension
- compute derived columns (e.g. ratios, differences)

## Check if DuckDB is available

```bash
duckdb --version
```

If the command is not found, install it before proceeding.

## Installation

```bash
# macOS
brew install duckdb

# Linux
curl -fsSL https://install.duckdb.org | sh

# Windows
winget install DuckDB.cli
```

## Typical usage with SDMX data

All examples assume the data was downloaded with `opensdmx get ... --out data.csv`.
Add `--labels` to that command to get `<dim>_label` columns (human-readable names)
alongside the codes — it avoids a manual codelist join in DuckDB.

### Quick inspection

```bash
duckdb -c "DESCRIBE SELECT * FROM 'data.csv';"
duckdb -c "SUMMARIZE SELECT * FROM 'data.csv';"
```

### Select most recent year per series

```bash
duckdb -c "
SELECT geo, sex, TIME_PERIOD, OBS_VALUE
FROM 'data.csv'
WHERE TIME_PERIOD = (SELECT MAX(TIME_PERIOD) FROM 'data.csv')
ORDER BY OBS_VALUE DESC;
"
```

### Exclude aggregate geo codes

```bash
duckdb -c "
SELECT * FROM 'data.csv'
WHERE geo NOT IN ('EU27_2020', 'EA20', 'EA21', 'EU', 'EU28');
"
```

### Save a transformed subset for plotting

```bash
duckdb -c "
COPY (
  SELECT geo, sex, OBS_VALUE AS pct
  FROM 'data.csv'
  WHERE TIME_PERIOD = '2023-01-01'
    AND sex IN ('M', 'F')
    AND geo NOT IN ('EU27_2020', 'EA20', 'EU')
) TO 'data_chart.csv' (HEADER, DELIMITER ',');
"
```

## Notes

- DuckDB reads CSV, Parquet, and JSON directly — no import step needed.
- The `duckdb -c "<sql>"` pattern is ideal for one-shot transformations.
- Use `FROM 'file.csv'` shorthand (no `SELECT *` needed) for quick reads.
