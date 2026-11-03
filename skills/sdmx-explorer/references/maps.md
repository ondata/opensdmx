# Maps of Eurostat data with eurostat-map

When the user asks for a map and the data comes from Eurostat, build a single self-contained HTML page with [eurostat-map](https://github.com/eurostat/eurostat-map), the D3 library Eurostat itself uses for its regional publications. No CLI change is involved: `opensdmx get` downloads the data, DuckDB shapes it, and the HTML is written by hand from the template below.

## Contents

- When this applies
- Step 1 — Get one value per region
- Step 2 — Choose the map type and NUTS level
- Step 3 — Write the HTML
- Export to PNG and SVG
- Insets for the overseas regions
- Colours that separate the classes
- Step 4 — Verify the map
- Pitfalls

This file covers the choropleth, the common data preparation, colours, insets, export and verification. Other map types have their own sub-reference, to read after this one:

- [maps-symbols.md](maps-symbols.md) — proportional symbols: one variable as circle size, or two variables (size + colour), with the dorling layout that keeps circles from overlapping
- [maps-flow.md](maps-flow.md) — flow maps between countries (trade, migration) from origin-destination data, e.g. Comext
- [maps-annotations.md](maps-annotations.md) — callout notes that point at a region on any map type

## When this applies

- **Provider is Eurostat** (or Comext, `-p comext`, for flow maps: see [maps-flow.md](maps-flow.md)) and the dataflow has a `geo` dimension with country or NUTS codes (`IT`, `ITC4`, `ITC4C`). eurostat-map draws NUTS geometries from [Nuts2json](https://github.com/eurostat/Nuts2json), and its region IDs are exactly Eurostat `geo` codes, so no join or code translation is needed.
- **Not for other providers.** ISTAT, OECD, World Bank and the others use their own territorial codes (ISTAT `ITTER107`, ISO alpha-3), which do not match NUTS IDs. For those, say that this recipe does not apply and propose a chart instead.
- The user asks for a map, or the data is regional and a map would read better than a bar chart: offer it as an option after SKILL.md Phase 4, Step 6 — Visualization.

"Self-contained" means one HTML file with the data embedded in it. The page still needs an internet connection when opened: it loads the library from unpkg and the NUTS geometries from Nuts2json on GitHub. Say this when you hand over the file.

## Step 1 — Get one value per region

A map shows one number per region. Fix every dimension except `geo` to a single code, and pick one time period.

```bash
opensdmx get tgs00010 --sex T --isced11 TOTAL --last-n 1 --labels --out data.csv
```

`--last-n 1` returns the last observation **of each series**, and series end in different years: in the example above, 289 regions have 2025 and 41 stop at 2019. Never map that mix. Use this download only as a preview, to choose the year: check when the series end and pick the year with most regions (usually the latest):

```bash
duckdb -c "select year(TIME_PERIOD) y, count(*) n
           from read_csv('data.csv', all_varchar=true, types={'OBS_VALUE':'DOUBLE','TIME_PERIOD':'DATE'})
           group by 1 order by 1"
```

Read the CSV with `all_varchar=true`: DuckDB otherwise sniffs `sex=T` as a BOOLEAN and codes like `EL`, `NO` can be mangled. Cast only `OBS_VALUE` and `TIME_PERIOD`.

These counts say when each series **ends**, not how many regions have a value in a given year: a region whose series ends in 2025 is missing from the 2024 count even when it has a 2024 value. So fetch the chosen year itself before building the map data:

```bash
opensdmx get tgs00010 --sex T --isced11 TOTAL --start-period 2025 --end-period 2025 --labels --out data.csv
```

Then export a JSON object keyed by `geo`, the shape `statData().setData()` expects (`{"AT11": {"value": 5.0, "status": ""}, ...}`). The `status` carries the Eurostat flag (`e` estimated, `p` provisional, `b` break) and the library shows it in the tooltip.

```bash
duckdb -json -c "
select json_group_object(geo, json_object(
         'value', case when OBS_VALUE = 0 then 1e-9 else OBS_VALUE end,   -- see below
         'status', coalesce(OBS_FLAG, ''))) d
from read_csv('data.csv', all_varchar=true, types={'OBS_VALUE':'DOUBLE','TIME_PERIOD':'DATE'})
where year(TIME_PERIOD) = 2025
  and OBS_VALUE is not null
  and length(geo) = 4                  -- one NUTS level only, see Step 2
" | jq -c '.[0].d' > data.json
jq length data.json                    # number of regions that will be coloured
```

**Never pass an exact 0.** eurostat-map 4.12-4.13 treats the value 0 as missing and gives the region an invalid class (`NaN`): on a choropleth the region turns grey as if it had no data; on proportional symbols the colour function throws, every circle drawn after it stays black and the dorling layout never starts — with no visible error, only a line in the console. Replacing 0 with `1e-9` puts the region in the class that starts at 0, and the tooltip still shows "0". Verified on both map types.

Before writing the HTML, check that only one row per `geo` survives (`count(*) = count(distinct geo)`): if not, a dimension is still unfixed.

## Step 2 — Choose the map type and NUTS level

**NUTS level from the code length**: 2 characters = country (level 0), 3 = NUTS 1, 4 = NUTS 2, 5 = NUTS 3. Keep one level and set `.nutsLevel()` to match. Aggregates (`EU27_2020`, `EA20`, `EU28`) have no geometry: filter them out with the length condition and mention the EU value in the subtitle if it matters.

**Map type** depends on what the number is:

| Variable | Map type | Why |
|---|---|---|
| Rate, share, density, per-capita, index (intensive) | `choropleth` | Colour compares values regardless of region size |
| Count, total, absolute amount (extensive: population, GDP in MIO_EUR, nights spent) | `proportionalSymbol` → [maps-symbols.md](maps-symbols.md) | Colouring big regions by totals mostly shows area; circles scale with the amount |
| A total and a rate together (population and its change, GDP and GDP per head) | `proportionalSymbol` with size + colour → [maps-symbols.md](maps-symbols.md) | Size carries the total, colour the rate |
| Flows between places (exports by partner, migration by origin) | `flow` → [maps-flow.md](maps-flow.md) | Needs origin-destination data, not one value per region |

For a total the user wants as a choropleth, propose dividing by population or area first.

**NUTS version** (`.nutsYear()`): default 2024. Recent Eurostat regional tables use NUTS 2024; older or long series may still be coded in NUTS 2021 or 2016. If regions you have data for show up grey, change `nutsYear` (2021, 2016) and compare. Available versions are listed in the [Nuts2json API](https://github.com/eurostat/Nuts2json/#api).

## Step 3 — Write the HTML

Inline the JSON with a heredoc. Pin the library version: an unpinned `unpkg.com/eurostat-map` follows every new release. `4.12.1` is the version this template was verified with.

```bash
DATA=$(jq -c . data.json)
cat > map.html <<EOF
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Unemployment rate by NUTS 2 region, 2025</title>
<style>
body{margin:0;font-family:system-ui,sans-serif;background:#fff}
#map{display:block;margin:0 auto}
.export{text-align:center;margin:8px 0}.export button{font:inherit;padding:4px 10px}
</style>
</head>
<body>
<svg id="map"></svg>
<p class="export"><button id="png">Download PNG</button> <button id="svg">Download SVG</button></p>
<script src="https://unpkg.com/eurostat-map@4.12.1/build/eurostatmap.min.js"></script>
<script>
const DATA = $DATA;
const map = eurostatmap.map('choropleth')
  .svgId('map').width(800).height(720)   // fixed size: same image for whoever exports it
  .zoomButtons(false)                    // they would end up in the exported image; wheel zoom still works
  .nutsLevel(2)
  .nutsYear(2024)
  .header(true).footer(true)
  .title('Unemployment rate by NUTS 2 region, 2025')
  .subtitle('Percentage of active population aged 15-74')
  .footnote('Source: Eurostat, dataset tgs00010')
  .showSourceLink(false)
  .numberOfClasses(6).classificationMethod('quantile')
  .colors(['#fde725','#7ad151','#22a884','#2a788e','#414487','#440154'])  // viridis, low -> high
  .noDataFillStyle('#969696')
  .noDataText('Data unavailable')        // library text: translate it, see below
  .legend({ title: '%', position: 'top right', decimals: 1 });
map.statData().setData(DATA);
map.statData().unitText('%');
map.build();

// Export with the library's own functions (see "Export to PNG and SVG").
const FILE = 'unemployment-nuts2-2025';
document.getElementById('png').onclick = () => {
  const svg = document.getElementById('map');
  map.exportMapToPNG(2 * svg.width.baseVal.value, 2 * svg.height.baseVal.value, FILE);
};
document.getElementById('svg').onclick = () => map.exportMapToSVG(FILE);
</script>
</body>
</html>
EOF
```

Fill title, subtitle, footnote and unit from what you learned in Phase 2-3: the title says what and when, the subtitle the fixed dimensions in words (from the `*_label` columns), the footnote the source and the dataflow ID. Write them in the user's language.

**Text generated by the library** is in English and is not covered by title and footnote: the no-data item in the legend and in the tooltip ("Data unavailable" / "No data"). Set it with `.noDataText()` in the user's language (`'Dati non disponibili'`, verified), together with the button labels of the page. Legends with their own no-data item (size legends of symbol maps) take `noDataText` in their own legend object.

**Numbers in legends follow the user's locale too.** The library writes `24.9` and `85.7 million`. For Italian, pass a `labelFormatter` to each legend (verified on class legends and size legends):

```js
// class legend: decimal comma
labelFormatter: v => (+v).toLocaleString('it-IT', { maximumFractionDigits: 1 })
// size legend: "85,7 mln", "38.423" (Intl compact notation would give "38,4K", not Italian usage)
labelFormatter: v => v >= 1e6 ? (v / 1e6).toLocaleString('it-IT', { maximumFractionDigits: 1 }) + ' mln'
                              : Math.round(v).toLocaleString('it-IT')
```

**The legend must sit on an empty area.** `position: 'top right'` falls on the sea on a map of Europe, but on a zoomed map (one country, a region) the same corner is often land with data on it: on the Italy zoom it covers Romania and Ukraine. Check the screenshot; if the legend covers coloured regions, move it to another corner (`position: 'top left'`, `'bottom left'`...) or place it with `x` / `y` over the sea.

**Place names.** Decide them by the number of units on the map:

- **Country level (NUTS 0)**: label the countries. Eurostat ships positioned labels: `eurostatmap.getDefaultLabels().EUR_3035.cc` (two-letter codes, language-neutral) and `.en` (English names, class `countries`, plus seas). Pass the filtered list to `.labels({ labels: [...] })`. Codes are the safe default: short, no translation needed. Names in the user's language can be made from the `cc` field with `Intl.DisplayNames`, but they are longer and collide more.
- **NUTS 2 and 3**: hundreds of regions, no labels; point at the few that matter with annotations ([maps-annotations.md](maps-annotations.md)).
- **Flow maps**: see [maps-flow.md](maps-flow.md) — codes on the flows, amounts in the footnote.

`showSourceLink(false)` because the link the library builds assumes it fetched the data itself through `eurostatDatasetCode`; here the data is inline and the footnote carries the source.

Useful variations:

- **Classes**: `classificationMethod` accepts `quantile` (default), `equinter`, `jenks`, `ckmeans`, `threshold`. With `threshold` set `.thresholds([5, 10, 15])` — good when the user has meaningful breaks in mind (e.g. the EU average).
- **Colours**: see the next section. `.colors([...])` takes one colour per class, from low to high. The bundle does not expose a global `d3`, so `d3.interpolate*` functions are not available in the page: always pass explicit hex lists.
- **Proportional symbols, flows, annotations**: see the sub-references listed at the top.
- **Single country focus**: keep the European frame but zoom with `.position({ x: <easting>, y: <northing>, z: <metres per pixel> })` in EPSG:3035. For Italy on an 800 × 720 map, `{ x: 4550000, y: 2250000, z: 2600 }` shows the whole country from the Alps to Sicily (verified). For other countries start from the centre of the country in EPSG:3035, check the screenshot and adjust: a larger `y` moves the view north, a larger `z` zooms out.
- **Overseas regions (insets)**: see "Insets for the overseas regions" below. Never use `.insets('default')`: its boxes cover the eastern part of the map.

## Export to PNG and SVG

The deliverable is the HTML file and nothing else: no executable, no extra install. The PNG and SVG come from the library itself, in the browser of whoever opens the page, through the two buttons of the template:

- `map.exportMapToPNG(width, height, filename)` redraws the SVG on a canvas at `width` × `height` and downloads `filename.png`. Passing twice the on-screen size gives a high-resolution image (1600 × 1440 for an 800 × 720 map).
- `map.exportMapToSVG(filename)` downloads the SVG, for editing in Inkscape or Illustrator.

Keep the buttons **outside** the `<svg>`, so they do not end up in the image. Fix `.width()` and `.height()`: without them the map takes its size from the browser window, and the same page exports a different framing on every screen.

The export copies the computed CSS styles onto each element. Effects that rely on paint order, such as a text halo made with `paint-order: stroke`, break in the PNG (the text turns white on white): for text that must stay readable over the map use a background box instead (see [maps-annotations.md](maps-annotations.md)).

A PNG without anyone opening the page is not possible with the library alone: something has to render the map, and the geometries load over the network. A plain `chrome --headless --screenshot` captures the page before the geometries arrive (only the loading spinner). Do not install a headless browser just for this: hand over the HTML and tell the user to click "Download PNG".

## Insets for the overseas regions

Canarias, Açores, Madeira, Malta and the French overseas regions are part of the data but are tiny or far away on the main map. Add insets when they matter: NUTS 2 and NUTS 3 maps, or whenever the user asks about them. For a country-level map Malta and Cyprus are visible enough and insets can be skipped.

`.insets('default')` is not readable: the library places its boxes over the eastern part of Europe (Turkey, Cyprus, the Black Sea coast). The layout below, verified on a NUTS 2 map, gives the insets their own column instead:

- a wider SVG (1000 × 700) with the insets in a 2 × 5 grid of 100 px boxes on the right;
- the mainland moved left and slightly zoomed out with `.position()`, so Turkey ends before the inset column;
- the legend in the top-left corner, over the Atlantic, where it covers nothing.

```js
const W = 1000, H = 700, S = 100, G = 6;           // map size, inset side, gap
const cell = (i, o) => ({ x: (i % 2) * (S + G), y: Math.floor(i / 2) * (S + G), width: S, height: S, ...o });
// Positions in EPSG:3035 from Eurostat's Regional Yearbook 2026 inset configuration.
const INSETS = [
  { geo: 'IC',   title: 'Canarias (ES)',   position: { x: 420000,  y: 3150000, z: 6800 } },
  { geo: 'PT20', title: 'Açores (PT)',     position: { x: 470000,  y: 4370000, z: 5000 } },
  { geo: 'PT30', title: 'Madeira (PT)',    position: { x: 323586,  y: 3632706, z: 2600 } },
  { geo: 'MT',   title: 'Malta',           position: { x: 4721000, y: 1440000, z: 900 } },
  { geo: 'GP',   title: 'Guadeloupe (FR)', position: { x: 680000,  y: 1810000, z: 1820 } },
  { geo: 'MQ',   title: 'Martinique (FR)', position: { x: 716521,  y: 1625000, z: 1800 } },
  { geo: 'GF',   title: 'Guyane (FR)',     position: { x: 269852,  y: 470000,  z: 6500 } },
  { geo: 'RE',   title: 'Réunion (FR)',    position: { x: 340011,  y: 7671627, z: 2000 } },
  { geo: 'YT',   title: 'Mayotte (FR)',    position: { z: 1200 } },
].map((c, i) => cell(i, c));

const map = eurostatmap.map('choropleth')
  .svgId('map').width(W).height(H)
  .position({ x: 5100000, y: 3480000, z: 7200 })   // mainland left of the inset column
  // ... nutsLevel, nutsYear, title, footnote, classes, colors, noDataFillStyle as in Step 3 ...
  .legend({ title: '%', position: 'top left', decimals: 1 });
map.statData().setData(DATA);
map.statData().unitText('%');
map.insets(INSETS).insetBoxPosition([W - 2 * S - G - 10, 70]);   // LAST, right before build()
map.build();
```

**Call `.insets()` last**, after `setData()`, `colors()`, `noDataFillStyle()` and the classification. The library copies the parent map's settings into each inset at the moment `.insets()` is called: put it earlier in the chain and the whole map, mainland included, renders without colours and without any console error.

Translate the inset titles into the user's language, and keep them short: a 100 px box fits about 14 characters, longer titles are cut ("Guyana francese (FR)" → "Guyana (FR)"). Drop the insets whose regions have no data in the chosen year, and recompute the grid. If the screenshot shows the mainland touching the inset column (a different NUTS level or a narrower page), increase `z` in `.position()` by about 5% at a time.

## Colours that separate the classes

A choropleth works only if the reader can tell which class each region falls in, by matching it against the legend. The cartographic literature agrees on a few rules, and they are what this section applies.

**Rules**

- **Ordered data, ordered lightness.** For a sequential variable, lightness must change steadily from low to high values: light = low, dark = high. Hue alone does not carry order; lightness does. Rainbow scales break this and mislead (Brewer 1994; Light & Bartlein 2004; Crameri et al. 2020).
- **Multi-hue beats single-hue.** Adding a hue change to the lightness ramp (yellow → green → blue) makes neighbouring classes easier to tell apart than shades of one hue (Brewer et al. 1997; Harrower & Brewer 2003).
- **Diverging data, diverging scheme.** When values have a meaningful midpoint (0 for a change rate, the EU average, 100 for an index), use two hues that grow darker away from a light neutral centre, and put a class break on the midpoint (Brewer 1994; Brewer et al. 1997).
- **No more than 6-7 classes.** Beyond that, adjacent classes become indistinguishable on a map, whatever the palette (Brewer 1994; Harrower & Brewer 2003). Use 5 or 6 by default.
- **Readable with colour-vision deficiency.** About 8% of men have a red-green deficiency. Avoid red-green pairs and prefer schemes that keep their lightness ramp under simulated deuteranopia and protanopia (Crameri et al. 2020).
- **No-data must not look like a class.** The library default `lightgray` is close to the lightest class of most sequential schemes and to the neutral centre of diverging ones. Use a mid grey (`#969696`) that stands apart from both.

**Measured contrast**

The table measures, for 6-class schemes, the smallest colour difference between two adjacent classes (CIEDE2000; Sharma et al. 2005) in normal vision and under simulated deuteranopia and protanopia (Machado et al. 2009), and the distance of the no-data grey from the nearest class. Higher is better. Below about 8 two adjacent classes start to blur on a map; the threshold is a working value from these measurements, not a standard.

| Scheme (6 classes) | Normal | Deutan | Protan | Gap from `lightgray` | Gap from `#969696` |
|---|---|---|---|---|---|
| **viridis** (sequential, default) | **18.5** | **11.4** | **9.3** | 28.3 | 23.2 |
| YlGnBu (ColorBrewer) | 10.7 | 7.1 | 5.8 | 19.0 | 22.4 |
| YlOrRd (ColorBrewer) | 12.5 | 5.3 | 8.3 | 22.7 | - |
| eurostat-map default blues | 10.3 | 10.6 | 9.7 | 9.5 | - |
| Blues (single hue) | 7.9 | 6.1 | 4.8 | 9.0 | - |
| **RdBu** (diverging, default) | **19.7** | **17.9** | **16.5** | 8.9 | 18.3 |
| PuOr (diverging) | 18.3 | 16.3 | 19.0 | 7.9 | 19.2 |

The class count matters as much as the scheme: viridis drops from 24.6 / 13.8 / 13.3 with 5 classes to 14.6 / 9.7 / 6.7 with 7 — the protan value falls below 8. Prefer 5 or 6 classes; go to 7 only when the user needs the detail. A 4-class RdBu measures 28.6 / 25.7 / 26.8.

**Palettes to use** (hex, low → high)

```js
// Sequential — default for rates, shares, densities
viridis5: ['#fde725','#5ec962','#21918c','#3b528b','#440154']
viridis6: ['#fde725','#7ad151','#22a884','#2a788e','#414487','#440154']
viridis7: ['#fde725','#90d743','#35b779','#21918c','#31688e','#443983','#440154']

// Diverging — values around a midpoint. Even class count, break on the midpoint.
RdBu4:  ['#ca0020','#f4a582','#92c5de','#0571b0']                      // red = below, blue = above
RdBu6:  ['#b2182b','#ef8a62','#fddbc7','#d1e5f0','#67a9cf','#2166ac']
PuOr6:  ['#b35806','#f1a340','#fee0b6','#d8daeb','#998ec3','#542788']  // when red/blue carries a political meaning
```

Swap the diverging ends when "high" is the bad side (e.g. unemployment change: blue = fell, red = rose). For a diverging map, use `classificationMethod('threshold')` with breaks symmetric around the midpoint, e.g. `.thresholds([-2, -1, 0, 1, 2])` with `RdBu6`, so that the light centre classes sit on either side of it.

If the user asks for other colours (a brand palette, a newspaper style), keep their hues but check that lightness still runs steadily from light to dark and that the no-data grey stands apart.

**Sources**

- Brewer, C. A. (1994). Color use guidelines for mapping and visualization. In A. M. MacEachren & D. R. F. Taylor (Eds.), *Visualization in Modern Cartography* (pp. 123-147). Elsevier.
- Brewer, C. A., MacEachren, A. M., Pickle, L. W., & Herrmann, D. (1997). Mapping mortality: Evaluating color schemes for choropleth maps. *Annals of the Association of American Geographers*, 87(3), 411-438.
- Harrower, M., & Brewer, C. A. (2003). ColorBrewer.org: An online tool for selecting colour schemes for maps. *The Cartographic Journal*, 40(1), 27-37. Palettes: [colorbrewer2.org](https://colorbrewer2.org)
- Light, A., & Bartlein, P. J. (2004). The end of the rainbow? Color schemes for improved data graphics. *Eos*, 85(40), 385-391.
- Smith, N., & van der Walt, S. (2015). *A better default colormap for Matplotlib* (viridis). SciPy 2015.
- Crameri, F., Shephard, G. E., & Heron, P. J. (2020). The misuse of colour in science communication. *Nature Communications*, 11, 5444.
- Machado, G. M., Oliveira, M. M., & Fernandes, L. A. F. (2009). A physiologically-based model for simulation of color vision deficiency. *IEEE Transactions on Visualization and Computer Graphics*, 15(6), 1291-1298.
- Sharma, G., Wu, W., & Dalal, E. N. (2005). The CIEDE2000 color-difference formula: Implementation notes, supplementary test data, and mathematical observations. *Color Research & Application*, 30(1), 21-30.

The full option list is in the [eurostat-map reference](https://eurostat.github.io/eurostat-map/docs/reference.html); the [examples page](https://eurostat.github.io/eurostat-map/examples/index.html) has a working page for every map type.

## Step 4 — Verify the map

If a browser automation tool is already available in your environment (for example `agent-browser`, or a Playwright/Chrome MCP), render the page before handing it over, the same quality loop as for charts. Do not install one for this.

```bash
agent-browser open "file://$PWD/map.html"
agent-browser wait 6000          # geometries arrive over the network
agent-browser screenshot "#map" "$PWD/map.png"   # the map element only
agent-browser errors             # must be empty
agent-browser console            # eurostat-map logs its own errors here, not as page errors
agent-browser close
```

Make the viewport taller than the map (`agent-browser set viewport 1000 1000`), otherwise the element screenshot is cut at the window edge. If no such tool is available, say that the map was not rendered and ask the user to open it and report what they see.

Read the screenshot and check:

- regions are coloured, not all grey (all grey = wrong `nutsLevel`, wrong `nutsYear`, `DATA` keys that are not `geo` codes, or `.insets()` called before data and colours);
- the number of coloured regions roughly matches `jq length data.json`; scattered grey regions where you have data point to a NUTS version mismatch;
- legend classes make sense (one huge outlier squashing everything into one class → use `threshold` breaks);
- the legend does not cover coloured regions, and all the text, library strings included, is in the user's language;
- title, subtitle and source are there.

Then open the HTML for the user (`wopen map.html` on WSL, `open`/`xdg-open` elsewhere), and say that it needs internet access to load the library and geometries.

## Pitfalls

- **Mixed years** from `--last-n 1`: always filter to one `TIME_PERIOD`.
- **Mixed NUTS levels**: filter by code length. If the user really wants a mix (e.g. NUTS 2 where available, country otherwise), use `.nutsLevel('mixed')`.
- **Unfixed dimensions**: two rows for the same `geo` means `sex`, `unit`, `age` or similar still has several codes; the last one wins silently in `json_group_object`.
- **Greece**: Eurostat uses `EL`, the same code as Nuts2json, so no mapping is needed — do not convert to ISO `GR`.
- **Values as strings**: `OBS_VALUE` must be a number in the JSON, otherwise classification breaks; cast it in DuckDB.
- **Large NUTS 3 maps**: ~1,500 regions are fine; keep the default `scale('20M')` simplification, `03M` is much heavier.
- **Exact zeros**: replace with `1e-9` (Step 1), otherwise the region looks like missing data or, on symbol maps, breaks the colouring of everything after it.
- **Reserved global names**: a top-level `const top = ...` clashes with the browser's `window.top`, and the code that uses it does nothing, with no page error. Use upper-case names for page variables (`DATA`, `TOP`, `GRAPH`).
