"""Build the static dashboard (site/index.html + site/data.csv) from the DB.

The site is fully static on purpose: visitors browse collected results without
burning API quota, and the page can be hosted anywhere (GitHub Pages, Render,
S3). Credibility comes from the data-integrity panel and the per-row
verification drawer, not from live queries.

Usage: python -m tracker.build_site
"""
import csv
import html
import json
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tracker.db import connect

# docs/ (not site/) because GitHub Pages serves from /root or /docs only
SITE_DIR = os.path.join(os.path.dirname(__file__), "..", "docs")
COLLECTION_INTERVAL_H = 24


def fetch_payload(conn):
    runs = [dict(r) for r in conn.execute("SELECT * FROM fetch_runs ORDER BY ts_utc")]
    checks = [dict(r) for r in conn.execute("SELECT * FROM checks ORDER BY ts_utc")]

    live_ok = [r for r in runs if r["layer"] == "live" and r["status"] == "success"]
    last_ok = live_ok[-1]["ts_utc"] if live_ok else None
    next_run = None
    if last_ok:
        nxt = datetime.strptime(last_ok, "%Y-%m-%dT%H:%M:%SZ") + timedelta(hours=COLLECTION_INTERVAL_H)
        next_run = nxt.strftime("%Y-%m-%dT%H:%M:%SZ")

    integrity = {
        "last_successful_fetch": last_ok,
        "next_scheduled_run": next_run,
        "runs_total": len(runs),
        "runs_success": sum(1 for r in runs if r["status"] == "success"),
        "runs_failed": sum(1 for r in runs if r["status"] == "failed"),
        "runs_retried_recovered": sum(
            1 for r in runs if r["status"] == "success" and r["attempts"] > 1),
        "live_runs": sum(1 for r in runs if r["layer"] == "live"),
        "seeded_runs": sum(1 for r in runs if r["layer"] == "seeded"),
        "tracked_depth": "Google page 1 (top ~10 organic results)",
        "source": "SerpAPI (google engine, gl=us) — raw API responses archived per run",
    }

    pairs = {}
    for c in checks:
        key = f"{c['keyword']}||{c['domain']}"
        pairs.setdefault(key, {"keyword": c["keyword"], "domain": c["domain"],
                               "history": []})
        run = next(r for r in runs if r["id"] == c["run_id"])
        pairs[key]["history"].append({
            "ts": c["ts_utc"], "position": c["position"], "status": c["status"],
            "layer": c["layer"], "matched_url": c["matched_url"],
            "title": c["title"], "snippet": c["snippet"],
            "serp_url": run["serp_url"], "attempts": run["attempts"],
            "error": run["error"], "raw_path": run["raw_path"],
        })
    return {"integrity": integrity, "pairs": list(pairs.values())}


def write_csv(payload, path):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp_utc", "keyword", "domain", "position", "status",
                    "data_layer", "matched_url", "fetch_attempts"])
        for p in payload["pairs"]:
            for h in p["history"]:
                w.writerow([h["ts"], p["keyword"], p["domain"],
                            h["position"] if h["position"] is not None else "",
                            h["status"], h["layer"], h["matched_url"] or "",
                            h["attempts"]])


TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SERP Rank Tracker — verifiable Google rankings</title>
<style>
  :root {{ --bg:#0f1420; --card:#171e2e; --line:#232d42; --tx:#dbe2ef; --dim:#8593ad;
          --ok:#3fb68b; --bad:#e05d5d; --warn:#d9a441; --seed:#5b8def; --live:#3fb68b; }}
  * {{ box-sizing:border-box; margin:0; }}
  body {{ background:var(--bg); color:var(--tx); font:15px/1.5 -apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif; }}
  .wrap {{ max-width:1080px; margin:0 auto; padding:28px 20px 60px; }}
  h1 {{ font-size:24px; letter-spacing:.2px; }}
  .tagline {{ color:var(--dim); margin:6px 0 22px; font-size:15px; }}
  .tagline b {{ color:var(--tx); }}
  .panel {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:18px 20px; margin-bottom:22px; }}
  .panel h2 {{ font-size:13px; text-transform:uppercase; letter-spacing:1.2px; color:var(--dim); margin-bottom:14px; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:14px; }}
  .stat .v {{ font-size:20px; font-weight:600; }}
  .stat .k {{ font-size:12px; color:var(--dim); margin-top:2px; }}
  .meta {{ margin-top:14px; padding-top:12px; border-top:1px solid var(--line); color:var(--dim); font-size:13px; }}
  .meta span {{ margin-right:18px; }}
  .legend i {{ display:inline-block; width:10px; height:10px; border-radius:50%; margin:0 5px 0 0; vertical-align:-1px; }}
  .legend .l-live i {{ background:var(--live); }}
  .legend .l-seed i {{ background:transparent; border:2px solid var(--seed); }}
  table {{ width:100%; border-collapse:collapse; }}
  th {{ text-align:left; font-size:12px; text-transform:uppercase; letter-spacing:1px; color:var(--dim); padding:8px 10px; border-bottom:1px solid var(--line); }}
  td {{ padding:11px 10px; border-bottom:1px solid var(--line); vertical-align:middle; }}
  tr.row {{ cursor:pointer; }} tr.row:hover td {{ background:#1b2438; }}
  .pos {{ font-size:21px; font-weight:700; width:54px; }}
  .delta-up {{ color:var(--ok); }} .delta-down {{ color:var(--bad); }} .delta-flat {{ color:var(--dim); }}
  .kw {{ font-weight:600; }} .dom {{ color:var(--dim); font-size:13px; }}
  .chip {{ font-size:11px; padding:2px 9px; border-radius:20px; border:1px solid var(--line); color:var(--dim); white-space:nowrap; }}
  .chip.ok {{ color:var(--ok); border-color:var(--ok); }}
  .chip.failed {{ color:var(--bad); border-color:var(--bad); }}
  .drawer td {{ background:#131a2a; padding:16px 18px; font-size:13px; }}
  .drawer dl {{ display:grid; grid-template-columns:170px 1fr; row-gap:7px; }}
  .drawer dt {{ color:var(--dim); }}
  .drawer a {{ color:var(--seed); word-break:break-all; }}
  .badge-seed {{ background:rgba(91,141,239,.15); color:var(--seed); font-size:11px; padding:2px 8px; border-radius:4px; }}
  .badge-live {{ background:rgba(63,182,139,.15); color:var(--live); font-size:11px; padding:2px 8px; border-radius:4px; }}
  .btn {{ display:inline-block; background:var(--seed); color:#fff; text-decoration:none; padding:8px 16px; border-radius:8px; font-size:14px; }}
  .foot {{ color:var(--dim); font-size:13px; margin-top:26px; }}
  .foot a {{ color:var(--seed); }}
  svg .seedline {{ stroke:var(--seed); stroke-dasharray:3 3; fill:none; stroke-width:1.5; }}
  svg .liveline {{ stroke:var(--live); fill:none; stroke-width:2; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>SERP Rank Tracker</h1>
  <p class="tagline">A real Google rank tracker that <b>records failures instead of inventing rankings</b> — every stored position traces back to an archived API response.</p>

  <div class="panel">
    <h2>Data integrity</h2>
    <div class="grid" id="stats"></div>
    <div class="meta" id="meta"></div>
    <div class="meta legend">
      <span class="l-live"><i></i>live collected data</span>
      <span class="l-seed"><i></i>seeded demo history (labeled synthetic backfill so the 2-week UI is visible — never mixed with live rows)</span>
    </div>
  </div>

  <div class="panel">
    <h2>Tracked rankings &nbsp;·&nbsp; click a row for verification details</h2>
    <table>
      <thead><tr><th>Pos</th><th>Δ</th><th>Keyword / domain</th><th>Trend (old → new)</th><th>Last checked (UTC)</th><th>Status</th></tr></thead>
      <tbody id="rows"></tbody>
    </table>
    <p style="margin-top:16px"><a class="btn" href="data.csv" download>Download CSV (full history, layer-labeled)</a></p>
  </div>

  <p class="foot">Built with Python + SerpAPI + SQLite → static HTML. Source &amp; setup: <a href="{repo_url}">GitHub repo</a>. Failed fetches stay FAILED after 3 labeled retry attempts; gaps are gaps, not interpolations.</p>
</div>
<script>
const DATA = {payload_json};

function fmt(ts) {{ return ts ? ts.replace('T',' ').replace('Z',' UTC') : '—'; }}

const ig = DATA.integrity;
const stats = [
  [fmt(ig.last_successful_fetch), 'last successful fetch'],
  [fmt(ig.next_scheduled_run), 'next scheduled run'],
  [ig.runs_success + ' / ' + ig.runs_total, 'runs succeeded / total'],
  [String(ig.runs_failed), 'runs failed (kept, never faked)'],
  [String(ig.runs_retried_recovered), 'retried → recovered'],
];
document.getElementById('stats').innerHTML = stats.map(
  s => `<div class="stat"><div class="v">${{s[0]}}</div><div class="k">${{s[1]}}</div></div>`).join('');
document.getElementById('meta').innerHTML =
  `<span>Source: ${{ig.source}}</span><span>Tracked depth: ${{ig.tracked_depth}}</span>` +
  `<span>${{ig.live_runs}} live runs · ${{ig.seeded_runs}} seeded runs</span>`;

function spark(hist) {{
  const W=190, H=34, P=3, n=hist.length;
  if (!n) return '';
  const x = i => P + i*(W-2*P)/Math.max(1,n-1);
  const y = p => P + (Math.min(p,10)-1)*(H-2*P)/9;
  let segs=[], pts=[];
  let path='', prevLayer=null;
  hist.forEach((h,i) => {{
    if (h.position==null) {{ path=''; prevLayer=null;
      if (h.status==='failed') pts.push(`<text x="${{x(i)-3}}" y="${{H-2}}" fill="#e05d5d" font-size="9">×</text>`);
      return; }}
    const cls = h.layer==='live' ? 'liveline' : 'seedline';
    if (path==='' || prevLayer!==cls) {{
      if (path) segs.push(`<path class="${{prevLayer}}" d="${{path}}"/>`);
      path = `M ${{x(i)}} ${{y(h.position)}}`;
    }} else path += ` L ${{x(i)}} ${{y(h.position)}}`;
    prevLayer = cls;
    if (h.layer==='live') pts.push(`<circle cx="${{x(i)}}" cy="${{y(h.position)}}" r="2.6" fill="#3fb68b"/>`);
  }});
  if (path) segs.push(`<path class="${{prevLayer}}" d="${{path}}"/>`);
  return `<svg width="${{W}}" height="${{H}}">${{segs.join('')}}${{pts.join('')}}</svg>`;
}}

function esc(s) {{ return (s||'').replace(/[&<>"]/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}})[c]); }}

const tbody = document.getElementById('rows');
DATA.pairs.forEach((p, idx) => {{
  const hist = p.history;
  const okHist = hist.filter(h => h.position != null);
  const cur = okHist.length ? okHist[okHist.length-1] : null;
  const prev = okHist.length > 1 ? okHist[okHist.length-2] : null;
  const last = hist[hist.length-1];
  let delta = '<span class="delta-flat">—</span>';
  if (cur && prev) {{
    const d = prev.position - cur.position;
    delta = d>0 ? `<span class="delta-up">▲ ${{d}}</span>` : d<0 ? `<span class="delta-down">▼ ${{-d}}</span>` : '<span class="delta-flat">＝</span>';
  }}
  const chipCls = last.status==='ok' ? 'ok' : last.status==='failed' ? 'failed' : '';
  const chipTxt = last.status==='ok' ? (last.layer==='live'?'ok · live':'ok · seeded')
                : last.status==='failed' ? 'FAILED (kept)' : 'not on page 1';
  const tr = document.createElement('tr');
  tr.className = 'row';
  tr.innerHTML = `<td class="pos">${{cur?('#'+cur.position):'—'}}</td><td>${{delta}}</td>
    <td><div class="kw">${{esc(p.keyword)}}</div><div class="dom">${{esc(p.domain)}}</div></td>
    <td>${{spark(hist)}}</td><td class="dom">${{fmt(last.ts)}}</td>
    <td><span class="chip ${{chipCls}}">${{chipTxt}}</span></td>`;
  const drawer = document.createElement('tr');
  drawer.className = 'drawer'; drawer.style.display = 'none';
  const v = cur || last;
  drawer.innerHTML = `<td colspan="6"><dl>
    <dt>Data layer</dt><dd>${{v.layer==='live'?'<span class="badge-live">live collected</span>':'<span class="badge-seed">seeded demo history</span>'}}</dd>
    <dt>Matched URL</dt><dd>${{v.matched_url?`<a href="${{esc(v.matched_url)}}" rel="nofollow">${{esc(v.matched_url)}}</a>`:'—'}}</dd>
    <dt>Result snippet</dt><dd>${{esc(v.snippet)||'—'}}</dd>
    <dt>Verify on Google</dt><dd><a href="${{esc(v.serp_url)}}" rel="nofollow">${{esc(v.serp_url)}}</a></dd>
    <dt>Fetched at</dt><dd>${{fmt(v.ts)}} · attempt(s): ${{v.attempts}}${{v.error?' · error: '+esc(v.error):''}}</dd>
    <dt>Raw API archive</dt><dd>${{v.raw_path?esc(v.raw_path)+' (in repo data pipeline, traceable per run)':'— (seeded rows have no raw payload, by design)'}}</dd>
  </dl></td>`;
  tr.onclick = () => {{ drawer.style.display = drawer.style.display==='none' ? '' : 'none'; }};
  tbody.appendChild(tr); tbody.appendChild(drawer);
}});
</script>
</body>
</html>
"""


def main():
    conn = connect()
    payload = fetch_payload(conn)
    os.makedirs(SITE_DIR, exist_ok=True)
    write_csv(payload, os.path.join(SITE_DIR, "data.csv"))
    out = TEMPLATE.format(
        payload_json=json.dumps(payload),
        repo_url="https://github.com/Tommyz123/serp-rank-tracker",
    )
    with open(os.path.join(SITE_DIR, "index.html"), "w") as f:
        f.write(out)
    n_pairs = len(payload["pairs"])
    print(f"[build_site] wrote docs/index.html ({n_pairs} tracked pairs) + docs/data.csv")


if __name__ == "__main__":
    main()
