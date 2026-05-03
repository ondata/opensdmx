"""Functions for retrieving data from SDMX datasets."""

from __future__ import annotations

import re

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
    dataset: dict,
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
    path = f"data/{dataset['df_id']}"
    if get_provider().get("data_key_format", "dots") != "empty":
        url_key = make_url_key(dataset["filters"])
        if url_key:
            path = f"{path}/{url_key}"

    params = {}
    if start_period:
        params["startPeriod"] = start_period
    if end_period:
        params["endPeriod"] = end_period
    if last_n_observations is not None:
        params["lastNObservations"] = last_n_observations
    if first_n_observations is not None:
        params["firstNObservations"] = first_n_observations

    data = sdmx_request_csv(path, **params)

    if get_provider().get("data_key_format", "dots") == "empty":
        for col, val in dataset.get("filters", {}).items():
            if not val or val == "." or col not in data.columns:
                continue
            allowed = val.split("+") if isinstance(val, str) else [str(v) for v in val]
            data = data.filter(pl.col(col).is_in(allowed))

    if "TIME_PERIOD" in data.columns:
        data = data.with_columns(
            parse_time_period(data["TIME_PERIOD"]).alias("TIME_PERIOD")
        ).sort("TIME_PERIOD")

    return data


def run_query(query_file: str) -> pl.DataFrame:
    """Run a query from a YAML file saved with `opensdmx get --query-file`.

    Args:
        query_file: path to the YAML query file

    Returns:
        Polars DataFrame
    """
    import yaml
    from pathlib import Path
    from .base import PROVIDERS, set_provider

    path = Path(query_file)
    if not path.exists():
        raise FileNotFoundError(f"Query file not found: {path}")

    with open(path) as fh:
        q = yaml.safe_load(fh)

    alias = q.get("provider")
    if alias and alias in PROVIDERS:
        set_provider(alias)
    elif q.get("provider_url"):
        set_provider(q["provider_url"], agency_id=q.get("agency_id") or None)

    dataset_id = q.get("dataset")
    if not dataset_id:
        raise ValueError("'dataset' field missing in query file")

    filters = {dim: info["value"] for dim, info in (q.get("filters") or {}).items()}

    ds = load_dataset(dataset_id)
    if filters:
        ds = set_filters(ds, **filters)

    return get_data(
        ds,
        start_period=q.get("start_period"),
        end_period=q.get("end_period"),
        last_n_observations=q.get("last_n"),
        first_n_observations=q.get("first_n"),
    )


def fetch(
    dataflow_id: str,
    start_period: str | None = None,
    end_period: str | None = None,
    last_n_observations: int | None = None,
    first_n_observations: int | None = None,
    **filters,
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
