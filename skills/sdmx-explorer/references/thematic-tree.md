# Thematic Tree — Top-down Discovery

Some SDMX providers expose a hierarchical catalog (`categoryscheme` + `categorisation`)
that organises dataflows by topic. Browsing this tree top-down is often more efficient
than keyword search when the user's question targets a well-defined domain
(agriculture, prices, education, health…) — the catalog itself becomes a guide.

This document is a deep-dive on the `opensdmx tree` workflow. It complements
"Step 1a+ — Narrow the search thematically with `opensdmx tree`" in the main `SKILL.md`.

## When to use what

`tree`, `search`, and `search --semantic` are not interchangeable — each fits a
different starting condition.

| Starting point | Best command | Why |
|---|---|---|
| User names a clear domain ("agricultural prices", "consumer prices in Italy") | `tree` (top-down) | Browse the catalog hierarchy; faster than keyword scanning when many dataflows share a root theme |
| User names a specific dataflow id (`UNE_RT_M`, `NAMA_10_GDP`) | `info` directly | No discovery needed |
| User uses standard technical terminology ("unemployment rate", "HICP") | `search "<keyword>"` | Keyword match on title is fast and precise |
| User uses informal phrasing or zero word overlap ("people without a job") | `search --semantic "<query>"` | Embedding similarity bridges vocabulary gaps |
| Generic or ambiguous keyword ("impresa", "energia") returning hundreds of hits | `tree` first, then `search --category` | Restrict the search universe before keyword filtering |

When the user's question is a domain (not a technical term), prefer `tree` first.

## Provider support

Not every provider exposes the thematic tree. Always check first:

```bash
opensdmx providers
```

The `categories` column tells you which providers support `tree`:

- Supported: `eurostat`, `istat`, `ecb`, `oecd`, `insee`, `abs`, `bis`
- Not supported: `comext`, `bundesbank`, `worldbank`, `imf` — skip `tree` and go
  straight to `search`.

## Top-down walkthrough — ISTAT Prezzi

A real example: the user asks "ho bisogno dei prezzi al consumo armonizzati per
l'Italia". Domain ("prezzi al consumo armonizzati") is broad — perfect for `tree`.

### Step 1 — list thematic schemes

```bash
opensdmx tree --provider istat
```

```
┏━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━┓
┃ scheme_id  ┃ scheme_name                              ┃ n_df ┃
┡━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━┩
│ Z0400PRI   │ Prezzi                                   │  141 │
│ Z0500LAB   │ Lavoro e retribuzioni                    │  527 │
│ ...        │ ...                                      │  ... │
└────────────┴──────────────────────────────────────────┴──────┘
```

`Z0400PRI` (141 dataflows) is the relevant scheme. Note the `scheme_id` — that's
what goes into `--scheme`.

### Step 2 — browse the scheme

```bash
opensdmx tree --scheme Z0400PRI --provider istat
```

```
Prezzi (Z0400PRI)
├── Costi di costruzione [DCSC_FABBRESID_1] (3 df)
├── Indice dei prezzi all'importazione - dati mensili [DCSC_PREIMPIND] (2 df)
├── Prezzi al consumo armonizzati per i paesi dell'Unione europea (Ipca) [PRI_HARCONEU] (3 df)
│   ├── Basi precedenti [PRI_HARCONEU_BRI] (2 df)
│   ├── Ipca - medie annue dal 1996 (base 2025) - Ecoicop 2 [DCSP_IPCA2B2025] (1 df)
│   ├── Ipca - mensili dal 2001 (base 2015) [DCSP_IPCA1B2015] (3 df)
│   └── ...
├── Prezzi al consumo per le famiglie di operai e impiegati (Foi) [PRI_CONBWCOL] (5 df)
└── ...
```

The `cat_id` is shown in `[square brackets]`. `PRI_HARCONEU` is the IPCA branch.

### Step 3 — zoom into the relevant subtree

`tree --category` filters the tree to a single branch:

```bash
opensdmx tree --scheme Z0400PRI --category PRI_HARCONEU --provider istat
```

```
Prezzi al consumo armonizzati per i paesi dell'Unione europea (Ipca) (PRI_HARCONEU)
├── Basi precedenti [PRI_HARCONEU_BRI] (2 df)
├── Ipca - medie annue dal 1996 (base 2025) - Ecoicop 2 [DCSP_IPCA2B2025] (1 df)
├── Ipca - medie annue dal 2001 (base 2015) [DCSP_IPCA2B2015] (3 df)
├── Ipca - mensili dal 1996 (base 2025) - Ecoicop 2 [DCSP_IPCA1B2025]
├── Ipca - mensili dal 2001 (base 2015) [DCSP_IPCA1B2015] (3 df)
├── Ipca - pesi dal 1996 - Ecoicop 2 [DCSP_IPCA3EC2] (2 df)
└── Ipca - pesi dal 2001 [DCSP_IPCA3] (3 df)
```

