# Cache Reference

opensdmx uses local cache files stored in a provider-specific cache directory. By default this is under the OS user cache directory, for example `~/.cache/opensdmx/eurostat/` on Linux.

Cache base resolution order:

1. `OPENSDMX_CACHE_DIR`
2. `platformdirs.user_cache_dir("opensdmx")`
3. `/tmp/opensdmx-{username}` as fallback if neither location is writable

Presets use their canonical key (`eurostat`, `istat`, `oecd`, and so on), not their agency ID. Custom URL providers use `agency_id` when set, otherwise `custom_` followed by the first eight hexadecimal characters of the base URL's SHA-256 hash. Two custom URLs with the same `agency_id` share a cache directory.

---

## Files

| File | Format | Content | Default TTL |
|---|---|---|---|
| `dataflows.parquet` | Parquet | Provider dataset catalog | 7 days |
| `categories.parquet` | Parquet | Provider category tree | 7 days |
| `categorisation.parquet` | Parquet | Dataflow-to-category links | 7 days |
| `embeddings.parquet` | Parquet | Semantic embeddings (per dataset) | No expiry |
| `inps_df_index.parquet` | Parquet | INPS dataflow-to-node/version index | Rebuilt with the INPS catalog |
| `cache.db` | SQLite | Dimensions, codelists, constraints, blacklist | Table-specific |

Examples for Eurostat and ISTAT:

```
~/.cache/opensdmx/eurostat/dataflows.parquet
~/.cache/opensdmx/eurostat/embeddings.parquet
~/.cache/opensdmx/eurostat/cache.db

~/.cache/opensdmx/istat/dataflows.parquet
~/.cache/opensdmx/istat/embeddings.parquet
~/.cache/opensdmx/istat/cache.db
```

---

## Parquet files

### `dataflows.parquet`

Built from the provider's catalog (SDMX `dataflow` for REST providers, middleware for INPS). Refreshed when older than the configured TTL, 7 days by default.

Columns:

| Column | Type | Description |
|---|---|---|
| `df_id` | String | Dataset identifier (e.g. `une_rt_m`, `151_914`) |
| `version` | String | Dataflow version |
| `df_description` | String | Human-readable dataset name |
| `df_structure_id` | String | Referenced Data Structure Definition ID |
| `has_constraint` | Boolean/null | `true` if matched by the bulk constraint probe; `false` if the probe succeeded without a match; null when unknown |
| `df_keywords` | String/null | Keywords from a configured dataflow annotation |
| `df_last_update` | String/null | Update information from a configured dataflow annotation |
| `df_notes` | String/null | Notes from a configured dataflow annotation |
| `df_bulk_files` | String/null | Attached-file information from a configured dataflow annotation |
| `df_geo_dim` | String/null | Territorial dimension from a configured dataflow annotation |
| `df_sdmx_description` | String/null | Optional SDMX `Description` text |

When the bulk probe also returns codes, they are saved in SQLite `available_constraints`. Older catalog files missing optional columns are read with those columns set to null.

### `categories.parquet` and `categorisation.parquet`

Built by `opensdmx tree` for providers that support SDMX `categoryscheme` and `categorisation` endpoints. Refreshed if either file is older than 7 days.

`categories.parquet` contains the category hierarchy. `categorisation.parquet` maps dataflows to category paths.

### `embeddings.parquet`

Built locally by `opensdmx embed` using Ollama (`nomic-embed-text-v2-moe`). Not automatically refreshed; rebuild manually when the catalog changes.

Columns:

| Column | Type | Description |
|---|---|---|
| `df_id` | String | Dataset identifier |
| `embedding` | List[Float32] | Embedding vector (dimension depends on the model) |

---

## SQLite: `cache.db`

Each provider cache directory has one SQLite database for structure, codelist and constraint metadata and the blacklist. Expiring rows use `cached_at` (a Unix timestamp); blacklist rows use `marked_at` and do not expire. Default TTLs for Parquet and SQLite caches:

