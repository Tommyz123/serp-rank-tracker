"""Fetch Google rankings for configured keyword x domain pairs via SerpAPI.

Design rule, stated once and enforced everywhere: this tracker records what
actually happened. A failed fetch is stored as FAILED (with the error and the
attempt count) — it is never retried into silence, interpolated, or replaced
with a guessed position. "No data" is a first-class result.

Usage:
    SERPAPI_KEY=... python -m tracker.collector          # collect all keywords
    SERPAPI_KEY=... python -m tracker.collector --dry    # parse config only

Raw SerpAPI responses are archived under data/raw/ so every stored position
can be traced back to the exact API payload it came from.
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tracker.db import connect

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config.json")
RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
MAX_ATTEMPTS = 3
RETRY_WAIT_S = 20


def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def serpapi_search(keyword, cfg, api_key):
    params = {
        "engine": "google",
        "q": keyword,
        "api_key": api_key,
        "num": "100",
        "hl": cfg.get("hl", "en"),
        "gl": cfg.get("gl", "us"),
        "location": cfg.get("location", ""),
    }
    url = "https://serpapi.com/search.json?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=60) as r:
        data = json.loads(r.read())
    if data.get("error"):
        raise RuntimeError(data["error"])
    return data


def public_serp_url(keyword, cfg):
    """The plain Google URL a human can open to eyeball the result."""
    q = urllib.parse.urlencode({"q": keyword, "hl": cfg.get("hl", "en"), "gl": cfg.get("gl", "us")})
    return "https://www.google.com/search?" + q


def match_domain(organic, domain):
    """First organic result whose link belongs to `domain` (or a subdomain)."""
    for item in organic:
        host = urllib.parse.urlparse(item.get("link", "")).netloc.lower()
        if host == domain or host.endswith("." + domain):
            return item
    return None


def archive_raw(keyword, ts, data):
    os.makedirs(RAW_DIR, exist_ok=True)
    safe = "".join(c if c.isalnum() else "_" for c in keyword)[:50]
    path = os.path.join(RAW_DIR, f"{ts.replace(':', '')}_{safe}.json")
    with open(path, "w") as f:
        json.dump(data, f)
    return os.path.relpath(path, os.path.join(os.path.dirname(__file__), ".."))


def collect(conn, cfg, api_key):
    for entry in cfg["keywords"]:
        keyword, domains = entry["keyword"], entry["domains"]
        ts = now_utc()
        data, error, attempts = None, None, 0
        for attempts in range(1, MAX_ATTEMPTS + 1):
            try:
                data = serpapi_search(keyword, cfg, api_key)
                break
            except Exception as e:
                error = str(e)
                print(f"[collector] attempt {attempts}/{MAX_ATTEMPTS} failed for "
                      f"'{keyword}': {error}", file=sys.stderr)
                if attempts < MAX_ATTEMPTS:
                    time.sleep(RETRY_WAIT_S)

        serp_url = public_serp_url(keyword, cfg)
        if data is None:
            run_id = conn.execute(
                "INSERT INTO fetch_runs (ts_utc, keyword, status, attempts, error, serp_url)"
                " VALUES (?, ?, 'failed', ?, ?, ?)",
                (ts, keyword, attempts, error, serp_url)).lastrowid
            for d in domains:
                conn.execute(
                    "INSERT INTO checks (run_id, ts_utc, keyword, domain, status)"
                    " VALUES (?, ?, ?, ?, 'failed')", (run_id, ts, keyword, d))
            conn.commit()
            continue

        raw_path = archive_raw(keyword, ts, data)
        organic = data.get("organic_results", [])
        # result_depth records how deep the SERP actually went — the dashboard
        # states "tracked depth" from this instead of claiming an untested top-100
        run_id = conn.execute(
            "INSERT INTO fetch_runs (ts_utc, keyword, status, attempts, serp_url,"
            " raw_path, result_depth) VALUES (?, ?, 'success', ?, ?, ?, ?)",
            (ts, keyword, attempts, serp_url, raw_path, len(organic))).lastrowid
        for d in domains:
            hit = match_domain(organic, d)
            if hit:
                conn.execute(
                    "INSERT INTO checks (run_id, ts_utc, keyword, domain, position,"
                    " matched_url, title, snippet, status)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ok')",
                    (run_id, ts, keyword, d, hit.get("position"), hit.get("link"),
                     hit.get("title"), (hit.get("snippet") or "")[:300]))
            else:
                conn.execute(
                    "INSERT INTO checks (run_id, ts_utc, keyword, domain, status)"
                    " VALUES (?, ?, ?, ?, 'not_found')", (run_id, ts, keyword, d))
        conn.commit()
        print(f"[collector] '{keyword}' ok (attempt {attempts}), "
              f"{len(organic)} organic results")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="validate config, no API calls")
    args = ap.parse_args()
    cfg = load_config()
    if args.dry:
        print(json.dumps(cfg, indent=2))
        return
    api_key = os.environ.get("SERPAPI_KEY")
    if not api_key:
        sys.exit("SERPAPI_KEY env var is required (see .env.example)")
    conn = connect()
    collect(conn, cfg, api_key)


if __name__ == "__main__":
    main()
