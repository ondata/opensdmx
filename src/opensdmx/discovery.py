"""Functions for discovering and exploring SDMX datasets."""

from __future__ import annotations


class ConstraintsUnavailable(Exception):
    """Raised when the availableconstraint endpoint returns 500 (hidden/not-yet-public dataflow)."""


class ConstraintsTimeout(Exception):
    """Raised when the availableconstraint endpoint times out (slow provider backend)."""

    def __init__(self, df_id: str, timeout: float):
        self.df_id = df_id
        self.timeout = timeout
        super().__init__(
            f"Constraints request timed out after {timeout:.1f}s for {df_id}. "
            f"Set OPENSDMX_AVAILCONSTRAINT_TIMEOUT to override."
        )


import logging
import os
import time

logger = logging.getLogger(__name__)

import httpx
import polars as pl

from .base import get_agency_id, get_cache_dir, get_provider, sdmx_request_xml
from .utils import get_name_by_lang, xml_attr_safe, xml_parse

from .cache_config import DATAFLOWS_CACHE_TTL


def _struct_path(endpoint: str) -> str:
    """Prepend metadata_prefix to structure endpoint paths when configured."""
    prefix = get_provider().get("metadata_prefix", "")
    return f"{prefix}/{endpoint}" if prefix else endpoint


def _dataflow_cache_path():
    return get_cache_dir() / "dataflows.parquet"


def _load_cached_dataflows() -> pl.DataFrame | None:
    """Return cached dataflow list if it exists and is < 24h old."""
    path = _dataflow_cache_path()
    if path.exists():
        age = time.time() - path.stat().st_mtime
        if age < DATAFLOWS_CACHE_TTL:
            return pl.read_parquet(path)
    return None


def _filter_invalid(df: pl.DataFrame) -> pl.DataFrame:
    """Remove datasets marked as invalid from the given DataFrame."""
    from .db_cache import get_invalid_dataset_ids
    invalid = get_invalid_dataset_ids()
    if invalid:
        df = df.filter(~pl.col("df_id").is_in(list(invalid)))
    return df


def all_available() -> pl.DataFrame:
    """List all available datasets for the active provider.

    Returns a Polars DataFrame with columns:
        df_id, version, df_description, df_structure_id

    Results are cached per provider for 24h.
    Invalid datasets (marked via guide) are excluded.
    """
    cached = _load_cached_dataflows()
    if cached is not None:
        return _filter_invalid(cached)

    agency_id = get_agency_id()
    language = get_provider()["language"]

    catalog_agency = get_provider().get("catalog_agency", agency_id)
    path = _struct_path(f"dataflow/{catalog_agency}")
    dataflow_params = get_provider().get("dataflow_params", {})
    content = sdmx_request_xml(path, **dataflow_params)
    root, ns = xml_parse(content)

    records = []
    for df in root.iter("{" + ns.get("structure", "") + "}Dataflow") if "structure" in ns else []:
        df_id_raw = xml_attr_safe(df, "id")
        df_agency = xml_attr_safe(df, "agencyID")
        # For providers with catalog_agency, store full "{agencyID},{df_id}" as df_id
        # so the data URL (data/{df_id}) resolves correctly
        if catalog_agency != agency_id and df_agency:
            df_id = f"{df_agency},{df_id_raw}"
        else:
            df_id = df_id_raw
        version = xml_attr_safe(df, "version")
        df_description = get_name_by_lang(df, language, ns) or get_name_by_lang(df, "en", ns)

        # Structure reference
        struct_ns = ns.get("structure", "")
        struct_ref = df.find(f".//{{{struct_ns}}}Structure/Ref") if struct_ns else None
        df_structure_id = struct_ref.get("id") if struct_ref is not None else None

        records.append({
            "df_id": df_id,
            "version": version,
            "df_description": df_description,
            "df_structure_id": df_structure_id,
        })

    df = pl.DataFrame(records, schema={
        "df_id": pl.Utf8,
        "version": pl.Utf8,
        "df_description": pl.Utf8,
        "df_structure_id": pl.Utf8,
    })
    try:
        df.write_parquet(_dataflow_cache_path())
    except OSError:
        pass
    return _filter_invalid(df)


