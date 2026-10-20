"""Tests for the explanatory-metadata link `info` surfaces for a dataflow.

Eurostat publishes the ESMS report as an ``ESMS_HTML`` annotation, but only at
``detail=full``: the catalogue is fetched at ``detail=allstubs``, which strips
annotations. These tests pin the extra single-dataflow request, the annotation
lookup, the provider declaration that enables it (so a provider whose catalogue
already carries annotations is not charged for a second request), and both
output shapes.
"""

from __future__ import annotations

import json
import re

import httpx
import polars as pl
import portalocker.exceptions
import pytest
from typer.testing import CliRunner

import opensdmx
import opensdmx.base
from opensdmx import discovery
from opensdmx.base import PROVIDERS
from opensdmx.cli import app

runner = CliRunner()

METADATA_URL = "https://ec.europa.eu/eurostat/cache/metadata/en/tour_occ_esms.htm"

DATAFLOW_XML = b"""\
<message:Structure xmlns:message="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message"
                   xmlns:structure="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure"
                   xmlns:common="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common">
  <message:Structures>
    <structure:Dataflows>
      <structure:Dataflow id="TOUR_OCC_ARM" agencyID="ESTAT" version="1.0">
        <common:Annotations>
          <common:Annotation>
            <common:AnnotationTitle>DATASET</common:AnnotationTitle>
            <common:AnnotationType>DISSEMINATION_OBJECT_TYPE</common:AnnotationType>
          </common:Annotation>
          <common:Annotation>
            <common:AnnotationTitle>Explanatory texts (metadata)</common:AnnotationTitle>
            <common:AnnotationType>ESMS_HTML</common:AnnotationType>
            <common:AnnotationURL>https://ec.europa.eu/eurostat/cache/metadata/en/tour_occ_esms.htm</common:AnnotationURL>
          </common:Annotation>
        </common:Annotations>
      </structure:Dataflow>
    </structure:Dataflows>
  </message:Structures>
</message:Structure>
"""

# Same dataflow without the ESMS annotations: the other annotation type must not
# be mistaken for the metadata link.
DATAFLOW_XML_NO_ESMS = b"""\
<message:Structure xmlns:message="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message"
                   xmlns:structure="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure"
                   xmlns:common="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common">
  <message:Structures>
    <structure:Dataflows>
      <structure:Dataflow id="TOUR_OCC_ARM" agencyID="ESTAT" version="1.0">
        <common:Annotations>
          <common:Annotation>
            <common:AnnotationTitle>DATASET</common:AnnotationTitle>
            <common:AnnotationType>DISSEMINATION_OBJECT_TYPE</common:AnnotationType>
          </common:Annotation>
        </common:Annotations>
      </structure:Dataflow>
    </structure:Dataflows>
  </message:Structures>
</message:Structure>
"""


def _use_provider(monkeypatch: pytest.MonkeyPatch, name: str) -> dict[str, object]:
    """Pin the active provider so a user-level portals file cannot change the test."""
    provider = PROVIDERS[name]
    monkeypatch.setattr(discovery, "get_provider", lambda: provider)
    monkeypatch.setattr(discovery, "get_agency_id", lambda: provider["agency_id"])
    return provider


def test_eurostat_declares_the_esms_annotation() -> None:
    assert PROVIDERS["eurostat"]["dataflow_metadata_annotation"] == "ESMS_HTML"


