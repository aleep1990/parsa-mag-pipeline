#!/usr/bin/env python3
"""Dedupe fetched items against the committed seen state, rank them, and
write one JSON draft file per new item under drafts/.

Ranking (documented, deliberately simple):
  score = source_weight + recency_bonus
  - source_weight: per-feed weight in SOURCE_WEIGHTS below (1.0 = full).
  - recency_bonus: +1.0 if pubDate is within 24h of fetch time,
    +0.5 if within 72h, else 0. Unparseable/missing pubDate scores 0.

Dedupe is link-based: a link already in state/seen.json never gets a
second draft file, even if it reappears in a later fetch.

Draft file name: drafts/<UTC-date>-<sha1(link)[:12]>.json — deterministic,
so a re-run never creates a duplicate file for the same link.

Draft fields: source, title, link, pubDate, fetchedAt (UTC ISO),
rank (rounded score), summary ("" until scripts/summarize.py fills it),
humanizer (null until the summary step fills it).

Seen state is capped at the newest 5000 links so the file stays small.
Usage: python3 scripts/dedupe_rank.py
"""
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

try:
    from email.utils import parsedate_to_datetime
except ImportError:  # pragma: no cover
    parsedate_to_datetime = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FETCHED_PATH = os.path.join(ROOT, "data", "fetched.json")
STATE_PATH = os.path.join(ROOT, "state", "seen.json")
DRAFTS_DIR = os.path.join(ROOT, "drafts")
MAX_SEEN = 5000

SOURCE_WEIGHTS = {
    "The Verge": 1.0,
    "TechCrunch": 1.0,
    "Wired": 0.9,
    "Ars Technica": 0.9,
    "MIT Technology Review": 0.9,
    "Digiato": 1.0,
    "Zoomit": 1.0,
}


def parse_date(raw):
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        pass
    if parsedate_to_datetime:
        try:
            dt = parsedate_to_datetime(raw)
            if dt is not None and dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except (ValueError, TypeError):
            return None
    return None


def rank(item, now):
    weight = SOURCE_WEIGHTS.get(item["source"], 0.8)
    pub = parse_date(item.get("pubDate", ""))
    bonus = 0.0
    if pub is not None:
        age_hours = (now - pub).total_seconds() / 3600.0
        # Allow 1h of future clock skew: a slightly future-dated item is
        # still fresh.
        if -1 <= age_hours <= 24:
            bonus = 1.0
        elif 24 < age_hours <= 72:
            bonus = 0.5
    return round(weight + bonus, 2)


def load_state():
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            data = json.load(f)
        links = data.get("seen_links", [])
        return links if isinstance(links, list) else []
    except (OSError, ValueError):
        return []


def main():
    if not os.path.exists(FETCHED_PATH):
        print(f"No {FETCHED_PATH} — run scripts/fetch_rss.py first.",
              file=sys.stderr)
        return 1
    with open(FETCHED_PATH, encoding="utf-8") as f:
        items = json.load(f)
    seen = load_state()
    seen_set = set(seen)
    now = datetime.now(timezone.utc)
    fetched_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    date_prefix = now.strftime("%Y%m%d")
    os.makedirs(DRAFTS_DIR, exist_ok=True)
    new_count = 0
    for item in items:
        link = item["link"]
        if link in seen_set:
            continue
        seen_set.add(link)
        seen.append(link)
        digest = hashlib.sha1(link.encode("utf-8")).hexdigest()[:12]
        draft = {
            "source": item["source"],
            "title": item["title"],
            "link": link,
            "pubDate": item.get("pubDate", ""),
            "fetchedAt": fetched_at,
            "rank": rank(item, now),
            "summary": "",
            "humanizer": None,
        }
        path = os.path.join(DRAFTS_DIR, f"{date_prefix}-{digest}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(draft, f, ensure_ascii=False, indent=2)
        new_count += 1
    # Cap the seen list (keep newest) so state/seen.json stays small.
    seen = seen[-MAX_SEEN:]
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump({"seen_links": seen}, f, ensure_ascii=False, indent=2)
    print(f"Wrote {new_count} new drafts; {len(items)} fetched, "
          f"{len(seen)} links in seen state.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