def _score_results(df: pl.DataFrame, tokens: list[str]) -> pl.DataFrame:
    """Add a synthetic relevance score and sort descending.

    Scoring per token (case-insensitive):
      +3  token found in df_id
      +2  token found in first 60 chars of df_description (topic tends to be upfront)
      +1  each occurrence of token in df_description
    """
    score_expr = pl.lit(0)
    for token in tokens:
        t = token.lower()
        score_expr = score_expr + (
            pl.col("df_id").str.to_lowercase().str.contains(t).cast(pl.Int32) * 3
        )
        score_expr = score_expr + (
            pl.col("df_description").str.to_lowercase().str.slice(0, 60).str.contains(t).cast(pl.Int32) * 2
        )
        score_expr = score_expr + (
            pl.col("df_description").str.to_lowercase().str.count_matches(t)
        )
    return df.with_columns(score_expr.alias("score")).sort("score", descending=True)


def search_dataset(keyword: str) -> pl.DataFrame:
    """Search datasets by keyword (case-insensitive) in description and ID.

    Splits keyword into tokens; all tokens must match in df_description or df_id.
    Results are sorted by a synthetic relevance score (id match, start-of-description,
    occurrence count). Returns columns: df_id, version, df_description, df_structure_id, score.
    """
    datasets = all_available()
    tokens = keyword.lower().split()

    filter_expr = pl.lit(True)
    for token in tokens:
        filter_expr = filter_expr & (
            pl.col("df_description").str.to_lowercase().str.contains(token)
            | pl.col("df_id").str.to_lowercase().str.contains(token)
        )

    results = datasets.filter(filter_expr)
    if results.is_empty():
        return results
    return _score_results(results, tokens)


def _resolve_codelist_from_concept(scheme_id: str, scheme_agency: str, concept_id: str) -> str | None:
    """Fetch a concept scheme and return the codelist ID from CoreRepresentation/Enumeration.

    Used as fallback when a DSD dimension lacks LocalRepresentation (e.g. IMF).
    Per SDMX 2.1 spec, the codelist may be attached to the concept rather than
    repeated in each DSD's LocalRepresentation.
    """
    try:
        path = _struct_path(f"conceptscheme/{scheme_agency}/{scheme_id}/latest")
        content = sdmx_request_xml(path)
        root, ns = xml_parse(content)
        struct_ns = ns.get("structure", "")
        tag = f"{{{struct_ns}}}Concept" if struct_ns else "Concept"
        for concept_node in root.iter(tag):
            if xml_attr_safe(concept_node, "id") == concept_id:
                enum_ref = concept_node.find(
                    f".//{{{struct_ns}}}CoreRepresentation//{{{struct_ns}}}Enumeration//Ref"
                ) if struct_ns else None
                if enum_ref is not None:
                    return enum_ref.get("id")
    except Exception:
        pass
    return None


def _get_dimensions(structure_id: str) -> dict:
    """Fetch dimension metadata for a data structure definition."""
    from .db_cache import get_cached_dims, save_dims
    cached = get_cached_dims(structure_id)
    if cached is not None:
        return cached

    ds_agency = get_provider().get("datastructure_agency", "ALL")
    path = _struct_path(f"datastructure/{ds_agency}/{structure_id}")
    content = sdmx_request_xml(path)
    root, ns = xml_parse(content)

    struct_ns = ns.get("structure", "")
    tag = f"{{{struct_ns}}}Dimension" if struct_ns else "Dimension"

    dims = {}
    for dim_node in root.iter(tag):
        dim_id = xml_attr_safe(dim_node, "id")
        position = xml_attr_safe(dim_node, "position")

        if not dim_id:
            continue

        # Codelist reference — first try LocalRepresentation (standard path),
        # then fall back to ConceptIdentity → ConceptScheme (used by IMF SDMX 2.1).
        local_rep = dim_node.find(f".//{{{struct_ns}}}LocalRepresentation//Ref") if struct_ns else None
        codelist_id = local_rep.get("id") if local_rep is not None else None

        if codelist_id is None and struct_ns:
            concept_ref = dim_node.find(f".//{{{struct_ns}}}ConceptIdentity//Ref")
            if concept_ref is not None:
                cs_id = concept_ref.get("maintainableParentID")
                cs_agency = concept_ref.get("agencyID")
                concept_ref_id = concept_ref.get("id")
                if cs_id and cs_agency and concept_ref_id:
                    codelist_id = _resolve_codelist_from_concept(cs_id, cs_agency, concept_ref_id)

        dims[dim_id] = {
            "id": dim_id,
            "position": int(position) if position else None,
            "codelist_id": codelist_id,
        }

    # Sort by position
    result = dict(sorted(
        ((k, v) for k, v in dims.items() if v["position"] is not None),
        key=lambda item: item[1]["position"]
    ))
    try:
        save_dims(structure_id, result)
    except Exception as e:
        logger.warning("Could not cache dimension metadata: %s", e)
    return result


