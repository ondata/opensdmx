"""Probe `contentconstraint` endpoint on every provider that supports constraints.

For each provider, calls GET <base_url>/contentconstraint/<agency_id>/<df_id>
and records HTTP status, response time and the dimensions exposed in the response.

Output: tmp/contentconstraint-probe.md
"""

from __future__ import annotations

import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx

PROBES = [
    ("eurostat", "ESTAT", "https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1", "PRC_HICP_MANR", {}),
    ("istat", "IT1", "https://esploradati.istat.it/SDMXWS/rest", "22_289_DF_DCIS_POPRES1_24", {}),
    ("abs", "ABS", "https://data.api.abs.gov.au/rest", "POPULATION_CLOCK", {}),
    ("bis", "BIS", "https://stats.bis.org/api/v1", "WS_XRU", {}),
    ("imf", "IMF.RES", "https://api.imf.org/external/sdmx/2.1", "WEO", {}),
    ("derzhstat", "SSSU", "https://stat.gov.ua/sdmx/workspaces/default:integration/registry/sdmx/2.1",
     "DF_GROUND_TRANSPORT_Q", {"User-Agent": "Mozilla/5.0"}),
]

ACCEPT = "application/vnd.sdmx.structure+xml;version=2.1"


def parse_dimensions(xml_bytes: bytes) -> tuple[list[str], int]:
    """Return (dimension_ids, total_value_count)."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return [], 0
    dims: list[str] = []
    total = 0
    for kv in root.iter():
        if kv.tag.endswith("KeyValue"):
            dim = kv.get("id")
            if dim and dim not in dims:
                dims.append(dim)
            for v in kv:
                if v.tag.endswith("Value") and v.text:
                    total += 1
    return dims, total


def probe(name: str, agency: str, base: str, df_id: str, headers: dict) -> dict:
    url = f"{base}/contentconstraint/{agency}/{df_id}"
    h = {"Accept": ACCEPT, **headers}
    start = time.time()
    try:
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            r = client.get(url, headers=h)
        elapsed = time.time() - start
        size = len(r.content)
        if r.status_code == 200:
            dims, total = parse_dimensions(r.content)
        else:
            dims, total = [], 0
        return dict(
            provider=name,
            url=url,
            status=r.status_code,
            elapsed=elapsed,
            size=size,
            dimensions=dims,
            n_values=total,
            error=None if r.status_code == 200 else r.text[:200],
        )
    except httpx.TimeoutException:
        return dict(provider=name, url=url, status=None, elapsed=time.time() - start,
                    size=0, dimensions=[], n_values=0, error="TIMEOUT 30s")
    except Exception as e:
        return dict(provider=name, url=url, status=None, elapsed=time.time() - start,
                    size=0, dimensions=[], n_values=0, error=f"{type(e).__name__}: {e}")


def main() -> int:
    out = Path(__file__).resolve().parents[1] / "tmp" / "contentconstraint-probe.md"
    results = []
    for name, agency, base, df_id, headers in PROBES:
        print(f"probing {name}... ", end="", flush=True)
        r = probe(name, agency, base, df_id, headers)
        results.append((df_id, r))
        if r["status"] == 200:
            print(f"ok {r['elapsed']:.2f}s, {len(r['dimensions'])} dims")
        else:
            print(f"FAIL {r['status']} ({r['error']})")
        time.sleep(2)

    lines = [
        "# contentconstraint probe — 2026-05-09",
        "",
        "URL pattern: `<base_url>/contentconstraint/<agency_id>/<df_id>`",
        "Accept header: `application/vnd.sdmx.structure+xml;version=2.1`",
        "",
        "| Provider | Dataflow | Status | Time | Size | Dims | n_values |",
        "|---|---|---|---|---|---|---|",
    ]
    for df_id, r in results:
        status = "OK" if r["status"] == 200 else f"{r['status']} {r['error'] or ''}"[:60]
        time_s = f"{r['elapsed']:.2f}s"
        size = f"{r['size']/1024:.1f} KB" if r["size"] else "-"
        n_dim = len(r["dimensions"])
        n_val = r["n_values"]
        lines.append(f"| `{r['provider']}` | `{df_id}` | {status} | {time_s} | {size} | {n_dim} | {n_val} |")

    lines += ["", "## Dimensions exposed per provider", ""]
    for df_id, r in results:
        if r["status"] == 200:
            dims = ", ".join(r["dimensions"]) if r["dimensions"] else "(none)"
            lines.append(f"- **{r['provider']}** (`{df_id}`): {dims}")
        else:
            lines.append(f"- **{r['provider']}** (`{df_id}`): FAILED — {r['error']}")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n")
    print(f"\nwritten {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
