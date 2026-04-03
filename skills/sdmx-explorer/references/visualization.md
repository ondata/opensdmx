# Data Visualization with plotnine (Grammar of Graphics)

The `opensdmx plot` command uses **plotnine** — the Python port of **ggplot2** — which
implements Leland Wilkinson's **Grammar of Graphics**. This means every chart is built
by composing independent layers: data, aesthetics (mappings), geometries, scales, and
themes. Understanding this grammar helps you build better charts.

## Supported chart types

The built-in `opensdmx plot` command supports three chart types via `--geom`:

| `--geom` | Type                   | Best for                          | Notes                                        |
|----------|------------------------|-----------------------------------|----------------------------------------------|
| `line`   | Line chart with points | Time series comparisons           | Default. Uses `geom_line` + `geom_point`     |
| `bar`    | Vertical bar chart     | Comparing categories over time    | With `--color` produces stacked bars         |
| `barh`   | Horizontal bar chart   | Rankings, sorted comparisons      | Bars auto-sorted by value (ascending)        |
| `point`  | Scatter plot           | Correlations between two variables| Uses `geom_point` only, no connecting lines  |

For other chart types — heatmaps, faceted plots, grouped (dodge) bars — write a
short Python script using plotnine directly. plotnine supports the full Grammar of
Graphics: `geom_bar`, `geom_col`, `geom_tile`, `geom_boxplot`, `facet_wrap`,
`facet_grid`, `coord_flip`, `position_dodge`, custom scales, and themes.

## Command reference

`opensdmx plot` accepts both dataflow IDs and local files (.csv, .tsv, .parquet):

```bash
# From a local CSV file
opensdmx plot /tmp/data.csv --color geo --title "My chart" --out /tmp/chart.png

# From a dataflow (fetches data on the fly)
opensdmx plot une_rt_m --freq M --geo IT+DE --color geo --out /tmp/chart.png
```

### Options

| Option           | Default        | Description                              |
|------------------|----------------|------------------------------------------|
| `--x`            | `TIME_PERIOD`  | Column mapped to x-axis                  |
| `--y`            | `OBS_VALUE`    | Column mapped to y-axis                  |
| `--color`        | (none)         | Column mapped to color aesthetic (groups) |
| `--title`        | dataset name   | Chart title                              |
| `--xlabel`       | column name    | X-axis label                             |
| `--ylabel`       | column name    | Y-axis label                             |
| `--out`          | `chart.png`    | Output file (.png, .pdf, .svg)           |
| `--width`        | `10`           | Width in inches                          |
| `--height`       | `5`            | Height in inches                         |
| `--start-period` | (none)         | Start period filter (dataflow mode only) |
| `--end-period`   | (none)         | End period filter (dataflow mode only)   |

## Data preparation before plotting

Raw SDMX data almost always needs preparation before it produces a good chart.
Use DuckDB to transform the data. The goal is: one clean CSV with only the columns
and rows the chart needs.

### Rule 1: Separate incompatible units

Never mix absolute numbers and rates in the same chart (e.g. `NR` and `P_MHAB`).
They have different scales — the smaller unit gets crushed to a flat line.

```bash
# Extract only rate per million
duckdb -c "
COPY (
  SELECT geo, strftime(TIME_PERIOD, '%Y') as year, OBS_VALUE
  FROM '/tmp/data.csv'
  WHERE unit = 'P_MHAB'
  ORDER BY geo, TIME_PERIOD
) TO '/tmp/data_rate.csv' (HEADER, DELIMITER ',');
"
```

### Rule 2: Limit series count

More than 6-8 color groups makes a chart unreadable. Select the most relevant:

- **Top N by value**: use `ORDER BY ... DESC LIMIT N`
- **User-specified**: the countries or categories the user asked about
- **Meaningful subsets**: EU founding members, Mediterranean countries, etc.

```bash
# Top 6 countries by total deaths
duckdb -c "
COPY (
  SELECT geo, strftime(TIME_PERIOD, '%Y') as year, OBS_VALUE
  FROM '/tmp/data.csv'
  WHERE unit = 'NR'
    AND geo IN (
      SELECT geo FROM '/tmp/data.csv'
      WHERE unit = 'NR'
      GROUP BY geo ORDER BY sum(OBS_VALUE) DESC LIMIT 6
    )
  ORDER BY geo, TIME_PERIOD
) TO '/tmp/data_top6.csv' (HEADER, DELIMITER ',');
"
```

### Rule 3: Remove aggregates from comparative charts

EU27 or OECD totals dwarf individual countries. Either show them separately
or exclude them from country comparisons.

### Rule 4: Use year strings for annual data

plotnine sometimes misparses SDMX date columns (`2023-01-01`) for annual data,
producing disconnected points instead of connected lines. Extract the year as a
string to avoid this:

```bash
duckdb -c "
COPY (
  SELECT geo, strftime(TIME_PERIOD, '%Y') as year, OBS_VALUE
  FROM '/tmp/data.csv'
  ORDER BY geo, TIME_PERIOD
) TO '/tmp/data_clean.csv' (HEADER, DELIMITER ',');
"
```

Then plot with `--x year` instead of `--x TIME_PERIOD`.

## Iterative chart quality loop

After generating any chart, you MUST follow this review cycle:

### 1. Read and evaluate

Read the generated image using the Read tool. Check:

- **Readability**: can you distinguish all series? Is the legend clear and not
  overlapping the data? Are labels legible?
- **Scale**: does one series dwarf all others? Are the axes appropriate for the data
  range? Is there wasted whitespace?
- **Meaning**: does the chart actually answer the user's question? Would someone
  unfamiliar with the data understand the story?
- **Cleanliness**: are the title, axis labels, and legend informative (not raw
  column names like `OBS_VALUE`)?

### 2. Fix and regenerate

If any check fails, diagnose the problem, prepare a better dataset, and regenerate.
Do NOT show the user a bad chart and ask them to fix it. Fix it yourself first.

Common problems and fixes:

| Problem                   | Diagnosis                        | Fix                                                      |
|---------------------------|----------------------------------|-----------------------------------------------------------|
| Lines not connected       | Date parsing issue               | Use year strings (`strftime(TIME_PERIOD, '%Y')`)          |
| One series crushes others | Mixed units or aggregate present | Separate units; remove EU27/OECD totals                   |
| Unreadable legend         | Too many series                  | Filter to top N; split into multiple charts               |
| Flat lines at bottom      | Scale mismatch                   | Separate charts per unit                                  |
| Scattered points          | Multiple values per x-position   | Check for duplicate dimensions; add more filters          |
| Title says "OBS_VALUE"    | Default labels used              | Set `--title`, `--ylabel`, `--xlabel` explicitly          |

### 3. Present to user

Once the chart is clean and informative, show it to the user with a brief explanation
of what it shows. Then ask if they want adjustments:

```
Here is the chart showing [what it shows]. [One sentence on the key insight.]
Would you like to adjust anything — different countries, time range, or chart style?
```

### 4. Multiple charts are often better than one

When the data has multiple meaningful facets (e.g. absolute numbers AND rates,
or data for 30+ countries), propose a set of focused charts rather than cramming
everything into one:

- Chart 1: top 6 countries by absolute numbers (line chart over time)
- Chart 2: all countries ranked by rate, latest year (prepared as a sorted CSV
  for bar-chart-style analysis or table)

Explain the rationale: "I split this into two charts because mixing absolute numbers
and rates on the same axis would make one of them invisible."