def _get_dimension_description(codelist_id: str | None) -> str | None:
    """Fetch the description of a codelist."""
    if not codelist_id:
        return None
    from .db_cache import get_cached_codelist_info, is_codelist_info_cached, save_codelist_info
    if is_codelist_info_cached(codelist_id):
        return get_cached_codelist_info(codelist_id)
    try:
        path = _struct_path(f"codelist/ALL/{codelist_id}")
        content = sdmx_request_xml(path)
        root, ns = xml_parse(content)
        struct_ns = ns.get("structure", "")
        tag = f"{{{struct_ns}}}Codelist" if struct_ns else "Codelist"
        codelist_node = root.find(f".//{tag}")
        description = get_name_by_lang(codelist_node, "en", ns) if codelist_node is not None else None
    except (httpx.HTTPError, OSError):
        description = None
    try:
        save_codelist_info(codelist_id, description)
    except Exception as e:
        logger.warning("Could not cache codelist info: %s", e)
    return description


def load_dataset(dataflow_identifier: str) -> dict:
    """Create a dataset object for a given dataflow ID, structure ID, or description.

    Returns a dict with keys:
        df_id, version, df_description, df_structure_id, dimensions, filters
    """
    all_ds = all_available()

    match_row = None
    identifier_upper = dataflow_identifier.upper()

    # Try df_id exact match (case-insensitive)
    rows = all_ds.filter(pl.col("df_id").str.to_uppercase() == identifier_upper)
    if not rows.is_empty():
        match_row = rows.row(0, named=True)

    # Try structure_id match (case-insensitive)
    if match_row is None:
        rows = all_ds.filter(pl.col("df_structure_id").str.to_uppercase() == identifier_upper)
        if not rows.is_empty():
            match_row = rows.row(0, named=True)

    # Try description match (case-sensitive, human-readable text)
    if match_row is None:
        rows = all_ds.filter(pl.col("df_description") == dataflow_identifier)
        if not rows.is_empty():
            match_row = rows.row(0, named=True)

    if match_row is None:
        raise ValueError(f"Could not find dataset with identifier: {dataflow_identifier}")

    structure_id = match_row["df_structure_id"] or match_row["df_id"]
    dimensions = _get_dimensions(structure_id)
    filters = {dim_id: "." for dim_id in dimensions}

    return {
        "df_id": match_row["df_id"],
        "version": match_row["version"],
        "df_description": match_row["df_description"],
        "df_structure_id": structure_id,
        "dimensions": dimensions,
        "filters": filters,
    }


def print_dataset(dataset: dict) -> None:
    """Print a human-readable summary of a dataset object."""
    print("Dataset")
    print("-------")
    print(f"ID:          {dataset['df_id']}")
    print(f"Version:     {dataset['version']}")
    print(f"Description: {dataset['df_description']}")
    print(f"Structure:   {dataset['df_structure_id']}")
    print(f"\nDimensions ({len(dataset['dimensions'])}):")
    for dim_id, info in dataset["dimensions"].items():
        val = dataset["filters"].get(dim_id, ".")
        if val == ".":
            fstr = "(all)"
        elif isinstance(val, list):
            fstr = "[" + ", ".join(val) + "]"
        else:
            fstr = str(val)
        print(f"  - {dim_id}: {fstr}")


