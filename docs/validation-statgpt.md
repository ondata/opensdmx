# Validation against the StatGPT benchmark

## Background

The IMF Statistics Department published [*StatGPT: AI for Official Statistics*](https://www.imf.org/en/publications/departmental-papers-policy-papers/issues/2026/03/10/statgpt-ai-for-official-statistics-573514) (2026), a paper
that benchmarks how well AI systems retrieve official statistics. The finding is stark: **off-the-shelf
large language models (ChatGPT, Gemini) return inaccurate numerical statistics up to two-thirds of
the time**, with errors ranging from 0.8 to 12.6 percentage points compared to published WEO values —
even when the correct figures are explicitly uploaded into the conversation.

The paper proposes a different architecture: use AI to *generate structured API queries* against
official statistical endpoints, not to generate the numbers. The LLM interprets the question;
the API returns the exact published figure.

**This is exactly what opensdmx does.** The CLI is a thin, precise layer over SDMX 2.1 REST APIs.
When paired with an AI agent (via the `sdmx-explorer` skill), the LLM handles discovery and query
construction; opensdmx handles the retrieval. Numbers are never fabricated.

This document reports validation tests inspired by the StatGPT paper, run on **2026-04-07**
using **Claude Sonnet 4.6** as the AI agent.

---

## The tests

The test was run twice, with different conditions, to measure both provider-choice convergence
and value convergence.

### Round 1 — OECD National Accounts

> **Note**: at the time of this test, the IMF provider had not yet been added to opensdmx.
> Agents chose OECD as the best available option for full G7 coverage, not as a free choice
> between OECD and IMF. Round 2 (below) repeats the test with IMF WEO available.

Three agents launched in parallel, no shared context. Each received the same request:

> *"I need GDP growth data for G7 countries (Canada, France, Germany, Italy, Japan, United Kingdom,
> United States) from 2019 to 2024."*

Agents worked autonomously through the full `sdmx-explorer` skill loop: discovery → schema → retrieval.

**Query convergence:**

| | Agent 1 | Agent 2 | Agent 3 |
|---|---|---|---|
| Provider | OECD | OECD | OECD |
| Dataset | `DSD_NAMAIN10@DF_TABLE1_EXPENDITURE_GROWTH` | same | same |
| Key filter | `TRANSACTION=B1GQ`, `UNIT_MEASURE=PC` | same | same |
| Countries | CAN+DEU+FRA+GBR+ITA+JPN+USA | same | same |

All three rejected Eurostat (missing US, Japan, Canada) and chose OECD. Reasoning identical
across agents despite complete isolation.

**Value convergence:** `42 / 42 observations match exactly — zero divergence`

| Country | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---|---|---|---|---|---|
| Canada | 1.91 | -5.04 | 5.95 | 4.70 | 1.95 | 2.05 |
| France | 2.03 | -7.44 | 6.88 | 2.72 | 1.44 | 1.19 |
| Germany | 0.98 | -4.13 | 3.91 | 1.81 | -0.87 | -0.50 |
| Italy | 0.43 | -8.87 | 8.93 | 4.82 | 0.92 | 0.78 |
| Japan | -0.31 | -4.28 | 3.56 | 1.33 | 0.72 | -0.24 |
| United Kingdom | 1.26 | -10.05 | 8.54 | 5.15 | 0.27 | 1.08 |
| United States | 2.58 | -2.08 | 6.15 | 2.52 | 2.93 | 2.79 |

*Source: OECD National Accounts, chain-linked volume, % change on previous year.*

---

### Round 2 — IMF WEO (the paper's own source)

The StatGPT paper uses **IMF World Economic Outlook** data as its benchmark — all tables
compare ChatGPT responses against *"actual World Economic Outlook estimates"*. The first
round did not use WEO because the IMF provider was newly added and agents lacked that context.

A second round was run targeting WEO directly, again with three isolated agents:

> *"I need GDP growth data for G7 countries from 2019 to 2024." — use `--provider imf`*

**Query convergence:**

| | Agent 1 | Agent 2 | Agent 3 |
|---|---|---|---|
| Provider | IMF | IMF | IMF |
| Dataset | `WEO` | `WEO` | `WEO` |
| Indicator | `NGDP_RPCH` | `NGDP_RPCH` | `NGDP_RPCH` |
| Countries | CAN+DEU+FRA+GBR+ITA+JPN+USA | same | same |

All three independently identified `NGDP_RPCH` ("GDP, Constant prices, Percent change")
as the correct indicator via `opensdmx constraints WEO INDICATOR --provider imf`.

**Value convergence:** `42 / 42 observations match exactly — zero divergence`

| Country | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---|---|---|---|---|---|
| Canada | 1.908 | -5.038 | 5.951 | 4.189 | 1.529 | 1.555 |
| France | 2.091 | -7.603 | 6.794 | 2.801 | 1.619 | 1.102 |
| Germany | 0.973 | -4.127 | 3.913 | 1.807 | -0.872 | -0.496 |
| Italy | 0.429 | -8.868 | 8.931 | 4.821 | 0.715 | 0.726 |
| Japan | -0.402 | -4.169 | 2.697 | 0.960 | 1.245 | 0.104 |
| United Kingdom | 1.624 | -10.297 | 8.576 | 4.839 | 0.397 | 1.101 |
| United States | 2.584 | -2.081 | 6.152 | 2.524 | 2.935 | 2.793 |

*Source: IMF World Economic Outlook (WEO), `NGDP_RPCH`, retrieved via opensdmx.*

These are the same figures the StatGPT paper uses as ground truth in its accuracy tables.

---

## Why this matters

The StatGPT paper tests ChatGPT with the same question across 10 separate conversations.
The results vary by 0.8–12.6 percentage points per series — the model fabricates plausible
but incorrect figures, and the figures change with each call.

These two rounds invert the experiment: six separate agents across two rounds, same question,
same tool, zero divergence in both.

The results demonstrate two properties that make opensdmx suitable as an AI data layer:

**1. The AI layer converges when the question has a clear best answer.**
LLMs are non-deterministic, but the skill's discovery logic has a dominant correct path for
well-defined questions. All agents independently reached the same dataset and the same
filters — LLM variance is absorbed at the reasoning level, not at the number level.

**2. The data layer is deterministic by construction.**
Once the query is built, `opensdmx get` calls the SDMX API and returns exactly what the
provider publishes. There is no generation, no interpolation, no hallucination. Running the
same query a hundred times returns the same number every time.

The combination — convergent reasoning + deterministic retrieval — produces results that are
both consistent across agents and grounded in official published data.

---

## Additional verification: single-series repeatability

The same WEO series (Japan GDP growth 2021) was queried three consecutive times:

```bash
opensdmx get WEO --provider imf \
  --COUNTRY JPN --INDICATOR NGDP_RPCH --FREQUENCY A \
  --start-period 2021 --end-period 2021
```

Result: **2.697** — identical across all three calls.

The response also includes provenance metadata:

| Field | Value |
|---|---|
| Historical data source | Cabinet Office of Japan via Haver Analytics |
| Methodology | System of National Accounts (SNA) 2008 |
| Chain weighted | Yes, from 1980 |
| Base year | 2015 |
| Last updated | 2025-11-19 |

Not only is the number identical every time — you also know exactly where it came from,
how it was calculated, and when it was last updated. An LLM generating statistics provides
none of this.

---

## Full test report

The complete validation report — covering discovery, schema exploration, cross-source accuracy
(Eurostat vs OECD vs IMF WEO), and all test details — is available at
[`tmp/statgpt-tests/REPORT.md`](../tmp/statgpt-tests/REPORT.md).
