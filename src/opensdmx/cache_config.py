"""Centralised cache TTL configuration, overridable via environment variables."""

from __future__ import annotations

import os

# Dataflow list (parquet file) — default 7 days
DATAFLOWS_CACHE_TTL: float = float(
    os.environ.get("OPENSDMX_DATAFLOWS_CACHE_TTL", 604_800)
)

# Structure dimensions + codelist info/values (SQLite) — default 30 days
METADATA_CACHE_TTL: float = float(
    os.environ.get("OPENSDMX_METADATA_CACHE_TTL", 2_592_000)
)

# Available constraints (SQLite) — default 7 days
CONSTRAINTS_CACHE_TTL: float = float(
    os.environ.get("OPENSDMX_CONSTRAINTS_CACHE_TTL", 604_800)
)

# Thematic category tree (parquet files) — default 7 days
CATEGORIES_CACHE_TTL: float = float(
    os.environ.get("OPENSDMX_CATEGORIES_CACHE_TTL", 604_800)
)