def dimensions_info(dataset: dict, include_descriptions: bool = True) -> pl.DataFrame:
    """Return a DataFrame with dimension metadata."""
    records = [
        {
            "dimension_id": dim["id"],
            "position": dim["position"],
            "codelist_id": dim["codelist_id"],
        }
        for dim in dataset["dimensions"].values()
    ]
    df = pl.DataFrame(records, schema={
        "dimension_id": pl.Utf8,
        "position": pl.Int64,
        "codelist_id": pl.Utf8,
    })

    if include_descriptions and not df.is_empty():
        descriptions = [
            _get_dimension_description(row["codelist_id"])
            for row in df.iter_rows(named=True)
        ]
        df = df.with_columns(pl.Series("description", descriptions, dtype=pl.Utf8))

    return df


def get_dimension_values(dataset: dict, dimension_id: str) -> pl.DataFrame:
    """Return available values (id, name) for a specific dimension."""
    dim_upper = {k.upper(): k for k in dataset["dimensions"]}
    actual = dim_upper.get(dimension_id.upper())
    if actual is None:
        avail = ", ".join(dataset["dimensions"].keys())
        raise ValueError(
            f"Dimension '{dimension_id}' not found. Available: {avail}"
        )
    dimension_id = actual

    codelist_id = dataset["dimensions"][dimension_id]["codelist_id"]
    if not codelist_id:
        logger.warning("No codelist found for dimension: %s", dimension_id)
        return pl.DataFrame({"id": [], "name": []})

    from .db_cache import get_cached_codelist_values, save_codelist_values
    cached = get_cached_codelist_values(codelist_id)
    if cached is not None:
        return pl.DataFrame(cached, schema={"id": pl.Utf8, "name": pl.Utf8})

    path = f"codelist/ALL/{codelist_id}"
    content = sdmx_request_xml(path)
    root, ns = xml_parse(content)

    struct_ns = ns.get("structure", "")
    tag = f"{{{struct_ns}}}Code" if struct_ns else "Code"

    records = []
    for code_node in root.iter(tag):
        records.append({
            "id": xml_attr_safe(code_node, "id"),
            "name": get_name_by_lang(code_node, "en", ns),
        })

    try:
        save_codelist_values(codelist_id, records)
    except Exception as e:
        logger.warning("Could not cache codelist values: %s", e)
    return pl.DataFrame(records, schema={"id": pl.Utf8, "name": pl.Utf8})


def _parse_constraint_xml(content: bytes) -> dict[str, list[str]]:
    """Parse KeyValue elements from a constraint XML response into a code dict."""
    root, ns = xml_parse(content)
    common_ns = ns.get("common", "")
    struct_ns = ns.get("structure", "")
    result: dict = {}
    kv_tags = []
    if struct_ns:
        kv_tags.append(f"{{{struct_ns}}}KeyValue")
    if common_ns:
        kv_tags.append(f"{{{common_ns}}}KeyValue")
    for kv_tag in kv_tags:
        for kv in root.iter(kv_tag):
            dim_id = kv.get("id")
            if not dim_id:
                continue
            values = [c.text.strip() for c in kv if c.text and c.text.strip()]
            if values:
                result[dim_id] = values
    return result


def _parse_serieskeys_xml(content: bytes) -> dict[str, list[str]]:
    """Parse a serieskeysonly GenericData XML into {dim_id: [unique sorted values]}."""
    root, ns = xml_parse(content)
    generic_ns = ns.get("generic", "")

    series_tag = f"{{{generic_ns}}}Series" if generic_ns else "Series"
    serieskey_tag = f"{{{generic_ns}}}SeriesKey" if generic_ns else "SeriesKey"
    val_tag = f"{{{generic_ns}}}Value" if generic_ns else "Value"

    result: dict[str, set[str]] = {}
    for series in root.iter(series_tag):
        sk = series.find(serieskey_tag)
        if sk is None:
            continue
        for v in sk.findall(val_tag):
            dim_id = v.get("id")
            value = v.get("value")
            if dim_id and value:
                result.setdefault(dim_id, set()).add(value)

    return {k: sorted(vs) for k, vs in result.items()}


