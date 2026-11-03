# Proportional symbol maps

Read [maps.md](maps.md) first: data preparation (one value per region, one year, one NUTS level, zeros replaced with `1e-9`), the HTML skeleton, export buttons, colours and verification all apply here. This file only adds what is specific to symbols.

## Contents

- When to use symbols
- One variable: circle size
- Two variables: size + colour
- Dorling layout
- Pitfalls

## When to use symbols

Use circles for **totals** (population, GDP in million euro, nights spent, number of enterprises). Colouring regions by a total mostly shows how big they are; a circle whose area grows with the value does not have that problem.

Add colour when the user wants a **second variable** on the same map, typically a total and a rate: population and population change, GDP and GDP per head, employment and unemployment rate. Size carries the total, colour the rate. Two separate maps are often clearer: propose the combined map when the user wants to see the two together.

## One variable: circle size

Same data preparation as in maps.md, Step 1, then:

```js
const map = eurostatmap.map('proportionalSymbol')
  .svgId('map').width(800).height(720).zoomButtons(false)
  .nutsLevel(0).nutsYear(2024)
  .title('Population, 2025')
  .footnote('Source: Eurostat, dataset demo_pjan')
  .showSourceLink(false)
  .psSettings({ fill: '#2a788e', fillOpacity: 0.85, stroke: '#fff', strokeWidth: 0.5 })
  .legend({ position: 'top right', sizeLegend: { title: 'Population' } });
map.statData().setData(DATA);
map.statData().unitText('inhabitants');
map.build();
```

**Label the circles at country level.** Without labels the reader cannot tell which circle belongs to which country. Use Eurostat's default country-code labels, filtered to the countries with data:

```js
.labels({ backgrounds: false, halos: true,
          labels: eurostatmap.getDefaultLabels().EUR_3035.cc.filter(d => DATA[d.text]) })
```

Do not use `psSettings({ codeLabels: true })` (codes inside the circles): on large circles it reads well, but on small ones (IS, LU, MT, the Baltic states) the code overflows the circle and turns white on white in the exported PNG (verified). At NUTS 2 and 3 there are too many circles for labels: annotate the few that matter instead ([maps-annotations.md](maps-annotations.md)).

Without `sizeLegend` the map has no legend and the reader cannot tell what a circle is worth. Readers judge circles by their area, so the area, not the radius, should grow with the value: if you set `psSettings({ sizeScale })`, use `'sqrt'`, not `'linear'`.

## Two variables: size + colour

Prepare two JSON objects keyed by `geo`, one per variable, with the same filter on year and NUTS level. Then bind each to an encoding channel by name:

```js
const POP = $POP;        // size: total population
const GROWTH = $GROWTH;  // colour: crude rate of population change, per 1000
const map = eurostatmap.map('proportionalSymbol')
  .svgId('map').width(800).height(720).zoomButtons(false)
  .nutsLevel(3).nutsYear(2024).scale('60M')
  .dorling(true)
  .title('Total population and population change')
  .subtitle('NUTS 3 regions, 2024')
  .footnote('Source: Eurostat, datasets demo_r_pjangrp3 and demo_r_gind3')
  .showSourceLink(false)
  .encoding('size',  { stat: 'symbolSize' })
  .encoding('color', { stat: 'symbolColor' })
  .psSettings({
    shape: 'circle', minSize: 2, maxSize: 21, fillOpacity: 1,
    colors: ['#b2182b','#ef8a62','#fddbc7','#d1e5f0','#67a9cf','#2166ac'],   // RdBu6
    classificationMethod: 'threshold', thresholds: [-10, -5, 0, 5, 10],
    stroke: 'white', strokeWidth: 0.1,
  })
  .legend({ x: 570, y: 0,
    sizeLegend:  { title: 'Total population', titlePadding: 20 },
    colorLegend: { title: 'Population change (‰)', marginTop: 50, labelType: 'threshold',
                   pointOfDivergence: 3, pointOfDivergenceLabel: 'Increase|Decrease' } });
map.statData('symbolSize').setData(POP);
map.statData('symbolSize').unitText('inhabitants');
map.statData('symbolColor').setData(GROWTH);
map.statData('symbolColor').unitText('‰');
map.build();
```

- The names `symbolSize` and `symbolColor` are free labels: what matters is that `encoding(..., { stat })` and `statData(name)` use the same one.
- `pointOfDivergence` is the index of the class break that sits on the midpoint (here the third threshold, 0), and draws the "Increase / Decrease" arrow in the legend.
- Colour rules are those of maps.md: a diverging scheme with a break on the midpoint for rates of change, viridis for a sequential second variable.
- `minSize` / `maxSize` are radii in pixels. Good starting values: NUTS 0 → 10 / 60, NUTS 1 → 3 / 20, NUTS 2 and 3 → 2 / 21 (from Eurostat's own example).
- Regions missing from the colour data get the no-data colour; regions missing from the size data get no circle at all.
- **Text in the user's language**: the colour legend has its own no-data item, translated with `noDataText` **inside `colorLegend`** (the map-level `.noDataText()` does not reach it), and its own `labelFormatter`; the size legend needs the "mln" formatter of maps.md. Verified: with only the map-level setting the colour legend still showed "No data".

## Dorling layout

`.dorling(true)` moves the circles apart so they do not overlap, keeping each one as close as possible to its region. It is what makes a NUTS 3 map readable in dense areas (Benelux, western Germany). It runs as an animation after the first render: wait a few seconds before taking a screenshot or exporting, otherwise the circles are caught halfway.

If the circles still overlap after several seconds, the layout did not start: check the console for `Error in proportional symbols styling` (see Pitfalls).

## Pitfalls

- **An exact 0 in the colour data breaks the map.** The region gets class `NaN`, the colour function throws (`b[c] is not a function` in the console), every circle drawn after it stays black, and the dorling layout never starts. Measured on a NUTS 3 map: 471 black circles out of 1,333, caused by four regions with change exactly 0. Replacing 0 with `1e-9` in data preparation fixes all of it (maps.md, Step 1).
- **Black circles** = missing fill, not a class. Count them before handing over: `[...document.querySelectorAll('#map g.em-centroid circle')].filter(c => !c.style.fill).length` must be 0.
- **Size and colour from different years or levels**: both JSON objects must use the same year and NUTS level, otherwise colour is missing for part of the circles.
