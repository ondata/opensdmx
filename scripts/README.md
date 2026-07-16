# Utility scripts

Standalone scripts for maintenance, monitoring and diagnostics. Run them with
`uv run python scripts/<name>.py` from the repo root.

> ⚠️ **ISTAT rate limiting**: ISTAT enforces ~5 requests/minute on its SDMX
> endpoint; exceeding it results in an IP ban for 1-2 days. The opensdmx
> package paces SDMX calls automatically (`rate_limit` in `portals.json`) —
> never bypass it with raw HTTP loops.

## constraints_archive.py

Incremental prober that grows the public constraints archive in
[`data/constraints/`](../data/constraints/) (see its README for the file
schemas). Budgeted: each run probes a batch of dataflows and stops; the
committed files are the persistent state. Scheduled daily by the
`constraints-archive.yml` workflow.

```bash
uv run python scripts/constraints_archive.py --provider istat
uv run python scripts/constraints_archive.py --provider eurostat --budget 300
uv run python scripts/constraints_archive.py --provider istat --stats
```

ISTAT is probed via the databrowser hub bulk endpoint (fast, outside the SDMX
rate limiter); other providers go through `load_dataset()` +
`get_available_values()`, paced by the package.

## monitor_latency.py

Latency monitor for SDMX endpoints (curl-based, evidence-grade). Scheduled by
the `latency-monitor.yml` workflow; appends to `output/latency.jsonl`.

## test_istat_endpoints.py

Diagnostic probe of the SDMX 2.1 metadata endpoints on ISTAT
(`actualconstraint`, `metadatastructure`, `metadata`, annotations). Documents
which discovery endpoints are (not) implemented — evidence for the ISTAT
advocacy correspondence. Re-run it when ISTAT announces changes.

## probe_contentconstraint.py

One-shot probe of the `contentconstraint` endpoint across providers; writes a
comparison table to `tmp/contentconstraint-probe.md`.

## probe_providers.sh

Tests constraints and `last_n` support for all built-in providers; used to
review/update provider capabilities in `portals.json`.

## eurostat-rss/

Cloudflare Worker mirroring the Eurostat RSS feed (see its own README).
