"""Assessment pipeline (SPEC §4 Phase 2): sampling → V1–V4 → scoring v0.

Subscores (0–100), computed over the seeded sample:
  completion   100 × delivered / sampled                     (V1)
  conformance  100 × mean(judge score)/10 over delivered     (V3)
  evidence     100 × (deliverable present AND settlement tx
                verified on Base) / delivered                (V2)
  latency      100 × fraction of delivered jobs with
                duration ≤ 2× their job-type median          (V4, provisional)

composite = Σ weight_i × subscore_i  (weights in config.yaml, provisional)

Determinism: seeded sample anchored to cache; judge + chain results cached in
SQLite; run twice on the same cache ⇒ identical numbers.
"""

import json
import sys
from datetime import datetime, timezone
from statistics import median

from src.chain_verify import ChainVerifier
from src.classify import duration_seconds, load_config
from src.db import connect
from src.judge import Judge, judge_input
from src.sample import sample_jobs

SCHEMA = """
CREATE TABLE IF NOT EXISTS assessments (
    agent_id TEXT, seed INTEGER, config_hash TEXT, n_sampled INTEGER,
    n_delivered INTEGER, completion REAL, conformance REAL, evidence REAL,
    latency REAL, composite REAL, window_start TEXT, window_end TEXT,
    run_at TEXT,
    PRIMARY KEY (agent_id, seed, config_hash)
);
CREATE TABLE IF NOT EXISTS assessment_jobs (
    agent_id TEXT, job_id TEXT, delivered INTEGER, judge_score INTEGER,
    judge_reason TEXT, evidence_verified INTEGER, duration_s REAL,
    latency_ratio REAL,
    PRIMARY KEY (agent_id, job_id)
);
"""


def resolve_agent(conn, query: str) -> str:
    if query.startswith("0x"):
        return query.lower()
    row = conn.execute(
        "SELECT agent_id FROM agents WHERE LOWER(name) LIKE ? ORDER BY agent_id",
        (f"%{query.lower()}%",)).fetchone()
    if not row:
        raise SystemExit(f"agent {query!r} not in cache")
    return row[0]


def config_hash() -> str:
    from src.census import config_hash as ch
    return ch()


def run_assessment(conn, agent_query: str, config: dict = None) -> dict:
    cfg = config or load_config()
    conn.executescript(SCHEMA)
    agent_id = resolve_agent(conn, agent_query)
    agent_names = [n for (n,) in conn.execute(
        "SELECT name FROM agents WHERE name IS NOT NULL")]

    job_ids = sample_jobs(conn, agent_id, cfg)
    judge = Judge(conn, cfg)
    chain = ChainVerifier(conn)

    # Job-type medians from ALL cached delivered jobs of this agent (stable
    # baseline independent of the sample).
    med_rows = conn.execute(
        "SELECT job_type, ts_request, ts_delivery FROM jobs WHERE agent_id=? "
        "AND status='COMPLETED' ORDER BY job_id", (agent_id,)).fetchall()
    by_type = {}
    for jtype, a, b in med_rows:
        d = duration_seconds(a, b)
        if d is not None and d >= 0:
            by_type.setdefault(jtype, []).append(d)
    type_median = {k: median(sorted(v)) for k, v in by_type.items()}

    details = []
    for jid in job_ids:
        status, jtype, ts_req, ts_del, raw = conn.execute(
            "SELECT status, job_type, ts_request, ts_delivery, raw_json "
            "FROM jobs WHERE job_id=?", (jid,)).fetchone()
        raw = json.loads(raw)
        delivered = status == "COMPLETED"

        jscore = jreason = None
        verified = None
        ratio = None
        dur = duration_seconds(ts_req, ts_del)
        if delivered:
            prompt = judge_input(raw, agent_names)
            if prompt:
                r = judge.score(jid, prompt, pass_n=1)
                jscore, jreason = r["score"], r["reason"]
            ev = chain.verify_job(raw)
            verified = int(bool(prompt) and ev["verified"])
            m = type_median.get(jtype)
            if dur is not None and m:
                ratio = dur / m
        details.append((agent_id, jid, int(delivered), jscore, jreason,
                        verified, dur, ratio))

    n = len(details)
    delivered_rows = [d for d in details if d[2]]
    nd = len(delivered_rows)
    scores = [d[3] for d in delivered_rows if d[3] is not None]
    ratios = [d[7] for d in delivered_rows if d[7] is not None]

    completion = 100 * nd / n if n else 0.0
    conformance = 100 * (sum(scores) / len(scores)) / 10 if scores else 0.0
    evidence = 100 * sum(d[5] or 0 for d in delivered_rows) / nd if nd else 0.0
    latency = 100 * sum(1 for r in ratios if r <= 2.0) / len(ratios) if ratios else 0.0

    w = cfg["weights"]
    composite = (w["completion"] * completion + w["conformance"] * conformance
                 + w["evidence"] * evidence + w["latency"] * latency)

    win = conn.execute(
        "SELECT MIN(ts_request), MAX(ts_request) FROM jobs WHERE job_id IN "
        f"({','.join('?' * n)})", job_ids).fetchone()

    conn.executemany(
        "INSERT OR REPLACE INTO assessment_jobs VALUES (?,?,?,?,?,?,?,?)",
        details)
    conn.execute(
        "INSERT OR REPLACE INTO assessments VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (agent_id, cfg["seed"], config_hash(), n, nd,
         round(completion, 4), round(conformance, 4), round(evidence, 4),
         round(latency, 4), round(composite, 4), win[0], win[1],
         datetime.now(timezone.utc).isoformat()))
    conn.commit()

    return {"agent_id": agent_id, "n_sampled": n, "n_delivered": nd,
            "completion": round(completion, 2),
            "conformance": round(conformance, 2),
            "evidence": round(evidence, 2), "latency": round(latency, 2),
            "composite": round(composite, 2),
            "judge_api_calls": judge.api_calls,
            "judge_run_cost_usd": round(judge.run_cost, 3),
            "rpc_calls": chain.rpc_calls}


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: python -m src.assess <agent>")
    conn = connect()
    result = run_assessment(conn, " ".join(sys.argv[1:]))
    for k, v in result.items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    main()
