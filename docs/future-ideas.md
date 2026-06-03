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
