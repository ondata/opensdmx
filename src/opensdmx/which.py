"""Capability index and ranker for `opensdmx which`."""

from __future__ import annotations

from typing import Any

WHICH_INDEX: list[dict] = [
    {
        "command": "search",
        "description": "Find datasets by keyword in the local cache (or semantically with --semantic).",
        "group": "Discovery",
    },
    {
        "command": "tree",
        "description": "Browse the thematic category tree of dataflows step-by-step.",
        "group": "Discovery",
    },
    {
        "command": "siblings",
        "description": "Find other dataflows in the same category as a given dataflow.",
        "group": "Discovery",
    },
    {
        "command": "get",
        "description": "Download SDMX data for a dataflow, filtered by dimension values.",
        "group": "Data retrieval",
    },
    {
        "command": "plot",
        "description": "Visualize a time series as a line, bar, barh, point, or heatmap chart.",
        "group": "Data retrieval",
    },
    {
        "command": "run",
        "description": "Execute a saved YAML query file produced with --query-file.",
        "group": "Data retrieval",
    },
    {
        "command": "info",
        "description": "Show metadata and available dimensions for a dataflow ID.",
        "group": "Inspection",
    },
    {
        "command": "values",
        "description": "List all valid values for a specific dimension of a dataflow.",
        "group": "Inspection",
    },
    {
        "command": "constraints",
        "description": "Show which dimension values are actually present in the data (not just defined).",
        "group": "Inspection",
    },
    {
        "command": "providers",
        "description": "List all built-in SDMX providers (alias, name, URL).",
        "group": "Inspection",
    },
]


def _score_entry(entry: dict, query: str, tokens: list[str]) -> int:
    score = 0
    cmd = entry["command"].lower()
    desc = entry["description"].lower()
    group = entry.get("group", "").lower()

    for token in tokens:
        if token in cmd.split():
            score += 3
    if query in cmd:
        score += 2
    if query in desc:
        score += 2
    else:
        # Per-token substring match on description (handles multi-word queries)
        for token in tokens:
            if len(token) >= 4 and token in desc:
                score += 1
    if query in group:
        score += 1
    return score


def rank_which(query: str, limit: int = 3) -> list[dict]:
    """Return scored matches from WHICH_INDEX for *query*.

    Empty query returns all entries at score 0 (listing mode).
    Non-empty query returns only entries with score > 0, sorted descending,
    capped at *limit*.
    """
    q = query.strip().lower()
    if not q:
        return [{"entry": e, "score": 0} for e in WHICH_INDEX]

    tokens = q.split()
    scored: list[dict[str, Any]] = [{"entry": e, "score": _score_entry(e, q, tokens)} for e in WHICH_INDEX]
    scored = [m for m in scored if m["score"] > 0]
    scored.sort(key=lambda m: m["score"], reverse=True)
    return scored[:limit]
