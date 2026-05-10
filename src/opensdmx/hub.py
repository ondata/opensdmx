"""Optional .Stat Suite hub integration (ISTAT-style providers).

Some SDMX providers — currently ISTAT — expose a `.Stat Suite` hub API alongside
the official SDMX 2.1 REST endpoint. The hub serves the same data through faster,
more focused endpoints (single-dimension value lookups, JSON catalog) and is the
backend behind the public databrowser UI.

This module is opt-in per provider via `portals.json`:

    "hub_base_url":     "https://esploradati.istat.it/databrowserhub/api/core"
    "hub_node_id":      "1"
    "hub_dataset_agency": "IT1"        # optional; defaults to provider agency_id
    "hub_timeout":      15.0           # optional; defaults to 15s

Providers without `hub_base_url` are unaffected by this module.

All hub calls degrade gracefully: any HTTP/parse error returns an empty result so
the caller falls through to the standard SDMX REST chain. The hub is an optimization,
never a hard requirement.

Reference: docs/istat/hub-api.md
"""

from __future__ import annotations

import json
import logging
import os

import httpx

from .base import get_provider

logger = logging.getLogger(__name__)


def is_hub_enabled(provider: dict | None = None) -> bool:
    """True when the active provider exposes a `.Stat Suite` hub.

    Pass an explicit `provider` dict to make the check independent of the
    module-level provider state (useful in tests where the caller already
    holds a patched provider dict). When omitted, reads the active provider.

    Honors `OPENSDMX_DISABLE_HUB=1` for emergency opt-out without code changes.
    """
    if os.environ.get("OPENSDMX_DISABLE_HUB"):
        return False
    p = provider if provider is not None else get_provider()
    return bool(p.get("hub_base_url"))


def _hub_node_url() -> str:
    """Return the per-node hub root: `{hub_base_url}/nodes/{hub_node_id}`."""
    p = get_provider()
    base = p["hub_base_url"].rstrip("/")
    node = str(p.get("hub_node_id", "1"))
    return f"{base}/nodes/{node}"


def _dataset_identifier(df_id: str, version: str | None) -> str:
    """Build the hub dataset identifier `{agency},{df_id},{version}`.

    Uses `hub_dataset_agency` from provider config, falling back to `agency_id`.
    Version defaults to `1.0` when missing.
    """
    p = get_provider()
    agency = p.get("hub_dataset_agency") or p["agency_id"]
    v = version or "1.0"
    return f"{agency},{df_id},{v}"


def _hub_get_json(path: str, timeout: float) -> dict | None:
    """GET a hub path and return parsed JSON, or `None` on any error.

    Errors are logged at WARNING and never propagate — callers must fall through
    to the existing SDMX REST chain whenever this returns None.
    """
    url = f"{_hub_node_url()}/{path.lstrip('/')}"
    p = get_provider()
    user_agent = (
        os.environ.get("OPENSDMX_USER_AGENT")
        or p.get("user_agent")
        or "opensdmx Python package"
    )
    headers = {
        "Accept": "application/json",
        "userlang": p.get("language", "en"),
        "User-Agent": user_agent,
    }
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.json()
    except (httpx.HTTPError, json.JSONDecodeError, ValueError) as e:
        logger.warning("hub request failed for %s: %s", path, e)
        return None


def get_dimension_values_via_hub(
    df_id: str,
    dim_id: str,
    version: str | None = None,
    *,
    timeout: float | None = None,
) -> list[str]:
    """Return the code IDs available for `dim_id` in `df_id`, via hub.

    Returns `[]` on any error, including when the active provider has no
    `hub_base_url` configured — the module's "fails gracefully" contract holds
    even if callers invoke this function without first checking
    `is_hub_enabled()`. The hub returns ground-truth values present in the
    dataset (not the codelist superset).
    """
    p = get_provider()
    if not p.get("hub_base_url"):
        return []
    effective_timeout = float(timeout if timeout is not None else p.get("hub_timeout", 15.0))
    ds_id = _dataset_identifier(df_id, version)
    path = f"datasets/{ds_id}/column/{dim_id}/partial/values"
    payload = _hub_get_json(path, effective_timeout)
    if not payload:
        return []
    try:
        criteria = payload["criteria"][0]
        return [v["id"] for v in criteria.get("values", []) if v.get("id")]
    except (KeyError, IndexError, TypeError) as e:
        logger.warning(
            "hub returned unexpected JSON shape for %s/%s: %s", df_id, dim_id, e
        )
        return []


def get_available_values_via_hub(dataset: dict) -> dict[str, list[str]]:
    """Return `{dim_id: [codes]}` for every codelist dimension via hub.

    Iterates the dataset's dimensions sequentially. Returns `{}` on any
    failure — including when the active provider has no `hub_base_url`
    configured — so callers fall through to the SDMX-REST chain. Partial
    results would mislead the caller into skipping the fallback, so any
    dimension miss aborts the whole hub attempt. TIME_PERIOD is excluded
    (it is a `TimeDimension` in the DSD and is normally not in
    `dataset["dimensions"]`, but we filter defensively).
    """
    if not get_provider().get("hub_base_url"):
        return {}
    df_id = dataset["df_id"]
    version = dataset.get("version")
    dim_ids = [d for d in dataset.get("dimensions", {}) if d.upper() != "TIME_PERIOD"]
    if not dim_ids:
        return {}

    result: dict[str, list[str]] = {}
    for dim_id in dim_ids:
        codes = get_dimension_values_via_hub(df_id, dim_id, version=version)
        if not codes:
            logger.warning(
                "hub returned no values for dimension %s of %s — aborting hub discovery",
                dim_id,
                df_id,
            )
            return {}
        result[dim_id] = codes
    return result
