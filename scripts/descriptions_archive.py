#!/usr/bin/env python3
"""Harvest authentic dataflow descriptions from a provider's reference-metadata API.

Many providers expose, per dataflow, a metadata-link annotation pointing at a
reference-metadata service that carries the human-written description shown in
their web data browser — text that never appears in the SDMX structure itself.
ISTAT is the first such provider: 81% of its dataflows carry a `METADATA_URL`
annotation resolving, via the `METADATA_API`, to prose in a `DATA_SOURCE` field.

This script reads that annotation for every dataflow (one catalog call),
de-duplicates by the shared report id (ISTAT: 3,974 dataflows -> 635 reports,
6.3x), fetches each unique report once from the metadata API, and writes the
per-dataflow description to a version-controlled resource under data/descriptions/.
The committed file is the persistent state, so the run is resumable and
opensdmx consumes it offline at embedding time.

The metadata API is a service distinct from the rate-limited SDMX data endpoint,
so the harvest is not bound by the SDMX throttle; a courtesy pause is kept anyway.

Files per provider:
    data/descriptions/{provider}.parquet   df_id, description, report_id,
                                           metadata_set_id, harvested_at

Usage:
    uv run python scripts/descriptions_archive.py --provider istat
    uv run python scripts/descriptions_archive.py --provider istat --stats

Exit codes: 0 success, 1 fatal error (catalog fetch failed, provider without a
metadata channel, unknown provider).
"""

from __future__ import annotations

import argparse
import html
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import polars as pl

import opensdmx
from opensdmx.base import get_provider, set_provider
from opensdmx.discovery import _local_tag, _struct_path
from opensdmx.utils import xml_parse

# The resource lives INSIDE the package so it is bundled in the wheel and read
# by opensdmx when pip-installed, not only from an editable checkout (portals.json
# ships the same way). uv_build includes non-.py files under src/opensdmx/.
DATA_DIR = Path(__file__).resolve().parents[1] / "src" / "opensdmx" / "data" / "descriptions"

RESOURCE_COLUMNS = {
    "df_id": pl.Utf8,
    "description": pl.Utf8,
    "report_id": pl.Utf8,
    "metadata_set_id": pl.Utf8,
    "siqual_id": pl.Utf8,  # id of the linked quality-system page (ISTAT SIQual), if any
    "harvested_at": pl.Utf8,  # ISO date
}

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_LINK_ID_RE = re.compile(r"[?&]id=(\w+)")


def parquet_path(provider: str) -> Path:
    return DATA_DIR / f"{provider}.parquet"


def clean_prose(raw: str | None) -> str:
    """Unescape HTML entities and strip markup, collapsing whitespace to plain text."""
    text = html.unescape(raw or "")
    text = _TAG_RE.sub(" ", text)
    return _WS_RE.sub(" ", text).strip()


def _annotation_text(df_node, ann_type: str, language: str) -> str | None:
    """Return the AnnotationText of the annotation whose AnnotationType matches.

    Mirrors discovery._keyword_annotation: namespace-agnostic, prefers the
    provider language, falls back to English, then the first available.
    """
    for child in df_node:
        if _local_tag(child) != "Annotations":
            continue
        for ann in child:
            if _local_tag(ann) != "Annotation":
                continue
            if not any(
                _local_tag(s) == "AnnotationType" and (s.text or "").strip() == ann_type
                for s in ann
            ):
                continue
            texts: dict[str, str] = {}
            for s in ann:
                if _local_tag(s) == "AnnotationText" and s.text and s.text.strip():
                    lang = s.get("{http://www.w3.org/XML/1998/namespace}lang", "")
                    texts[lang] = s.text.strip()
            if not texts:
                return None
            return texts.get(language) or texts.get("en") or next(iter(texts.values()))
    return None


