# SERP Rank Tracker: Auditable Daily Google Ranking Reports

> A Google rank tracker that **records failures instead of inventing rankings** — every live-collected number on the dashboard can be audited down to the raw API response it came from.

**See it in 30 seconds:** open the [live dashboard](https://tommyz123.github.io/serp-rank-tracker/), read the Data Integrity panel at the top, click any row's verification drawer to see the evidence behind the number, download the CSV. Code: [github.com/Tommyz123/serp-rank-tracker](https://github.com/Tommyz123/serp-rank-tracker)

*Portfolio demo running on real data: live daily collection via SerpAPI started 2026-07-18, so the live history grows every day. Keywords are public sample queries on public domains — no client data, no private analytics.*

---

## What it does

- **Collects daily** — queries Google (via SerpAPI) for each configured keyword, matches tracked domains against the organic results, and stores positions *with evidence* (matched URL, title, snippet) in SQLite.
- **Publishes a static dashboard** — data-integrity panel, trend sparklines, per-row verification drawer, CSV export.
- **Runs itself** — a daily cron job collects, rebuilds the page, and publishes; after setup it's a low-maintenance pipeline.

---

## What this means for a client

- **Replaces manual rank checking** with a scheduled pipeline — no one has to remember to look.
- **A failed data pull is never mistaken for a ranking drop.** Failures are stored and shown as gaps, not smoothed into the trend line — so you don't panic (or celebrate) over an artifact.
- **Every reported position carries an audit trail** back to the archived raw response — agencies can show clients *why* a number is trustworthy, not just assert it.
- **Reports export cleanly** (CSV with full provenance columns) and the dashboard hosts free as a static page.
- **Easily customized** — keywords, locations, tracked domains, competitors, alerting — on top of the same small schema.

---

## The problem it solves

Rank trackers tend to fail quietly: a fetch times out and the chart still shows a smooth line; demo data blends silently with measured data; "top-100 tracking" claims outrun what the parser actually saw. For anyone buying SEO reporting, the core question is **"are these numbers real?"** This project makes the honest answer *structural* — enforced by the schema and the pipeline, not by good intentions.

---

## How integrity is enforced

- **Failures are first-class rows.** A fetch gets 3 labeled retry attempts; if all fail, the run is stored as `failed` with its error message and attempt count, and a failed check is written for every tracked domain. Gaps render as gaps — nothing is interpolated or carried forward.
- **Every live number has a paper trail.** Each successful run archives the **raw API response to disk** and stores its path plus the public SERP URL beside the parsed result. The UI exposes this as a per-row verification drawer. (Seeded demo rows are labeled synthetic and excluded from live claims.)
- **Synthetic history is a separate data layer by construction.** The demo's two-week back-history carries `layer='seeded'`, enforced by a SQLite `CHECK` constraint, rendered with distinct hollow markers and a badge, and flagged in the CSV. Live and seeded rows are never blended — and the seeded history deliberately includes a failed run, so the demo shows its own failure handling.
- **Depth is recorded, not asserted.** Each run stores `result_depth` — how many organic results were actually parsed — for auditing. The demo tracks and labels Google page 1.

---

## Kept deliberately small — on purpose

- **Static dashboard**: free hosting, instant loads, and visitors never burn API quota.
- **Python standard library only**: nothing to break, trivial to hand off, runs anywhere Python runs.
- **Quota-aware**: one API search covers *all* domains tracked under a keyword, so cost scales with keywords × runs, not with how many domains you watch.

---

## Verified before shipping

A five-point checklist, run before the demo went live:

1. **Storage ↔ archive audit** — stored positions cross-checked row-by-row against the archived raw API responses.
2. **Export completeness** — CSV verified to contain every check row, including failed and seeded ones, with the layer column intact.
3. **Layer purity** — confirmed seeded rows cannot leak into live aggregates, end-to-end.
4. **Browser test** — zero JS console errors; every verification drawer and export control functional.
5. **Failure-path test** — collector run against bad input to confirm a real failure is *recorded as a failure*, not papered over.

The design was also pressure-tested against likely buyer objections before build — which is why the integrity panel sits at the top of the page and the scope stays inside what a visitor can verify in 30 seconds.

---

## Natural extensions for client work

Alert emails on rank drops · competitor columns · multi-location tracking · deeper pagination · scheduled PDF/email reports — each a straightforward addition on the same runs/checks schema.

### Tech stack
Python 3.10+ (standard library only) · SQLite · SerpAPI · GitHub Pages · cron
