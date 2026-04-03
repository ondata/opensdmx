"""Tests for opensdmx.utils – XML helpers and URL key builder."""

from __future__ import annotations

import pytest
from opensdmx.utils import (
    get_name_by_lang,
    make_url_key,
    xml_attr_safe,
    xml_parse,
    xml_text_safe,
)


# ── xml_parse ────────────────────────────────────────────────────────

MINIMAL_XML = b"""\
<message:Structure xmlns:message="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message"
                   xmlns:structure="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure"
                   xmlns:common="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common">
  <message:Header><message:ID>TEST</message:ID></message:Header>
</message:Structure>
"""


def test_xml_parse_canonical_namespaces():
    root, ns = xml_parse(MINIMAL_XML)
    assert "message" in ns
    assert "structure" in ns
    assert "common" in ns
    assert root.tag.endswith("Structure")


def test_xml_parse_non_canonical_prefix():
    """Prefixes in source XML are remapped to canonical names."""
    xml = b"""\
    <msg:Structure xmlns:msg="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message">
      <msg:Header><msg:ID>X</msg:ID></msg:Header>
    </msg:Structure>
    """
    _, ns = xml_parse(xml)
    assert "message" in ns  # "msg" → "message"


# ── xml_attr_safe ────────────────────────────────────────────────────

def test_xml_attr_safe_present():
    root, _ = xml_parse(b'<root id="abc"/>')
    assert xml_attr_safe(root, "id") == "abc"


def test_xml_attr_safe_missing():
    root, _ = xml_parse(b"<root/>")
    assert xml_attr_safe(root, "id") is None
    assert xml_attr_safe(root, "id", "fallback") == "fallback"


# ── xml_text_safe ────────────────────────────────────────────────────

def test_xml_text_safe_found():
    root, _ = xml_parse(b"<root><child>hello</child></root>")
    assert xml_text_safe(root, "child", {}) == "hello"


def test_xml_text_safe_missing():
    root, _ = xml_parse(b"<root/>")
    assert xml_text_safe(root, "child", {}) is None
    assert xml_text_safe(root, "child", {}, "default") == "default"


def test_xml_text_safe_empty_text():
    root, _ = xml_parse(b"<root><child></child></root>")
    assert xml_text_safe(root, "child", {}) is None


# ── get_name_by_lang ────────────────────────────────────────────────

NAME_XML = b"""\
<Codelist xmlns:common="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common">
  <common:Name xml:lang="en">English</common:Name>
  <common:Name xml:lang="it">Italiano</common:Name>
</Codelist>
"""


def test_get_name_by_lang_en():
    root, ns = xml_parse(NAME_XML)
    assert get_name_by_lang(root, "en", ns) == "English"


def test_get_name_by_lang_it():
    root, ns = xml_parse(NAME_XML)
    assert get_name_by_lang(root, "it", ns) == "Italiano"


def test_get_name_by_lang_fallback_first():
    root, ns = xml_parse(NAME_XML)
    assert get_name_by_lang(root, "fr", ns) == "English"  # first element


def test_get_name_by_lang_no_names():
    root, _ = xml_parse(b"<root/>")
    assert get_name_by_lang(root, "en", {}) is None


# ── make_url_key ─────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "filters, expected",
    [
        ({}, ""),
        ({"FREQ": ["A"], "GEO": ["IT"]}, "A.IT"),
        ({"FREQ": ["A", "Q"], "GEO": ["IT"]}, "A+Q.IT"),
        ({"FREQ": ".", "GEO": ["IT"]}, ".IT"),
        ({"FREQ": [""], "GEO": ["DE"]}, ".DE"),
        ({"FREQ": [], "GEO": ["IT"]}, ".IT"),
        ({"DIM1": ["V1"], "DIM2": "single"}, "V1.single"),
    ],
)
def test_make_url_key(filters, expected):
    assert make_url_key(filters) == expected
