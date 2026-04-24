# OECD-MCP — LLM Instructions

**Source**: `isakskogstad/OECD-MCP` — `src/resources.ts` → `LLM_INSTRUCTIONS` constant  
**MCP resource URI**: `oecd://llm-instructions`  
**Retrieved**: 2026-04-24  
**Repo**: https://github.com/isakskogstad/OECD-MCP

---

# Instructions for LLMs Using OECD MCP Server

## Overview
You have access to OECD's statistical database containing 5,000+ datasets across 19 categories covering economy, health, education, environment, trade, employment, and more.

## Recommended Workflow

### Step 1: Find the Right Dataset
- Use `search_dataflows` with keywords (e.g., "GDP", "unemployment", "inflation")
- Or use `list_dataflows` with category filter (ECO, HEA, EDU, ENV, TRD, JOB, etc.)
- Or use `get_popular_datasets` for commonly used data
- Or use `search_indicators` for specific economic/social indicators

### Step 2: Understand the Structure
- Call `get_data_structure` with the dataflow_id
- Note the dimension order - this is CRITICAL for building filters
- Check what values are available for each dimension

### Step 3: Query the Data
- Build filter matching dimension order from structure
- Always use `last_n_observations` to limit data size (default: 100, max: 1000)
- Use `start_period` and `end_period` for time ranges

### Step 4: Provide User Access
- Call `get_dataflow_url` to give user a link to OECD Data Explorer
- This lets them explore and download data interactively

## Critical Rules

### DO:
- Always check structure before building filters
- Limit queries with `last_n_observations` (default: 100, max: 1000)
- Use ISO 3166-1 alpha-3 country codes (SWE, not Sweden)
- Combine multiple countries with + (SWE+NOR+DNK)
- Use empty positions (..) for wildcard dimensions

### DON'T:
- Never guess filter format - check structure first
- Never query without limits - large datasets have 70,000+ observations
- Never use country names - always use codes
- Never assume dimension order - it varies by dataset

## Common Country Codes
- Nordic: SWE, NOR, DNK, FIN, ISL
- Major economies: USA, GBR, DEU, FRA, JPN, CHN
- Aggregates: OECD, EU27, G7, G20, WLD

## Filter Syntax
- Dimensions separated by periods: SWE.GDP.A
- Multiple values with plus: SWE+NOR+DNK.GDP.A
- Wildcards with empty position: SWE..A (all values for middle dimension)

## Error Handling
- 422 errors usually mean invalid filter - check structure and dimension order
- Timeout errors - try smaller query with `last_n_observations` or retry
- Empty results - verify filter values exist in the dataset's codelists

## Example Workflow

User: "What's Sweden's GDP growth?"

1. Search: `search_dataflows({query: "GDP"})`
   → Found QNA (Quarterly National Accounts)

2. Structure: `get_data_structure({dataflow_id: "QNA"})`
   → Dimensions: REF_AREA, TRANSACTION, PRICE_BASE, ADJUSTMENT, FREQ

3. Query: `query_data({dataflow_id: "QNA", filter: "SWE.B1_GE..", last_n_observations: 20})`
   → Returns GDP data

4. Link: `get_dataflow_url({dataflow_id: "QNA", filter: "SWE.B1_GE"})`
   → https://data-explorer.oecd.org/vis?df=QNA&dq=SWE.B1_GE

## Available Resources
- `oecd://countries` - Country codes and regional groups
- `oecd://filter-guide` - Detailed filter syntax guide
- `oecd://glossary` - Statistical terms and definitions
- `oecd://categories` - All 19 data categories
- `oecd://dataflows/popular` - Commonly used datasets
- `oecd://api/info` - API endpoint information
