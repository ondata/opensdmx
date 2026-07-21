"""Functions for retrieving data from SDMX datasets."""

from __future__ import annotations

import logging
import re
from typing import Any

import polars as pl

from .base import get_provider, sdmx_request_csv
from .discovery import load_dataset, set_filters
from .utils import make_url_key


def parse_time_period(series: pl.Series) -> pl.Series:
    """Convert SDMX time period strings to Python date objects.

    Handles: YYYY, YYYY-MM, YYYY-Qn, YYYY-Sn, YYYY-Wnn, YYYY-MM-DD
    """
    def _parse_one(tp: str | None) -> str | None:
        if tp is None:
            return None
        tp = str(tp).strip()

        # Annual: YYYY
        if re.fullmatch(r"\d{4}", tp):
            return f"{tp}-01-01"

        # Monthly: YYYY-MM
        if re.fullmatch(r"\d{4}-\d{2}", tp):
            return f"{tp}-01"

        # Quarterly: YYYY-Q1..Q4
        m = re.fullmatch(r"(\d{4})-Q([1-4])", tp)
        if m:
            year, q = m.group(1), int(m.group(2))
            month = (q - 1) * 3 + 1
            return f"{year}-{month:02d}-01"

        # Semester: YYYY-S1, YYYY-S2
        m = re.fullmatch(r"(\d{4})-S([1-2])", tp)
        if m:
            year, s = m.group(1), int(m.group(2))
            month = (s - 1) * 6 + 1
            return f"{year}-{month:02d}-01"

        # Weekly: YYYY-W01..W53
        m = re.fullmatch(r"(\d{4})-W(\d{2})", tp)
        if m:
            year, week = int(m.group(1)), int(m.group(2))
            from datetime import date, timedelta
            d = date(year, 1, 1) + timedelta(weeks=week - 1)
            return d.isoformat()

        # Daily: YYYY-MM-DD (pass through)
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", tp):
            return tp

        return None

    parsed = series.map_elements(_parse_one, return_dtype=pl.Utf8)
    return parsed.str.to_date(format="%Y-%m-%d", strict=False)


def get_data(
    dataset: dict[str, Any],
    start_period: str | None = None,
    end_period: str | None = None,
    last_n_observations: int | None = None,
    first_n_observations: int | None = None,
) -> pl.DataFrame:
    """Retrieve data from a dataset using the current filters.

    Args:
        dataset: dict returned by load_dataset()
        start_period: optional start date (YYYY-MM-DD or YYYY)
        end_period: optional end date (YYYY-MM-DD or YYYY)
        last_n_observations: optional, return only last N observations per series
        first_n_observations: optional, return only first N observations per series

    Returns:
        Polars DataFrame sorted by TIME_PERIOD ascending
    """
    provider = get_provider()
    hub_only = provider.get("hub_only", False)
    empty_key = provider.get("data_key_format", "dots") == "empty"

    if hub_only:
        # Hub-only providers (INPS) have no SDMX-REST data endpoint: download the
        # full dataflow via the middleware and filter client-side below.
        if last_n_observations is not None or first_n_observations is not None:
            logging.getLogger(__name__).warning(
                "Provider does not support first_n/last_n observations "
                "(hub-only full download); ignoring these arguments."
            )
        from . import inps
        data: pl.DataFrame = inps.get_data(dataset)
    else:
        path = f"data/{dataset['df_id']}"
        if not empty_key:
            url_key = make_url_key(dataset["filters"])
            if url_key:
                path = f"{path}/{url_key}"

        params: dict[str, str | int] = {}
        if start_period:
            params["startPeriod"] = start_period
        if end_period:
            params["endPeriod"] = end_period
        if last_n_observations is not None:
            params["lastNObservations"] = last_n_observations
        if first_n_observations is not None:
            params["firstNObservations"] = first_n_observations

        data = sdmx_request_csv(path, **params)

    # Client-side dimension filter for providers that download unfiltered:
    # empty-key (Derzhstat) and hub-only (INPS).
    if hub_only or empty_key:
        for col, val in dataset.get("filters", {}).items():
            if not val or val == "." or col not in data.columns:
                continue
            allowed = val.split("+") if isinstance(val, str) else [str(v) for v in val]
            data = data.filter(pl.col(col).is_in(allowed))

    # Hub-only downloads are full: apply the period window client-side (by year),
    # since the middleware ignores startPeriod/endPeriod. INPS keeps intra-annual
    # granularity in a dimension (e.g. MESE), never in TIME_PERIOD — which is
    # always the year (YYYY) — so a year comparison is correct here; a full-date
    # compare would wrongly drop annual rows on a sub-annual start/end.
    if hub_only and "TIME_PERIOD" in data.columns:
        if start_period:
            data = data.filter(pl.col("TIME_PERIOD").str.slice(0, 4) >= str(start_period)[:4])
        if end_period:
            data = data.filter(pl.col("TIME_PERIOD").str.slice(0, 4) <= str(end_period)[:4])

    if "TIME_PERIOD" in data.columns:
        data = data.with_columns(
            parse_time_period(data["TIME_PERIOD"]).alias("TIME_PERIOD")
        ).sort("TIME_PERIOD")

    return data


