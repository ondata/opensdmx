[![PyPI version](https://img.shields.io/pypi/v/opensdmx)](https://pypi.org/project/opensdmx/)
[![GitHub](https://img.shields.io/badge/github-ondata%2Fopensdmx-blue?logo=github)](https://github.com/ondata/opensdmx)
[![deepwiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/ondata/opensdmx)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Newsletter](https://img.shields.io/badge/newsletter-ondata-FF6719?logo=substack)](https://ondata.substack.com/)

# opensdmx

> **Note:** this is an experimental tool — help us test it by [opening issues](https://github.com/ondata/opensdmx/issues) or sharing feedback.

Simple Python CLI and library for any SDMX 2.1 REST API. Default provider: **Eurostat**. Built-in support for ISTAT, OECD, ECB, World Bank, and more.

**The right way to get official statistics with AI.** Large language models are good at understanding questions, but they fabricate numerical data — research shows GenAI returns inaccurate statistics up to two-thirds of the time (IMF, *StatGPT: AI for Official Statistics*, 2026). The correct pattern is to use AI to *generate structured API queries*, not to generate the numbers. opensdmx is the execution layer for that pattern: the AI decides what to fetch, opensdmx fetches the exact published figure.

> **Best used with AI.** opensdmx works well on its own, but **it shines when driven by an AI agent**: the CLI is designed to be composed, queried, and orchestrated step by step. For a guided, interactive experience — dataset discovery, schema exploration, filter selection, and data retrieval — pair it with the [`sdmx-explorer`](https://github.com/ondata/opensdmx/blob/main/skills/sdmx-explorer/SKILL.md) Agent Skill included in this repo. See the [**installation guide**](https://github.com/ondata/opensdmx/blob/main/docs/skill/README.md) for step-by-step instructions.

## Installation

**As a CLI tool** (recommended — available system-wide):

```bash
uv tool install opensdmx
```

> **Install uv** — Linux/macOS: `curl -LsSf https://astral.sh/uv/install.sh | sh` · Windows: `winget install astral-sh.uv`

**As a library** (for use in Python projects):

```bash
uv add opensdmx
# or
pip install opensdmx
```

**Update to the latest version:**

```bash
uv tool upgrade opensdmx            # if installed as CLI with `uv tool`
uv lock --upgrade-package opensdmx  # if used as a library dependency
pip install --upgrade opensdmx      # if installed with pip
```

## CLI quick start

```bash
opensdmx search "unemployment"
opensdmx info UNE_RT_M
opensdmx constraints UNE_RT_M geo
opensdmx get UNE_RT_M --freq M --geo IT --sex T --out data.csv

# Save a query for later reuse
opensdmx get TIPSUN20 --sex T --age Y15-74 --start-period 2020 --query-file unemployment.yaml

# Re-run from the saved query
opensdmx run unemployment.yaml --out results.csv
```

## Python quick start

```python
import opensdmx

# Default provider: Eurostat
datasets = opensdmx.all_available()
print(datasets.head())

# Search by keyword
results = opensdmx.search_dataset("unemployment")

# One-liner retrieval (Eurostat default)
data = opensdmx.fetch("UNE_RT_M", freq="M", geo="IT", sex="T", age="TOTAL")

# Switch provider
opensdmx.set_provider("istat")
opensdmx.set_provider("oecd")
opensdmx.set_provider("ecb")
```

## Providers

```python
import opensdmx

# Built-in presets
opensdmx.set_provider("eurostat")   # default
opensdmx.set_provider("istat")
opensdmx.set_provider("oecd")
opensdmx.set_provider("ecb")
opensdmx.set_provider("worldbank")

# Custom provider (agency_id optional)
opensdmx.set_provider("https://mysdmx.org/rest")
opensdmx.set_provider("https://mysdmx.org/rest", agency_id="XYZ", rate_limit=1.0)

# Check active provider
opensdmx.get_provider()  # returns dict with base_url, agency_id, rate_limit, language
```

> **Note on output columns:** Eurostat uses the compact `SDMX-CSV` format (dimensions + `TIME_PERIOD` + `OBS_VALUE`). Other providers (ECB, OECD, etc.) return the generic `text/csv` format, which includes additional series metadata columns (`TITLE`, `UNIT`, `DECIMALS`, etc.). This is expected behavior — filter columns with standard tools if needed.

### Provider via CLI and environment variables

Use `--provider` (or `-p`) on any command, or set `OPENSDMX_PROVIDER` once for the whole session:

```bash
# Per-command
opensdmx search "inflation" --provider ecb
opensdmx get EXR --provider https://data-api.ecb.europa.eu/service --FREQ D

# Session-wide via env var
export OPENSDMX_PROVIDER=ecb
opensdmx search "inflation"
opensdmx get EXR --FREQ D --CURRENCY USD

# Custom URL with agency
export OPENSDMX_PROVIDER=https://mysdmx.org/rest
export OPENSDMX_AGENCY=XYZ
opensdmx get MYDATASET
```

## Python API

| Function | Description |
|---|---|
| `set_provider(name_or_url, ...)` | Set active provider (`'eurostat'`, `'istat'`, or custom URL) |
| `get_provider()` | Return active provider config dict |
| `all_available()` | List all datasets → Polars DataFrame |
| `search_dataset(keyword)` | Search by keyword in description |
| `load_dataset(id)` | Create a dataset object (dict) |
| `print_dataset(ds)` | Print dataset summary |
| `dimensions_info(ds)` | Dimension metadata → Polars DataFrame |
| `get_dimension_values(ds, dim)` | Codelist values for a dimension |
| `get_available_values(ds)` | Values actually present in the data (via `availableconstraint`) |
| `set_filters(ds, **kwargs)` | Set dimension filters |
| `reset_filters(ds)` | Reset all filters to `"."` (all) |
| `get_data(ds, ...)` | Retrieve data → Polars DataFrame |
| `fetch(id, ..., **filters)` | One-liner: load dataset + set filters + get data |
| `run_query(query_file)` | Run a query from a YAML file saved with `--query-file` → Polars DataFrame |
| `semantic_search(query, n)` | Semantic search via Ollama embeddings → Polars DataFrame (requires `build_embeddings` first) |
| `build_embeddings(progress)` | Build and cache Ollama embeddings for all datasets (requires Ollama + `nomic-embed-text-v2-moe`) |
| `set_timeout(seconds)` | Get/set API timeout (default: 300 s) |
| `parse_time_period(series)` | Convert SDMX time strings to dates |

### `get_data` and `fetch` parameters

| Parameter | Type | Description |
|---|---|---|
| `start_period` | `str` | Start date: `"2020"`, `"2020-Q1"`, `"2020-01"` |
| `end_period` | `str` | End date (same formats) |
| `last_n_observations` | `int` | Return only last N observations per series |
| `first_n_observations` | `int` | Return only first N observations per series |

## Example: EU Unemployment Rate

```python
import opensdmx
from plotnine import ggplot, aes, geom_line, geom_point, labs, theme_minimal, scale_x_date

# Eurostat monthly unemployment by sex and age
ds = opensdmx.load_dataset("UNE_RT_M")
ds = opensdmx.set_filters(ds, freq="M", geo="IT", sex="T", age="TOTAL", s_adj="SA", unit="PC_ACT")
data = opensdmx.get_data(ds, start_period="2015", last_n_observations=60)

import polars as pl
data = data.with_columns(pl.col("OBS_VALUE").cast(pl.Float64))

plot = (
    ggplot(data.to_pandas(), aes(x="TIME_PERIOD", y="OBS_VALUE"))
    + geom_line(color="#1f77b4", size=1)
    + geom_point(color="#1f77b4", size=0.8)
    + labs(title="Italy Unemployment Rate (Monthly)", x="Year", y="Rate (%)")
    + scale_x_date(date_breaks="2 years", date_labels="%Y")
    + theme_minimal()
)
plot.save("unemployment.png", dpi=150, width=10, height=5)
```

## CLI

### Commands

All commands accept `--provider` (`-p`) to select the provider.

| Command | Description |
|---|---|
| `opensdmx search <keyword> [--n N] [-p provider]` | Keyword search in dataset descriptions (default: 20 results) |
| `opensdmx search --semantic <query> [--n N]` | Semantic search (requires `opensdmx embed`) |
| `opensdmx embed [-p provider]` | Build semantic embeddings cache via Ollama |
| `opensdmx info <id> [-p provider]` | Show dataset metadata and dimensions |
| `opensdmx values <id> <dim> [--grep pattern] [-p provider]` | Show codelist values for a dimension (case-insensitive); optionally filter by regex |
| `opensdmx constraints <id> [dim] [--grep pattern] [-p provider]` | Show values actually present in the dataflow (via `availableconstraint`); optionally filter by regex |
| `opensdmx tree [--scheme ID] [--category CAT] [--depth N] [-p provider]` | Browse the thematic tree (SDMX `categoryscheme` + `categorisation`); use `--category` to zoom into a subtree; ASCII tree in table mode, flat rows in JSON/CSV |
| `opensdmx siblings <id> [-p provider]` | Show dataflow siblings in each category — discover related variants that text search misses |
| `opensdmx search <keyword> --category <CAT> [-p provider]` | Restrict search to a category (leaf id or dotted path); cuts false positives vs pure token match |
| `opensdmx get <id> [--DIM VALUE] [--start-period P] [--end-period P] [--last-n N] [--first-n N] [--out file] [--query-file file.yaml] [-p provider]` | Download data; optionally save the query as YAML |
| `opensdmx run <query.yaml> [--out file] [-p provider]` | Re-run a query saved with `--query-file` |
| `opensdmx plot <id\|file.csv> [--DIM VALUE] [--geom line\|bar\|barh\|point\|scatter] [--out file] [-p provider]` | Plot data as chart |
| `opensdmx blacklist [-p provider]` | List and remove datasets from the unavailability blacklist |

### Examples

```bash
# Eurostat (default)
opensdmx search "unemployment"
opensdmx search "unemployment" --n 5
opensdmx info UNE_RT_M
opensdmx values UNE_RT_M FREQ          # case-insensitive: freq works too
opensdmx constraints UNE_RT_M
opensdmx constraints UNE_RT_M geo
opensdmx get UNE_RT_M --freq M --geo IT --out data.csv
opensdmx get UNE_RT_M --freq M --geo IT --out data.parquet
opensdmx plot UNE_RT_M --freq M --geo IT --geom line
opensdmx plot data.csv --geom scatter --x TIME_PERIOD --y OBS_VALUE

# Other providers
opensdmx search "disoccupazione" --provider istat
opensdmx get 151_929 --provider istat --FREQ A --REF_AREA IT --out data.csv
opensdmx search "GDP" --provider oecd
opensdmx search "inflation" --provider ecb

# Thematic tree (categoryscheme + categorisation)
opensdmx tree --provider istat                                            # list thematic schemes
opensdmx tree --scheme Z1000AGR --provider istat                          # browse ISTAT Agricoltura
opensdmx tree --scheme Z0400PRI --category PRI_HARCONEU --provider istat  # zoom into IPCA subtree
opensdmx tree --scheme t_economy --category t_prc                         # zoom into Prices subtree
opensdmx search "prezzi" --category DCSP_PREZZIAGR --provider istat
opensdmx siblings NAMA_10_GDP                        # 27 Eurostat GDP-related dataflows
opensdmx siblings 104_466_DF_DCSP_FERTILIZZANTI_2 --provider istat  # all 7 fertilizer variants
```

Not every provider exposes the thematic tree. Run `opensdmx providers` and check
the `categories` column (✓/✗). Currently supported: `eurostat`, `istat`, `ecb`,
`oecd`, `insee`, `abs`, `bis`.

### Query files

Save any `get` command as a YAML file with `--query-file`. The file captures the full query — provider, dataset, filters with human-readable descriptions, and time range — so it can be re-run, shared, or version-controlled.

```bash
# Save query
opensdmx get TIPSUN20 \
  --sex T --age Y15-74 --unit PC_ACT \
  --geo "AT+BE+DE+ES+FR+IT" \
  --start-period 2020 --end-period 2024 \
  --query-file unemployment_eu.yaml
```

The generated YAML:

```yaml
provider: eurostat
provider_url: https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1
agency_id: ESTAT
dataset: TIPSUN20
description: Unemployment rate - annual data
filters:
  sex:
    value: T
    description: Total
  age:
    value: Y15-74
    description: From 15 to 74 years
  unit:
    value: PC_ACT
    description: Percentage of population in the labour force
  geo:
    value: AT+BE+DE+ES+FR+IT
    description: ''
start_period: '2020'
end_period: '2024'
last_n: null
first_n: null
```

Re-run with `run` — output goes to stdout by default, or to a file with `--out`:

```bash
opensdmx run unemployment_eu.yaml
opensdmx run unemployment_eu.yaml --out results.csv
opensdmx run unemployment_eu.yaml --out results.parquet
```

Provider resolution order: `--provider` CLI flag → alias in YAML → `provider_url` + `agency_id` in YAML → environment variable. This means query files work with any provider, including custom URLs.

### Thematic tree

SDMX providers organise their datasets into a hierarchical **category tree** (schemes → categories → subcategories → datasets). `opensdmx tree` lets you browse this tree instead of guessing keywords.

**Step 1 — list available schemes**

```bash
opensdmx tree
```

```
┏━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━┓
┃ scheme_id  ┃ scheme_name                          ┃ n_df ┃
┡━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━┩
│ economy    │ Economy and finance                  │  418 │
│ popul      │ Population and social conditions     │ 3747 │
│ t_economy  │ Economy and finance                  │  130 │
│ …          │ …                                    │  …   │
└────────────┴──────────────────────────────────────┴──────┘
```

**Step 2 — browse a scheme**

```bash
opensdmx tree --scheme t_economy
```

```
Economy and finance (t_economy)
├── Exchange rates  (3 df)
├── Government statistics
│   └── Government finance statistics (EDP and ESA 2010)
│       ├── Annual government finance statistics  (2 df)
│       ├── Government deficit and debt  (3 df)
│       └── Quarterly government finance statistics  (2 df)
├── National accounts (including GDP)
│   ├── Annual national accounts
│   │   ├── Main GDP aggregates  (10 df)
│   │   └── …
│   └── …
└── Prices
    ├── Harmonised index of consumer prices (HICP)  (24 df)
    └── …
```

The ASCII tree does not show category IDs. To retrieve them (needed for `--category` filtering), use CSV output:

```bash
opensdmx --output csv tree --scheme t_economy | grep -i hicp
# t_economy,Economy and finance,t_prc_hicp,…,Harmonised index of consumer prices (HICP),…
```

**Step 3 — restrict search to a category**

Without a category filter, `search "annual"` returns 502 datasets from across all themes. With `--category`, it narrows to the exact subcategory:

```bash
opensdmx search "annual"                          # 502 results across all themes
opensdmx search "annual" --category t_prc_hicp    # 1 result: HICP - all items - annual average indices
```

**Step 4 — zoom into a subtree with `--category`**

To navigate deeper without scrolling through the entire scheme, pass a category ID to `--category`:

```bash
opensdmx tree --scheme t_economy --category t_prc
```

```
Prices (t_prc)
├── Harmonised index of consumer prices (HICP)  (24 df)
├── Housing price statistics  (1 df)
└── Purchasing power parities  (3 df)
```

To list all dataflows inside a category branch, combine `tree --category` (for the hierarchy) with `search "" --category` (for the actual datasets):

```bash
opensdmx tree --scheme t_economy --category t_prc       # see the subcategory structure
opensdmx search "" --category t_prc                     # list all dataflows in that branch
```

If you accidentally pass a category ID to `--scheme`, the CLI detects it and suggests the correct command:

```bash
opensdmx tree --scheme t_prc
# → 't_prc' is a category, not a scheme.
# → Use: opensdmx tree --scheme t_economy --category t_prc
```

Use `--depth` to limit the tree depth when a scheme is very large:

```bash
opensdmx tree --scheme t_economy --depth 1
```

### Semantic search

`opensdmx search` has two modes:

| Mode | How it works | Best for |
|---|---|---|
| Keyword (default) | Exact substring match on dataset title | When you know the right technical term |
| `--semantic` | Embedding similarity via Ollama | When you don't know the exact wording, or want conceptually related datasets |

#### Setup

Requires [Ollama](https://ollama.com) with the `nomic-embed-text-v2-moe` model:

```bash
ollama pull nomic-embed-text-v2-moe
opensdmx embed              # build embeddings for default provider (eurostat)
opensdmx embed -p istat     # build embeddings for ISTAT
```

#### Why semantic search matters

The SDMX catalog uses technical terminology. The same concept can appear under many different labels, or under none of the words you'd naturally use. Semantic search bridges that gap.

**Example 1 — colloquial phrase, zero word overlap with catalog**

```bash
opensdmx search "people struggling to make ends meet"            # 0 results
opensdmx search --semantic "people struggling to make ends meet" # finds ILC_MDES09 with score 0.844
```

| df_id | df_description | score |
|---|---|---|
| ILC_MDES09 | Inability to make ends meet | 0.844 |
| ILC_DI10 | Mean and median income by ability to make ends meet | 0.586 |
| ILC_IGTP02 | Transition of ability to make ends meet from childhood to current situation | 0.557 |
| HLTH_DM060 | Ability to make ends meet by level of disability | 0.521 |
| … | … | … |

The query shares no words with the results — the model matches the concept, not the text.

**Example 2 — informal phrasing for a technical concept**

```bash
opensdmx search "people without a job"            # 0 results
opensdmx search --semantic "people without a job" # finds unemployed/jobless datasets
```

| df_id | df_description | score |
|---|---|---|
| MED_PS423 | Proportion of persons living in jobless households | 0.609 |
| LFSA_UGATES | Unemployed persons by type of employment sought | 0.592 |
| LFSA_UGAN | Unemployed persons by citizenship | 0.581 |
| LFSA_UGPIS | Unemployed persons by previous occupation | 0.578 |
| … | … | … |

**Example 3 — demographic concept expressed differently**

```bash
opensdmx search "aging population senior citizens"            # 0 results
opensdmx search --semantic "aging population senior citizens" # finds population 65+ datasets
```

| df_id | df_description | score |
|---|---|---|
| TPS00028 | Proportion of population aged 65 and over | 0.646 |
| TPS00010 | Population by age group | 0.550 |
| ILC_LVPS30 | Distribution of population aged 65 and over by type of household | 0.544 |
| … | … | … |

**When keyword search is enough**

When you already know the technical term, keyword search is faster and returns all matching datasets (not capped at 10). `search "unemployment"` returns 114 results; `search --semantic "unemployment"` returns the 10 most similar by score — useful to surface the most relevant ones quickly.

**Rule of thumb:** start with a keyword search. If results are empty or off-target, switch to `--semantic`.

#### How the score works

The `score` column is the **[cosine similarity](https://en.wikipedia.org/wiki/Cosine_similarity)** between the query vector and each dataset description vector. Both are produced by [`nomic-embed-text-v2-moe`](https://huggingface.co/nomic-ai/nomic-embed-text-v2-moe) — the score is the model's native output, not a rescaled metric. It ranges from 0 to 1 (higher = more similar); in practice most relevant results fall between 0.5 and 0.7.

The model converts text into high-dimensional vectors such that semantically related phrases point in similar directions, regardless of the exact words used. Cosine similarity measures the angle between two such vectors: a score of 1 means identical direction, 0 means orthogonal (unrelated).

The ranking therefore depends entirely on the model: a different model would produce different vectors and a different ordering. The model is fixed — if you rebuild embeddings with `opensdmx embed`, the same model is used.

### Caching

Cache is namespaced per provider under `~/.cache/opensdmx/{AGENCY_ID}/`.

| File | Content | Default TTL |
|---|---|---|
| `dataflows.parquet` | Dataset catalog | 7 days |
| `cache.db` — structures + codelists | Dimensions, codelist descriptions and values | 30 days |
| `cache.db` — constraints | Available constraint values per dataflow | 7 days |

Environment variables:

| Variable | Description |
|---|---|
| `OPENSDMX_PROVIDER` | Provider name or custom base URL (session-wide default) |
| `OPENSDMX_AGENCY` | Agency ID for custom URL providers |
| `OPENSDMX_DATAFLOWS_CACHE_TTL` | Dataset catalog TTL in seconds (default: `604800` — 7 days) |
| `OPENSDMX_METADATA_CACHE_TTL` | Structure/codelist TTL in seconds (default: `2592000` — 30 days) |
| `OPENSDMX_CONSTRAINTS_CACHE_TTL` | Constraints TTL in seconds (default: `604800` — 7 days) |

See `.env.example` for a ready-to-use template.

## Timeout

```python
opensdmx.set_timeout()      # get current timeout (default: 300s)
opensdmx.set_timeout(600)   # set to 10 minutes
```

## Validation

opensdmx was tested against the benchmark scenario described in the IMF [*StatGPT: AI for Official Statistics*](https://www.imf.org/en/publications/departmental-papers-policy-papers/issues/2026/03/10/statgpt-ai-for-official-statistics-573514) paper (2026).
Three independent AI agents received the same natural language question about G7 GDP growth,
worked through the full skill loop autonomously, and produced **42/42 identical observations** —
zero divergence across agents, zero variance on repeated calls.

See [docs/validation-statgpt.md](docs/validation-statgpt.md) for the full test and results.

## Acknowledgements

Inspired by [istatR](https://github.com/jfulponi/istatR) by [@jfulponi](https://github.com/jfulponi) and [istatapi](https://github.com/Attol8/istatapi) by [@Attol8](https://github.com/Attol8).

## Eurostat release calendar RSS feed

A Cloudflare Worker that converts the Eurostat data release calendar into an RSS feed, filtered to data releases only.

```
https://eurostat-rss.andy-pr.workers.dev/
```

Filter by theme (`economy`, `agriculture`, `transport`, `environment`, `industry`, `population`, `international`, `science`):

```
https://eurostat-rss.andy-pr.workers.dev/?theme=economy
```

Source: [`scripts/eurostat-rss/`](scripts/eurostat-rss/).

## License

MIT License — Copyright (c) 2026 Andrea Borruso