def _fallback_serieskeysonly(dataset: dict, provider: dict) -> dict[str, pl.DataFrame]:
    """Discover available codes via data?detail=serieskeysonly.

    Used when availableconstraint times out. Sends an all-wildcard data request
    with detail=serieskeysonly — the server returns series keys (no observations),
    which encode exactly which dimension value combinations exist.

    Fast on datasets with few dimensions (<6); may still time out on large
    territorial/census datasets (9+ dims).
    """
    from .base import sdmx_request
    from .db_cache import save_available_constraints

    df_id = dataset["df_id"]
    n_dims = len(dataset.get("dimensions", {}))
    key = "." * (n_dims - 1) if n_dims > 1 else ""
    path = f"data/{df_id}"
    if key:
        path = f"{path}/{key}"

    env_timeout = os.environ.get("OPENSDMX_AVAILCONSTRAINT_TIMEOUT")
    fallback_timeout = float(env_timeout) if env_timeout else float(
        provider.get("constraint_fallback_timeout", 30.0)
    )

    logger.info("constraints: trying serieskeysonly fallback for %s", df_id)
    try:
        resp = sdmx_request(
            path,
            accept="application/xml",
            _timeout=fallback_timeout,
            _max_retries=1,
            detail="serieskeysonly",
        )
    except httpx.TimeoutException as e:
        logger.warning(
            "serieskeysonly fallback timed out after %.1fs for %s",
            fallback_timeout, df_id,
        )
        raise ConstraintsTimeout(df_id, fallback_timeout) from e
    except Exception as e:
        logger.warning("serieskeysonly fallback failed for %s: %s", df_id, e)
        return {}

    result = _parse_serieskeys_xml(resp.content)
    if not result:
        return {}

    try:
        save_available_constraints(df_id, result)
    except Exception as ex:
        logger.warning("Could not cache serieskeysonly values: %s", ex)

    return {dim_id: pl.DataFrame({"id": codes}) for dim_id, codes in result.items()}


def _fallback_availableconstraint(dataset: dict, provider: dict) -> dict[str, pl.DataFrame]:
    """Query availableconstraint when contentconstraint returned 404.

    Builds the all-wildcard key from the dataset's dimension count and version.
    Caches results on success; raises ConstraintsTimeout if the endpoint is slow.
    """
    from .db_cache import save_available_constraints

    df_id = dataset["df_id"]
    agency_id = provider.get("agency_id", "")
    version = dataset.get("version") or "1.0"
    n_dims = len(dataset.get("dimensions", {}))
    # SDMX key: N values separated by N-1 dots; all-wildcard = (N-1) dots
    key = "." * (n_dims - 1) if n_dims > 1 else ""
    path = f"availableconstraint/{agency_id},{df_id},{version}/{key}"

    # Shorter timeout to fail fast on unresponsive backends.
    # Precedence: env var > provider config > default 30s.
    env_timeout = os.environ.get("OPENSDMX_AVAILCONSTRAINT_TIMEOUT")
    fallback_timeout: float = float(env_timeout) if env_timeout else float(
        provider.get("constraint_fallback_timeout", 30.0)
    )

    try:
        content = sdmx_request_xml(
            path,
            _timeout=fallback_timeout,
            _max_retries=1,
            mode="Available",
            references="none",
        )
    except httpx.TimeoutException as e:
        logger.warning(
            "availableconstraint fallback timed out after %.1fs for %s",
            fallback_timeout, df_id,
        )
        raise ConstraintsTimeout(df_id, fallback_timeout) from e
    except Exception as e:
        logger.warning("availableconstraint fallback also failed for %s: %s", df_id, e)
        return {}

    result = _parse_constraint_xml(content)

    try:
        save_available_constraints(df_id, result)
    except Exception as ex:
        logger.warning("Could not cache constraint values: %s", ex)

    return {dim_id: pl.DataFrame({"id": codes}) for dim_id, codes in result.items()}


