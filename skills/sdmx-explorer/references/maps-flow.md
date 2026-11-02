# Flow maps

Read [maps.md](maps.md) first: the HTML skeleton, export buttons, verification and pitfalls apply here. This file covers what is specific to flows.

## Contents

- When to use a flow map
- Step 1 — Get origin-destination data
- Step 2 — Build the graph
- Step 3 — Write the HTML
- Pitfalls

## When to use a flow map

A flow map draws one band per pair of places, with a width proportional to the value: exports from one country to its partners, migrants by country of origin, passengers between countries. It needs **two territorial dimensions** (origin and destination), not one value per region.

Keep it readable: **one origin and its top 8-12 destinations** (or one destination and its top origins). All pairs between all countries is unreadable; propose the top ones and say how much of the total they cover.

## Step 1 — Get origin-destination data

The typical source is Comext (`--provider comext`), the Eurostat database for international trade in goods. `DS-045409` (EU trade since 1988 by CN8) has `reporter` and `partner` dimensions:

```bash
opensdmx get DS-045409 -p comext --freq A --reporter IT --product TOTAL --flow 2 \
  --indicators VALUE_IN_EUROS --start-period 2024 --end-period 2024 --labels --out it_exp.csv
```

`--flow 2` is exports, `1` imports. The answer has one row per partner (241 for Italy in 2024), aggregates included: `WORLD`, `EXT_EU27_2020`, `INT_EU27_2020`, `EXT_EA`... Keep only partners that are countries on the map. Partners outside Europe (US, CN) have no geometry on a Europe map and are dropped by the list below.

```bash
EUROPE="'AT','BE','BG','CY','CZ','DE','DK','EE','ES','FI','FR','GR','HR','HU','IE','IT','LT','LU','LV','MT','NL','PL','PT','RO','SE','SI','SK','CH','NO','IS','LI','GB','AL','BA','ME','MK','RS','TR','MD','UA'"
duckdb -json -c "
select partner, OBS_VALUE::double v
from read_csv('it_exp.csv', all_varchar=true)
where partner in ($EUROPE)
order by v desc limit 10" > top.json
```

## Step 2 — Build the graph

The library wants `{ nodes: [{id}], links: [{source, target, value}] }`, with node IDs that are **NUTS 0 codes**. Comext uses ISO codes, which differ for two countries: `GR` → `EL` and `GB` → `UK`. Without the conversion Greece and the United Kingdom stay uncoloured and get no flow.

```bash
GRAPH=$(jq -c '
  def nuts: if . == "GR" then "EL" elif . == "GB" then "UK" else . end;
  { nodes: ([{id: "IT"}] + [.[] | {id: (.partner | nuts)}]),
    links: [.[] | {source: "IT", target: (.partner | nuts), value: .v}] }' top.json)
```

For imports, swap the roles: the partners are the sources and the reporter is the target.

## Step 3 — Write the HTML

Same skeleton as maps.md (fixed size, export buttons), with this map definition:

```js
const GRAPH = $GRAPH;
const fmt = new Intl.NumberFormat('it-IT', { notation: 'compact', maximumFractionDigits: 1 });
const CODE_BY_VALUE = new Map(GRAPH.links.map(l => [l.value, l.target]));   // flow label = country code, see below
const map = eurostatmap.map('flow')
  .svgId('map').width(800).height(720).zoomButtons(false)
  .nutsLevel(0).scale('60M')
  .title('Italian exports of goods')
  .subtitle('Top 10 European destinations, 2024, euro')
  .footnote('Bn €: ' + GRAPH.links.slice().sort((a, b) => b.value - a.value)
      .map(l => l.target + ' ' + (l.value / 1e9).toFixed(1)).join(' · ')
      + '. Source: Eurostat Comext, dataset DS-045409')   // amounts here, codes on the map
  .footnoteWrap(false)
  .showSourceLink(false)
  .flowGraph(GRAPH)
  .flowSettings({ arrows: false, opacity: 1, color: '#2a788e',
                  regionColors: ['#bbd7ee', '#c7e3c6'], regionLabels: ['Exporter', 'Importer'] })
  .legend({ x: 10, y: 120, boxOpacity: 0,
    flowWidthLegend: { title: 'Exports (€)', titlePadding: 25,
                       values: [20e9, 70e9], labels: [20e9, 70e9].map(v => fmt.format(v)) },
    regionColorLegend: { title: ' ', labels: ['Exporter', 'Importer'] } })
  .labels({ values: true, backgrounds: true, shadows: false, valuesFormatter: v => CODE_BY_VALUE.get(v) || fmt.format(v) })
  .insets(false);
map.build();
```

