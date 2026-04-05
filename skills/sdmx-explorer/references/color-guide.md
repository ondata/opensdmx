# Color Guide for Categorical Data

## The core problem

Default colors in plotnine/matplotlib are not designed for statistical communication.
They use arbitrary hues that can be hard to distinguish, especially for colorblind
readers (roughly 8% of men). For categorical data, always use a purpose-built palette.

## Recommended palettes

### Okabe-Ito (best default for categorical data)

Designed for colorblind accessibility. Works for up to 8 categories.

| Name        | Hex       | Use for                        |
|-------------|-----------|--------------------------------|
| Orange      | `#E69F00` | first category                 |
| Sky blue    | `#56B4E9` | second category                |
| Green       | `#009E73` | third category                 |
| Yellow      | `#F0E442` | fourth (avoid on white bg)     |
| Blue        | `#0072B2` | fifth                          |
| Vermilion   | `#D55E00` | sixth                          |
| Pink        | `#CC79A7` | seventh                        |
| Black       | `#000000` | eighth / reference line        |

```python
# plotnine snippet
OKABE_ITO = ["#E69F00","#56B4E9","#009E73","#F0E442","#0072B2","#D55E00","#CC79A7","#000000"]
+ scale_fill_manual(values=OKABE_ITO)
+ scale_color_manual(values=OKABE_ITO)
```

### ColorBrewer Qualitative — Set2 (soft, 8 colors)

Good for light backgrounds, reports, and print.

```python
SET2 = ["#66C2A5","#FC8D62","#8DA0CB","#E78AC3","#A6D854","#FFD92F","#E5C494","#B3B3B3"]
+ scale_fill_manual(values=SET2)
```

### Two-category contrast (e.g. fresh vs. industrial, male vs. female)

Use high-contrast complementary pairs:

| Pair | Colors | When |
|------|--------|------|
| Warm/Cool | `#E07B39` / `#2E86AB` | two neutral categories |
| Dark red/Teal | `#C0392B` / `#16A085` | diverging emphasis |
| Blue/Orange | `#0072B2` / `#E69F00` | Okabe-Ito first two |

## Rules for choosing colors

1. **≤ 8 categories**: use Okabe-Ito. More than 8 → split into multiple charts.
2. **Ordered data** (low → high): use a sequential palette, not qualitative.
3. **Diverging data** (below/above zero or baseline): use diverging palette (e.g. RdBu).
4. **Avoid**: rainbow/jet palettes, pure red+green combinations (colorblind conflict).
5. **Two groups**: pick two colors with high luminance contrast (not just hue difference).
6. **Background**: light colors work on white; dark backgrounds need lighter palettes.

## Applying colors via `opensdmx plot` CLI

`opensdmx plot` does not expose a `--palette` flag. Colors are controlled only via
Python scripts using plotnine directly.

When using the CLI and colors matter:
- If only 2 categories: the default teal/salmon pair is often acceptable.
- If ≥ 3 categories and colors are important: generate the chart in Python with
  `scale_fill_manual` or `scale_color_manual` using the palettes above.

## plotnine snippets

### Full categorical chart with Okabe-Ito

```python
from plotnine import ggplot, aes, geom_col, scale_fill_manual, labs, theme_minimal

OKABE_ITO = ["#E69F00","#56B4E9","#009E73","#0072B2","#D55E00","#CC79A7"]

(
    ggplot(df, aes(x="anno", y="valore", fill="categoria"))
    + geom_col()
    + scale_fill_manual(values=OKABE_ITO)
    + labs(title="...", x=None, y="...", fill="Categoria")
    + theme_minimal()
)
```

### Rotate x-axis labels (when they overlap)

```python
from plotnine import theme, element_text

+ theme(axis_text_x=element_text(angle=90, hjust=1))   # vertical
+ theme(axis_text_x=element_text(angle=45, hjust=1))   # diagonal (less extreme)
```

Prefer `--geom barh` (horizontal bars) over rotating labels when the categories
are long strings — it's more readable and avoids the rotation entirely.