def collect_metadata_links(provider_cfg: dict, agency: str, language: str) -> dict[str, dict]:
    """One catalog call -> {df_id: {report_id, metadata_set_id, base_url}} for linked dataflows."""
    ann = provider_cfg["metadata_annotation"]
    content = opensdmx.base.sdmx_request_xml(_struct_path(f"dataflow/{agency}"))
    root, ns = xml_parse(content)

    links: dict[str, dict] = {}
    for df in root.iter("{" + ns.get("structure", "") + "}Dataflow"):
        df_id = df.get("id") or ""
        url = _annotation_text(df, ann, language)
        if not url:
            continue
        q = parse_qs(urlparse(url).query)
        report_id = q.get("reportId", [None])[0]
        set_id = q.get("metadataSetId", [None])[0]
        base = q.get("BaseUrlMDA", [None])[0]
        if not (report_id and set_id and base):
            continue
        links[df_id] = {"report_id": report_id, "metadata_set_id": set_id, "base_url": base}
    return links


def _find_attribute(payload: dict, attr_id: str, language: str = "en") -> str | None:
    """Return the raw text of a reported attribute by id, walking nested sets.

    Walks nested reportedAttributes across every metadataSet/report. When the
    attribute carries per-language ``texts``, prefer the provider ``language``
    (en fallback, then the first available). Pure function, unit-tested offline.
    """

    def walk_attrs(attrs):
        for a in attrs:
            if a.get("id") == attr_id:
                texts = a.get("texts") or {}
                txt = a.get("text") or texts.get(language) or texts.get("en") or next(iter(texts.values()), None)
                if txt:
                    return txt
            found = walk_attrs(a.get("attributeSet", {}).get("reportedAttributes", []))
            if found:
                return found
        return None

    for ms in payload.get("data", {}).get("metadataSets", []):
        for rep in ms.get("reports", []):
            raw = walk_attrs(rep.get("attributeSet", {}).get("reportedAttributes", []))
            if raw:
                return raw
    return None


def extract_description(payload: dict, attr_id: str, language: str = "en") -> str | None:
    """Return the cleaned description prose (ISTAT: DATA_SOURCE), or None."""
    raw = _find_attribute(payload, attr_id, language)
    return clean_prose(raw) if raw else None


def extract_link_id(payload: dict, link_attr: str, language: str = "en") -> str | None:
    """Return the ``id=`` value from a link attribute (ISTAT: DATA_SOURCE_LINK), or None.

    The link points at the provider's quality system (ISTAT SIQual,
    ``visualizza.do?id=0019100``); the id is the same for the survey's SIQual
    detail and disaggregation pages.
    """
    raw = _find_attribute(payload, link_attr, language)
    if not raw:
        return None
    m = _LINK_ID_RE.search(raw)
    return m.group(1) if m else None


def fetch_report(
    client: httpx.Client, base_url: str, api_path: str, set_id: str, report_id: str,
    attr_id: str, link_attr: str | None, language: str = "en"
) -> tuple[str | None, str | None]:
    """Fetch one report's metadata once; return (cleaned description, siqual_id)."""
    resp = client.get(
        base_url.rstrip("/") + api_path,
        params={"metadataSetId": set_id, "reportId": report_id},
        timeout=30,
        follow_redirects=True,
    )
    resp.raise_for_status()
    payload = resp.json()
    desc = extract_description(payload, attr_id, language)
    siqual_id = extract_link_id(payload, link_attr, language) if link_attr else None
    return desc, siqual_id


def load_existing(provider: str) -> pl.DataFrame:
    path = parquet_path(provider)
    if path.exists():
        return pl.read_parquet(path)
    return pl.DataFrame(schema=RESOURCE_COLUMNS)


def print_stats(provider: str) -> None:
    df = load_existing(provider)
    if df.is_empty():
        print(f"{provider}: no description resource yet.")
        return
    reports = df["report_id"].n_unique()
    print(f"{provider}: {df.height} dataflows described, {reports} unique reports "
          f"({parquet_path(provider)})")