- **Legend labels**: set `values` and `labels` explicitly with the same formatter as the flow labels. Left automatic, the legend writes `70G` (SI prefix) while the flows write `70.5B`; `labelFormatter` in `flowWidthLegend` is ignored in 4.12.1.
- Pick legend `values` that are round and inside the data range (here 20 and 70 billion for flows between 12.5 and 70.5).
- **Exporter / Importer**: the legend reads its labels from `regionColorLegend.labels`, not from `flowSettings.regionLabels` (verified: with only `regionLabels` translated the legend stayed in English). Translate them there ("Esportatore", "Importatore").
- **Say which country each flow goes to.** With value labels only ("70,5 Mld") the reader cannot tell the destinations apart. Measured on the 10-destination export map (bounding boxes of the labels):
  - full names + value ("Germania 70,5 Mld"): 2 collisions (Belgio over Germania, Svizzera over Francia) — flows to neighbouring countries end close to each other and all labels grow in the same direction;
  - two-letter code + value ("DE 70,5 Mld"): still the same 2 collisions;
  - two-letter code only ("DE"): no collisions.

  So: label each flow with the **two-letter code only**, and put the amounts in the footnote, ordered, one line: `Mld €: DE 70,5 · FR 61,7 · ... · AT 12,5. Fonte: ...`. The band width and the width legend carry the size; the footnote carries the exact figure. The library passes only the node value to `valuesFormatter`, so the code is looked up from the value (flow values are distinct):

  ```js
  const CODE_BY_VALUE = new Map(GRAPH.links.map(l => [l.value, l.target]));
  // .labels({ values: true, backgrounds: true, shadows: false, valuesFormatter: v => CODE_BY_VALUE.get(v) || fmt.format(v) })
  // .footnote('Mld €: ' + GRAPH.links.slice().sort((a, b) => b.value - a.value)
  //     .map(l => l.target + ' ' + (l.value / 1e9).toLocaleString('it-IT', { maximumFractionDigits: 1 })).join(' · ')
  //     + '. Fonte: Eurostat Comext, dataset DS-045409')
  // .footnoteWrap(false)   // the library wraps on any space and splits "AT" from "12,5"; keep it on one line
  ```

  Use Eurostat codes (`EL`, `UK`) on the map, as everywhere else in Eurostat products. With 5 destinations or fewer, names + value usually fit: check the screenshot. Country names in the user's language, if needed elsewhere, come from `new Intl.DisplayNames(['it'], { type: 'region' }).of(iso)` (ISO code: `GR`, `GB`).
- **Value labels need a background**: `backgrounds: true` puts a white box behind each label. With the default shadow only, labels that fall on a band ("30,2 Mld" over the France flow) are black text on dark teal.
- **Number format**: `new Intl.NumberFormat('it-IT', { notation: 'compact' })` gives "70,5 Mld", which is Italian usage for billions; use it for both the flow labels and the width legend.
- `scale('60M')` is enough at country level and keeps the page light.

## Pitfalls

- **ISO vs NUTS codes**: `GR`/`GB` from Comext must become `EL`/`UK` (Step 2). Eurostat datasets with a `geo` dimension already use `EL`/`UK`.
- **Aggregates as partners**: `WORLD`, `EXT_EU27_2020` and the like would become huge flows to nowhere. Filter on a list of countries, never on "everything except a few codes".
- **Overlapping value labels**: two destinations with similar values and close positions (Belgium and the Netherlands) can put their labels on top of each other. Check the screenshot; if they collide, drop `labels({ values: true })` and rely on the tooltip, or keep fewer destinations.
