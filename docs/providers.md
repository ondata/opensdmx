# Provider Reference

opensdmx supports 15 configured SDMX 2.1 providers, configured in `src/opensdmx/portals.json`. Any SDMX 2.1-compliant endpoint can also be used as a custom provider.

---

## Configured providers

### eurostat (default)

| Field | Value |
|---|---|
| Name | Eurostat |
| `base_url` | `https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1` |
| `agency_id` | `ESTAT` |
| `rate_limit` | 0.5 s |
| `language` | `en` |
| `dataflow_params` | `detail=allstubs&references=none` |
| `constraint_endpoint` | `contentconstraint` |
| `datastructure_agency` | `ESTAT` |
| `data_format_param` | `SDMX-CSV` |

Quirks: Eurostat does not accept `Accept: text/csv`. Data must be requested with `Accept: application/xml` and the `format=SDMX-CSV` query parameter. The `contentconstraint` endpoint is used instead of `availableconstraint`. The `dataflow` request includes `detail=allstubs` and `references=none` for performance.

### istat

| Field | Value |
|---|---|
| Name | ISTAT |
| `base_url` | `https://esploradati.istat.it/SDMXWS/rest` |
| `agency_id` | `IT1` |
| `rate_limit` | 15.0 s |
| `language` | `it` |
| `constraint_endpoint` | `contentconstraint` |
| `constraint_bulk_supported` | `true` |
| `hub_base_url` | `https://esploradati.istat.it/databrowserhub/api/core` |

Quirks: ISTAT enforces a strict rate limit. The 15-second minimum interval between calls avoids HTTP 429 errors. Data is fetched using `Accept: text/csv` (no `data_format_param`). Dataset descriptions are in Italian; the embedded catalog language is `it`. ISTAT supports bulk `contentconstraint` discovery and has an optional Data Browser hub fast path for some metadata.

### comext

| Field | Value |
|---|---|
| Name | Eurostat Comext |
| `base_url` | `https://ec.europa.eu/eurostat/api/comext/dissemination/sdmx/2.1` |
| `agency_id` | `ESTAT` |
| `rate_limit` | 0.5 s |
| `language` | `en` |
| `dataflow_params` | `detail=allstubs&references=none` |
| `datastructure_agency` | `ESTAT` |
| `data_format_param` | `SDMX-CSV` |

Quirks: Comext uses Eurostat's SDMX-CSV format but exposes a trade-specific catalog. Full dataset download is disabled by the API, so dimension filters are required for practical data retrieval.

### ecb

| Field | Value |
|---|---|
| Name | European Central Bank |
| `base_url` | `https://data-api.ecb.europa.eu/service` |
| `agency_id` | `ECB` |
| `rate_limit` | 0.5 s |
| `language` | `en` |

### oecd

| Field | Value |
|---|---|
| Name | OECD |
| `base_url` | `https://sdmx.oecd.org/public/rest` |
| `agency_id` | `OECD` |
| `rate_limit` | 0.5 s |
| `data_rate_limit` | 60 s |
| `language` | `en` |

Quirks: OECD uses `catalog_agency = all` for catalog discovery and a dedicated 60-second data-request timer while structure calls keep the default rate limit.

### insee

| Field | Value |
|---|---|
| Name | INSEE (France) |
| `base_url` | `https://www.bdm.insee.fr/series/sdmx` |
| `agency_id` | `FR1` |
| `rate_limit` | 0.5 s |
| `language` | `en` |

### bundesbank

| Field | Value |
|---|---|
| Name | Deutsche Bundesbank |
| `base_url` | `https://api.statistiken.bundesbank.de/rest` |
| `agency_id` | `BBK` |
| `rate_limit` | 0.5 s |
| `language` | `en` |

Quirks: Bundesbank uses a `metadata` prefix for structure endpoints and `BBK` as the datastructure agency.

### worldbank

| Field | Value |
|---|---|
| Name | World Bank |
| `base_url` | `https://api.worldbank.org/v2/sdmx/rest` |
| `agency_id` | `WB` |
| `rate_limit` | 0.5 s |
| `language` | `en` |

Quirks: World Bank data retrieval uses SDMX-JSON. `lastNObservations` and `firstNObservations` are not supported and are dropped before the data request.

### abs

| Field | Value |
|---|---|
| Name | Australian Bureau of Statistics |
| `base_url` | `https://data.api.abs.gov.au/rest` |
| `agency_id` | `ABS` |
| `rate_limit` | 0.5 s |
| `language` | `en` |

### bis