def _parse_bulk_constraint_xml(content: bytes) -> dict[str, dict[str, list[str]]]:
    """Parse a bulk contentconstraint response into {short_df_id: {dim_id: [values]}}.

    Merges multiple constraints for the same dataflow by taking the union of values
    per dimension. TIME_PERIOD ranges (TimeRange elements) are silently ignored.
    The short df_id is extracted from the long form by splitting on '_DF_'.
    """
    root, ns = xml_parse(content)
    struct_ns = ns.get("structure", "")
    common_ns = ns.get("common", "")

    cc_tag = f"{{{struct_ns}}}ContentConstraint" if struct_ns else "ContentConstraint"
    kv_tag = f"{{{common_ns}}}KeyValue" if common_ns else "KeyValue"
    val_tag = f"{{{common_ns}}}Value" if common_ns else "Value"

    result: dict[str, dict[str, list[str]]] = {}
    for cc in root.iter(cc_tag):
        df_ref_path = (
            f".//{{{struct_ns}}}ConstraintAttachment/{{{struct_ns}}}Dataflow/Ref"
            if struct_ns else ".//Ref"
        )
        df_ref = cc.find(df_ref_path)
        if df_ref is None:
            continue
        long_id = df_ref.get("id", "")
        parts = long_id.split("_DF_")
        short_id = parts[0] if len(parts) > 1 else long_id
        if not short_id:
            continue

        merged = result.setdefault(short_id, {})
        for kv in cc.findall(f".//{kv_tag}"):
            dim_id = kv.get("id")
            if not dim_id:
                continue
            values = [v.text.strip() for v in kv.findall(val_tag) if v.text and v.text.strip()]
            if not values:
                continue
            if dim_id in merged:
                merged[dim_id] = list(dict.fromkeys(merged[dim_id] + values))
            else:
                merged[dim_id] = values

    return result


def _fetch_and_cache_bulk_constraints(agency_id: str) -> set[str]:
    """Fetch all contentconstraints in bulk for an agency, cache them, and return covered df_ids."""
    from .db_cache import save_available_constraints, save_bulk_constraint_index

    path = _struct_path(f"contentconstraint/{agency_id}")
    try:
        content = sdmx_request_xml(path)
    except Exception as e:
        logger.warning("Could not fetch bulk constraints for %s: %s", agency_id, e)
        save_bulk_constraint_index(agency_id, set())
        return set()

    parsed = _parse_bulk_constraint_xml(content)
    for short_df_id, dims in parsed.items():
        try:
            save_available_constraints(short_df_id, dims)
        except Exception as e:
            logger.warning("Could not cache constraints for %s: %s", short_df_id, e)

    covered = set(parsed.keys())
    try:
        save_bulk_constraint_index(agency_id, covered)
    except Exception as e:
        logger.warning("Could not save bulk constraint index: %s", e)
    return covered


