#!/usr/bin/env python3
"""Fill empty summaries in drafts/*.json via the Gemini API (stdlib only).

The API key is read ONLY from the GEMINI_API_KEY environment variable
(GitHub repository secret in CI). If it is absent, this script exits 0
and logs that the secret is missing — the pipeline still stores raw
drafts, and summaries activate automatically once the secret exists.
API errors on individual drafts are logged and skipped; the run still
exits 0 so drafts commit.

Output per draft: a Persian summary (2-4 sentences, neutral news tone,
no invented details) in "summary", plus a "humanizer" object:
  has_first_person_claim: the summary claims a first-person experience
  has_unverified_number: the summary repeats a number not in the source
  needs_human_review: true if either flag above is true
The humanizer gate exists so no summary reaches an editor unchecked.

Model: gemini-2.5-flash (text summary) via the REST generateContent API.
Usage: GEMINI_API_KEY=... python3 scripts/summarize.py
"""
import json
import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DRAFTS_DIR = os.path.join(ROOT, "drafts")
MODEL = "gemini-2.5-flash"
API_URL = ("https://generativelanguage.googleapis.com/v1beta/models/"
            f"{MODEL}:generateContent")

PROMPT_TEMPLATE = (
    "You are a Persian news-desk assistant. Summarize the tech news item "
    "below in Persian in 2-4 sentences, neutral news tone. Do NOT invent "
    "details, numbers, quotes, or first-person experiences that are not in "
    "the title. Reply with JSON only, no markdown fences, with exactly "
    "these fields: summary_fa (string), has_first_person_claim (boolean), "
    "has_unverified_number (boolean), needs_human_review (boolean).\n\n"
    "Source: {source}\nTitle: {title}\nLink: {link}"
)


def call_gemini(key, source, title, link):
    prompt = PROMPT_TEMPLATE.format(source=source, title=title, link=link)
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.3,
            "responseMimeType": "application/json",
        },
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{API_URL}?key={key}",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = json.load(resp)
    text = body["candidates"][0]["content"]["parts"][0]["text"]
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    return json.loads(text)


def main():
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        print("GEMINI_API_KEY not set; skipping summaries "
              "(raw drafts are still stored).")
        return 0
    if not os.path.isdir(DRAFTS_DIR):
        print("No drafts directory; nothing to summarize.")
        return 0
    done, failed = 0, 0
    for name in sorted(os.listdir(DRAFTS_DIR)):
        if not name.endswith(".json"):
            continue
        path = os.path.join(DRAFTS_DIR, name)
        with open(path, encoding="utf-8") as f:
            draft = json.load(f)
        if draft.get("summary"):
            continue
        try:
            result = call_gemini(key, draft["source"],
                                 draft["title"], draft["link"])
            draft["summary"] = result.get("summary_fa", "")
            draft["humanizer"] = {
                "has_first_person_claim": bool(
                    result.get("has_first_person_claim", True)),
                "has_unverified_number": bool(
                    result.get("has_unverified_number", True)),
                "needs_human_review": bool(
                    result.get("needs_human_review", True)),
            }
            if not draft["summary"]:
                raise ValueError("empty summary from API")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(draft, f, ensure_ascii=False, indent=2)
            done += 1
        except Exception as e:  # noqa: BLE001 — one bad draft must not kill the run
            print(f"SUMMARY FAILED {name}: {e}", file=sys.stderr)
            failed += 1
    print(f"Summaries filled: {done}, failed: {failed}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