| Field | Value |
|---|---|
| Name | Bank for International Settlements |
| `base_url` | `https://stats.bis.org/api/v1` |
| `agency_id` | `BIS` |
| `rate_limit` | 0.5 s |
| `language` | `en` |

### imf

| Field | Value |
|---|---|
| Name | International Monetary Fund |
| `base_url` | `https://api.imf.org/external/sdmx/2.1` |
| `agency_id` | `IMF.RES` |
| `catalog_agency` | `all` |
| `rate_limit` | 0.5 s |
| `language` | `en` |

Quirks: IMF catalog discovery uses `catalog_agency = all`. World Economic Outlook data is available through dataflow `WEO`; country codes are ISO alpha-3.

### ilo

| Field | Value |
|---|---|
| Name | International Labour Organization |
| `base_url` | `https://sdmx.ilo.org/rest` |
| `agency_id` | `ILO` |
| `rate_limit` | 0.5 s |
| `language` | `en` |

### unicef

| Field | Value |
|---|---|
| Name | UNICEF |
| `base_url` | `https://sdmx.data.unicef.org/ws/public/sdmxapi/rest` |
| `agency_id` | `UNICEF` |
| `rate_limit` | 0.5 s |
| `language` | `en` |
| `data_format_param` | `csvdata` |

Quirks: UNICEF data requests use `?format=csvdata`.

### derzhstat

| Field | Value |
|---|---|
| Name | Derzhstat |
| `base_url` | `https://stat.gov.ua/sdmx/workspaces/default:integration/registry/sdmx/2.1` |
| `agency_id` | `SSSU` |
| `rate_limit` | 3.0 s |
| `language` | `en` |
| `user_agent` | `Mozilla/5.0` |
| `data_key_format` | `empty` |

Quirks: Derzhstat blocks default library user-agents, so opensdmx sends a browser-like user-agent. Wildcard dot keys return 404, so dimension filters are applied client-side after download.

### inps

| Field | Value |
|---|---|
| Name | INPS |
| `agency_id` | `INPS` |
| `rate_limit` | 0.5 s |
| `language` | `it` |
| `hub_base_url` | `https://opendata.inps.it/databrowser/api/core` |
| `hub_only` | `true` |
| `hub_nodes` | `{pensioni:2, dipendenti:3, imprese:4, politiche_occupazionali:1}` |
| `user_agent` | `Mozilla/5.0` |

Quirks: INPS is **hub-only** — its classic SDMX-REST endpoint is blocked by a WAF, so it has no `base_url`; every catalog/structure/constraint/data call goes through the `.Stat Suite` DataBrowser middleware (`hub_base_url`, POST + GET JSON), routed by the dedicated `inps.py` adapter. The middleware is split into four *nodes* (one per observatory: pensions, employees, companies, employment policies); the `code→nodeId` map lives in `hub_nodes`, and a `df_id→node` index is built once from the four catalogs and cached. Data retrieval downloads the whole dataflow as SDMX-CSV (the middleware has no server-side filter) and filters client-side, mirroring Derzhstat's `data_key_format: "empty"`; the period window is applied client-side by year and `last_n`/`first_n` are unavailable. Territory codes are NUTS 2021 (Lombardia = `ITC4`). See [inps/middleware-api.md](inps/middleware-api.md) for the endpoint reference.

---

## Provider configuration fields

| Field | Type | Default | Description |
|---|---|---|---|
| `name` | string | — | Human-readable provider name |
| `base_url` | string | — | SDMX 2.1 REST base URL (required) |
| `agency_id` | string | — | Agency code used in SDMX endpoints (required) |
| `rate_limit` | float | `0.5` | Minimum seconds between API calls |
| `language` | string | `"en"` | Preferred language for dataset descriptions |
| `dataflow_params` | dict | `{}` | Extra query parameters appended to `dataflow/{agency_id}` requests |
| `constraint_endpoint` | string | `"availableconstraint"` | Endpoint for fetching available values (`availableconstraint` or `contentconstraint`) |
| `constraint_bulk_supported` | boolean | `false` | Whether a provider supports catalog-level bulk content constraints |
| `constraint_params` | dict | absent | Extra query parameters appended to constraint requests |
| `datastructure_agency` | string | `"ALL"` | Agency used in `datastructure/{agency}/...` requests |
| `catalog_agency` | string | absent | Agency used for catalog requests when different from `agency_id` |
| `metadata_prefix` | string | absent | Prefix prepended to structure endpoints for providers that split metadata paths |
| `data_format_param` | string | absent | If present, sent as `?format={value}` for data requests instead of `Accept: text/csv` |
| `data_accept` | string | absent | If present, used as the data request `Accept` header |
| `data_path_suffix` | string | absent | Suffix appended to data paths for providers that require it |
| `unsupported_params` | list | `[]` | Data request parameters to drop for providers that do not support them |
| `data_rate_limit` | float | absent | Dedicated rate limit for data requests, separate from structure requests |
| `user_agent` | string | absent | Provider-specific `User-Agent`; can be overridden with `OPENSDMX_USER_AGENT` |
| `data_key_format` | string | `"dots"` | SDMX key path style; `"empty"` omits wildcard dot keys and filters client-side |
| `hub_base_url` | string | absent | `.Stat Suite` DataBrowser middleware base URL (ISTAT constraints fast path; INPS full backend) |
| `hub_only` | boolean | `false` | When `true`, the provider has no SDMX-REST endpoint; catalog/structure/constraints are served entirely via `hub_base_url` (INPS) |
| `hub_nodes` | dict | absent | `code→nodeId` map for hub-only providers whose middleware is split into nodes (INPS observatories) |
| `constraints_supported` | boolean | provider-specific | Capability flag shown by `opensdmx providers` |
| `last_n_supported` | boolean | provider-specific | Capability flag for observation count parameters |
| `categories_supported` | boolean | provider-specific | Capability flag for category tree support |

Fields not specified in `portals.json` fall back to the defaults listed above (applied in `base.py` at load time).

---

## Rate limiting

The `rate_limit` field in `portals.json` sets the minimum number of seconds that must elapse between consecutive HTTP calls to a provider. It is enforced automatically — no configuration is needed at runtime.

Providers can also define `data_rate_limit`. When present, data requests use a separate timestamp and lock from structure/metadata requests. This lets slow or strict data endpoints be throttled without blocking catalog and metadata calls.

### How it works

1. opensdmx resolves a user cache directory using this order:

   ```
   OPENSDMX_CACHE_DIR
   platformdirs.user_cache_dir("opensdmx")
   /tmp/opensdmx-{username}  # fallback only
   ```

2. Rate-limit timestamp and lock files are stored under that cache root in `rate_limit/`, keyed by provider.

3. Before each HTTP request, opensdmx takes an exclusive file lock for the provider, reads the previous timestamp, and computes the elapsed time. If `elapsed < rate_limit`, it sleeps for the remaining seconds, showing a live countdown on stderr:

   ```
   Waiting (11s)...
   ```

4. The timestamp is written at request start, before the HTTP call, so the interval is measured send-to-send. The lock is held for the whole HTTP call, so parallel processes cannot bypass the provider limit.

### When it fires

Rate limiting applies only to actual HTTP calls. It does **not** fire on cache hits (SQLite or Parquet). The full call chain is:

```
CLI command
  └─ check SQLite / Parquet cache
       ├─ hit  → return cached data  (no wait, no timestamp update)
       └─ miss → sdmx_request()
                   └─ acquire provider lock
                        └─ _rate_limit_check()   ← waits if needed
                             └─ write timestamp
                                  └─ HTTP call
```

### Cross-process behavior

The rate-limit files persist across separate CLI invocations. Running two commands back-to-back in separate shells will respect the rate limit:

```bash
opensdmx constraints 151_929 --provider istat   # makes HTTP call, writes timestamp
opensdmx info 151_929 --provider istat          # waits if < 15s have passed
```

### Cold start

On the first call to a provider (no timestamp file), no wait is applied. The timestamp file is created before the first HTTP request is sent.

### Configuring rate limits

To adjust the interval for a built-in provider, edit `src/opensdmx/portals.json`:

```json
"istat": {
  "rate_limit": 15.0
}
```

For custom providers, pass `rate_limit` to `set_provider()`:

```python
opensdmx.set_provider("https://mysdmx.example.org/rest", agency_id="XYZ", rate_limit=5.0)
```

---

## Using a custom provider

Any SDMX 2.1-compliant REST endpoint can be used as a custom provider:

```python
import opensdmx

opensdmx.set_provider(
    "https://mysdmx.example.org/rest",
    agency_id="XYZ",
    rate_limit=1.0,
    language="en",
)
```

From the CLI:

```bash
opensdmx search "unemployment" --provider https://mysdmx.example.org/rest
```

When a custom URL is given, `agency_id` is optional but recommended. The custom provider uses all default field values unless overridden via `set_provider()` parameters. If `agency_id="XYZ"` is provided, the cache directory uses `XYZ`; otherwise opensdmx derives a short hash from the base URL so different custom URLs do not share cache or lock files.

Custom providers are not persisted; they must be set each time.
