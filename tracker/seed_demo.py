"""Generate clearly-labeled synthetic back-history for the demo dashboard.

Why this exists: a tracker that started collecting yesterday has a two-point
trend line, which demonstrates nothing. This script seeds ~2 weeks of history
so the UI has something to show — and every seeded row is stored with
layer='seeded', rendered with hollow markers and a "seeded demo history"
badge, and flagged in the CSV export. Seeded and live data are never blended:
the whole point of this tracker is that it does not invent rankings, so the
invented part announces itself.

The seed includes one failed run (all retries exhausted) and one
retried-then-recovered run, so the failure/retry audit trail is visible
without waiting for a real outage.

Usage: python -m tracker.seed_demo   (idempotent: wipes previous seeded rows)
"""
import os
import random
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tracker.db import connect
from tracker.collector import load_config, public_serp_url

SEED_DAYS = 14
FAILED_DAY = 5      # days-ago index that simulates a full outage
RETRIED_DAY = 3     # days-ago index that simulates retry-then-recover
rng = random.Random(42)


def main():
    conn = connect()
    cfg = load_config()
    conn.execute("DELETE FROM checks WHERE layer='seeded'")
    conn.execute("DELETE FROM fetch_runs WHERE layer='seeded'")

    first_live = conn.execute(
        "SELECT MIN(ts_utc) AS t FROM fetch_runs WHERE layer='live'").fetchone()["t"]
    anchor = (datetime.strptime(first_live, "%Y-%m-%dT%H:%M:%SZ")
              if first_live else datetime.now(timezone.utc).replace(tzinfo=None))

    for entry in cfg["keywords"]:
        keyword, domains = entry["keyword"], entry["domains"]
        # anchor each domain's walk at its current live position so the
        # seeded curve flows into the real data without a visible jump
        anchors = {}
        for d in domains:
            row = conn.execute(
                "SELECT position FROM checks WHERE keyword=? AND domain=? AND layer='live'"
                " AND position IS NOT NULL ORDER BY ts_utc LIMIT 1", (keyword, d)).fetchone()
            anchors[d] = row["position"] if row else rng.randint(3, 8)

        walks = {d: [anchors[d]] for d in domains}
        for _ in range(SEED_DAYS - 1):
            for d in domains:
                nxt = walks[d][-1] + rng.choice([-1, 0, 0, 0, 1])
                walks[d].append(max(1, min(10, nxt)))

        for days_ago in range(SEED_DAYS, 0, -1):
            ts = (anchor - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")
            serp_url = public_serp_url(keyword, cfg)
            if days_ago == FAILED_DAY:
                run_id = conn.execute(
                    "INSERT INTO fetch_runs (ts_utc, keyword, status, attempts, error,"
                    " serp_url, layer) VALUES (?, ?, 'failed', 3,"
                    " 'SerpAPI timeout after 3 attempts (seeded example)', ?, 'seeded')",
                    (ts, keyword, serp_url)).lastrowid
                for d in domains:
                    conn.execute(
                        "INSERT INTO checks (run_id, ts_utc, keyword, domain, status, layer)"
                        " VALUES (?, ?, ?, ?, 'failed', 'seeded')", (run_id, ts, keyword, d))
                continue
            attempts = 2 if days_ago == RETRIED_DAY else 1
            run_id = conn.execute(
                "INSERT INTO fetch_runs (ts_utc, keyword, status, attempts, serp_url,"
                " result_depth, layer) VALUES (?, ?, 'success', ?, ?, 9, 'seeded')",
                (ts, keyword, attempts, serp_url)).lastrowid
            for d in domains:
                pos = walks[d][days_ago - 1]
                conn.execute(
                    "INSERT INTO checks (run_id, ts_utc, keyword, domain, position,"
                    " status, layer) VALUES (?, ?, ?, ?, ?, 'ok', 'seeded')",
                    (run_id, ts, keyword, d, pos))
    conn.commit()
    n = conn.execute("SELECT COUNT(*) AS c FROM checks WHERE layer='seeded'").fetchone()["c"]
    print(f"[seed_demo] seeded {n} check rows across {SEED_DAYS} days "
          f"(1 failed run + 1 retried run per keyword, all labeled layer='seeded')")


if __name__ == "__main__":
    main()
