# Future Ideas

## Feynman-Inspired: opensdmx as a Statistical Research Agent

Inspired by [Feynman](https://github.com/getcompanion-ai/feynman), an open-source AI research agent for academic workflows.

### Core Analogy

Feynman is to academic papers what opensdmx could be to statistical data. Both aim at the same goal: verifiable, traceable information retrieval from primary sources. Every claim grounded, every number traceable.

### Ideas

**1. High-level research workflows**

Feynman exposes `/deepresearch`, `/compare`, `/watch` commands. opensdmx has granular primitives but no high-level workflows. Candidates:

- `opensdmx research "eurozone inflation 2020-2024"` — agent that discovers relevant dataflows across providers, fetches data, and produces a grounded report
- `opensdmx compare --indicator CPI --providers oecd,imf,istat` — cross-provider comparison of the same indicator, with discrepancy reporting
- `opensdmx watch <dataflow>` — periodic polling, notifies on new data releases

**2. Systematic provenance**

Feynman generates a `.provenance.md` for every output. opensdmx already has some provenance work (StatGPT validation), but it could be formalized: every `opensdmx data` call could optionally emit a provenance file — DSD used, codelist version, observation attributes, query URL, timestamp.

**3. Multi-agent cross-source verification**

Feynman has a `Verifier` agent that validates every citation. opensdmx could have a `verify` command that takes a numeric value and searches it across alternative providers — "is this figure confirmed by both IMF and OECD?"

**4. Natural language statistical research assistant** *(partially implemented)*

The most ambitious idea: a mode where the user asks a question in natural language and the system:

1. Discovers relevant dataflows (already works via `catalog`) ✓
2. Resolves dimensions and filters (already works via `values`/`constraints`) ✓
3. Fetches the data ✓
4. Answers with figures traced to the exact SDMX source

The `sdmx-explorer` skill is already a working embryo of this pattern. What's missing: persistent state, structured output artifacts, verification loops.

### Architectural Direction

Feynman has a multi-agent orchestration layer (Pi runtime + 4 specialized subagents). opensdmx is currently a one-shot CLI. The interesting evolution would be adding an agentic/conversational layer **on top of** the existing CLI — not replacing it, but using it as the reliable, verifiable tool that agents call.

The `sdmx-explorer` skill is already an embryo of this pattern. Feynman suggests going deeper: persistent state, structured artifacts, verification loops, composable workflows.

---

## 2025-2026 Ecosystem Trends

Survey of similar projects published or updated in 2025-2026, and what they suggest for opensdmx.

### Dominant trend: MCP servers for AI agents

All major players moved to MCP servers as the standard interface for AI agents: Google Data Commons (September 2025), World Bank `data360-mcp` (October 2025), `oecd-mcp` (November 2025), StatBridge (March 2026). opensdmx has a Claude Code skill but no native MCP server — this is the most critical gap relative to the ecosystem.

### Actionable ideas

**5. Native MCP server** *(high priority, medium effort)*

A standalone `mcp-server-opensdmx` package exposing tools `search_datasets`, `get_data`, `browse_tree` as MCP primitives. The CLI logic already exists; this would be a thin wrapper. Publishable separately on PyPI. Would reposition opensdmx from "CLI for humans" to "data infrastructure for AI agents" — the Feynman direction made concrete.

References: `worldbank/data360-mcp`, `isakskogstad/oecd-mcp`.

**6. `llm-instructions` resource** *(high priority, low effort)*

OECD-MCP exposes an `llm-instructions` resource that explicitly guides LLM reasoning on how to use SDMX data correctly (anti-hallucination, codelist interpretation, query sequencing). World Bank does the same with a `data360://system-prompt` MCP resource.

opensdmx could expose a structured instruction block — via MCP resource or as a Claude resource — that tells LLMs how to orchestrate SDMX queries correctly. Extends the anti-hallucination philosophy already validated against the StatGPT benchmark.

**7. Semantic topic registry** *(medium priority, low effort)*

StatBridge ships 25 curated semantic topics (`unemployment_rate`, `gdp_growth`, etc.) as an alternative to raw SDMX codes. opensdmx has semantic search via Ollama (requires local embeddings), but a curated `topics.yaml` mapping `topic_name → (provider, dataflow_id, base_filters)` would be lighter and immediately usable without Ollama.

**8. Federated multi-provider search** *(medium priority, medium effort)*

OpenEcon Data aggregates 330,000 indicators from 8+ providers in a single search. opensdmx currently searches one provider at a time. A `--all-providers` flag that queries all configured providers in parallel and returns unified ranked results would be a strong differentiator for discovery.

Example: `opensdmx search --all-providers "inflation"`.

**9. Multi-dataset recipe / join** *(low priority, low effort)*

`oecddatabuilder` extends the YAML query pattern already in opensdmx: declare multiple datasets to merge into a single DataFrame with automatic join on common dimensions. Could be implemented by adding a `join_on: [REF_AREA, TIME_PERIOD]` field and multi-dataflow support to the existing `--query-file` format.

**10. SDMX 3.0 / REST 2.0** *(low priority, high effort)*

`sdmx1` and `pysdmx` (BIS) already support SDMX 3.0. No mainstream provider requires it today, but it is an emerging requirement. Defer until Eurostat or OECD mandate REST 2.0.

---

## rsdmx-Inspired Improvements

Patterns from open issues in [eblondel/rsdmx](https://github.com/eblondel/rsdmx) (R package for SDMX) that reveal unmet user needs.

**11. Hierarchical parent labels in codelist enrichment** *(low priority, medium effort)*

When enriching a dataset with DSD labels, also return parent code labels (and grandparent, if present). rsdmx #109 has been open since 2016 — a persistent user need. opensdmx already does label lookup but ignores hierarchy. Useful for geographic hierarchies (country → region → city) and classification trees.

**Feasibility note (2026-05-01):** SDMX 2.1 defines a `<structure:Parent><Ref id="..."/></structure:Parent>` element for explicit hierarchy. ISTAT uses it (e.g. CL_ITTER107: 12,465/12,471 codes have a parent). However, Eurostat and OECD do not — their hierarchy is implicit in the code structure (`OC1 → OC11 → OC111`) and would require provider-specific heuristics. Two separate code paths needed for limited gain: downgraded to low priority.

**12. Codelist filtered by constraint** *(low priority, low effort)*

`opensdmx values` currently returns all values declared in the codelist, not only those present in the dataset. rsdmx #190 exposes the same bug. Fix: apply the `AvailableConstraint` to filter the codelist before returning it. Note: `opensdmx constraints` already does this correctly — the gap is only in `values`.

**Coverage note:** the `sdmx-explorer` skill already addresses this for AI-orchestrated use: it explicitly instructs never to use `opensdmx values` to validate filter codes and routes all constraint checks through `opensdmx constraints`. The remaining gap is purely UX for human users running `values` directly from the terminal.

**13. Custom HTTP headers for authenticated providers** *(medium priority, low effort)*

Some providers (e.g. ABS Australia) require API key in the HTTP header, not the query string. rsdmx #162. opensdmx has no mechanism for this. A `--header "X-Api-Key: ..."` flag or a per-provider `headers:` key in `providers.yaml` would cover the gap.

**14. Auto-coercion of TIME_PERIOD to ISO dates** *(implemented)*

`parse_time_period()` is applied by default in `retrieval.py` on every `get` call and in `plot`. No action needed.

**15. Dataset validation against DSD** *(low priority, medium effort)*

A command `opensdmx validate <dataflow> [--file data.csv]` that checks a dataset for compliance with its DSD: required dimensions present, values in declared codelists, observation attributes valid. rsdmx #107.

## OpenEcon-Inspired

From a comparison with [OpenEcon Data](https://github.com/hanlulong/openecon-data) (330k indicators, LLM-driven routing). The point of these ideas is to match what makes OpenEcon's output trustworthy — explicit, verifiable provenance — while keeping opensdmx's thin, no-LLM-inside, standards-based design. OpenEcon attaches `apiUrl` + `sourceUrl` to every result; the LLM picks the series internally (its responses literally carry `"__decision_source":"llm_pick"`), which is convenient but opaque. opensdmx can deliver the same provenance *more* transparently because the intelligence stays in the external orchestrating agent.

**16. Provenance on a channel separate from the data** *(medium priority, low effort)*

Surface, for every `get`, the exact SDMX query URL (`query_url`) and a human-readable source URL (`source_url`). **Constraint: never inline in stdout** — the data stream (CSV/table, pipes, `--out file.csv`) must stay clean and machine-parseable. Correct form:

- **CSV/table mode** → provenance goes to **stderr**, so stdout and `--out` files stay untouched.
- **JSON output mode** (see idea #8 / JSON-as-default) → provenance is just a field in the envelope (`query_url`, `source_url`); no readability problem since the output is structured.
- Optional dedicated subcommand `opensdmx url <dataflow> [filters]` that prints *only* the query URL, no data — zero pollution by design.

Recommended default: JSON carries the field; CSV/table emits it on stderr. No flag needed for the common case.

**17. Static country-group aliases** *(low priority, low effort)*

A no-LLM alias map expanding `--geo G7` / `BRICS` / `OECD` into the underlying ISO/GEO code lists (Eurostat already has `EU27_2020`, `EA20` as native codes; the value is groups that are *not* SDMX codes). Mechanical, thin, no model involved.

**18. Reproducible-command export** *(low priority, low effort)*

After a `get`, optionally emit the exact `opensdmx` command (or API URL) that reproduces the result — the verifiable, no-LLM analogue of OpenEcon's "export as Python/Stata code".

**19. Auditable provenance of the *choice*, not just the number** *(strategic, in the skill)*

opensdmx's differentiator vs LLM-inside routers: because the agent drives `search → constraints → get` step by step, the `sdmx-explorer` skill can leave an auditable trail of *why* a given dataflow and codes were selected — provenance of the decision, not only of the datum. Lives in the skill, not the core.

### Related projects to monitor

| Project | URL | Notes |
|---|---|---|
| pysdmx (BIS) | github.com/bis-med-it/pysdmx | Active, opinionated, advanced metadata mapping |
| sdmx1 | github.com/khaeru/sdmx | Mature, SDMX 2.1 + 3.0, 7 releases in 2025 |
| data-commons-mcp | docs.datacommons.org/mcp | Google, statistical grounding for LLMs |
| data360-mcp | github.com/worldbank/data360-mcp | World Bank, MCP + anti-hallucination patterns |
| oecd-mcp | github.com/isakskogstad/oecd-mcp | 5,000+ OECD datasets via SDMX, `llm-instructions` |
| StatBridge | statbridge.net | SaaS MCP + topic registry, built on sdmx1 |
| OpenEcon Data | github.com/hanlulong/openecon-data | 330k indicators, federated multi-source search |
| oecddatabuilder | pypi.org/project/oecddatabuilder | YAML recipe for reproducible OECD pipelines |

## Embedding-Only Semantic Search & Routing — prototype validated (2026-08-04)

Tested embedding-based semantic search over the harvested ISTAT descriptions (`src/opensdmx/data/descriptions/istat.parquet`, 3,949 docs) with **no LLM**: fastembed (`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, 384 dim, ONNX on CPU) + cosine similarity. Prototype: `tmp/semantic_route_test.py`.

> **Not the fastembed attempt that was reverted.** `LOG.md` (2026-03-31) records fastembed being tried as an Ollama replacement and reverted for poor quality on Italian queries — that attempt used `nomic-ai/nomic-embed-text-v1.5-Q`, a different model. The two results are about different models and are not in conflict.

### Results

- One-time corpus embedding: ~155 s on CPU; cache ~6 MB (`.npy`).
- Query latency: **16–18 ms** per query, embedding included. Works on minimal hardware, zero tokens.
- Quality on Italian natural-language queries:
  - "dammi i dati sulle nascite" → all top-5 are birth dataflows (`25_74*`) ✅
  - "inflazione e prezzi al consumo" → IPCA/NIC dataflows ✅
  - "incidenti stradali nelle province" → road-accident dataflows ✅
  - "quanti stranieri vivono in italia" → residence permits (relevant, arguably not the best possible set) ~
  - "quante persone lavorano nel settore agricolo" → generic employment + agritourism (weak: compound intents dilute) ⚠️
  - "previsioni meteo" (out-of-domain) → top score 0.40, correctly **below the 0.45 routing threshold** → no match ✅

### Takeaways

- Supports the case for a self-contained backend (no Ollama): retrieval quality is good enough for a first-pass ranker, and a threshold gives a deterministic "no match" guardrail instead of hallucinated picks.
- **Status of the plan this was meant to confirm (updated 2026-08-21): its premise no longer holds.** The plan approved on 2026-07-16 was built around `google/embeddinggemma-300m`, with `multilingual-e5-small` as fallback, chosen so the same model would carry over to a Rust/Tauri app. fastembed 0.8.0 exposes neither. The plan document itself is no longer on disk. Treat the direction as open, not approved.
- **This prototype has never been scored.** The evidence above is qualitative, on a corpus of descriptions only, with a different model and dimensionality from the shipping index. [Dataset search](search.md) sets the bar any replacement has to clear on the same gold set — MRR 0.135 to beat BM25, ~0.327 to replace nomic — and no candidate has been measured against it. That measurement, not another spike, is what would settle the question.
- Same embeddings can also do **intent routing** (route query → action: search / territorial view / fetch) in a future no-LLM app — the pattern Aurelio's semantic-router popularized.
- Corpus hygiene matters: catalog names like "dataflow eliminato" surface in top results; deleted dataflows should be filtered before indexing.
- Literature check (2025-2026): lightweight routers reach 80–88% accuracy at <4 ms vs ~91% for LLMs at 60–700 ms — [GQR-Bench, arXiv:2505.14524](https://arxiv.org/abs/2505.14524); simple kNN over embeddings beats learned routers — [arXiv:2505.12601](https://arxiv.org/abs/2505.12601); tool-calling routers are an active 2026 topic — [Switchcraft, arXiv:2605.07112](https://doi.org/10.48550/arxiv.2605.07112), [NTILC, arXiv:2606.06566](https://arxiv.org/abs/2606.06566). Reference libraries: [semantic-router](https://github.com/aurelio-labs/semantic-router) (FastEmbed encoder supported), [SynaptoRoute](https://github.com/sitanshukr08/SynaptoRoute).

## sdmx-dl-Inspired (2026-08-19)

Reviewed [nbbrd/sdmx-dl](https://github.com/nbbrd/sdmx-dl) (Java, National Bank of Belgium, EUPL) looking for ideas that fit opensdmx **without changing its logic**. Its source registry (`docs/assets/sources.csv`) is the direct counterpart of our `portals.json`; the CLI is a `verb + noun` hierarchy (`fetch data`, `list flows`, `check status`, `setup completion`).

### Worth adopting

**1. User-extensible source registry** *(implemented in v0.29.0: user-level `portals.json`, #94)*
sdmx-dl reads source definitions from a file that the user can point at (`-s, --sources <file>`, or the `sdmxdl.registry.sourceFile` property / `SDMXDL_REGISTRY_SOURCEFILE` env var), overlaying the built-in registry. In opensdmx a new provider requires a PR to `portals.json`; `--provider <URL>` + `OPENSDMX_AGENCY` already resolve an unlisted endpoint, but with no place to declare its quirks. An overlay file (`OPENSDMX_PROVIDERS_FILE`, same schema as `portals.json`, merged over the built-ins) extends a mechanism that already exists and keeps quirks declarative — no scattered `if provider == ...`.

**2. `--explain` — print the execution plan without fetching** *(implemented: `--explain` on `get` and the other commands)*
sdmx-dl has a common `--explain` option that writes the execution plan to stderr. opensdmx has no equivalent: `--query-file` saves parameters, not URLs. Printing the exact endpoint(s) a command would call — and stopping there — serves provenance (the AI can inspect the query before spending a call) and rate-limited providers such as ISTAT, where a wrong query costs minutes.

**3. `check access` as a first-class command** *(medium priority, low effort)*
sdmx-dl exposes reachability with a fixed output shape: `Source | Accessible | URI | DurationInMillis | ErrorMessage`. We already have the logic in `_check_api_reachable()` and `scripts/monitor_latency.py`, but not as a user-facing command. Promoting it (`opensdmx check <provider>`) is packaging, not new logic. Their `check status` reads an external uptime monitor (Upptime, declared per-source in the registry) — worth noting as an optional `monitor_url` field, not as a dependency.

**4. Language priority list** *(medium priority, low effort)*
`-l, --languages fr,nl,en` selects the label language with a fallback chain. `portals.json` carries a single `language`; ISTAT and Eurostat both serve multilingual labels, so `--labels` currently gets whatever the provider default is. A priority list is contained and directly improves label quality.

**5. An `evaluate-source` skill for onboarding a new provider** *(medium priority, low effort)*
`.agents/skills/evaluate-source/SKILL.md` is a checklist for assessing a candidate endpoint: probe `dataflow/all/all/all`, test `detail=allcompletestubs` and the trailing-slash quirk, verify the **whole** chain `flows → structure → data` down to one real observation, capture raw payloads as test fixtures, and treat documentation as a hypothesis to verify against live responses. It is the same discipline we apply by hand; it belongs next to `docs/provider-proposals.md` and the `multiprovider-reviewer` agent.

**6. Probed vs declared capabilities** *(low priority, medium effort)*
`opensdmx providers` already shows `constraints`/`last_n`/`categories` — but as flags **declared** in `portals.json`. sdmx-dl's `list features` reports what the endpoint actually answers. A `--probe` flag that verifies the declared flags against the live service would keep `portals.json` honest over time.

### Already solved differently

- **`fetch keys` / `SERIES_KEYS_ONLY`** — listing series keys without observations. We cover the same need with `constraints` (real codes, not codelists) plus `--last-n 1`.
- **Per-source `Confidentiality` driving cache policy** — meaningful when sources are private; all 15 of our providers are public.
- **Aliases, per-source properties, rate limits** — already in `portals.json`.

### Deliberately not adopted

- **`verb + noun` command hierarchy** (`fetch data`, `list flows`) — cleaner on paper, but it would break every existing script, the saved queries and the `sdmx-explorer` skill. Not worth it.
- **gRPC/REST web service** (`sdmx-dl-grpc`, ports 4557/4559) — a different product; our bridge to other tools is the CLI plus the Agent Skill / MCP route.
- **MSAL + OS keystore authentication** — Windows-only in their implementation, and no provider we support requires credentials.
- **SPI/driver plugin architecture** (`ServiceLoader`, `list plugins`) — the right answer for a Java library with 10+ dialects; over-engineering for a declarative `portals.json`.

## StatCheck/STaR-Inspired (2026-09-23)

Reviewed the work of Inria's CEDAR team (Ioana Manolescu) on statistical fact-checking, presented at the médialab Sciences Po [seminar of 8 October 2026](https://medialab.sciencespo.fr/en/news/statcheck-vers-un-acces-rapide-et-sur-a-des-statistiques-de-qualite-ioana-manolescu-cedar/). StatCheck, built with Radio France journalists over INSEE and Eurostat, chains three problems: finding data files on websites, turning human-oriented spreadsheets into machine-readable tables, and answering a natural-language question from those tables. Only the third one applies to opensdmx.

Sources: [StatCheck in Action, CIKM 2022](https://inria.hal.science/hal-03767992); [STaR: Space and Time-aware Statistic Query Answering, CIKM 2024](https://doi.org/10.1145/3627673.3679209); [STAR: Efficient, Scalable, and Modular Retrieval of Statistical Tables, extended version](https://pierre.senellart.com/publications/gauquier2026star.pdf); [project page](https://team.inria.fr/cedar/projects/statcheck/).

### Worth adopting

**1. Space and time as filters, not as keywords** *(high priority, medium effort)*
STaR extracts location and time from the query ("youth unemployment *in Sicily* *in 2023*"), uses them only to filter tables by their declared spatial and temporal scope, and ranks the survivors on the stripped remainder ("youth unemployment"). The authors report a clear quality gain over treating the whole query as text. Today `search` feeds "Sicilia" to BM25 as an ordinary token, rewarding titles that mention it instead of dataflows that actually carry regional data. Most pieces already exist: `REF_AREA` and `TIME_PERIOD` coverage per dataflow in `data/constraints/`, the territorial view `istat_territorial.csv`, and the BM25 ranker in `ranking.py`. Missing: a no-LLM extractor (gazetteer of NUTS/ISTAT place names + year regex) and a pre-ranking filter. Must be measured on the existing gold sets before shipping.

**2. Query relaxation along the geographic hierarchy** *(medium priority, low effort once #1 exists)*
When nothing matches at the requested granularity, STaR climbs the space hierarchy (municipality → province → region → NUTS1) or widens the time range. For an AI orchestrating the CLI, "not available by municipality, available by province in these dataflows" is far more useful than zero results.

**3. Index the labels of the codes actually present** *(medium priority, medium effort)*
StatCheck indexes, per dataset, the decoded labels of the concept codes it contains (Eurostat dictionaries), not just title and comments. The constraints archive already holds the real codes per dataflow: adding their labels to the search corpus would let "graduates" reach dataflows that contain an `ISCED 5-8` value even when the title does not say so. Index size must be checked against the Eurostat catalogue.

**4. Answer at series level, not only at dataflow level** *(low priority, high effort)*
StatCheck returns, in priority order, a cell, a row, a column, then the whole table. The SDMX equivalent is proposing a ready-made key — a `get` command with filters inferred from the query. Overlaps with the research-agent direction in the Feynman section above.

### Confirmed design choices

- **Index everything except the values.** Fact values answer questions but never appear in them, so only non-value cells need indexing; this keeps StatCheck's indexes tractable on hundreds of millions of facts. Same principle as indexing metadata and codes rather than observations.
- **Statistical tables are order-independent.** The authors argue against serialising rows for language models: column order carries no meaning in multidimensional data. Consistent with working on dimensions and codes.

### Not applicable

- **Focused crawling** ([SB-Classifier, arXiv:2602.11874](https://arxiv.org/abs/2602.11874)) and **spreadsheet table extraction** ([Cao et al. 2017](https://inria.hal.science/hal-01496700), [Kronlund-Drouault 2025](https://inria.hal.science/hal-05219883)) solve problems SDMX does not have: the data is already structured and queryable. They are a good argument for *why* SDMX matters.
- **Claim detection** in text is outside the scope of a data CLI.

### Open question

The extended STAR paper introduces a benchmark for "statistical table discovery". Not yet checked whether it is public; if so, it could complement our gold sets to measure #1.

## Eurostat API Guide-Inspired (2026-11-03)

Reviewed the [Eurostat "Data access via API" user guide](https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access) against the current code. None of the endpoints below is used by opensdmx today.

### Worth adopting

**1. Handle asynchronous delivery and `EXTRACTION_TOO_BIG`** *(partly implemented in v0.30.1, #101: the queued envelope stops `get` with the request id, a 413 prints a hint; still missing: polling and downloading the queued result)*
Eurostat estimates the cost of a data query as the product of the positions matched by each dimension filter: below 500,000 cells the answer is synchronous, between 500,000 and 5,000,000 it is asynchronous, above 5,000,000 it is a 413 `EXTRACTION_TOO_BIG`. Requests can also be forced to async by fair-use thresholds (concurrency, requests and cumulative cost per day/7/30 days). An async answer is a SOAP envelope (`syncResponse/queued/id`), to be polled at `/1.0/async/status/<id>` (`SUBMITTED`, `PROCESSING`, `AVAILABLE`, `EXPIRED`, `UNKNOWN_REQUEST`, `ERROR`) and then downloaded. `sdmx_request_csv()` passes the body straight to `pl.read_csv`, so this envelope would be parsed as CSV (not reproduced live, to avoid a heavy query). Applies to Comext too, where unfiltered CN8 products hit the async range easily. Declare it as a quirk in `portals.json`. Bonus: with constraints already cached, `--explain` can estimate the cost and say "sync / async / rejected" before fetching. Tracked in [#40](https://github.com/ondata/opensdmx/issues/40) (closed, not a priority): the guide's examples run on the `/sdmx/2.1/data/` endpoint opensdmx uses, but the prerequisite stays a raw capture of a filtered SDMX-CSV query in the 500k-5M window, to see what comes back. [Guide](https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-detailed-guidelines/asynchronous-api).

**2. `metabase.txt.gz` as the Eurostat constraints source** *(high priority, low effort)*
One gzipped TSV with `dataset / dimension / position` for every Eurostat dataset — the codes actually present. It is what `data/constraints/eurostat.parquet` assembles one dataflow at a time: one daily download would make the archive complete, and `constraints` could work offline. [Guide](https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-detailed-guidelines/catalogue-api/metabase), [file](https://ec.europa.eu/eurostat/api/dissemination/catalogue/metabase.txt.gz).

**3. Table of contents (TOC) for freshness, coverage and descriptions** *(medium priority, low effort)*
`catalogue/toc/xml` gives, per dataset: last data update, last structure change, data start and end, number of values, short description (EN/FR/DE) and position in the navigation tree. None of this is in the `allstubs` dataflow list. It would enrich `search` and `info` (stale vs current data, years covered) and give real text to semantic search, as METADATA_API does for ISTAT. [Guide](https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-detailed-guidelines/catalogue-api/toc).

### Minor

- **RSS feed of changes** (last 7 days, rebuilt at 11:00 and 23:00): targeted cache invalidation for datasets, structures and codelists that actually changed, instead of the fixed 7-day TTL. [Guide](https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-detailed-guidelines/catalogue-api/rss).
- **`detail=serieskeysonly`** to count series before downloading; **`compressed=true`** to cut transfer size.
- **`geoLevel`** (`aggregate`, `country`, `nuts1-3`, `city`) exists only in the Statistics API, not in SDMX; the same filter can be done client-side from the length of `geo` codes.

### Already solved differently

- **Server-side labels** (`labels=both` in SDMX 3.0 CSV): `--labels` already covers it.
- **Fair use** (one request at a time, no parallelism): the built-in rate limiter already serialises calls.

## OECDdata-Inspired (2026-11-03)

Reviewed [OECDdata](https://cran.r-project.org/web/packages/OECDdata/index.html) 0.3.4 (R, MIT, published 2026-11-01), an OECD-only client modelled on `eurodata`: SDMX REST v2 by default, SDMX-CSV 2 payloads, catalogue-resolved short codes, coverage-based `describe`/`compare`.

### Worth adopting

**1. Catalogue-resolved short dataflow IDs** *(high priority, low effort)*
OECDdata accepts `CLI`, `DF_CLI`, `DSD_STES@DF_CLI` or the full `OECD.SDD.STES,DSD_STES@DF_CLI`. Short forms are matched against the current catalogue (no hard-coded aliases) and ambiguity is an error. In opensdmx, checked 2026-11-03: `opensdmx info DF_CLI -p oecd` and `opensdmx info CLI -p oecd` both fail with `Could not find dataset`; only the full ID works, after a `search`. For an AI orchestrating the CLI this means one call less and fewer invented IDs. Declare it in `portals.json` (the `AGENCY,DSD@DF` shape is OECD-specific), not as an `if provider == "oecd"`.

**2. `compare` — code coverage across dataflows** *(medium priority, low effort)*
Rows are the union of dimension/code pairs, with one boolean column per dataflow; conflicting labels are joined and warned about, not overwritten. Built on our constraints, it would answer "which of these two dataflows has provinces?" in one output. Same caveat as theirs: matching dimension IDs do not prove the same concept. Different from the cross-provider indicator `compare` in the Feynman section above.

### Minor

- **Explicit offline mode**: accept expired but intact cache entries, and fail explicitly on missing or corrupt ones instead of going to the network. Useful in sandboxes without network.
- **Read `Retry-After`**: they honour it and fail when the wait exceeds a maximum. We deliberately do not retry on 4xx (ISTAT bans); reading the header only to tell the user how long to wait fits that choice.
- **Local download budget** (60 attempts per rolling hour, retries included): our limiter spaces calls but has no ceiling.

### Already solved

- Actual constraints vs allowed codelists kept distinct: `constraints` vs `values`.
- `UNIT_MULT` not applied automatically, free dimensions and series gaps before computing changes: covered as analysis guidance in the sdmx-explorer skill.
