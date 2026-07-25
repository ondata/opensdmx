# Dataflow descriptions archive

Authentic, human-written dataflow descriptions harvested from a provider's
reference-metadata service and shipped inside the package so opensdmx can fold
them into semantic-search embeddings offline.

These descriptions do **not** exist in the SDMX structure of the dataflows. For
ISTAT they are the prose shown on EsploraDati, reachable via the `METADATA_URL`
annotation → `METADATA_API` (`DATA_SOURCE` field), covering ~81% of the catalog.

## Files

One Parquet file per provider, keyed by `df_id`:

| column | description |
|---|---|
| `df_id` | dataflow id |
| `description` | plain-text description (HTML-unescaped, markup stripped) |
| `report_id` | source reference-metadata report id (shared across dataflows) |
| `metadata_set_id` | source metadata set id |
| `siqual_id` | id of the linked quality-system page, when present (ISTAT SIQual: `visualizza.do?id=<siqual_id>` / `disaggregazioni.do?id=<siqual_id>`), extracted from the metadata link attribute |
| `harvested_at` | ISO date of the harvest |

The `siqual_id` bridges a dataflow to ISTAT's SIQual quality system, which documents the survey's methodology and its territorial disaggregation level (e.g. municipality vs region). opensdmx does not fetch SIQual itself; the id is captured here at zero extra cost so the mapping is available.

## Regenerating

```bash
uv run python scripts/descriptions_archive.py --provider istat
uv run python scripts/descriptions_archive.py --provider istat --stats
```

The run is resumable (reports already present are not re-fetched) and refreshed
monthly by `.github/workflows/descriptions-archive.yml`. The metadata API is a
separate service from the rate-limited SDMX data endpoint.

## How it is consumed

`opensdmx embed` reads `<provider>.parquet` **if present** and appends each
dataflow's description to the embedded document text. When the file is absent,
embeddings are unchanged — no network request is made at embedding time.