Now the structure is clear: monthly vs annual, current base vs old base, weights
vs values. Pick the right leaf based on the user's intent.

### Step 4 — list the actual dataflows in the branch

`tree --category` shows the **category hierarchy with dataflow counts** — but
not the dataflow IDs themselves. To list the actual dataflows in a branch, use
`search` with an empty keyword and `--category`:

```bash
opensdmx search "" --category PRI_HARCONEU --provider istat
```

This is the **complementary pair** to remember:

| Command | Shows |
|---|---|
| `opensdmx tree --scheme S --category C` | Category hierarchy under C, with dataflow counts |
| `opensdmx search "" --category C` | Actual dataflow IDs and titles in C (and descendants) |

Use both: `tree` to navigate, `search` to enumerate.

### Step 5 — proceed with the standard flow

Once a dataflow id is identified, continue with Phase 2 of the main skill
(`opensdmx info`, `constraints`, etc.).

## Extracting cat_ids when the ASCII tree is too long

The ASCII tree is human-friendly but truncates long names and is hard to grep.
For programmatic discovery (or when the tree has hundreds of categories), use CSV
or JSON output — these include the `cat_id` and `cat_path` columns explicitly:

```bash
opensdmx --output csv tree --scheme t_economy | grep -i hicp
```

```
t_economy,Economy and finance,t_prc_hicp,t_prc.t_prc_hicp,Harmonised index of consumer prices (HICP),t_prc,2,24
```

Output columns: `scheme_id`, `scheme_name`, `cat_id`, `cat_path`, `cat_name`,
`parent_path`, `depth`, `n_df`. Use `cat_id` for `--category` filters.

JSON output works the same way and is easier to parse from scripts:

```bash
opensdmx --output json tree --scheme t_economy | jq '.[] | select(.cat_name | test("HICP"; "i"))'
```

## Auto-correction hint when --scheme receives a category ID

A common mistake — the user (or AI) sees `[PRI_HARCONEU]` in the tree output and
tries to drill into it as if it were a scheme. The CLI detects this and suggests
the correct command:

```bash
opensdmx tree --scheme PRI_HARCONEU --provider istat
# → 'PRI_HARCONEU' is a category, not a scheme.
# → Use: opensdmx tree --scheme Z0400PRI --category PRI_HARCONEU
```

When you see this hint, just run the suggested command — no need to look up the
parent scheme manually.

## Eurostat walkthrough — Prices

Same workflow on a different provider. User asks "I want EU consumer price data".

```bash
# Step 1 — list schemes (Eurostat is the default, no --provider needed)
opensdmx tree

# Step 2 — economy scheme (t_economy is more focused than the full popul tree)
opensdmx tree --scheme t_economy

# Step 3 — zoom into the Prices subtree
opensdmx tree --scheme t_economy --category t_prc
```

```
Prices (t_prc)
├── Harmonised index of consumer prices (HICP)  (24 df)
├── Housing price statistics  (1 df)
└── Purchasing power parities  (3 df)
```

Note: Eurostat's ASCII tree does not show `[cat_id]` for all nodes (older catalog
format). Use `--output csv` to get them when needed:

```bash
opensdmx --output csv tree --scheme t_economy | grep -i "hicp"
# → t_prc_hicp is the cat_id for the HICP branch
```

```bash
# Step 4 — list dataflows under HICP
opensdmx search "" --category t_prc_hicp
```

## When to skip the tree

Provider does not support categories (`comext`, `bundesbank`, `worldbank`, `imf`):
go straight to `search`. World Bank is a special case — it has a single dataflow
`WDI` containing all 1400+ indicators; see SKILL.md "World Bank flow" for details.

The user already provides a precise dataflow id or unambiguous acronym
(`NAMA_10_GDP`, `LFSA_ERGAN`): skip `tree`, run `info` directly.

The keyword is technical and specific (`HICP all-items annual change`): a single
`search` will return precise hits — no need to navigate the tree.

## Performance note

The first `tree` call per provider triggers a one-time fetch of the full
categorisation response (Eurostat: ~24 MB, ~1 minute; ISTAT: faster). The result
is cached for 7 days under the provider's cache directory, so subsequent `tree`
calls are instant. Plan accordingly: if you know you'll need the tree, run a
warm-up call early in the session.
