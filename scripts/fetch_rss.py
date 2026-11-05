#!/usr/bin/env python3
"""Fetch tech-news RSS/Atom feeds (stdlib only) and write data/fetched.json.

Same 7 feeds as the Parsa Mag news engine, same output fields
(source/title/link/pubDate only). Feeds that fail are reported on stderr
and skipped — one dead feed never kills the run.

Notes:
- The Verge serves Atom, not RSS, so the parser handles both <item> (RSS)
  and <entry> (Atom) elements. Atom link comes from <link href="...">.
- Output is written to data/fetched.json (relative to the repo root),
  not printed, so the next script in the chain can read it.
Usage: python3 scripts/fetch_rss.py
"""
import json
import os
import sys
import urllib.request
import xml.etree.ElementTree as ET

FEEDS = [
    ("The Verge", "https://www.theverge.com/rss/index.xml"),
    ("TechCrunch", "https://techcrunch.com/feed/"),
    ("Wired", "https://www.wired.com/feed/rss"),
    ("Ars Technica", "https://arstechnica.com/feed/"),
    ("MIT Technology Review", "https://www.technologyreview.com/feed/"),
    ("Digiato", "https://digiato.com/feed"),
    ("Zoomit", "https://zoomit.ir/feed"),
]

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "parsa-mag-pipeline/1.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read()


def _text(elem, tag):
    if elem is None:
        return ""
    # Match by local name so Atom's namespaced tags (atom:title) work too.
    for child in elem.iter():
        if child.tag.rsplit("}", 1)[-1] == tag:
            return (child.text or "").strip()
    return ""


def _atom_link(entry):
    for child in entry:
        if child.tag.rsplit("}", 1)[-1] == "link":
            href = child.get("href", "").strip()
            rel = child.get("rel", "alternate")
            if href and rel in ("alternate", ""):
                return href
    return ""


def parse(xml_bytes, source):
    root = ET.fromstring(xml_bytes)
    items = []
    for elem in root.iter():
        local = elem.tag.rsplit("}", 1)[-1]
        if local == "item":  # RSS
            title = _text(elem, "title")
            link = _text(elem, "link")
            pub = _text(elem, "pubDate")
        elif local == "entry":  # Atom
            title = _text(elem, "title")
            link = _atom_link(elem)
            pub = _text(elem, "published") or _text(elem, "updated")
        else:
            continue
        if title and link:
            items.append({"source": source, "title": title,
                          "link": link, "pubDate": pub})
    return items


def main():
    seen, out = set(), []
    for name, url in FEEDS:
        try:
            items = parse(fetch(url), name)
        except Exception as e:  # noqa: BLE001 — one dead feed must not kill the run
            print(f"FEED FAILED {name} ({url}): {e}", file=sys.stderr)
            continue
        for it in items:
            if it["link"] not in seen:
                seen.add(it["link"])
                out.append(it)
    data_dir = os.path.join(ROOT, "data")
    os.makedirs(data_dir, exist_ok=True)
    out_path = os.path.join(data_dir, "fetched.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"Fetched {len(out)} items -> {out_path}")


if __name__ == "__main__":
    main()
