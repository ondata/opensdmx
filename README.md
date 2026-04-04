[![PyPI version](https://img.shields.io/pypi/v/opensdmx)](https://pypi.org/project/opensdmx/)
[![GitHub](https://img.shields.io/badge/github-aborruso%2Fopensdmx-blue?logo=github)](https://github.com/aborruso/opensdmx)
[![deepwiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/aborruso/opensdmx)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

# opensdmx

Simple Python CLI and library for any SDMX 2.1 REST API. Default provider: **Eurostat**. Built-in support for ISTAT, OECD, ECB, World Bank, and more.

> **Best used with AI.** opensdmx works well on its own, but it shines when driven by an AI agent: the CLI is designed to be composed, queried, and orchestrated step by step. For a guided, interactive experience — dataset discovery, schema exploration, filter selection, and data retrieval — pair it with the [`sdmx-explorer`](skills/sdmx-explorer/SKILL.md) Agent Skill included in this repo.

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

## CLI quick start

```bash
opensdmx search "unemployment"
opensdmx info une_rt_m
opensdmx constraints une_rt_m geo
opensdmx get une_rt_m --freq M --geo IT --sex T --out data.csv

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
data = opensdmx.fetch("une_rt_m", freq="M", geo="IT", sex="T", age="TOTAL")

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
ds = opensdmx.load_dataset("une_rt_m")
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
| `opensdmx values <id> <dim> [-p provider]` | Show codelist values for a dimension (case-insensitive) |
| `opensdmx constraints <id> [dim] [-p provider]` | Show values actually present in the dataflow (via `availableconstraint`) |
| `opensdmx get <id> [--DIM VALUE] [--start-period P] [--end-period P] [--last-n N] [--first-n N] [--out file] [--query-file file.yaml] [-p provider]` | Download data; optionally save the query as YAML |
| `opensdmx run <query.yaml> [--out file] [-p provider]` | Re-run a query saved with `--query-file` |
| `opensdmx plot <id\|file.csv> [--DIM VALUE] [--geom line\|bar\|barh\|point\|scatter] [--out file] [-p provider]` | Plot data as chart |
| `opensdmx blacklist [-p provider]` | List and remove datasets from the unavailability blacklist |

### Examples

```bash
# Eurostat (default)
opensdmx search "unemployment"
opensdmx search "unemployment" --n 5
opensdmx info une_rt_m
opensdmx values une_rt_m FREQ          # case-insensitive: freq works too
opensdmx constraints une_rt_m
opensdmx constraints une_rt_m geo
opensdmx get une_rt_m --freq M --geo IT --out data.csv
opensdmx get une_rt_m --freq M --geo IT --out data.parquet
opensdmx plot une_rt_m --freq M --geo IT --geom line
opensdmx plot data.csv --geom scatter --x TIME_PERIOD --y OBS_VALUE

# Other providers
opensdmx search "disoccupazione" --provider istat
opensdmx get 151_929 --provider istat --FREQ A --REF_AREA IT --out data.csv
opensdmx search "GDP" --provider oecd
opensdmx search "inflation" --provider ecb
```

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

### Semantic search setup

Requires [Ollama](https://ollama.com) with the `nomic-embed-text-v2-moe` model:

```bash
ollama pull nomic-embed-text-v2-moe
opensdmx embed              # build embeddings for default provider (eurostat)
opensdmx embed -p istat     # build embeddings for ISTAT
opensdmx search --semantic "unemployment"
```

Tip: semantic search matches meaning, not exact words. Try synonyms or related terms for better results (e.g. "jobless" instead of "unemployment").

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

## Acknowledgements

Inspired by [istatR](https://github.com/jfulponi/istatR) by [@jfulponi](https://github.com/jfulponi) and [istatapi](https://github.com/Attol8/istatapi) by [@Attol8](https://github.com/Attol8).

## License

MIT License — Copyright (c) 2026 Andrea Borruso
