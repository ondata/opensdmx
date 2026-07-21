"""INPS hub-only adapter (`.Stat Suite` `api/core` middleware).

INPS (Istituto Nazionale della Previdenza Sociale) publishes its statistical
observatories through a `.Stat Suite` DataBrowser whose classic SDMX-REST (NSI
WS) endpoint is blocked by a WAF for external access. Only the middleware
`https://opendata.inps.it/databrowser/api/core` is reachable, and it serves
catalog/structure/constraints over JSON (GET + POST), not SDMX-REST.

This module is the single home for all INPS-specific logic. The core discovery
functions delegate here via a `if get_provider().get("hub_only"): return ...`
branch, so `portals.json` (`hub_only: true`) is the only switch — there are no
scattered `if provider == "inps"` checks.

The middleware is organised into four *nodes* (one per observatory). The mapping
`code -> nodeId` lives in `portals.json` under `hub_nodes`:

    pensioni=2, dipendenti=3, imprese=4, politiche_occupazionali=1

Every dataflow belongs to exactly one node; the `df_id -> node_id` index is
built once from the four catalogs and cached as Parquet next to the other
per-provider caches.

All hub calls go through `base.sdmx_request(..., _base_url=hub, _method=...)`,
inheriting the provider's rate-limit, retry, file-lock and User-Agent handling.

Reference: docs/inps/middleware-api.md
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import polars as pl

from .base import get_cache_dir, get_provider, sdmx_request
from .categories import CATEGORIES_SCHEMA, CATEGORISATION_SCHEMA

logger = logging.getLogger(__name__)

_DATAFLOW_SCHEMA = {
    "df_id": pl.Utf8,
    "version": pl.Utf8,
    "df_description": pl.Utf8,
    "df_structure_id": pl.Utf8,
    "has_constraint": pl.Boolean,
}


# --------------------------------------------------------------------------- #
# Low-level hub access
# --------------------------------------------------------------------------- #
def _hub_base() -> str:
    return str(get_provider()["hub_base_url"]).rstrip("/")


def _agency() -> str:
    return str(get_provider().get("agency_id", "INPS"))


def _nodes() -> dict[str, int]:
    """Return the `code -> nodeId` map from provider config."""
    return {str(k): int(v) for k, v in get_provider().get("hub_nodes", {}).items()}


def _hub_timeout() -> float | None:
    """Per-provider hub timeout (`hub_timeout` in portals.json), or None for default."""
    t = get_provider().get("hub_timeout")
    return float(t) if t is not None else None


def _hub_json(node: int, path: str, *, method: str = "GET", body: Any = None) -> Any:
    """Call a per-node hub endpoint and return parsed JSON.

    Routes through `base.sdmx_request` so rate-limit/retry/lock/User-Agent are
    inherited from the active (INPS) provider, while the base URL is overridden
    to the hub host and the request is bounded by the provider's `hub_timeout`.
    """
    full_path = f"nodes/{node}/{path.lstrip('/')}"
    resp = sdmx_request(
        full_path,
        accept="application/json",
        _base_url=_hub_base(),
        _method=method,
        _json_body=body,
        _timeout=_hub_timeout(),
    )
    return resp.json()


def _ds_identifier(df_id: str, version: str | None = None) -> str:
    """Build the hub dataset identifier `{agency},{df_id},{version}`."""
    return f"{_agency()},{df_id},{version or '1.0'}"


def _bare_df_id(full_identifier: str) -> str:
    """Extract the bare flow id from `INPS,{flow},1.0`."""
    parts = full_identifier.split(",")
    return parts[1] if len(parts) >= 2 else full_identifier


# --------------------------------------------------------------------------- #
# Catalog fetch + df->node index
# --------------------------------------------------------------------------- #
def _fetch_catalogs() -> dict[int, dict[str, Any]]:
    """Fetch the catalog JSON for every configured node: `{node_id: catalog}`."""
    catalogs: dict[int, dict[str, Any]] = {}
    for node in _nodes().values():
        catalogs[node] = _hub_json(node, "catalog")
    return catalogs


def _index_cache_path() -> Path:
    return get_cache_dir() / "inps_df_index.parquet"


def _save_index(index: dict[str, tuple[int, str]]) -> None:
    try:
        pl.DataFrame(
            {
                "df_id": list(index.keys()),
                "node_id": [n for n, _ in index.values()],
                "version": [v for _, v in index.values()],
            },
            schema={"df_id": pl.Utf8, "node_id": pl.Int64, "version": pl.Utf8},
        ).write_parquet(_index_cache_path())
    except OSError as e:
        logger.warning("Could not write INPS df->node index: %s", e)


def _load_index() -> dict[str, tuple[int, str]] | None:
    path = _index_cache_path()
    if not path.exists():
        return None
    try:
        df = pl.read_parquet(path)
        if "version" not in df.columns:  # pre-versioned cache → force rebuild
            return None
        return {r["df_id"]: (r["node_id"], r["version"]) for r in df.iter_rows(named=True)}
    except (OSError, pl.exceptions.PolarsError):
        return None


def _resolve(df_id: str) -> tuple[int, str]:
    """Return `(node_id, version)` for `df_id`, building the index if necessary."""
    index = _load_index()
    if index is None or df_id not in index:
        # Cold path: build the catalog-derived caches, then retry.
        all_available()
        index = _load_index() or {}
    entry = index.get(df_id)
    if entry is None:
        raise ValueError(f"INPS dataflow '{df_id}' not found in any node catalog.")
    return entry


def _node_for_df(df_id: str) -> int:
    """Return the node id owning `df_id`, building the index if necessary."""
    return _resolve(df_id)[0]


# --------------------------------------------------------------------------- #
# all_available()  — dataflow list + df->node index (side effect)
# --------------------------------------------------------------------------- #
def all_available() -> pl.DataFrame:
    """Return the INPS dataflow list and (re)build the df->node index.

    Schema matches `discovery.all_available`:
        df_id, version, df_description, df_structure_id, has_constraint

    `df_id` is the bare flow id (e.g. `DFB_ST_DIP_ATECO_REG_01`), version is read
    from the catalog identifier (`INPS,{flow},{version}`), `df_structure_id` is
    None (structure is fetched by df_id), and `has_constraint` is True (the hub
    always exposes per-dimension values). Descriptions come from each node's
    `datasetMap` title; the leaf category label is a fallback when absent.
    """
    catalogs = _fetch_catalogs()

    # Fallback descriptions: leaf-category label per dataflow (analogue of the
    # ISTAT cat_context), used only when datasetMap has no title.
    leaf_label = _leaf_labels(catalogs)

    records: list[dict[str, Any]] = []
    index: dict[str, tuple[int, str]] = {}
    seen: set[str] = set()
    for node, catalog in catalogs.items():
        # The authoritative dataflow set is the category tree's
        # `datasetIdentifiers` (same source as load_categories); `datasetMap`
        # is only a title lookup and may not cover every dataflow.
        title_map = {
            _bare_df_id(fid): (meta or {}).get("title")
            for fid, meta in (catalog.get("datasetMap") or {}).items()
            if isinstance(meta, dict)
        }
        for full_id in _catalog_dataset_ids(catalog):
            df_id = _bare_df_id(full_id)
            parts = full_id.split(",")
            version = parts[2] if len(parts) >= 3 else "1.0"
            if df_id in seen:
                # A flow id shared across observatories keeps its first node;
                # warn so the ambiguity is visible rather than silent.
                if index.get(df_id, (node, ""))[0] != node:
                    logger.warning(
                        "INPS dataflow '%s' appears in multiple nodes; keeping node %s",
                        df_id, index[df_id][0],
                    )
                continue
            seen.add(df_id)
            index[df_id] = (node, version)
            description = title_map.get(df_id) or leaf_label.get(df_id) or df_id
            records.append({
                "df_id": df_id,
                "version": version,
                "df_description": description,
                "df_structure_id": None,
                "has_constraint": True,
            })

    _save_index(index)
    return pl.DataFrame(records, schema=_DATAFLOW_SCHEMA)


def _catalog_dataset_ids(catalog: dict[str, Any]) -> list[str]:
    """Return every dataset identifier in a node catalog (recursive over categories)."""
    ids: list[str] = []

    def walk(cat: dict[str, Any]) -> None:
        ids.extend(cat.get("datasetIdentifiers", []) or [])
        for child in cat.get("childrenCategories", []) or []:
            walk(child)

    for group in catalog.get("categoryGroups", []) or []:
        for topcat in group.get("categories", []) or []:
            walk(topcat)
    return ids


def _leaf_labels(catalogs: dict[int, dict[str, Any]]) -> dict[str, str]:
    """Map each dataflow id to the label of the leaf category containing it."""
    labels: dict[str, str] = {}

    def walk(cat: dict[str, Any]) -> None:
        label = cat.get("label", "")
        for full_id in cat.get("datasetIdentifiers", []) or []:
            labels.setdefault(_bare_df_id(full_id), label)
        for child in cat.get("childrenCategories", []) or []:
            walk(child)

    for catalog in catalogs.values():
        for group in catalog.get("categoryGroups", []) or []:
            for topcat in group.get("categories", []) or []:
                walk(topcat)
    return labels


# --------------------------------------------------------------------------- #
# load_categories()  — thematic tree
# --------------------------------------------------------------------------- #
def load_categories() -> tuple[pl.DataFrame, pl.DataFrame]:
    """Build (categories_df, categorisation_df) from the four node catalogs.

    Each observatory's top category (e.g. OS15, OS06, OS11, OS10) is exposed as
    a *scheme*; its child categories are the tree levels. Schemas match the
    constants in `categories.py`.
    """
    catalogs = _fetch_catalogs()

    cat_rows: list[dict[str, Any]] = []
    cz_rows: list[dict[str, Any]] = []

    def walk(
        cat: dict[str, Any],
        scheme_id: str,
        scheme_name: str,
        parent_path: str,
        depth: int,
    ) -> None:
        cid = cat.get("id")
        if not cid:
            return
        cat_path = f"{parent_path}.{cid}" if parent_path else cid
        cat_rows.append({
            "scheme_id": scheme_id,
            "scheme_name": scheme_name,
            "cat_id": cid,
            "cat_path": cat_path,
            "cat_name": cat.get("label", ""),
            "cat_description": None,
            "parent_path": parent_path,
            "depth": depth,
        })
        for full_id in cat.get("datasetIdentifiers", []) or []:
            cz_rows.append({
                "df_id": _bare_df_id(full_id),
                "scheme_id": scheme_id,
                "cat_path": cat_path,
            })
        for child in cat.get("childrenCategories", []) or []:
            walk(child, scheme_id, scheme_name, cat_path, depth + 1)

    for catalog in catalogs.values():
        for group in catalog.get("categoryGroups", []) or []:
            for topcat in group.get("categories", []) or []:
                # Each observatory top category becomes a scheme; its child
                # categories are the depth-1 tree levels (mirrors the SDMX
                # providers, whose scheme sits above depth-1 categories).
                scheme_id = topcat.get("id", "")
                scheme_name = topcat.get("label", "")
                # Some observatories (e.g. Imprese/OS11) have no child
                # categories and hang their datasets directly off the top
                # category. Emit the top category itself as a depth-1 category
                # so the scheme is never empty and those datasets have a home.
                if topcat.get("datasetIdentifiers"):
                    walk_self = {
                        "id": topcat.get("id"),
                        "label": topcat.get("label", ""),
                        "datasetIdentifiers": topcat.get("datasetIdentifiers", []),
                        "childrenCategories": [],
                    }
                    walk(walk_self, scheme_id, scheme_name, "", 1)
                for child in topcat.get("childrenCategories", []) or []:
                    walk(child, scheme_id, scheme_name, "", 1)

    categories_df = pl.DataFrame(cat_rows, schema=CATEGORIES_SCHEMA)
    categorisation_df = pl.DataFrame(cz_rows, schema=CATEGORISATION_SCHEMA)
    return categories_df, categorisation_df


# --------------------------------------------------------------------------- #
# Dimensions (structure)
# --------------------------------------------------------------------------- #
def _codelist_from_ref(ref: str | None) -> str | None:
    """Parse `INPS+CL_HIER_TERRITORIO_REG+1.0` -> `CL_HIER_TERRITORIO_REG`."""
    if not ref:
        return None
    parts = ref.split("+")
    return parts[1] if len(parts) >= 2 else None


def get_dimensions(df_id: str, version: str | None = None) -> dict[str, dict[str, Any]]:
    """Return `{dim_id: {id, position, codelist_id}}` in DSD order.

    Reads `criteria` from the hub structure (array order = position 1..N).
    TIME_PERIOD is excluded (it is the `timeDimension`, mirroring how every
    SDMX DSD keeps the time dimension out of the ordinary dimension list).
    """
    node, resolved_version = _resolve(df_id)
    ds_id = _ds_identifier(df_id, version or resolved_version)
    structure = _hub_json(node, f"datasets/{ds_id}/structure")
    time_dim = structure.get("timeDimension")

    dims: dict[str, dict[str, Any]] = {}
    position = 0
    for criterion in structure.get("criteria", []) or []:
        dim_id = criterion.get("id")
        if not dim_id or dim_id == time_dim:
            continue
        position += 1
        extra = criterion.get("extra", {}) or {}
        dims[dim_id] = {
            "id": dim_id,
            "position": position,
            "codelist_id": _codelist_from_ref(extra.get("DataStructureRef")),
            "description": criterion.get("label") or None,
        }
    return dims


# --------------------------------------------------------------------------- #
# Constraints (PartialCodelists) + territory hierarchy
# --------------------------------------------------------------------------- #
def _partial_codelist(
    node: int, ds_full: str, dim_id: str, parent: str | None = None
) -> list[dict[str, Any]]:
    """POST PartialCodelists/{dim} and return its raw value list.

    `parent` selects the children of a hierarchical parent code (used to expand
    the territorial dimension); `None` requests the root level (body `[]`).
    """
    body: list[dict[str, Any]] = (
        [] if parent is None else [{"id": dim_id, "values": [{"id": parent}]}]
    )
    payload = _hub_json(
        node,
        f"datasets/{ds_full}/PartialCodelists/{dim_id}",
        method="POST",
        body=body,
    )
    criteria = payload.get("criteria", []) or []
    # Select the criterion matching the requested dimension rather than assuming
    # position 0 — guards against reordered or multi-criterion responses.
    for crit in criteria:
        if crit.get("id") == dim_id:
            return crit.get("values", []) or []
    return criteria[0].get("values", []) or [] if criteria else []


def _collect_dim_records(node: int, ds_full: str, dim_id: str) -> list[dict[str, str]]:
    """Return selectable `(id, name)` codes for a dimension.

    Handles hierarchical dimensions (e.g. TERRITORIO): a value flagged
    `isSelectable: false` is a parent node, so its children are fetched and the
    parent itself is dropped. Non-hierarchical dimensions return their values
    directly (all selectable). A `seen` set guards against cycles/repeats.
    """
    records: list[dict[str, str]] = []
    seen: set[str] = set()

    def descend(parent: str | None) -> None:
        for value in _partial_codelist(node, ds_full, dim_id, parent):
            vid = value.get("id")
            if not vid or vid in seen:
                continue
            seen.add(vid)
            if value.get("isSelectable", True):
                records.append({"id": vid, "name": value.get("name", "") or ""})
            else:
                descend(vid)

    descend(None)
    return records


def get_available_values(dataset: dict[str, Any]) -> dict[str, list[str]]:
    """Return `{dim_id: [codes]}` for every (non-time) dimension via the hub.

    An unknown dataflow or a hub/network error propagates (the discovery caller
    has no SDMX-REST fallback for a hub-only provider); dimensions that simply
    return no values are omitted from the result.
    """
    df_id = dataset["df_id"]
    node, resolved_version = _resolve(df_id)
    ds_full = _ds_identifier(df_id, dataset.get("version") or resolved_version)

    result: dict[str, list[str]] = {}
    for dim_id in dataset.get("dimensions", {}):
        if dim_id.upper() == "TIME_PERIOD":
            continue
        records = _collect_dim_records(node, ds_full, dim_id)
        if records:
            result[dim_id] = [r["id"] for r in records]
    return result


# --------------------------------------------------------------------------- #
# Data download (full dataflow — no server-side filter)
# --------------------------------------------------------------------------- #
def get_data(dataset: dict[str, Any]) -> pl.DataFrame:
    """Download the whole dataflow as SDMX-CSV via the hub.

    The middleware ignores selection criteria on `download/csv` and always
    returns the full dataflow, so `retrieval.get_data` filters client-side
    (same contract as `data_key_format: "empty"`). Privacy-suppressed cells
    carry `_` in OBS_VALUE and are read as null.
    """
    import io

    df_id = dataset["df_id"]
    node, resolved_version = _resolve(df_id)
    ds_full = _ds_identifier(df_id, dataset.get("version") or resolved_version)
    path = f"nodes/{node}/datasets/{ds_full}/download/csv"

    # The hub occasionally returns a partial/malformed body with HTTP 200; that
    # fails at parse time, *outside* sdmx_request's retry (which only fires on
    # network/5xx). Re-download once so a rare truncated response is not fatal.
    last_err: Exception | None = None
    for attempt in range(2):
        resp = sdmx_request(
            path,
            accept="application/vnd.sdmx.data+csv",
            _base_url=_hub_base(),
            _method="POST",
            _json_body=[],
            _is_data=True,
            _timeout=_hub_timeout(),
        )
        try:
            return pl.read_csv(
                io.BytesIO(resp.content),
                infer_schema_length=0,
                null_values=["_"],
                schema_overrides={"TIME_PERIOD": pl.Utf8, "OBS_VALUE": pl.Float64},
            )
        except (pl.exceptions.PolarsError, ValueError) as e:
            last_err = e
            logger.warning(
                "INPS download parse failed for %s (attempt %d/2), retrying: %s",
                df_id, attempt + 1, e,
            )
    raise last_err  # type: ignore[misc]


def get_codelist_records(dataset: dict[str, Any], dimension_id: str) -> list[dict[str, Any]]:
    """Return `[{id, name, parent, order}]` for one dimension (labels for CLI).

    Used by `_load_codelist_records` so `constraints DIM` / `values DIM` show
    human-readable names. `parent`/`order` are None (the hub's flat selectable
    view is sufficient for label lookup).
    """
    df_id = dataset["df_id"]
    node, resolved_version = _resolve(df_id)
    ds_full = _ds_identifier(df_id, dataset.get("version") or resolved_version)
    return [
        {"id": r["id"], "name": r["name"], "parent": None, "order": None}
        for r in _collect_dim_records(node, ds_full, dimension_id)
    ]
