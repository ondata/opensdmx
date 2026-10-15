"""The codelist request path: provider metadata_prefix and codelist agency (#85)."""

from __future__ import annotations

from unittest.mock import patch

from opensdmx.discovery import _codelist_path, _get_dimension_description, get_dimension_values

_CODELIST_XML = b"""<?xml version="1.0" encoding="utf-8"?>
<message:Structure
  xmlns:message="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message"
  xmlns:structure="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure"
  xmlns:common="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common">
  <message:Structures>
    <structure:Codelists>
      <structure:Codelist id="CL_BBK_STD_FREQ" agencyID="BBK" version="1.0">
        <common:Name xml:lang="en">Frequency</common:Name>
        <structure:Code id="A">
          <common:Name xml:lang="en">Annual</common:Name>
        </structure:Code>
      </structure:Codelist>
    </structure:Codelists>
  </message:Structures>
</message:Structure>
"""

_BUNDESBANK = {
    "name": "Deutsche Bundesbank",
    "base_url": "https://api.statistiken.bundesbank.de/rest",
    "agency_id": "BBK",
    "metadata_prefix": "metadata",
    "datastructure_agency": "BBK",
    "codelist_agency": "BBK",
    "language": "en",
}

# The catch-all agency, and no metadata prefix: what every other provider uses.
# `datastructure_agency` is set to the real preset's value on purpose: if the
# helper ever reused that key instead of `codelist_agency`, this provider would
# ask for codelist/ESTAT/... and the default test below would fail.
_EUROSTAT = {
    "name": "Eurostat",
    "base_url": "https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1",
    "agency_id": "ESTAT",
    "datastructure_agency": "ESTAT",
    "language": "en",
}


def _dataset() -> dict:
    return {
        "df_id": "BBEE1",
        "version": "1.0",
        "df_description": "Test",
        "df_structure_id": "BBK_STD_FREQ",
        "dimensions": {
            "FREQ": {"id": "FREQ", "position": 1, "codelist_id": "CL_BBK_STD_FREQ"}
        },
        "filters": {"FREQ": "."},
    }


def test_path_uses_the_declared_agency():
    with patch("opensdmx.discovery.get_provider", return_value=_BUNDESBANK):
        assert _codelist_path("CL_BBK_STD_FREQ") == "metadata/codelist/BBK/CL_BBK_STD_FREQ"


def test_path_defaults_to_all_without_a_declared_agency():
    with patch("opensdmx.discovery.get_provider", return_value=_EUROSTAT):
        assert _codelist_path("CL_FREQ") == "codelist/ALL/CL_FREQ"


def test_values_requests_the_declared_agency():
    with patch("opensdmx.discovery.get_provider", return_value=_BUNDESBANK), \
         patch("opensdmx.discovery.sdmx_request_xml", return_value=_CODELIST_XML) as mock_req, \
         patch("opensdmx.db_cache.get_cached_codelist_values", return_value=None), \
         patch("opensdmx.db_cache.save_codelist_values"):
        values = get_dimension_values(_dataset(), "FREQ")

    assert mock_req.call_args[0][0] == "metadata/codelist/BBK/CL_BBK_STD_FREQ"
    assert set(values["id"].to_list()) == {"A"}


def test_description_requests_the_declared_agency():
    with patch("opensdmx.discovery.get_provider", return_value=_BUNDESBANK), \
         patch("opensdmx.discovery.sdmx_request_xml", return_value=_CODELIST_XML) as mock_req, \
         patch("opensdmx.db_cache.is_codelist_info_cached", return_value=False), \
         patch("opensdmx.db_cache.save_codelist_info"):
        description = _get_dimension_description("CL_BBK_STD_FREQ")

    assert mock_req.call_args[0][0] == "metadata/codelist/BBK/CL_BBK_STD_FREQ"
    assert description == "Frequency"


def test_bundesbank_is_configured_for_its_own_codelist_agency():
    """The portal declares it; a provider entry without the key keeps `ALL`."""
    from opensdmx.base import PROVIDERS, set_provider

    set_provider("bundesbank")
    try:
        assert _codelist_path("CL_BBK_STD_FREQ") == "metadata/codelist/BBK/CL_BBK_STD_FREQ"
    finally:
        set_provider("eurostat")

    assert "codelist_agency" not in PROVIDERS["eurostat"]