def run(provider: str, pause: float) -> int:
    set_provider(provider)
    cfg = get_provider()
    if not cfg.get("metadata_annotation"):
        print(f"Provider '{provider}' declares no metadata channel "
              f"(missing 'metadata_annotation' in portals.json).", file=sys.stderr)
        return 1

    agency = cfg["agency_id"]
    language = cfg.get("language", "en")
    api_path = cfg.get("metadata_api_path", "/api/getMetadata")
    attr_id = cfg.get("metadata_description_attribute", "DATA_SOURCE")
    link_attr = cfg.get("metadata_link_attribute")

    print(f"Collecting {cfg['metadata_annotation']} links from the {provider} catalog...")
    links = collect_metadata_links(cfg, agency, language)
    total_linked = len(links)
    if not total_linked:
        print("No dataflows carry the metadata annotation. Nothing to harvest.")
        return 0

    # Resume: keep descriptions (and siqual_id) for reports already harvested,
    # re-fetch the rest. Tolerates an older resource without the siqual_id column.
    existing = load_existing(provider)
    known: dict[str, tuple[str, str | None]] = {}
    if not existing.is_empty():
        has_siqual = "siqual_id" in existing.columns
        cols = ["report_id", "description"] + (["siqual_id"] if has_siqual else [])
        for row in existing.select(cols).unique(subset=["report_id"]).iter_rows(named=True):
            known[row["report_id"]] = (row["description"], row.get("siqual_id"))

    unique_reports = {v["report_id"]: v for v in links.values()}
    to_fetch = [r for r in unique_reports if r not in known]
    print(f"{total_linked} linked dataflows -> {len(unique_reports)} unique reports "
          f"({len(known)} cached, {len(to_fetch)} to fetch).")

    report_text = {rid: v[0] for rid, v in known.items()}
    report_siqual = {rid: v[1] for rid, v in known.items() if v[1]}
    with httpx.Client(headers={"User-Agent": "opensdmx-descriptions-archive"}) as client:
        for i, report_id in enumerate(to_fetch, 1):
            meta = unique_reports[report_id]
            try:
                text, siqual_id = fetch_report(
                    client, meta["base_url"], api_path, meta["metadata_set_id"], report_id,
                    attr_id, link_attr, language
                )
            except Exception as e:  # noqa: BLE001 - log and continue, resumable next run
                print(f"  ! {report_id}: {type(e).__name__}: {e}", file=sys.stderr)
                text, siqual_id = None, None
            if text:
                report_text[report_id] = text
            if siqual_id:
                report_siqual[report_id] = siqual_id
            if i % 50 == 0:
                print(f"  ...{i}/{len(to_fetch)} reports fetched")
            time.sleep(pause)

    harvested_at = datetime.now(timezone.utc).date().isoformat()
    rows = []
    for df_id, meta in links.items():
        text = report_text.get(meta["report_id"])
        if not text:
            continue
        rows.append({
            "df_id": df_id,
            "description": text,
            "report_id": meta["report_id"],
            "metadata_set_id": meta["metadata_set_id"],
            "siqual_id": report_siqual.get(meta["report_id"]),
            "harvested_at": harvested_at,
        })

    result = pl.DataFrame(rows, schema=RESOURCE_COLUMNS).sort("df_id")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    result.write_parquet(parquet_path(provider))

    covered = result.height
    uncovered = total_linked - covered
    with_siqual = result.filter(pl.col("siqual_id").is_not_null()).height if covered else 0
    print(f"Wrote {parquet_path(provider)}: {covered} dataflows described "
          f"from {result['report_id'].n_unique()} reports "
          f"({with_siqual} with a siqual_id); "
          f"{uncovered} linked dataflows without text this run.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--provider", required=True, help="opensdmx provider id (istat, ...)")
    parser.add_argument("--pause", type=float, default=0.2,
                        help="courtesy pause between metadata requests, seconds (default: 0.2)")
    parser.add_argument("--stats", action="store_true", help="print resource stats and exit")
    args = parser.parse_args()

    if args.stats:
        print_stats(args.provider)
        return 0
    try:
        return run(args.provider, args.pause)
    except Exception as e:  # noqa: BLE001
        print(f"Fatal: {type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
