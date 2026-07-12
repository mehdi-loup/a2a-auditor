"""SQLite cache for raw ACP data. Schema per SPEC.md §6."""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "acp.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS agents (
    agent_id       TEXT PRIMARY KEY,
    name           TEXT,
    endpoints_json TEXT,
    first_seen     TEXT,
    jobs_total     INTEGER
);

CREATE TABLE IF NOT EXISTS jobs (
    job_id              TEXT PRIMARY KEY,
    agent_id            TEXT,
    requester_id        TEXT,
    ts_request          TEXT,
    ts_delivery         TEXT,
    job_type            TEXT,
    price_usd           REAL,
    request_uri         TEXT,
    deliverable_uri     TEXT,
    status              TEXT,
    chain_evidence_json TEXT,
    raw_json            TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_jobs_agent ON jobs(agent_id);

CREATE TABLE IF NOT EXISTS pulls (
    pull_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT NOT NULL,
    agent_id    TEXT,
    pulled_at   TEXT NOT NULL,
    params_json TEXT,
    n_records   INTEGER
);
"""


def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    return conn


if __name__ == "__main__":
    conn = connect()
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    print(f"initialized {DB_PATH} with tables: {', '.join(tables)}")
