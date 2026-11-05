# Parsa Mag — fallback news pipeline (drafts only)

A GitHub Actions fallback for the Parsa Mag news pipeline, running in
parallel with the self-hosted n8n route. It does one job: regularly fetch
tech news, dedupe and rank it, optionally summarize it with Gemini, and
store **drafts** in this repo for a human editor.

## Schedule

- Every 30 minutes via GitHub's own scheduler (`*/30 * * * *` in
  `.github/workflows/news-pipeline.yml`), plus manual runs from the repo's
  **Actions** tab (`workflow_dispatch`).
- No Muse agent cron is involved anywhere in this pipeline.

## How it works

1. `scripts/fetch_rss.py` — fetches 7 feeds (The Verge, TechCrunch,
   Wired, Ars Technica, MIT Technology Review, Digiato, Zoomit) and writes
   `data/` (transient, git-ignored). Stdlib only. Handles both RSS
   (`<item>`) and Atom (`<entry>`, which is what The Verge serves).
   A failed feed is logged and skipped; it never kills the run.
2. `scripts/dedupe_rank.py` — drops items whose link is already in
   `state/seen.json` (link-based dedupe, capped at the newest 5000 links),
   ranks the rest, and writes one JSON file per new draft under `drafts/`.
3. `scripts/summarize.py` — fills empty `summary` fields via Gemini
   (`gemini-2.5-flash`). Runs only when the `GEMINI_API_KEY` repository
   secret exists; otherwise it exits 0 and raw drafts are still stored.
4. The workflow commits `drafts/` + `state/seen.json` back to this repo.
   When nothing is new, it logs "No new drafts" and does not fail.

## Draft format

One JSON file per draft: `drafts/<UTC-date>-<sha1(link)[:12]>.json`

```json
{
  "source": "TechCrunch",
  "title": "Example headline",
  "link": "https://example.com/post",
  "pubDate": "Mon, 01 Jan 2026 00:00:00 GMT",
  "fetchedAt": "2026-01-01T00:00:00Z",
  "rank": 1.9,
  "summary": "",
  "humanizer": null
}
```

Ranking: `score = source_weight + recency_bonus` (weights in
`scripts/dedupe_rank.py`; +1.0 if published within the last 24h, +0.5
within 72h, else 0; 1h of future clock skew still counts as fresh).
After summarization, `summary` holds a 2–4 sentence Persian summary and
`humanizer` holds the gate flags (`has_first_person_claim`,
`has_unverified_number`, `needs_human_review`) so no summary reaches an
editor unchecked.

## What works without the secret vs with it

- **Without `GEMINI_API_KEY`:** fetch + dedupe + rank + store raw drafts.
  Everything else works; summaries stay empty.
- **With `GEMINI_API_KEY`:** the same, plus Persian summaries and
  humanizer-gate flags on new drafts.

## Adding the Gemini secret (user step, GitHub UI only)

Repo → **Settings → Secrets and variables → Actions → New repository
secret**, name `GEMINI_API_KEY`, value your Gemini API key. The key is
never written in chat, in any file, or in any commit — it lives only as
a GitHub secret. This is separate from the n8n route's Gemini credential
(a different secret home for each route).

## Hard limits

- **No auto-publish to the site:** no deploy or upload step to Botkeep,
  Wispbyte, or any host exists in this repo.
- **No Telegram send step of any kind.**
- **No credentials or API keys in any file, commit message, or log.**
- **No Muse agent cron:** GitHub's own scheduler only.