| Cache type | Default TTL | Environment override |
|---|---:|---|
| Dataflow catalog | 7 days | `OPENSDMX_DATAFLOWS_CACHE_TTL` |
| Category tree | 7 days | `OPENSDMX_CATEGORIES_CACHE_TTL` |
| Structure dimensions and codelists | 30 days | `OPENSDMX_METADATA_CACHE_TTL` |
| Available constraints | 7 days | `OPENSDMX_CONSTRAINTS_CACHE_TTL` |

### Tables

#### `structure_dims`

Dimension metadata for a Data Structure Definition (fetched from the `datastructure` endpoint).

| Column | Type | Notes |
|---|---|---|
| `structure_id` | TEXT | SDMX structure ID — PK part |
| `dimension_id` | TEXT | Dimension code (e.g. `FREQ`, `REF_AREA`) — PK part |
| `position` | INTEGER | Position in the SDMX key (1-based) |
| `codelist_id` | TEXT | Associated SDMX codelist ID, when known |
| `cached_at` | REAL | Unix timestamp |

#### `codelist_info`

Human-readable description of a codelist (e.g. "Frequency of collection").

| Column | Type | Notes |
|---|---|---|
| `codelist_id` | TEXT | PK |
| `description` | TEXT | Codelist name, preferring English when available |
| `cached_at` | REAL | Unix timestamp |

#### `codelist_values`

Individual code entries within a codelist (e.g. `A = Annual`).

| Column | Type | Notes |
|---|---|---|
| `codelist_id` | TEXT | Cache key (`<codelist_id>:<language>` for REST codelists) — PK part |
| `code_id` | TEXT | Code value (e.g. `A`, `IT`) — PK part |
| `code_name` | TEXT | Human-readable label |
| `code_parent` | TEXT | Parent code ID, if declared |
| `code_order` | INTEGER | Numeric `ORDER` annotation, if available |
| `cached_at` | REAL | Unix timestamp |

Existing databases gain `code_parent` and `code_order` in place. Existing rows have null values until refreshed.

#### `available_constraints`

Codes actually present in a dataset. Depending on the provider, sources include the hub, SDMX constraint endpoints, and a `serieskeysonly` response. These are narrower than a full codelist, which can include codes not present in the dataset.

| Column | Type | Notes |
|---|---|---|
| `df_id` | TEXT | Dataset ID — PK part |
| `dimension_id` | TEXT | Dimension code — PK part |
| `code_id` | TEXT | Available code — PK part |
| `cached_at` | REAL | Unix timestamp |

On write, the existing rows for `df_id` are deleted before re-inserting, so the table always reflects the latest constraint snapshot.

#### `invalid_datasets`

Datasets that failed an API availability check (triggered during `guide`). These are excluded from all future searches and listings. There is no automatic expiry; entries must be removed manually via `opensdmx blacklist`.

| Column | Type | Notes |
|---|---|---|
| `df_id` | TEXT | PK |
| `description` | TEXT | Dataset name at the time of marking |
| `marked_at` | REAL | Unix timestamp |

---

## ER diagram

```mermaid
erDiagram
    structure_dims {
        TEXT structure_id PK
        TEXT dimension_id PK
        INTEGER position
        TEXT codelist_id
        REAL cached_at
    }
    codelist_info {
        TEXT codelist_id PK
        TEXT description
        REAL cached_at
    }
    codelist_values {
        TEXT codelist_id PK
        TEXT code_id PK
        TEXT code_name
        TEXT code_parent
        INTEGER code_order
        REAL cached_at
    }
    available_constraints {
        TEXT df_id PK
        TEXT dimension_id PK
        TEXT code_id PK
        REAL cached_at
    }
    invalid_datasets {
        TEXT df_id PK
        TEXT description
        REAL marked_at
    }

```