def enrich_with_labels(dataset: dict[str, Any], data: pl.DataFrame) -> pl.DataFrame:
    """Append human-readable label columns for each dimension in the data.

    For every dimension whose column appears in ``data`` (matched
    case-insensitively) and that has a codelist, adds a sibling
    ``<col>_label`` column with the code's name resolved from the codelist
    cache, in the provider's language. Original code columns are preserved and
    row order is unchanged. Dimensions without a codelist add no column; codes
    with no matching label get a null label.

    Args:
        dataset: dict returned by load_dataset()
        data: DataFrame returned by get_data()

    Returns:
        Polars DataFrame with added ``<col>_label`` columns.
    """
    from .discovery import get_dimension_values

    if data.is_empty():
        return data

    col_by_upper = {c.upper(): c for c in data.columns}
    for dim_id, info in (dataset.get("dimensions") or {}).items():
        col = col_by_upper.get(dim_id.upper())
        if col is None or not (info or {}).get("codelist_id"):
            continue
        values = get_dimension_values(dataset, dim_id)
        if values.is_empty():
            continue
        mapping = dict(zip(values["id"], values["name"]))
        data = data.with_columns(
            pl.col(col).replace_strict(mapping, default=None).alias(f"{col}_label")
        )
    return data


def run_query(query_file: str, provider: str | None = None) -> pl.DataFrame:
    """Run a query from a YAML file saved with `opensdmx get --query-file`.

    Provider resolution, highest precedence first: the `provider` argument, the
    file's `provider` alias, its `provider_url`, then the `OPENSDMX_PROVIDER`
    environment variable. If none apply the active provider is left untouched.

    Args:
        query_file: path to the YAML query file
        provider:   override the provider named in the file

    Returns:
        Polars DataFrame
    """
    import yaml
    from pathlib import Path
    from .base import PROVIDER_ALIASES, PROVIDERS, resolve_provider, set_provider, set_provider_from_env

    path = Path(query_file)
    if not path.exists():
        raise FileNotFoundError(f"Query file not found: {path}")

    with open(path) as fh:
        q = yaml.safe_load(fh)

    alias = q.get("provider")
    if provider:
        # agency_id falls back to OPENSDMX_AGENCY inside resolve_provider, so a
        # custom --provider URL keeps the agency the CLI already resolved.
        resolve_provider(provider, agency_id=q.get("agency_id") or None)
    elif alias and PROVIDER_ALIASES.get(alias, alias) in PROVIDERS:
        set_provider(PROVIDER_ALIASES[alias] if alias in PROVIDER_ALIASES else alias)
    elif q.get("provider_url"):
        set_provider(q["provider_url"], agency_id=q.get("agency_id") or None)
    else:
        set_provider_from_env()

    dataset_id = q.get("dataset")
    if not dataset_id:
        raise ValueError("'dataset' field missing in query file")

    filters = {dim: info["value"] for dim, info in (q.get("filters") or {}).items()}

    ds = load_dataset(dataset_id)
    if filters:
        ds = set_filters(ds, **filters)

    data = get_data(
        ds,
        start_period=q.get("start_period"),
        end_period=q.get("end_period"),
        last_n_observations=q.get("last_n"),
        first_n_observations=q.get("first_n"),
    )
    if q.get("labels"):
        data = enrich_with_labels(ds, data)
    return data


def fetch(
    dataflow_id: str,
    start_period: str | None = None,
    end_period: str | None = None,
    last_n_observations: int | None = None,
    first_n_observations: int | None = None,
    **filters: Any,
) -> pl.DataFrame:
    """Quick one-call retrieval: loads dataset, sets filters, fetches data.

    Args:
        dataflow_id: Dataflow ID (e.g. "une_rt_m" for Eurostat, "139_176" for ISTAT)
        start_period: optional start date
        end_period: optional end date
        last_n_observations: optional, return only last N observations per series
        first_n_observations: optional, return only first N observations per series
        **filters: dimension filters (e.g. FREQ="M", geo="IT")

    Returns:
        Polars DataFrame
    """
    ds = load_dataset(dataflow_id)
    if filters:
        ds = set_filters(ds, **filters)
    return get_data(ds, start_period=start_period, end_period=end_period,
                    last_n_observations=last_n_observations,
                    first_n_observations=first_n_observations)
