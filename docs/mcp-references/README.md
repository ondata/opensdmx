# MCP LLM Instructions — Reference Collection

Reference files collected from MCP servers that expose statistical data to AI agents.

Each file contains the verbatim `llm-instructions` or `system-prompt` resource published by a given server. These are the instructions the server authors wrote to guide LLMs on how to use their tool correctly — anti-hallucination rules, recommended workflows, filter syntax, error handling.

Useful for designing opensdmx's own MCP server and `sdmx-explorer` skill.

## Files

| File | Project | Source |
|---|---|---|
| `oecd-mcp-llm-instructions.md` | isakskogstad/OECD-MCP | `oecd://llm-instructions` resource |
| `worldbank-data360-system-prompt.md` | worldbank/data360-mcp | `data360://system-prompt` resource |

## How to add more

1. Find the MCP server repo on GitHub
2. Locate the file that defines `llm-instructions`, `system-prompt`, or equivalent resources
3. Copy the verbatim string constant into a new `.md` file here
4. Add a row to the table above
