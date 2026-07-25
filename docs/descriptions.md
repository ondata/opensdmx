# Dataflow descriptions for semantic search

How opensdmx gives each dataflow enough descriptive text for semantic search to work, and why the pipeline is shaped the way it is. This is design rationale — the runnable parts live in `scripts/descriptions_archive.py`, `src/opensdmx/embed.py`, and the resource under `src/opensdmx/data/descriptions/`.

## Provider scope

opensdmx is multi-provider. The description-harvest mechanism is generic: a provider opts in by declaring a reference-metadata channel in `portals.json` (`metadata_annotation`, `metadata_api_path`, `metadata_description_attribute`), and `embed.py` folds the harvested text in only when the provider's resource exists. Providers without such a channel keep their previous embeddings (title + category context), with no behaviour change.

**Today only ISTAT declares such a channel**, so the endpoints, coverage figures, and examples in the rest of this document are ISTAT-specific. Other providers would follow the same shape with their own metadata service.

## The problem

Over SDMX, most ISTAT dataflows expose only a terse `Name` (~49 characters, often a leaf label such as "Sport - età dettaglio"). The rich, human-written descriptions shown on EsploraDati never appear in the SDMX structure. ISTAT confirmed (2026-07-23) it will not add `<common:Description>` to the DSD. Without descriptive text, semantic search has almost nothing to match a natural-language question against.

## What text the embedding is built from

For each dataflow the embedded document concatenates, in order, the signals that are actually available:

| Signal | Source | Coverage (ISTAT) | Discriminates |
|---|---|---|---|
| `df_id` | catalog | 100% | — |
| title (`Name`) | catalog | 100% | the individual cut (leaf label) |
| category context | `opensdmx tree` cache | ~99% | the topic |
| harvested description | METADATA_API resource | ~81% | the **survey** |
| keyword annotation | `LAYOUT_DATAFLOW_KEYWORDS` | ~3% | cuts, where present |

Each signal is optional and folded in only when present, so providers and checkouts without a given source produce the same text they did before.

## Where the real descriptions come from

The descriptions ISTAT publishes on EsploraDati are reachable programmatically, just not as an SDMX description. Each dataflow carries a `METADATA_URL` annotation whose query string names a metadata report (`metadataSetId`, `reportId`) on the ISTAT `METADATA_API`. Fetching that report returns SDMX-JSON metadata whose `DATA_SOURCE` attribute holds the prose.

`scripts/descriptions_archive.py` harvests this: one catalog call collects every `METADATA_URL`, the reports are de-duplicated, each is fetched once, the prose is HTML-cleaned, and the result is written per dataflow to `src/opensdmx/data/descriptions/<provider>.parquet`.

## Key decisions

**Harvest offline into a shipped resource, not a live fetch.** The descriptions are quasi-static — they describe a survey's methodology, not its data. Fetching them at query or embedding time would add latency and a network dependency for no benefit, and would make embeddings non-reproducible across machines. Instead a scheduled script (monthly is ample) writes a version-controlled Parquet file that is bundled in the wheel, exactly as `portals.json` is. `embed.py` reads it locally and makes no metadata request.

**De-duplicate by report, not by dataflow.** The `reportId` is shared across all the cuts of one survey, so the metadata is fetched once per report and mapped back to every referencing dataflow. For ISTAT this turns 3,974 linked dataflows into 622 unique fetches (6.3×). The metadata API is a service distinct from the rate-limited SDMX data endpoint, so the harvest is not bound by that throttle.

**Declare the channel per provider, never branch on the provider name.** ISTAT sets `metadata_annotation`, `metadata_api_path`, and `metadata_description_attribute` in `portals.json`; the harvester and `embed.py` read them via `.get()`. A provider that declares nothing is never touched, and no library code contains `if provider == "istat"`.

**Guard the consumer on file existence.** `embed.py` joins the resource only when the file for the active provider exists. Absent — for the other providers, or a fresh checkout — the embedded text is byte-identical to before and no error is raised.

## Known limitations

**The description is written at the survey level, not the cut level.** Every cut of one survey shares a single description — e.g. all 176 cuts of the permanent census of enterprises carry the same text. This is why the description alone is never embedded: title, category, and keywords still discriminate between the cuts of a survey, while the description discriminates between surveys.

**Dimensions are not in the embedded text.** The catalog carries a dataflow's title and its `df_structure_id`, but not the names of its dimensions or codelists. Those live in the DSD and are not yet fetched. For ISTAT the leaf-label titles happen to name the breakdown in words ("età, titolo di studio"), but this is not guaranteed for other providers.

## Declared follow-ups

- **Deterministic composition from the DSD.** Pull dimension and codelist names into the embedded text, resolving the ~19% of ISTAT dataflows without a `METADATA_URL` and extending real descriptive text to providers with no metadata channel. Feasible at low cost: `df_structure_id` is already known and DSDs are shared, so the same report-style de-duplication applies.
- **Optional offline LLM prose.** Generate a description from title, category, and structure at build time only. The distributed package stays free of any runtime LLM dependency.
