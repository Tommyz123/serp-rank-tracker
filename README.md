# SERP Rank Tracker

A real Google rank tracker that **records failures instead of inventing rankings**.

Live demo: https://tommyz123.github.io/serp-rank-tracker/ *(static dashboard built from collected data)*

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
    { "keyword": "emergency plumber denver", "domains": ["blueskyplumbing.com", "rotorooter.com"] }
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
