# SDMX constraints archive

An incrementally-growing, public archive of **available constraints** — which
codes are actually present in each dataflow, per dimension — for the SDMX
providers used by opensdmx. One datafile per provider.

Most SDMX providers don't expose this information efficiently (ISTAT exposes
constraints for only ~1.5% of its dataflows and implements none of the SDMX 2.1
metadata discovery endpoints). This archive answers discovery questions like
*"which ISTAT datasets have municipal-level detail?"* offline, without hammering
the provider.

## How it grows

A daily GitHub Action ([constraints-archive.yml](../../.github/workflows/constraints-archive.yml))
runs [scripts/constraints_archive.py](../../scripts/constraints_archive.py) with a
small per-provider budget. Each run probes a batch of not-yet-covered dataflows
and commits the result: the files in this folder are the persistent state, so
coverage converges over days/weeks and then only new or stale dataflows get
re-probed (default staleness: 180 days). No bulk sweeps, minimal load on the
providers.

Probe paths:

- **istat** — databrowser hub bulk endpoint (one sub-second JSON call per
  dataflow, no rate-limited SDMX calls)
- **other providers** — `load_dataset()` + `get_available_values()`, paced by
  the opensdmx built-in rate limiter

## Files

### `{provider}.parquet` — the archive

| column | description |
|---|---|
| `df_id` | dataflow ID |
| `dimension_id` | dimension ID (e.g. `ITTER107`) |
| `code_id` | code available in the data for that dimension |
| `checked_at` | ISO date of the probe |

Query it directly, e.g.:

```sql
-- dataflows with municipal detail (6-digit territorial codes)
SELECT DISTINCT df_id
FROM 'data/constraints/istat.parquet'
WHERE dimension_id IN ('ITTER107', 'REF_AREA')
  AND regexp_matches(code_id, '^[0-9]{6}$');
```

### `{provider}_status.csv` — probe status per dataflow

Human-diffable progress tracker: `df_id`, `df_description`, `status`
(`ok` / `empty` / `error`), `source` (`hub` / `sdmx`), `n_dims`, `n_codes`,
`error_count`, `last_error`, `checked_at`. Errored dataflows are retried on
later runs (max 3 attempts).

### `istat_territorial.csv` — derived view (ISTAT only)

Territorial granularity per dataflow, classified from the codes of the
territorial dimension (`ITTER107` in older dataflows, `REF_AREA` in newer
ones — same code hierarchy):

| code pattern | level |
|---|---|
| `IT` | nazionale |
| `IT` + 1 char (e.g. `ITC`) | ripartizione |
| `IT` + 2 chars (e.g. `ITC1`) | regione |
| `IT` + 3 chars (e.g. `ITC11`) | provincia |
| 6 digits (e.g. `001272`) | comune |

Columns: `df_id`, `df_description`, `dimension_id`, `max_level`, `levels`
(pipe-separated levels present), `n_territories`, `checked_at`.

```sql
SELECT df_id, df_description, n_territories
FROM 'data/constraints/istat_territorial.csv'
WHERE max_level = 'comune'
ORDER BY df_id;
```