def get_available_values(dataset: dict) -> dict[str, pl.DataFrame]:
    """Get all available values for all dimensions via constraint endpoint.

    Resolution order:
      1. SQLite cache (7 days)
      2. `.Stat Suite` hub, when configured (currently ISTAT) — per-dimension
         ground truth, typically sub-second per call, sidesteps the SDMX-REST
         `availableconstraint` timeout pattern on large datasets (still bounded
         by `hub_timeout`; on any failure falls through to step 3)
      3. Bulk contentconstraint catalog when `constraint_bulk_supported`
      4. Per-dataflow contentconstraint / availableconstraint
      5. `data?detail=serieskeysonly` fallback

    Steps 2+ are gated by provider config: providers without `hub_base_url`
    skip step 2; providers without `constraint_bulk_supported` skip step 3.
    Hub failures fall through transparently to the existing chain.
    """
    from .db_cache import get_cached_available_constraints, save_available_constraints

    df_id = dataset["df_id"]
    cached = get_cached_available_constraints(df_id)
    if cached is not None:
        return {dim_id: pl.DataFrame({"id": codes}) for dim_id, codes in cached.items()}

    provider = get_provider()

    # `.Stat Suite` hub fast path: opt-in via provider config (`hub_base_url`).
    # Skipped entirely for non-hub providers (Eurostat, OECD, ECB, ...). On any
    # hub failure, falls through to the existing SDMX REST chain unchanged.
    # Pass the patched provider explicitly so test patches on get_provider
    # control hub activation deterministically.
    from .hub import is_hub_enabled, get_available_values_via_hub
    if is_hub_enabled(provider):
        hub_result = get_available_values_via_hub(dataset)
        if hub_result:
            try:
                save_available_constraints(df_id, hub_result)
            except Exception as e:
                logger.warning("Could not cache hub-derived constraints: %s", e)
            return {dim_id: pl.DataFrame({"id": codes}) for dim_id, codes in hub_result.items()}

    constraint_endpoint = provider.get("constraint_endpoint", "availableconstraint")
    constraint_suffix = provider.get("constraint_path_suffix", "")

    # Bulk path: providers that expose a full constraint catalog in one call (e.g. ISTAT).
    # Avoids per-dataflow 404 roundtrips for the ~99% of dataflows with no contentconstraint.
    if provider.get("constraint_bulk_supported") and constraint_endpoint == "contentconstraint":
        from .db_cache import get_df_ids_with_content_constraint
        agency_id = provider.get("agency_id", "")
        covered = get_df_ids_with_content_constraint(agency_id)
        if covered is None:
            covered = _fetch_and_cache_bulk_constraints(agency_id)
        if df_id not in covered:
            try:
                return _fallback_availableconstraint(dataset, provider)
            except ConstraintsTimeout:
                logger.warning(
                    "availableconstraint timed out for %s — trying serieskeysonly", df_id
                )
                return _fallback_serieskeysonly(dataset, provider)
        # Data was just populated in available_constraints by the bulk fetch
        cached = get_cached_available_constraints(df_id)
        if cached is not None:
            return {dim_id: pl.DataFrame({"id": codes}) for dim_id, codes in cached.items()}
        # Edge case: covered by index but not in per-df cache — fall through to per-df call

    if constraint_endpoint == "contentconstraint":
        path = f"{constraint_endpoint}/{provider['agency_id']}/{df_id}"
    else:
        path = f"{constraint_endpoint}/{df_id}{constraint_suffix}"

    # Precedence: env var > provider config > module default (None → fallback in sdmx_request).
    env_timeout = os.environ.get("OPENSDMX_AVAILCONSTRAINT_TIMEOUT")
    if env_timeout:
        constraint_timeout = float(env_timeout)
    else:
        provider_timeout = provider.get("constraint_timeout")
        constraint_timeout = float(provider_timeout) if provider_timeout is not None else None
    constraint_max_retries = provider.get("constraint_max_retries")  # None → default 3 in sdmx_request

    try:
        constraint_params = provider.get("constraint_params", {"references": "none"})
        content = sdmx_request_xml(
            path,
            _timeout=constraint_timeout,
            _max_retries=constraint_max_retries,
            **constraint_params,
        )
        result = _parse_constraint_xml(content)
    except httpx.TimeoutException:
        provider_name = provider.get("name", "unknown")
        # If no override was set, the module default applied — surface that to the user.
        from .base import _timeout as _module_timeout
        effective_timeout = constraint_timeout if constraint_timeout is not None else _module_timeout
        logger.warning(
            "availableconstraint timed out after %.1fs for %s on provider %s",
            effective_timeout, df_id, provider_name,
        )
        logger.warning(
            "availableconstraint timed out for %s — trying serieskeysonly", df_id
        )
        return _fallback_serieskeysonly(dataset, provider)
    except Exception as e:
        if isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 500:
            raise ConstraintsUnavailable(df_id) from e
        if (
            constraint_endpoint == "contentconstraint"
            and isinstance(e, httpx.HTTPStatusError)
            and e.response.status_code == 404
        ):
            logger.warning(
                "contentconstraint returned 404 for %s — falling back to availableconstraint",
                df_id,
            )
            try:
                return _fallback_availableconstraint(dataset, provider)
            except ConstraintsTimeout:
                logger.warning(
                    "availableconstraint timed out for %s — trying serieskeysonly", df_id
                )
                return _fallback_serieskeysonly(dataset, provider)
        logger.warning("Could not retrieve available values: %s", e)
        return {}

    try:
        save_available_constraints(df_id, result)
    except Exception as e:
        logger.warning("Could not cache constraint values: %s", e)

    return {dim_id: pl.DataFrame({"id": codes}) for dim_id, codes in result.items()}


def set_filters(dataset: dict, **kwargs) -> dict:
    """Set dimension filters (case-insensitive). Returns a new dataset dict."""
    import copy
    dataset = copy.deepcopy(dataset)
    dim_upper = {k.upper(): k for k in dataset["dimensions"]}

    for key, value in kwargs.items():
        actual = dim_upper.get(key.upper())
        if actual is None:
            logger.warning("Dimension '%s' not found. Ignoring.", key)
            continue
        dataset["filters"][actual] = value

    return dataset


def reset_filters(dataset: dict) -> dict:
    """Reset all filters to '.' (all values). Returns a new dataset dict."""
    import copy
    dataset = copy.deepcopy(dataset)
    for key in dataset["filters"]:
        dataset["filters"][key] = "."
    return dataset
