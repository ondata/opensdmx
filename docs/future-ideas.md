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

**4. Natural language statistical research assistant**

The most ambitious idea: a mode where the user asks a question in natural language and the system:

1. Discovers relevant dataflows (already works via `catalog`)
2. Resolves dimensions and filters (already works via `values`/`constraints`)
3. Fetches the data
4. Answers with figures traced to the exact SDMX source

This would be the statistical equivalent of Feynman.

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
