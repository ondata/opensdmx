# Annotations

Read [maps.md](maps.md) first. Annotations are callout notes with a connector that point at a region: "Andalucía — unemployment rate 15.2%". They work on any map type. eurostat-map draws them with [d3-annotation](https://d3-annotation.susielu.com/).

## Contents

- When to annotate
- Choosing the region
- Placing the note
- Code
- Pitfalls

## When to annotate

One or two notes that carry the message of the map: the region the user asked about, the extreme the title talks about, an outlier that needs explaining. More than three notes compete with the legend and with each other.

## Choosing the region

Choose the annotated region **with the user**, or check it on the screenshot before handing over. Do not pick it automatically ("the maximum") and ship it unseen:

- **It must be visible.** Picking the maximum of a NUTS 2 unemployment map lands on Melilla (ES64), an autonomous city on the North African coast that is 0.4 × 0.9 pixels on a European map: the note points at what looks like a random spot in Morocco. Prefer a region the reader can see; if the one that matters is tiny or overseas, annotate it in its inset (maps.md, insets) or say in the note where it is ("Melilla (ES), enclave on the North African coast").
- **Check ties.** In the same data Melilla and Mayotte share the top value (24.9%). "The highest rate" is wrong if it names only one; name all of them or change the wording.
- **Use the region name from the geometry** (`properties.na`) or from the `geo_label` column, in the user's language when available.

## Placing the note

Annotation coordinates are **pixels in the SVG**, not map coordinates. The region's position is only known once the map is drawn, so the note is added in `onBuild`, from the bounding box of the region's path.

- Put the note text **over the sea or over an empty area**, not over coloured regions: `dx` / `dy` are the offset in pixels from the region to the note.
- Give the note a **white background box**. d3-annotation already draws a rectangle behind each note (`rect.annotation-note-bg`), transparent by default: one CSS rule makes it visible, and `padding` gives the text some room. Black text over dark polygons (viridis top classes, RdBu ends) is unreadable without it.
- Do not use a text halo (`paint-order: stroke`): it looks fine on screen but breaks in the PNG export, where the text turns white on white.
- `wrap` is the line width in pixels: make it wide enough to keep the label on one or two lines. Translated labels are often longer than the English ones: "Tasso di disoccupazione: 15,2%" went to three lines and was cut at the bottom of the map; "Disoccupazione: 15,2%" fits. Prefer a short label and check the screenshot.
- Format the number in the label with the user's locale too (`value.toLocaleString('it-IT')` → "15,2").

## Code

Add the CSS rule to the `<style>` of the page:

```css
.annotation-note-bg { fill: #fff; fill-opacity: .9; }
```

Then, after the map definition and data, before `map.build()`:

```js
const TOP = ['ES61', DATA.ES61];   // region chosen with the user; do not name it `top` (window.top)
map.onBuild(() => {
  const path = [...document.querySelectorAll('#map path')]
    .find(p => p.__data__?.properties?.id === TOP[0]);
  if (!path) return;
  const svg = document.getElementById('map').getBoundingClientRect();
  const r = path.getBoundingClientRect();
  const x = r.x - svg.x + r.width / 2, y = r.y - svg.y + r.height / 2;
  map.annotations({ editMode: false, annotations: [{
    note: { title: path.__data__.properties.na,
            label: 'Unemployment: ' + TOP[1].value + '%', wrap: 260, padding: 6 },
    connector: { end: 'dot' }, color: '#333',
    x, y, dx: 150, dy: 25,
  }] });
  // White casing under connector and dot: dark line, light border, readable on any class colour.
  document.querySelectorAll('#map .annotation-connector path').forEach(p => {
    const casing = p.cloneNode(true);
    casing.setAttribute('class', 'connector-casing');
    casing.style.stroke = '#fff'; casing.style.strokeWidth = '4px'; casing.style.fill = 'none';
    p.parentNode.insertBefore(casing, p);
  });
});
map.build();
```

**The connector needs a casing.** A dark connector and dot on a dark polygon (Andalucía in the darkest viridis class) almost disappear; a light one disappears on light classes. The cartographic fix is a casing: the same line drawn underneath, white and thicker, so the dark line has a light border on any colour. The code above clones each connector path (line and dot) under itself with a 4 px white stroke. It is plain SVG, so it survives the PNG export (verified); a CSS `filter` or `paint-order` halo would not.

The centre of the bounding box is a good anchor for compact regions. For regions with a long or curved shape (Norway, Croatia) the centre can fall outside the region: check the screenshot and adjust `x` / `y` by hand.

`editMode: true` lets the reader drag the note with the mouse: useful when the user wants to fine-tune the placement before exporting the PNG.

## Pitfalls

- **Tiny or overseas region**: the dot lands on nothing visible (see Choosing the region).
- **Note outside the frame**: a large `dy` can push the text below the SVG, where it is cut. Keep the note inside the map area and check the screenshot.
- **`const top`**: clashes with `window.top`; the annotation code does nothing and no page error is raised. Use `TOP`.
