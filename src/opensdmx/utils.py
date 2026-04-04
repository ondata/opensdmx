"""XML parsing helpers and URL key builder."""

from lxml import etree


_NS_CANONICAL = {
    "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message": "message",
    "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure": "structure",
    "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common": "common",
}


def xml_parse(content: bytes):
    """Parse XML bytes and return (root, namespaces dict).

    Namespace prefixes are normalized to canonical names (message, structure, common)
    regardless of the prefix used in the source XML.
    """
    root = etree.fromstring(content)
    ns = {}
    for element in root.iter():
        for prefix, uri in element.nsmap.items():
            if uri in ns.values():
                continue
            if prefix is not None:
                canonical = _NS_CANONICAL.get(uri, prefix)
                ns[canonical] = uri
            elif uri in _NS_CANONICAL:
                # default namespace (prefix=None) — include only if canonically known
                ns[_NS_CANONICAL[uri]] = uri
    return root, ns


def xml_attr_safe(node, attr: str, default: str | None = None) -> str | None:
    """Extract an attribute from an XML node safely."""
    val = node.get(attr)
    return val if val is not None else default


def xml_text_safe(node, xpath: str, ns: dict, default: str | None = None) -> str | None:
    """Find a child node via XPath and return its text content."""
    found = node.find(xpath, ns)
    if found is not None and found.text:
        return found.text.strip()
    return default


def get_name_by_lang(node, lang: str = "en", ns: dict | None = None) -> str | None:
    """Return the Name element text for the given language, falling back to first Name."""
    ns = ns or {}
    names = []
    if "common" in ns:
        names = node.findall(".//common:Name", ns)
    if not names:
        names = node.findall(".//Name")

    for name_node in names:
        node_lang = name_node.get("{http://www.w3.org/XML/1998/namespace}lang")
        if node_lang == lang:
            return name_node.text.strip() if name_node.text else None

    if names:
        return names[0].text.strip() if names[0].text else None
    return None


def _get_code_label(codelist_id: str | None, code_value: str) -> str:
    """Return human-readable label for a single code from cache, or '' if not found."""
    if not codelist_id:
        return ""
    # Only single-value codes can be looked up; skip multi-value (AT+BE+...)
    if "+" in code_value:
        return ""
    from .db_cache import get_cached_codelist_values
    cached = get_cached_codelist_values(codelist_id)
    if not cached:
        return ""
    for entry in cached:
        if entry["id"] == code_value:
            return entry["name"] or ""
    return ""


def build_query_dict(
    ds: dict,
    filters: dict,
    start_period: str | None = None,
    end_period: str | None = None,
    last_n: int | None = None,
    first_n: int | None = None,
    provider: str | None = None,
) -> dict:
    """Build a plain dict representing a query, ready for YAML serialisation.

    For each active filter, looks up the code label in SQLite cache.
    If not cached, description is left as an empty string.
    """
    from .base import _active_provider, get_agency_id, get_base_url
    if provider:
        provider_name = provider
    elif isinstance(_active_provider, str):
        provider_name = _active_provider  # e.g. "eurostat"
    else:
        provider_name = _active_provider.get("agency_id", "")
    provider_url = get_base_url()
    agency_id = get_agency_id()

    filters_section: dict = {}
    for dim_id, value in filters.items():
        if value in ("", "."):
            continue
        codelist_id = (ds.get("dimensions") or {}).get(dim_id, {}).get("codelist_id")
        label = _get_code_label(codelist_id, value)
        filters_section[dim_id] = {"value": value, "description": label}

    return {
        "provider": provider_name,
        "provider_url": provider_url,
        "agency_id": agency_id,
        "dataset": ds["df_id"],
        "description": ds.get("df_description") or "",
        "filters": filters_section,
        "start_period": start_period,
        "end_period": end_period,
        "last_n": last_n,
        "first_n": first_n,
    }


def make_url_key(filters: dict) -> str:
    """Build an SDMX filter key string from dimension filters.

    Multiple values are joined with '+', dimensions separated by '.'.
    '.' means all values for a dimension.
    """
    if not filters:
        return ""

    parts = []
    for values in filters.values():
        if not values or values == "." or values == [""]:
            parts.append("")  # empty = all values in SDMX key
        elif isinstance(values, (list, tuple)):
            parts.append("+".join(str(v) for v in values if v))
        else:
            parts.append(str(values))

    return ".".join(parts)
