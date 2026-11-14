"""Rebuild `checks` rows from the archived SerpAPI responses in data/raw/.

Two uses:
  1. A site was added to config.json later: its history is filled in from the
     responses that were already archived on each day (no new API calls).
  2. The way a response is read was fixed (for example: `link` became a Google
     redirect): the affected days are read again from the same archived files.

Only live runs are touched. Failed runs stay failed (a site added later gets a
'failed' row for them),
seeded rows are never touched, and nothing is guessed: a row can only get what
the archived response of that run contains.

Usage:
    python -m tracker.reparse           # show what would change
    python -m tracker.reparse --write   # apply
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tracker.collector import load_config, parse_check
from tracker.db import connect

ROOT = os.path.join(os.path.dirname(__file__), "..")
FIELDS = ("status", "position", "matched_url", "title", "snippet")


def reparse(conn, cfg, write=False):
    domains_by_kw = {e["keyword"]: e["domains"] for e in cfg["keywords"]}
    added, changed, missing = [], [], 0
    runs = conn.execute(
        "SELECT * FROM fetch_runs WHERE layer='live' AND status='success'"
        " ORDER BY ts_utc").fetchall()
    for run in runs:
        domains = domains_by_kw.get(run["keyword"])
        if not domains:
            continue
        path = os.path.join(ROOT, run["raw_path"] or "")
        if not run["raw_path"] or not os.path.exists(path):
            missing += 1
            continue
        with open(path) as f:
            organic = json.load(f).get("organic_results", [])
        for d in domains:
            new = parse_check(organic, d)
            row = conn.execute(
                "SELECT * FROM checks WHERE run_id=? AND domain=?",
                (run["id"], d)).fetchone()
            if row is None:
                added.append((run["ts_utc"], run["keyword"], d, new["status"], new["position"]))
                if write:
                    conn.execute(
                        "INSERT INTO checks (run_id, ts_utc, keyword, domain, position,"
                        " matched_url, title, snippet, status)"
                        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (run["id"], run["ts_utc"], run["keyword"], d, new["position"],
                         new["matched_url"], new["title"], new["snippet"], new["status"]))
            elif (row["status"], row["position"]) != (new["status"], new["position"]):
                changed.append((run["ts_utc"], run["keyword"], d,
                                f"{row['status']} {row['position']}",
                                f"{new['status']} {new['position']}"))
                if write:
                    conn.execute(
                        "UPDATE checks SET position=?, matched_url=?, title=?, snippet=?,"
                        " status=? WHERE id=?",
                        (new["position"], new["matched_url"], new["title"],
                         new["snippet"], new["status"], row["id"]))
    # A failed run has no response to read. A site added later still gets a
    # 'failed' row for it, so the gap shows in its history like everyone else's.
    failed = conn.execute(
        "SELECT * FROM fetch_runs WHERE layer='live' AND status='failed'").fetchall()
    for run in failed:
        for d in domains_by_kw.get(run["keyword"], []):
            if conn.execute("SELECT 1 FROM checks WHERE run_id=? AND domain=?",
                            (run["id"], d)).fetchone() is None:
                added.append((run["ts_utc"], run["keyword"], d, "failed", None))
                if write:
                    conn.execute(
                        "INSERT INTO checks (run_id, ts_utc, keyword, domain, status)"
                        " VALUES (?, ?, ?, ?, 'failed')",
                        (run["id"], run["ts_utc"], run["keyword"], d))
    if write:
        conn.commit()
    return added, changed, missing


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="apply the changes")
    args = ap.parse_args()
    added, changed, missing = reparse(connect(), load_config(), write=args.write)
    for c in changed:
        print(f"[reparse] changed {c[0]} '{c[1]}' {c[2]}: {c[3]} -> {c[4]}")
    print(f"[reparse] rows added: {len(added)}, rows changed: {len(changed)}, "
          f"runs without an archived response: {missing}"
          + ("" if args.write else "  (dry run, use --write to apply)"))


if __name__ == "__main__":
    main()
