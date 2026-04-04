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
            if prefix is not None and uri not in ns.values():
                canonical = _NS_CANONICAL.get(uri, prefix)
                ns[canonical] = uri
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