def test_metadata_url_from_published_annotation(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_provider(monkeypatch, "eurostat")
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_request(path: str, **params: object) -> bytes:
        calls.append((path, params))
        return DATAFLOW_XML

    monkeypatch.setattr(discovery, "sdmx_request_xml", fake_request)

    assert discovery.dataflow_metadata_url("TOUR_OCC_ARM") == METADATA_URL
    assert calls == [
        (
            "dataflow/ESTAT/TOUR_OCC_ARM",
            # Fail fast: this line is decoration, and info must not hang on it.
            {"_timeout": 30, "_max_retries": 1, "detail": "full", "references": "none"},
        )
    ]


def test_returns_none_when_annotation_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_provider(monkeypatch, "eurostat")
    monkeypatch.setattr(discovery, "sdmx_request_xml", lambda path, **kw: DATAFLOW_XML_NO_ESMS)

    assert discovery.dataflow_metadata_url("TOUR_OCC_ARM") is None


def test_istat_is_not_charged_for_a_second_request(monkeypatch: pytest.MonkeyPatch) -> None:
    """ISTAT resolves `metadata_url` from its catalogue, for the description harvester.

    That is a different consumer, with a 15 s data rate limit: `info` must not
    start re-fetching it just because the annotation has a familiar name.
    """
    provider = _use_provider(monkeypatch, "istat")
    assert "metadata_url" in provider["annotations"]
    called: list[str] = []
    monkeypatch.setattr(discovery, "sdmx_request_xml", lambda path, **kw: called.append(path))

    assert discovery.dataflow_metadata_url("151_929") is None
    assert called == []


def test_returns_none_when_the_request_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_provider(monkeypatch, "eurostat")

    def boom(path: str, **kw: object) -> bytes:
        raise httpx.ConnectError("metadata endpoint is down")

    monkeypatch.setattr(discovery, "sdmx_request_xml", boom)

    assert discovery.dataflow_metadata_url("TOUR_OCC_ARM") is None


def test_returns_none_when_the_response_is_not_xml(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_provider(monkeypatch, "eurostat")
    monkeypatch.setattr(discovery, "sdmx_request_xml", lambda path, **kw: b"<not-xml")

    assert discovery.dataflow_metadata_url("TOUR_OCC_ARM") is None


def test_empty_identifier_makes_no_request(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_provider(monkeypatch, "eurostat")
    called: list[str] = []
    monkeypatch.setattr(discovery, "sdmx_request_xml", lambda path, **kw: called.append(path))

    assert discovery.dataflow_metadata_url("") is None
    assert called == []


def test_returns_none_when_the_lock_file_cannot_be_taken(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The rate-limit lock raises a `LockException`, which is not an `OSError`."""
    _use_provider(monkeypatch, "eurostat")

    def locked(path: str, **kw: object) -> bytes:
        raise portalocker.exceptions.LockException("no lock")

    monkeypatch.setattr(discovery, "sdmx_request_xml", locked)

    assert discovery.dataflow_metadata_url("TOUR_OCC_ARM") is None


def test_unexpected_errors_are_not_swallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only the expected transport/parse failures are absorbed, not bugs."""
    _use_provider(monkeypatch, "eurostat")

    def bug(path: str, **kw: object) -> bytes:
        raise RuntimeError("a bug, not a provider outage")

    monkeypatch.setattr(discovery, "sdmx_request_xml", bug)

    with pytest.raises(RuntimeError):
        discovery.dataflow_metadata_url("TOUR_OCC_ARM")


# ── CLI output ───────────────────────────────────────────────────────

DATASET = {
    "df_id": "TOUR_OCC_ARM",
    "version": "1.0",
    "df_description": "Occupancy of tourist accommodation establishments",
    "df_structure_id": "TOUR_OCC_ARM",
    "dimensions": {"freq": {"position": 1, "codelist_id": "FREQ"}},
    "filters": {},
    "has_constraint": True,
    "notes": [],
}


def _patch_info(
    monkeypatch: pytest.MonkeyPatch,
    provider: dict[str, object],
    request,
) -> None:
    # `info` resolves the provider through `base` at call time; the helper holds
    # its own binding from `discovery`, so both have to point at the same one.
    monkeypatch.setattr(opensdmx.base, "get_provider", lambda: provider)
    monkeypatch.setattr(discovery, "get_provider", lambda: provider)
    monkeypatch.setattr(discovery, "get_agency_id", lambda: provider["agency_id"])
    monkeypatch.setattr(discovery, "sdmx_request_xml", request)
    monkeypatch.setattr(opensdmx, "load_dataset", lambda _id: dict(DATASET))
    monkeypatch.setattr(opensdmx, "dimensions_info", lambda _ds, **_kw: pl.DataFrame())
    monkeypatch.setattr("opensdmx.cli._check_api_reachable", lambda: None)


def test_info_table_shows_the_metadata_line(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_info(monkeypatch, PROVIDERS["eurostat"], lambda path, **kw: DATAFLOW_XML)

    result = runner.invoke(app, ["info", "TOUR_OCC_ARM"])

    assert result.exit_code == 0, result.output
    # The panel wraps the URL inside its border, so drop whitespace and box glyphs.
    flat = re.sub(r"[│╭╮╰╯─\s]", "", result.output)
    assert f"Metadata:{METADATA_URL}" in flat


def test_info_json_carries_the_metadata_url(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_info(monkeypatch, PROVIDERS["eurostat"], lambda path, **kw: DATAFLOW_XML)

    result = runner.invoke(app, ["--output", "json", "info", "TOUR_OCC_ARM"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["metadata_url"] == METADATA_URL


def test_info_omits_the_key_when_the_link_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def down(path: str, **kw: object) -> bytes:
        raise httpx.ConnectError("metadata endpoint is down")

    _patch_info(monkeypatch, PROVIDERS["eurostat"], down)

    result = runner.invoke(app, ["--output", "json", "info", "TOUR_OCC_ARM"])

    assert result.exit_code == 0, result.output
    assert "metadata_url" not in json.loads(result.stdout)


def test_info_leaves_providers_without_the_annotation_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: list[str] = []
    helper_calls: list[str] = []
    _patch_info(
        monkeypatch,
        PROVIDERS["istat"],
        lambda path, **kw: (called.append(path), DATAFLOW_XML)[1],
    )
    real_helper = discovery.dataflow_metadata_url
    monkeypatch.setattr(
        discovery,
        "dataflow_metadata_url",
        lambda identifier: (helper_calls.append(identifier), real_helper(identifier))[1],
    )

    result = runner.invoke(app, ["--output", "json", "info", "151_929"])

    assert result.exit_code == 0, result.output
    assert "metadata_url" not in json.loads(result.stdout)
    assert helper_calls == [], "the CLI gate must not even call the helper"
    assert called == []
