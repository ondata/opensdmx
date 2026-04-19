"""Thematic category tree support (SDMX categoryscheme + categorisation)."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import polars as pl

from .base import get_cache_dir, get_provider, sdmx_request_xml
from .cache_config import CATEGORIES_CACHE_TTL
from .utils import xml_attr_safe, xml_parse

logger = logging.getLogger(__name__)


class CategoriesNotSupported(Exception):
    """Raised when the active provider does not expose /categoryscheme."""


CATEGORIES_SCHEMA = {
    "scheme_id": pl.Utf8,
    "scheme_name": pl.Utf8,
    "cat_id": pl.Utf8,
    "cat_path": pl.Utf8,
    "cat_name": pl.Utf8,
    "parent_path": pl.Utf8,
    "depth": pl.Int32,
}

CATEGORISATION_SCHEMA = {
    "df_id": pl.Utf8,
    "scheme_id": pl.Utf8,
    "cat_path": pl.Utf8,
}


def _struct_path(endpoint: str) -> str:
    prefix = get_provider().get("metadata_prefix", "")
    return f"{prefix}/{endpoint}" if prefix else endpoint


def _categories_cache_path() -> Path:
    return get_cache_dir() / "categories.parquet"


def _categorisation_cache_path() -> Path:
    return get_cache_dir() / "categorisation.parquet"


def _load_cached() -> tuple[pl.DataFrame, pl.DataFrame] | None:
    cp = _categories_cache_path()
    zp = _categorisation_cache_path()
    if not (cp.exists() and zp.exists()):
        return None
    age = time.time() - min(cp.stat().st_mtime, zp.stat().st_mtime)
    if age >= CATEGORIES_CACHE_TTL:
        return None
    return pl.read_parquet(cp), pl.read_parquet(zp)


def _direct_name(elem, language: str, ns: dict) -> str:
    """Return the Name element (direct child) for the given language.

    Falls back to any direct-child Name if preferred language is missing.
    We do NOT search descendants — that would pick up child categories' names.
    """
    common_ns = ns.get("common", "")
    tag = f"{{{common_ns}}}Name" if common_ns else "Name"
    direct_names = [n for n in elem.findall(tag)]
    for n in direct_names:
        if n.get("{http://www.w3.org/XML/1998/namespace}lang") == language:
            return (n.text or "").strip()
    if direct_names:
        return (direct_names[0].text or "").strip()
    return ""


def _walk_categories(parent_elem, scheme_id, scheme_name, parent_path, depth, language, ns, rows):
    struct_ns = ns.get("structure", "")
    tag = f"{{{struct_ns}}}Category" if struct_ns else "Category"
    for cat in parent_elem.findall(tag):
        cid = xml_attr_safe(cat, "id")
        if not cid:
            continue
        cat_path = f"{parent_path}.{cid}" if parent_path else cid
        rows.append({
            "scheme_id": scheme_id,
            "scheme_name": scheme_name,
            "cat_id": cid,
            "cat_path": cat_path,
            "cat_name": _direct_name(cat, language, ns),
            "parent_path": parent_path,
            "depth": depth,
        })
        _walk_categories(cat, scheme_id, scheme_name, cat_path, depth + 1, language, ns, rows)


def _fetch_categoryscheme() -> pl.DataFrame:
    """Fetch and parse /categoryscheme into a flat DataFrame."""
    provider = get_provider()
    catalog_agency = provider.get("catalog_agency", provider["agency_id"])
    language = provider.get("language", "en")
    path = _struct_path(f"categoryscheme/{catalog_agency}/ALL/latest")
    content = sdmx_request_xml(path)
    root, ns = xml_parse(content)
    struct_ns = ns.get("structure", "")

    rows: list[dict] = []
    scheme_tag = f"{{{struct_ns}}}CategoryScheme" if struct_ns else "CategoryScheme"
    for scheme in root.iter(scheme_tag):
        sid = xml_attr_safe(scheme, "id")
        if not sid:
            continue
        sname = _direct_name(scheme, language, ns)
        _walk_categories(scheme, sid, sname, "", 1, language, ns, rows)

    return pl.DataFrame(rows, schema=CATEGORIES_SCHEMA)


def _fetch_categorisation() -> pl.DataFrame:
    """Fetch and parse /categorisation into df_id -> (scheme_id, cat_path)."""
    provider = get_provider()
    agency_id = provider["agency_id"]
    catalog_agency = provider.get("catalog_agency", agency_id)
    path = _struct_path(f"categorisation/{catalog_agency}/ALL/latest")
    content = sdmx_request_xml(path)
    root, ns = xml_parse(content)
    struct_ns = ns.get("structure", "")

    rows: list[dict] = []
    cz_tag = f"{{{struct_ns}}}Categorisation" if struct_ns else "Categorisation"
    src_tag = f"{{{struct_ns}}}Source" if struct_ns else "Source"
    tgt_tag = f"{{{struct_ns}}}Target" if struct_ns else "Target"
    for cz in root.iter(cz_tag):
        src = cz.find(f"{src_tag}/Ref")
        tgt = cz.find(f"{tgt_tag}/Ref")
        if src is None or tgt is None:
            continue
        if src.get("class") and src.get("class") != "Dataflow":
            continue
        df_id = src.get("id")
        src_agency = src.get("agencyID")
        # Mirror discovery.all_available(): if provider uses a cross-agency
        # catalog, prefix df_id with the source agency so categorisation rows
        # match the dataflow list (otherwise siblings/filter return empty).
        if df_id and src_agency and catalog_agency != agency_id:
            df_id = f"{src_agency},{df_id}"
        scheme_id = tgt.get("maintainableParentID")
        cat_path = tgt.get("id")
        if not (df_id and scheme_id and cat_path):
            continue
        rows.append({
            "df_id": df_id,
            "scheme_id": scheme_id,
            "cat_path": cat_path,
        })

    return pl.DataFrame(rows, schema=CATEGORISATION_SCHEMA)


def supported_providers() -> list[str]:
    """Return list of provider aliases with categories_supported=true in portals.json."""
    portals_path = Path(__file__).parent / "portals.json"
    with open(portals_path) as f:
        portals = json.load(f)
    return [k for k, v in portals.items() if v.get("categories_supported")]


def load_categories() -> tuple[pl.DataFrame, pl.DataFrame]:
    """Return (categories_df, categorisation_df) for the active provider.

    First call fetches from the SDMX endpoints and caches two parquet files.
    Subsequent calls read from cache until TTL expires.

    Raises:
        CategoriesNotSupported: provider does not expose /categoryscheme.
    """
    provider = get_provider()
    if not provider.get("categories_supported", False):
        supported = supported_providers()
        raise CategoriesNotSupported(
            "Active provider does not expose /categoryscheme. "
            f"Providers with category tree: {', '.join(supported) or '(none)'}"
        )

    cached = _load_cached()
    if cached is not None:
        return cached

    logger.info(
        "Building thematic cache from categoryscheme + categorisation "
        "(first run can take 1-2 minutes)..."
    )

    categories_df = _fetch_categoryscheme()
    categorisation_df = _fetch_categorisation()

    _warn_stale(categorisation_df)

    try:
        categories_df.write_parquet(_categories_cache_path())
        categorisation_df.write_parquet(_categorisation_cache_path())
    except OSError as e:
        logger.warning(f"Could not write categories cache: {e}")

    return categories_df, categorisation_df


def _warn_stale(categorisation_df: pl.DataFrame) -> None:
    """Log a single aggregated warning if some df_ids in categorisation are stale."""
    try:
        from .discovery import all_available
        valid = set(all_available()["df_id"].to_list())
    except Exception as e:
        logger.warning(f"Could not cross-check stale dataflows: {e}")
        return

    if categorisation_df.is_empty():
        return
    total = len(categorisation_df)
    stale = categorisation_df.filter(~pl.col("df_id").is_in(list(valid)))
    n_stale = len(stale)
    if n_stale:
        logger.warning(
            f"{n_stale}/{total} entries in categorisation not found in dataflows list (stale entries)"
        )


def siblings_of(df_id: str) -> list[dict]:
    """Return all dataflow siblings grouped by category.

    A dataflow can belong to multiple categories (cross-listed). This function
    returns one group per (scheme_id, cat_path) membership, each group
    containing the dataflows sharing that category.

    Each returned group has keys:
        scheme_id, scheme_name, cat_path, cat_name, siblings (list of dict).
    Each sibling has: df_id, df_description, is_target (bool).

    Returns empty list if the dataflow is not categorized or the provider
    does not expose categories.
    """
    categories_df, categorisation_df = load_categories()
    memberships = categorisation_df.filter(pl.col("df_id") == df_id)
    if memberships.is_empty():
        return []

    from .discovery import all_available
    try:
        dataflows = all_available().select(["df_id", "df_description"])
    except Exception as e:
        logger.warning(f"Could not load dataflow list for descriptions: {e}")
        dataflows = pl.DataFrame(
            schema={"df_id": pl.Utf8, "df_description": pl.Utf8}
        )

    groups = []
    for row in memberships.iter_rows(named=True):
        scheme_id = row["scheme_id"]
        cat_path = row["cat_path"]
        cat_info = categories_df.filter(
            (pl.col("scheme_id") == scheme_id) & (pl.col("cat_path") == cat_path)
        )
        cat_name = cat_info.select("cat_name").row(0)[0] if not cat_info.is_empty() else ""
        scheme_name = cat_info.select("scheme_name").row(0)[0] if not cat_info.is_empty() else ""

        sib_ids = categorisation_df.filter(
            (pl.col("scheme_id") == scheme_id) & (pl.col("cat_path") == cat_path)
        ).select("df_id").unique()
        # Left-join so the sibling list survives when the dataflows table is
        # unavailable (e.g. provider-side error on the /dataflow endpoint).
        sibs = sib_ids.join(dataflows, on="df_id", how="left").with_columns(
            pl.col("df_description").fill_null("")
        )

        siblings = [
            {
                "df_id": r["df_id"],
                "df_description": r["df_description"] or "",
                "is_target": r["df_id"] == df_id,
            }
            for r in sibs.sort("df_id").iter_rows(named=True)
        ]
        groups.append({
            "scheme_id": scheme_id,
            "scheme_name": scheme_name,
            "cat_path": cat_path,
            "cat_name": cat_name,
            "siblings": siblings,
        })
    return groups


def filter_by_category(cat_id_or_path: str) -> pl.DataFrame:
    """Return dataflows belonging to a category (exact path or leaf id).

    Matches any cat_path that ends with the given token. Returns the
    dataflows DataFrame enriched with cat_path + scheme_id.
    """
    _, categorisation_df = load_categories()
    if categorisation_df.is_empty():
        return categorisation_df

    needle = cat_id_or_path
    mask = (
        (pl.col("cat_path") == needle)
        | pl.col("cat_path").str.ends_with(f".{needle}")
    )
    matched = categorisation_df.filter(mask)

    from .discovery import all_available
    try:
        dataflows = all_available()
    except Exception as e:
        logger.warning(f"Could not load dataflow list: {e}; returning category ids only")
        return matched
    return dataflows.join(matched, on="df_id", how="inner")
