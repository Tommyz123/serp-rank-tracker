"""SQLite schema and helpers for the rank tracker.

Two tables:
  fetch_runs — one row per SerpAPI request (the audit trail: every attempt,
               success or failure, is recorded; failures are never backfilled).
  checks     — one row per (run, tracked domain): the parsed ranking result.

Every row carries a `layer` column: 'live' (real SerpAPI fetch) or
'seeded' (clearly-labeled synthetic history used to demonstrate the UI).
The two layers are never mixed silently — the dashboard renders them
with distinct markers and the CSV export includes the column.
"""
import os
import sqlite3

DB_PATH = os.environ.get(
    "TRACKER_DB", os.path.join(os.path.dirname(__file__), "..", "data", "tracker.db")
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS fetch_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_utc TEXT NOT NULL,
    keyword TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('success', 'failed')),
    attempts INTEGER NOT NULL DEFAULT 1,
    error TEXT,
    serp_url TEXT,
    raw_path TEXT,
    result_depth INTEGER,
    layer TEXT NOT NULL DEFAULT 'live' CHECK (layer IN ('live', 'seeded'))
);
CREATE TABLE IF NOT EXISTS checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES fetch_runs(id),
    ts_utc TEXT NOT NULL,
    keyword TEXT NOT NULL,
    domain TEXT NOT NULL,
    position INTEGER,
    matched_url TEXT,
    title TEXT,
    snippet TEXT,
    status TEXT NOT NULL CHECK (status IN ('ok', 'not_found', 'failed')),
    layer TEXT NOT NULL DEFAULT 'live' CHECK (layer IN ('live', 'seeded'))
);
CREATE INDEX IF NOT EXISTS idx_checks_kd ON checks(keyword, domain, ts_utc);
"""


def connect(db_path=None):
    path = db_path or DB_PATH
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn
