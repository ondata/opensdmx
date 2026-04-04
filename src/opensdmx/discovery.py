"""Functions for discovering and exploring SDMX datasets."""

from __future__ import annotations


class ConstraintsUnavailable(Exception):
    """Raised when the availableconstraint endpoint returns 500 (hidden/not-yet-public dataflow)."""

import time
import warnings

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


def search_dataset(keyword: str) -> pl.DataFrame:
    """Search datasets by keyword (case-insensitive) in their description."""
    datasets = all_available()
    results = datasets.filter(
        pl.col("df_description").str.to_lowercase().str.contains(keyword.lower())
    )
    if results.is_empty():
        warnings.warn(f"No datasets found matching keyword: {keyword}", stacklevel=2)
    return results


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

        # Codelist reference
        local_rep = dim_node.find(f".//{{{struct_ns}}}LocalRepresentation//Ref") if struct_ns else None
        codelist_id = local_rep.get("id") if local_rep is not None else None

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
    save_dims(structure_id, result)
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
    except Exception:
        description = None
    save_codelist_info(codelist_id, description)
    return description


def load_dataset(dataflow_identifier: str) -> dict:
    """Create a dataset object for a given dataflow ID, structure ID, or description.

    Returns a dict with keys:
        df_id, version, df_description, df_structure_id, dimensions, filters
    """
    all_ds = all_available()

    match_row = None

    # Try df_id exact match
    rows = all_ds.filter(pl.col("df_id") == dataflow_identifier)
    if not rows.is_empty():
        match_row = rows.row(0, named=True)

    # Try structure_id match
    if match_row is None:
        rows = all_ds.filter(pl.col("df_structure_id") == dataflow_identifier)
        if not rows.is_empty():
            match_row = rows.row(0, named=True)

    # Try description match
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
        warnings.warn(f"No codelist found for dimension: {dimension_id}", stacklevel=2)
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

    save_codelist_values(codelist_id, records)
    return pl.DataFrame(records, schema={"id": pl.Utf8, "name": pl.Utf8})


def get_available_values(dataset: dict) -> dict[str, pl.DataFrame]:
    """Get all available values for all dimensions via availableconstraint endpoint.

    Results are cached in SQLite for 7 days.
    """
    from .db_cache import get_cached_available_constraints, save_available_constraints

    df_id = dataset["df_id"]
    cached = get_cached_available_constraints(df_id)
    if cached is not None:
        return {dim_id: pl.DataFrame({"id": codes}) for dim_id, codes in cached.items()}

    provider = get_provider()
    constraint_endpoint = provider.get("constraint_endpoint", "availableconstraint")
    if constraint_endpoint == "contentconstraint":
        path = f"{constraint_endpoint}/{provider['agency_id']}/{df_id}"
    else:
        path = f"{constraint_endpoint}/{df_id}"
    try:
        constraint_params = provider.get("constraint_params", {"references": "none"})
        content = sdmx_request_xml(path, **constraint_params)
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

        save_available_constraints(df_id, result)
        return {dim_id: pl.DataFrame({"id": codes}) for dim_id, codes in result.items()}

    except Exception as e:
        import httpx
        if isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 500:
            raise ConstraintsUnavailable(df_id) from e
        warnings.warn(f"Could not retrieve available values: {e}", stacklevel=2)
        return {}


def set_filters(dataset: dict, **kwargs) -> dict:
    """Set dimension filters (case-insensitive). Returns a new dataset dict."""
    import copy
    dataset = copy.deepcopy(dataset)
    dim_upper = {k.upper(): k for k in dataset["dimensions"]}

    for key, value in kwargs.items():
        actual = dim_upper.get(key.upper())
        if actual is None:
            warnings.warn(f"Dimension '{key}' not found. Ignoring.", stacklevel=2)
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
