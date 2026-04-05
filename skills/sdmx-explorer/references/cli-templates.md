# CLI Templates for Common Chart Scenarios

Ready-to-use `opensdmx plot` parameter combinations for typical SDMX use cases.
All assume data has been prepared with DuckDB first (see `visualization.md`).

## Time series — N countries, line chart

```bash
opensdmx plot /tmp/data.csv \
  --geom line \
  --x year --y OBS_VALUE --color geo \
  --title "Unemployment rate by country" \
  --ylabel "%" --xlabel "" \
  --width 12 --height 6 \
  --out /tmp/timeseries.png
```

**Best for:** ≤ 8 countries, trend over time.
**Prep:** extract year string, remove EU aggregates, one unit only.

---

## Rankings — horizontal bar, single year

```bash
opensdmx plot /tmp/data.csv \
  --geom barh \
  --x geo --y OBS_VALUE \
  --title "Unemployment rate, 2023" \
  --ylabel "" --xlabel "%" \
  --width 10 --height 7 \
  --out /tmp/ranking.png
```

**Best for:** comparing all countries at a single point in time.
**Prep:** filter to one year and one unit; sort by value in DuckDB.
**Note:** `barh` auto-sorts bars by value — no need to pre-sort.

---

## Stacked bar — categories over time

```bash
opensdmx plot /tmp/data.csv \
  --geom bar \
  --x year --y OBS_VALUE --color category \
  --title "Production by type" \
  --ylabel "Quintals" --xlabel "" \
  --width 10 --height 6 \
  --out /tmp/stacked.png
```

**Best for:** part-to-whole breakdown across years (≤ 5 categories).

---

## Faceted — one panel per group

```bash
opensdmx plot /tmp/data.csv \
  --geom bar \
  --x year --y OBS_VALUE --color category \
  --facet geo --ncol 4 \
  --title "Production by province" \
  --ylabel "Quintals" --xlabel "" \
  --width 16 --height 8 \
  --out /tmp/facets.png
```

**Best for:** comparing patterns across many groups (countries, provinces, age bands).
**Rule:** keep `--ncol` such that panels are roughly square. For 5 panels use `--ncol 5`;
for 12 panels try `--ncol 4` (3 rows of 4).
**Labels:** if x-axis labels overlap in faceted charts, prefer short strings in DuckDB
(e.g. year as `'22`, `'23`) or use `--geom barh` to flip axes.

---

## Scatter — two numeric variables

```bash
opensdmx plot /tmp/data.csv \
  --geom point \
  --x gdp --y unemployment --color geo \
  --title "GDP vs Unemployment" \
  --xlabel "GDP per capita (USD)" --ylabel "Unemployment (%)" \
  --width 10 --height 7 \
  --out /tmp/scatter.png
```

---

## Size / dimensions quick reference

| Chart type         | `--width` | `--height` | Notes                         |
|--------------------|-----------|------------|-------------------------------|
| Line, ≤ 6 series   | 12        | 6          | Standard                      |
| Bar, ≤ 5 years     | 10        | 6          | Standard                      |
| Barh, 20 countries | 10        | 9          | Taller for more bars          |
| Facet, 5 panels    | 16        | 6          | Wide                          |
| Facet, 12 panels   | 16        | 10         | Wide + tall                   |
| Scatter            | 10        | 7          | Near-square                   |
