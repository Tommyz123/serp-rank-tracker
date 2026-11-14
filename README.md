# SERP Rank Tracker

A real Google rank tracker that **records failures instead of inventing rankings**.

Live demo: https://tommyz123.github.io/serp-rank-tracker/ *(static dashboard built from collected data)*
Case study: [CASE_STUDY.md](CASE_STUDY.md) — the design decisions and what they mean for a client

## Why another rank tracker

Most homemade rank trackers quietly fill gaps: a fetch fails, a domain drops off
the page, and the chart still shows a smooth line. This one treats "no data" as
a first-class result:

- A failed fetch is stored as **FAILED** with its error and attempt count (3
  labeled retries, then it stays failed). Gaps are gaps, not interpolations.
- Every stored position traces back to an **archived raw API response**, so any
  number on the dashboard can be audited down to the exact payload it came from.
- The demo's synthetic back-history is stored and rendered as a separate
  `seeded` data layer — clearly badged in the UI and flagged in the CSV export,
  never blended with live rows.

## What it does

1. **Collect** — `tracker/collector.py` queries Google (via SerpAPI) for each
   configured keyword, matches your tracked domains against the organic
   results, and stores positions + evidence (URL, title, snippet) in SQLite.
2. **Publish** — `tracker/build_site.py` renders a fully static dashboard
   (`docs/index.html`) with a data-integrity panel, trend sparklines, per-row
   verification details, and a CSV export. Static on purpose: visitors don't
   burn API quota, and the page hosts anywhere.

## Setup

```bash
git clone https://github.com/Tommyz123/serp-rank-tracker
cd serp-rank-tracker
cp .env.example .env        # add your SerpAPI key (free tier: 250 searches/mo)
```

No third-party Python dependencies — standard library only (Python 3.10+).

## Configure

`config.json`:

```json
{
  "gl": "us",
  "hl": "en",
  "keywords": [
    { "keyword": "emergency plumber denver", "domains": ["teamdavelogan.com", "rotorooter.com"] }
  ]
}
```

One SerpAPI search covers **all** domains tracked under that keyword (the whole
result page is parsed once), so quota cost = keywords × runs, regardless of how
many domains you watch.

## Run

```bash
export $(grep -v '^#' .env | xargs)
python3 -m tracker.collector      # fetch + store (one search per keyword)
python3 -m tracker.build_site     # regenerate docs/index.html + docs/data.csv
```

Schedule both with cron (daily is plenty for rank tracking):

```cron
10 11 * * *  cd /path/to/serp-rank-tracker && export $(grep -v '^#' .env | xargs) && python3 -m tracker.collector && python3 -m tracker.build_site
```

## Re-reading archived responses

`tracker/reparse.py` rebuilds result rows from the responses saved in
`data/raw/`, with no new API calls:

```bash
python3 -m tracker.reparse          # show what would change
python3 -m tracker.reparse --write  # apply
python3 -m unittest discover tests  # tests for matching and re-reading
```

It was used twice on 2026-11-14:

- **A matching bug.** Some SerpAPI responses put a Google redirect in `link`
  (`/goto?url=...`) instead of the site's own URL. The collector matched sites
  by `link` only, so on those results a site that was on the page was stored as
  "not found". 14 rows between 2026-09-08 and 2026-11-14 were wrong (13 "not
  found" that were on the page, 1 position that was #1 and stored as #2). The
  collector now reads the site from `displayed_link` when `link` is a redirect,
  and those rows were corrected from the same archived responses.
- **Changed demo sites.** Two of the demo sites (ramoslaw.com, phillipslaw.com)
  had not appeared on page 1 for weeks, and others appeared only on some days.
  Five sites were replaced in `config.json` with sites that appeared on page 1
  more often in the archived results. Their history was read from the responses
  already archived on each day, so it is real data for those days, not seeded.
  Note that these sites were chosen after looking at that history. The removed
  sites stay in the database and in the CSV export (`currently_tracked = no`).

Known limit: when `link` is a redirect and `displayed_link` is not an address
(social results show "610+ followers"), the site cannot be identified and is
not matched.

## How to read the dashboard

- **Pos** is the result of the latest check only. If the latest check did not
  find the site, Pos shows "—" and, in small text, the last position that was
  found and its date.
- **Δ** compares the latest check with the check before it, when both found the site.
- Results vary from day to day: the searches are sent without a fixed location,
  and Google does not return the same page every time.

`tracker/seed_demo.py` (optional) generates the labeled 14-day demo backfill —
useful for previewing the UI, safe to skip in real deployments.

## Data model

```
fetch_runs — one row per API request: timestamp, status (success/failed),
             attempts, error, public SERP URL, raw archive path, result depth
checks     — one row per (run × tracked domain): position, matched URL,
             title, snippet, status (ok / not_found / failed), data layer
```

Tracked depth is recorded per run (`result_depth`) rather than assumed — the
dashboard reports what was actually parsed (Google currently serves ~10 organic
results on page 1).

## Extending

The core pipeline stays deliberately small. Natural client-specific
extensions: alert emails on rank drops, competitor columns, multi-location
tracking, deeper pagination, scheduled reports. Each is a straightforward
addition on top of the same runs/checks schema.
