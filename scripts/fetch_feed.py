#!/usr/bin/env python3
"""
Scarica il feed RSS di una newsletter Substack e ne estrae i metadati in JSON.

Pensato per il pattern "git scraping": ogni run sovrascrive data/<newsletter>.json,
la history di git conserva le versioni precedenti (diff = nuovi post / modifiche).

Uso:
    python fetch_feed.py <newsletter-subdomain> [--out data]

Esempio:
    python fetch_feed.py ondata
    -> scrive data/ondata.json
"""

import argparse
import json
import sys
import urllib.request
import urllib.error
from pathlib import Path
from xml.etree import ElementTree as ET

USER_AGENT = "ondata-feed-fetcher/1.0 (+https://ondata.it)"
NS = {"dc": "http://purl.org/dc/elements/1.1/"}


def fetch_feed(subdomain: str) -> bytes:
    url = f"https://{subdomain}.substack.com/feed"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            print(f"HTTP {resp.status} da {resp.url}")
            print(f"  content-type: {resp.headers.get('Content-Type')}")
            print(f"  server: {resp.headers.get('Server')}  cf-ray: {resp.headers.get('CF-Ray')}")
            return resp.read()
    except urllib.error.HTTPError as e:
        body = e.read()[:300]
        print(f"HTTP {e.code} per {url}", file=sys.stderr)
        print(f"  server: {e.headers.get('Server')}  cf-ray: {e.headers.get('CF-Ray')}", file=sys.stderr)
        print(f"  primi byte: {body!r}", file=sys.stderr)
        sys.exit(f"Errore HTTP {e.code} per {url} — feed disattivato dall'autore o richiesta bloccata.")
    except urllib.error.URLError as e:
        sys.exit(f"Errore di rete su {url}: {e.reason}")


def _text(item, tag, ns=None):
    el = item.find(tag, ns) if ns else item.find(tag)
    return el.text.strip() if el is not None and el.text else None


def parse_items(xml_bytes: bytes) -> list[dict]:
    # Cloudflare può rispondere 200 con una pagina di challenge HTML: senza questo
    # controllo il ParseError sembrerebbe un feed malformato invece di un blocco.
    head = xml_bytes.lstrip()[:300]
    if not head.startswith(b"<?xml") and b"<rss" not in head:
        sys.exit(f"Risposta non XML (probabile blocco o challenge). Primi byte: {head!r}")

    root = ET.fromstring(xml_bytes)
    channel = root.find("channel")
    if channel is None:
        sys.exit("Formato feed inatteso: nodo <channel> non trovato.")

    items = []
    for item in channel.findall("item"):
        items.append({
            "title": _text(item, "title"),
            "link": _text(item, "link"),
            "guid": _text(item, "guid"),
            "pubDate": _text(item, "pubDate"),
            "creator": _text(item, "dc:creator", NS),
            "categories": [c.text for c in item.findall("category") if c.text],
            "description": _text(item, "description"),
        })
    return items


def main():
    parser = argparse.ArgumentParser(
        description="Scarica metadati dal feed RSS di una newsletter Substack."
    )
    parser.add_argument("subdomain", help="es. 'ondata' per ondata.substack.com")
    parser.add_argument("--out", default="data", help="cartella di output (default: data)")
    args = parser.parse_args()

    xml_bytes = fetch_feed(args.subdomain)
    items = parse_items(xml_bytes)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{args.subdomain}.json"
    out_path.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Scritti {len(items)} post in {out_path}")


if __name__ == "__main__":
    main()
