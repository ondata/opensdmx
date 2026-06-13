from __future__ import annotations

import sqlite3
import time
from unittest.mock import patch

import opensdmx.db_cache as db_cache

# Codelist with a hierarchy (Parent refs) and ORDER annotations, plus edge
# cases: a root (no Parent), and a code with no ORDER / a non-numeric ORDER.
_HIER_CODELIST_XML = b"""<?xml version="1.0" encoding="utf-8"?>
<message:Structure
  xmlns:message="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message"
  xmlns:structure="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure"
  xmlns:common="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common"
  xmlns:xml="http://www.w3.org/XML/1998/namespace">
  <message:Structures>
    <structure:Codelists>
      <structure:Codelist id="CL_GEO" agencyID="IT1" version="1.0">
        <structure:Code id="IT">
          <common:Annotations>
            <common:Annotation id="ORDER">
              <common:AnnotationText xml:lang="it">2</common:AnnotationText>
            </common:Annotation>
          </common:Annotations>
          <common:Name xml:lang="it">Italia</common:Name>
        </structure:Code>
        <structure:Code id="ITC1">
          <common:Annotations>
            <common:Annotation id="ORDER">
              <common:AnnotationText xml:lang="it">9</common:AnnotationText>
            </common:Annotation>
          </common:Annotations>
          <common:Name xml:lang="it">Piemonte</common:Name>
          <structure:Parent>
            <Ref id="IT"/>
          </structure:Parent>
        </structure:Code>
        <structure:Code id="NOORD">
          <common:Name xml:lang="it">Senza ordine</common:Name>
          <structure:Parent>
            <Ref id="ITC1"/>
          </structure:Parent>
        </structure:Code>
        <structure:Code id="BADORD">
          <common:Annotations>
            <common:Annotation id="ORDER">
              <common:AnnotationText xml:lang="it">x</common:AnnotationText>
            </common:Annotation>
          </common:Annotations>
          <common:Name xml:lang="it">Ordine non numerico</common:Name>
        </structure:Code>
      </structure:Codelist>
    </structure:Codelists>
  </message:Structures>
</message:Structure>
"""

_PROVIDER = {
    "name": "ISTAT",
    "base_url": "https://esploradati.istat.it/SDMXWS/rest",
    "agency_id": "IT1",
    "rate_limit": 15.0,
    "language": "it",
}


def _dataset() -> dict:
    return {
        "df_id": "TEST_DF",
        "version": "1.0",
        "df_description": "Test",
        "df_structure_id": "TEST_DSD",
        "dimensions": {"GEO": {"id": "GEO", "position": 1, "codelist_id": "CL_GEO"}},
        "filters": {"GEO": "."},
    }


def test_hierarchy_parses_parent_and_order():
    from opensdmx.discovery import get_codelist_hierarchy

    with patch("opensdmx.discovery.get_provider", return_value=_PROVIDER), \
         patch("opensdmx.discovery.sdmx_request_xml", return_value=_HIER_CODELIST_XML), \
         patch("opensdmx.db_cache.get_cached_codelist_values", return_value=None), \
         patch("opensdmx.db_cache.save_codelist_values"):
        df = get_codelist_hierarchy(_dataset(), "GEO")

    rows = {r["id"]: r for r in df.to_dicts()}
    # parent: root null, children point up
    assert rows["IT"]["parent"] is None
    assert rows["ITC1"]["parent"] == "IT"
    assert rows["NOORD"]["parent"] == "ITC1"
    # order: numeric parsed, missing/non-numeric -> null
    assert rows["IT"]["order"] == 2
    assert rows["ITC1"]["order"] == 9
    assert rows["NOORD"]["order"] is None
    assert rows["BADORD"]["order"] is None
    assert df.columns == ["id", "name", "parent", "order"]


def test_get_dimension_values_unchanged_contract():
    """Regression: default output stays exactly (id, name)."""
    from opensdmx.discovery import get_dimension_values

    with patch("opensdmx.discovery.get_provider", return_value=_PROVIDER), \
         patch("opensdmx.discovery.sdmx_request_xml", return_value=_HIER_CODELIST_XML), \
         patch("opensdmx.db_cache.get_cached_codelist_values", return_value=None), \
         patch("opensdmx.db_cache.save_codelist_values"):
        df = get_dimension_values(_dataset(), "GEO")

    assert df.columns == ["id", "name"]
    assert set(df["id"].to_list()) == {"IT", "ITC1", "NOORD", "BADORD"}


def test_save_and_read_roundtrip_with_hierarchy(tmp_path, monkeypatch):
    db_file = tmp_path / "cache.db"
    monkeypatch.setattr(db_cache, "_get_db_path", lambda: db_file)
    monkeypatch.setattr(db_cache, "_INITIALIZED_DBS", set())

    db_cache.save_codelist_values("CL_GEO:it", [
        {"id": "IT", "name": "Italia", "parent": None, "order": 2},
        {"id": "ITC1", "name": "Piemonte", "parent": "IT", "order": 9},
    ])
    got = db_cache.get_cached_codelist_values("CL_GEO:it")
    by_id = {r["id"]: r for r in got}
    assert by_id["ITC1"]["parent"] == "IT"
    assert by_id["ITC1"]["order"] == 9
    assert by_id["IT"]["parent"] is None


def test_migration_adds_columns_without_data_loss(tmp_path, monkeypatch):
    db_file = tmp_path / "cache.db"
    # Create an OLD-schema codelist_values table (no parent/order) and a row.
    conn = sqlite3.connect(db_file)
    conn.executescript("""
        CREATE TABLE codelist_values (
            codelist_id TEXT NOT NULL,
            code_id     TEXT NOT NULL,
            code_name   TEXT,
            cached_at   REAL NOT NULL,
            PRIMARY KEY (codelist_id, code_id)
        );
    """)
    conn.execute(
        "INSERT INTO codelist_values VALUES (?, ?, ?, ?)",
        ("CL_OLD:it", "X", "Old row", time.time()),
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(db_cache, "_get_db_path", lambda: db_file)
    monkeypatch.setattr(db_cache, "_INITIALIZED_DBS", set())

    # Trigger schema init + migration via any cache access.
    got = db_cache.get_cached_codelist_values("CL_OLD:it")

    # Old row survived and now exposes null parent/order.
    assert got is not None
    assert got[0]["id"] == "X"
    assert got[0]["name"] == "Old row"
    assert got[0]["parent"] is None
    assert got[0]["order"] is None

    # Columns physically present now.
    conn = sqlite3.connect(db_file)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(codelist_values)")}
    conn.close()
    assert {"code_parent", "code_order"} <= cols
