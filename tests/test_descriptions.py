"""Tests for the dataflow-descriptions capability: harvester pure logic + embed guard."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import polars as pl

# The harvester lives under scripts/ (not an installed package): load it by path.
_SPEC = importlib.util.spec_from_file_location(
    "descriptions_archive",
    Path(__file__).resolve().parents[1] / "scripts" / "descriptions_archive.py",
)
archive = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(archive)


def _df_node(annotations_xml: str = ""):
    from lxml import etree

    xml = (
        '<str:Dataflow xmlns:str="s" xmlns:com="c" '
        'xmlns:xml="http://www.w3.org/XML/1998/namespace" id="DF" agencyID="IT1">'
        f"{annotations_xml}</str:Dataflow>"
    )
    return etree.fromstring(xml.encode())


_METADATA_ANN = (
    "<com:Annotations><com:Annotation>"
    "<com:AnnotationType>METADATA_URL</com:AnnotationType>"
    '<com:AnnotationText xml:lang="it">https://esploradati.istat.it/RefMeta/x'
    "?nodeId=DW&amp;metadataSetId=MS_ISTAT_TOPMETA2&amp;reportId=DCIS_NATI2&amp;lang=it"
    "&amp;BaseUrlMDA=https://esploradati.istat.it/METADATA_API</com:AnnotationText>"
    '<com:AnnotationText xml:lang="en">https://esploradati.istat.it/RefMeta/x'
    "?metadataSetId=MS_ISTAT_TOPMETA2&amp;reportId=DCIS_NATI2&amp;lang=en"
    "&amp;BaseUrlMDA=https://esploradati.istat.it/METADATA_API</com:AnnotationText>"
    "</com:Annotation></com:Annotations>"
)


# --- clean_prose -----------------------------------------------------------

def test_clean_prose_unescapes_and_strips_markup():
    raw = "Natalit&agrave; e fecondit&agrave;.<br/> <b>P4</b>   modello"
    assert archive.clean_prose(raw) == "Natalità e fecondità. P4 modello"


def test_clean_prose_empty():
    assert archive.clean_prose("") == ""
    assert archive.clean_prose(None) == ""


# --- METADATA_URL annotation parsing --------------------------------------

def test_annotation_text_prefers_language_and_parses_params():
    node = _df_node(_METADATA_ANN)
    url = archive._annotation_text(node, "METADATA_URL", "it")
    q = parse_qs(urlparse(url).query)
    assert q["reportId"][0] == "DCIS_NATI2"
    assert q["metadataSetId"][0] == "MS_ISTAT_TOPMETA2"
    assert q["lang"][0] == "it"
    assert q["BaseUrlMDA"][0] == "https://esploradati.istat.it/METADATA_API"


def test_annotation_text_falls_back_to_english():
    node = _df_node(_METADATA_ANN)
    url = archive._annotation_text(node, "METADATA_URL", "fr")
    assert "lang=en" in url


def test_annotation_text_absent_returns_none():
    assert archive._annotation_text(_df_node(), "METADATA_URL", "it") is None


# --- DATA_SOURCE extraction ------------------------------------------------

def _payload(attr_id: str, text: str) -> dict:
    return {
        "data": {
            "metadataSets": [
                {
                    "reports": [
                        {
                            "attributeSet": {
                                "reportedAttributes": [
                                    {"id": "OTHER", "text": "ignore"},
                                    {
                                        "id": "GROUP",
                                        "attributeSet": {
                                            "reportedAttributes": [
                                                {"id": attr_id, "text": text}
                                            ]
                                        },
                                    },
                                ]
                            }
                        }
                    ]
                }
            ]
        }
    }


def test_extract_description_from_nested_attribute():
    payload = _payload("DATA_SOURCE", "Rilevazione P4: natalit&agrave;.")
    assert archive.extract_description(payload, "DATA_SOURCE") == "Rilevazione P4: natalità."


def test_extract_description_missing_attribute_returns_none():
    payload = _payload("DATA_SOURCE", "x")
    assert archive.extract_description(payload, "NOPE") is None


def test_extract_description_prefers_provider_language():
    payload = {
        "data": {
            "metadataSets": [
                {
                    "reports": [
                        {
                            "attributeSet": {
                                "reportedAttributes": [
                                    {"id": "DATA_SOURCE", "texts": {"de": "Beschreibung", "en": "Description"}}
                                ]
                            }
                        }
                    ]
                }
            ]
        }
    }
    assert archive.extract_description(payload, "DATA_SOURCE", "de") == "Beschreibung"
    assert archive.extract_description(payload, "DATA_SOURCE", "fr") == "Description"  # en fallback


# --- SIQual id from the link attribute ------------------------------------

def test_extract_link_id_pulls_siqual_id():
    link = "Iscritti in anagrafe per nascita[http://siqual.istat.it/SIQual/visualizza.do?id=0019100&refresh=true&language=IT]"
    payload = _payload("DATA_SOURCE_LINK", link)
    assert archive.extract_link_id(payload, "DATA_SOURCE_LINK") == "0019100"


def test_extract_link_id_absent_returns_none():
    # attribute present but no id= param
    payload = _payload("DATA_SOURCE_LINK", "http://siqual.istat.it/SIQual/home.do")
    assert archive.extract_link_id(payload, "DATA_SOURCE_LINK") is None
    # attribute missing entirely
    assert archive.extract_link_id(_payload("DATA_SOURCE", "x"), "DATA_SOURCE_LINK") is None


# --- embed.py guard --------------------------------------------------------

def test_descriptions_for_embed_missing_resource_is_empty(monkeypatch, tmp_path):
    from opensdmx import embed

    monkeypatch.setattr(embed, "_descriptions_resource_path", lambda: tmp_path / "nope.parquet")
    out = embed._descriptions_for_embed()
    assert out.is_empty()
    assert set(out.columns) == {"df_id", "description"}


def test_descriptions_for_embed_loads_resource(monkeypatch, tmp_path):
    from opensdmx import embed

    res = tmp_path / "istat.parquet"
    pl.DataFrame({"df_id": ["A"], "description": ["prose"], "report_id": ["R"]}).write_parquet(res)
    monkeypatch.setattr(embed, "_descriptions_resource_path", lambda: res)
    out = embed._descriptions_for_embed()
    assert out.columns == ["df_id", "description"]
    assert out["description"].to_list() == ["prose"]
